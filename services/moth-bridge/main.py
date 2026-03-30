"""Moth Bridge 진입점 — config.yaml에서 채널 목록을 로드하고 병렬 구독 실행."""

import asyncio
import json
import logging

import redis.asyncio as aioredis
import yaml

from adapters import ADAPTER_REGISTRY, ParsedReport
from config import settings
from moth_client import ChannelConfig, MothChannelClient

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


def load_channels(path: str) -> list[ChannelConfig]:
    with open(path) as f:
        cfg = yaml.safe_load(f)

    channels = []
    for ch in cfg.get("channels", []):
        adapter_cls = ADAPTER_REGISTRY.get(ch["adapter"])
        if adapter_cls is None:
            raise ValueError(f"Unknown adapter: {ch['adapter']}")
        channels.append(ChannelConfig(
            name=ch["name"],
            moth_channel_type=ch["moth_channel_type"],
            moth_channel_name=ch["moth_channel_name"],
            moth_track=ch["moth_track"],
            moth_source=ch.get("moth_source", "base"),
            adapter=adapter_cls(),
            platform_type=ch.get("platform_type", "vessel"),
        ))
    return channels


async def main() -> None:
    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    channels = load_channels(settings.channels_config)
    logger.info("Loaded %d channel(s)", len(channels))

    async def publish_report(report: ParsedReport) -> None:
        channel_key = f"platform.report.{report.platform_id}"
        payload = json.dumps(report.to_redis_payload())
        await redis.publish(channel_key, payload)

        # 최신 상태 캐시 (TTL 60s)
        cache_key = f"platform:state:{report.platform_id}"
        await redis.set(cache_key, payload, ex=60)

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

    try:
        await asyncio.gather(*tasks)
    finally:
        await redis.aclose()
        logger.info("Moth Bridge stopped")


if __name__ == "__main__":
    asyncio.run(main())
