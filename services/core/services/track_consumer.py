"""Redis에서 PlatformReport 이벤트를 구독하여 DB에 저장하고 WS로 브로드캐스트.

플랫폼 메타데이터(type, name)는 인메모리 캐시(_platform_meta)로 관리한다.
플랫폼당 최초 1회만 DB 조회 후 캐시에 저장 → 초당 수천 건 처리 시 N+1 쿼리 방지.
플랫폼 정보가 외부에서 변경될 경우 clear_platform_cache()로 캐시를 무효화할 수 있다.
"""

import json
import logging
from base64 import b64decode
from datetime import datetime, timezone

import redis.asyncio as aioredis
from sqlalchemy.dialects.postgresql import insert as pg_insert

from db import AsyncSessionLocal
from models import PlatformModel, PlatformReportModel
from shared.events import build_event, platform_report_pattern
from ws_hub import hub

logger = logging.getLogger(__name__)

# platform_id → (platform_type, name)
# 프로세스 생존 기간 동안 유지. 플랫폼 메타가 드물게 변경되므로 TTL 불필요.
_platform_meta: dict[str, tuple[str, str]] = {}


def clear_platform_cache(platform_id: str | None = None) -> None:
    """플랫폼 메타 캐시 무효화. platform_id 생략 시 전체 삭제."""
    if platform_id is None:
        _platform_meta.clear()
    else:
        _platform_meta.pop(platform_id, None)


async def consume_platform_reports(redis: aioredis.Redis) -> None:
    """platform.report.* 채널을 구독하여 처리."""
    pubsub = redis.pubsub()
    pattern = platform_report_pattern()
    await pubsub.psubscribe(pattern)
    logger.info("Track consumer started — subscribed to %s", pattern)

    async for message in pubsub.listen():
        if message["type"] != "pmessage":
            continue
        try:
            data = json.loads(message["data"])
            await _handle_report(data)
        except Exception:
            logger.exception("Failed to process platform report: %s", message["data"])


async def _handle_report(data: dict) -> None:
    platform_id = data["platform_id"]
    platform_type = data.get("platform_type") or "vessel"
    platform_name = data.get("name") or platform_id
    source_protocol = data.get("source_protocol", "custom")
    schema_version = data.get("schema_version", 1)
    timestamp = datetime.fromisoformat(data["timestamp"])
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    else:
        timestamp = timestamp.astimezone(timezone.utc)

    raw_payload_b64 = data.get("raw_payload_b64")
    raw_payload = b64decode(raw_payload_b64) if raw_payload_b64 else None

    async with AsyncSessionLocal() as session:
        # 신규 플랫폼은 INSERT, 기존 플랫폼은 name/platform_type을 최신 보고 기준으로 갱신
        insert_stmt = pg_insert(PlatformModel).values(
            platform_id=platform_id,
            platform_type=platform_type,
            name=platform_name,
            source_protocol=source_protocol,
            capabilities=[],
            metadata_={},
        )
        await session.execute(
            insert_stmt.on_conflict_do_update(
                index_elements=["platform_id"],
                set_={
                    "platform_type": insert_stmt.excluded.platform_type,
                    "name": insert_stmt.excluded.name,
                },
            )
        )

        report = PlatformReportModel(
            time=timestamp,
            platform_id=platform_id,
            lat=data["lat"],
            lon=data["lon"],
            depth_m=data.get("depth_m"),
            altitude_m=data.get("altitude_m"),
            sog=data.get("sog"),
            cog=data.get("cog"),
            heading=data.get("heading"),
            rot=data.get("rot"),
            nav_status=data.get("nav_status"),
            source_protocol=source_protocol,
            raw_payload=raw_payload,
        )
        session.add(report)
        await session.commit()

    # 캐시를 항상 최신 보고 기준으로 갱신
    _platform_meta[platform_id] = (platform_type, platform_name)

    # WebSocket 브로드캐스트
    await hub.broadcast(
        "platforms",
        {
            "type": "position_update",
            "event": build_event(
                "position_update",
                "core",
                produced_at=data.get("timestamp"),
            ),
            "platform_id": platform_id,
            "platform_type": platform_type,
            "name": platform_name,
            "timestamp": data["timestamp"],
            "schema_version": schema_version,
            "source": data.get("source", "moth-bridge"),
            "source_protocol": source_protocol,
            "lat": data["lat"],
            "lon": data["lon"],
            "sog": data.get("sog"),
            "cog": data.get("cog"),
            "heading": data.get("heading"),
            "nav_status": data.get("nav_status"),
        },
    )
