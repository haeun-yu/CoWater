"""Moth Bridge 진입점 — config.yaml에서 채널 목록을 로드하고 병렬 구독 실행.

추가: FastAPI WebSocket relay 서버를 함께 실행하여
프론트엔드가 Redis/Core를 거치지 않고 위치 데이터를 직접 수신할 수 있도록 한다.
"""

import asyncio
import json
import logging

import redis.asyncio as aioredis
import uvicorn
import yaml

from adapters import ADAPTER_REGISTRY, ParsedReport
from config import settings
from moth_client import ChannelConfig, MothChannelClient
from ws_relay import app as relay_app
from ws_relay import broadcast

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


async def _redis_write_with_retry(operation, *, label: str) -> None:
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            await operation()
            return
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Redis write failed: %s attempt=%s", label, attempt, exc_info=exc
            )
            if attempt < 3:
                await asyncio.sleep(0.2 * attempt)

    assert last_error is not None
    raise last_error


def _raw_payload_protocols() -> set[str]:
    return {
        protocol.strip().lower()
        for protocol in settings.raw_payload_protocols.split(",")
        if protocol.strip()
    }


def _raw_payload_enabled(report: ParsedReport) -> bool:
    if settings.raw_payload_mode == "off" or report.raw_payload is None:
        return False
    protocols = _raw_payload_protocols()
    return not protocols or report.source_protocol.lower() in protocols


async def _raw_payload_fields(
    redis: aioredis.Redis,
    report: ParsedReport,
) -> tuple[str | None, str | None, bool]:
    if not _raw_payload_enabled(report):
        return None, None, False

    encoded, truncated = report.encode_raw_payload(settings.raw_payload_max_bytes)
    if encoded is None:
        return None, None, False

    if settings.raw_payload_mode == "db":
        return encoded, None, truncated

    cache_key = f"platform:raw:{report.platform_id}:{report.timestamp.isoformat()}"
    await _redis_write_with_retry(
        lambda: redis.set(cache_key, encoded, ex=settings.raw_payload_ttl_sec),
        label=f"raw-payload:{report.platform_id}",
    )
    return None, cache_key, truncated


def load_channels(path: str) -> list[ChannelConfig]:
    with open(path) as f:
        cfg = yaml.safe_load(f)

    channels = []
    for ch in cfg.get("channels", []):
        adapter_cls = ADAPTER_REGISTRY.get(ch["adapter"])
        if adapter_cls is None:
            raise ValueError(f"Unknown adapter: {ch['adapter']}")
        channels.append(
            ChannelConfig(
                name=ch["name"],
                moth_channel_type=ch["moth_channel_type"],
                moth_channel_name=ch["moth_channel_name"],
                moth_track=ch["moth_track"],
                moth_source=ch.get("moth_source", "base"),
                adapter=adapter_cls(),
                platform_type=ch.get("platform_type", "vessel"),
            )
        )
    return channels


async def run_moth(redis: aioredis.Redis) -> None:
    channels = load_channels(settings.channels_config)
    logger.info("Loaded %d channel(s)", len(channels))

    async def publish_report(report: ParsedReport) -> None:
        # 1) Redis pub/sub — agents, core 소비용
        channel_key = f"platform.report.{report.platform_id}"
        (
            raw_payload_b64,
            raw_payload_cache_key,
            raw_payload_truncated,
        ) = await _raw_payload_fields(
            redis,
            report,
        )
        payload = json.dumps(
            report.to_redis_payload(
                raw_payload_b64=raw_payload_b64,
                raw_payload_cache_key=raw_payload_cache_key,
                raw_payload_truncated=raw_payload_truncated,
            )
        )
        await _redis_write_with_retry(
            lambda: redis.publish(channel_key, payload),
            label=f"publish:{report.platform_id}",
        )

        # 최신 상태 캐시 (TTL 60s)
        cache_key = f"platform:state:{report.platform_id}"
        await _redis_write_with_retry(
            lambda: redis.set(cache_key, payload, ex=60),
            label=f"platform-state:{report.platform_id}",
        )

        # 2) WebSocket relay — 프론트엔드 직접 전송 (지연 최소화)
        await broadcast(report)

        logger.debug(
            "Published: platform=%s lat=%.4f lon=%.4f sog=%s",
            report.platform_id,
            report.position.lat,
            report.position.lon,
            report.sog,
        )

    tasks = [
        asyncio.create_task(
            MothChannelClient(ch, publish_report).run(),
            name=f"moth-{ch.name}",
        )
        for ch in channels
    ]
    logger.info("Moth Bridge started — subscribing to %d channel(s)", len(tasks))
    await asyncio.gather(*tasks)


async def run_relay() -> None:
    """FastAPI WebSocket relay 서버 실행 (포트 8002)."""
    config = uvicorn.Config(
        relay_app,
        host="0.0.0.0",
        port=8002,
        log_level=settings.log_level.lower(),
    )
    server = uvicorn.Server(config)
    await server.serve()


async def main() -> None:
    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        await asyncio.gather(
            run_moth(redis),
            run_relay(),
        )
    finally:
        await redis.aclose()
        logger.info("Moth Bridge stopped")


if __name__ == "__main__":
    asyncio.run(main())
