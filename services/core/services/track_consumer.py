"""Redis에서 PlatformReport 이벤트를 구독하여 DB에 저장하고 WS로 브로드캐스트."""

import json
import logging
from datetime import datetime, timezone

import redis.asyncio as aioredis
from sqlalchemy.dialects.postgresql import insert as pg_insert

from db import AsyncSessionLocal
from models import PlatformModel, PlatformReportModel
from ws_hub import hub

logger = logging.getLogger(__name__)


async def consume_platform_reports(redis: aioredis.Redis) -> None:
    """platform.report.* 채널을 구독하여 처리."""
    pubsub = redis.pubsub()
    await pubsub.psubscribe("platform.report.*")
    logger.info("Track consumer started — subscribed to platform.report.*")

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
    source_protocol = data.get("source_protocol", "custom")

    async with AsyncSessionLocal() as session:
        # platform_reports → platforms FK 보장:
        # 최초 수신 시 platforms 행을 자동 생성 (이미 있으면 무시)
        await session.execute(
            pg_insert(PlatformModel).values(
                platform_id=platform_id,
                platform_type="vessel",
                name=platform_id,
                source_protocol=source_protocol,
                capabilities=[],
                metadata_={},
            ).on_conflict_do_nothing(index_elements=["platform_id"])
        )

        report = PlatformReportModel(
            time=datetime.fromisoformat(data["timestamp"]).replace(tzinfo=timezone.utc),
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
        )
        session.add(report)
        await session.commit()

        # 플랫폼 메타 조회 (프론트엔드에 type/name 전달용)
        platform_row = await session.get(PlatformModel, platform_id)

    platform_type = platform_row.platform_type if platform_row else "vessel"
    platform_name = (platform_row.name if platform_row else None) or platform_id

    # WebSocket 브로드캐스트
    await hub.broadcast("platforms", {
        "type": "position_update",
        "platform_id": platform_id,
        "platform_type": platform_type,
        "name": platform_name,
        "timestamp": data["timestamp"],
        "lat": data["lat"],
        "lon": data["lon"],
        "sog": data.get("sog"),
        "cog": data.get("cog"),
        "heading": data.get("heading"),
        "nav_status": data.get("nav_status"),
    })
