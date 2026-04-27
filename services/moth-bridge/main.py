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

from adapters import ADAPTER_REGISTRY, GeoPoint, ParsedReport, ParsedStreamMessage
from config import settings
from moth_client import ChannelConfig, MothChannelClient
from shared.events import build_event, platform_report_channel
from ws_relay import app as relay_app
from ws_relay import (
    attach_redis,
    broadcast,
    set_expected_channels,
    track_publish_result,
    track_report_activity,
)

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
                is_simulator=ch.get("is_simulator", False),
            )
        )
    return channels


async def run_moth(redis: aioredis.Redis) -> None:
    channels = load_channels(settings.channels_config)
    set_expected_channels(len(channels))
    logger.info("Loaded %d channel(s)", len(channels))

    def make_publish_callback(is_simulator: bool):
        async def publish_report(report: ParsedReport) -> None:
            # 1) Redis pub/sub — agents, core 소비용
            channel_key = platform_report_channel(report.platform_id)
            (
                raw_payload_b64,
                raw_payload_cache_key,
                raw_payload_truncated,
            ) = await _raw_payload_fields(
                redis,
                report,
            )
            payload_dict = report.to_redis_payload(
                raw_payload_b64=raw_payload_b64,
                raw_payload_cache_key=raw_payload_cache_key,
                raw_payload_truncated=raw_payload_truncated,
            )
            payload_dict["source"] = "moth-bridge"
            if is_simulator:
                payload_dict["is_simulator"] = True
            payload_dict["event"] = build_event(
                "platform_report",
                "moth-bridge",
                channel=channel_key,
                produced_at=report.timestamp.isoformat(),
            )
            payload = json.dumps(payload_dict)
            track_report_activity(report)
            try:
                await _redis_write_with_retry(
                    lambda: redis.publish(channel_key, payload),
                    label=f"publish:{report.platform_id}",
                )
                track_publish_result(True)
            except Exception:
                track_publish_result(False)
                logger.exception(
                    "Failed to publish report to Redis: %s", report.platform_id
                )
            else:
                # 최신 상태 캐시 (TTL 60s)
                cache_key = f"platform:state:{report.platform_id}"
                await _redis_write_with_retry(
                    lambda: redis.set(cache_key, payload, ex=60),
                    label=f"platform-state:{report.platform_id}",
                )

            # 2) WebSocket relay — 프론트엔드 직접 전송 (지연 최소화)
            await broadcast(report)

            logger.debug(
                "Published: platform=%s lat=%.4f lon=%.4f sog=%s is_simulator=%s",
                report.platform_id,
                report.position.lat,
                report.position.lon,
                report.sog,
                is_simulator,
            )
        return publish_report

    def make_stream_callback(is_simulator: bool, publish_report):
        async def publish_stream(message: ParsedStreamMessage) -> None:
            subject = f"{message.stream.strip('.')}.{message.device_id}"
            payload_dict = message.to_redis_payload()
            if is_simulator:
                payload_dict["is_simulator"] = True
            payload = json.dumps(payload_dict)

            try:
                await _redis_write_with_retry(
                    lambda: redis.publish(subject, payload),
                    label=f"publish-stream:{subject}",
                )
            except Exception:
                logger.exception("Failed to publish stream to Redis: %s", subject)
                return

            if (
                settings.project_position_streams_to_platform_reports
                and message.stream == "telemetry.position"
            ):
                report = _position_stream_to_report(message)
                if report is not None:
                    await publish_report(report)

            logger.debug(
                "Published stream: stream=%s device=%s qos=%s",
                message.stream,
                message.device_id,
                message.qos,
            )

        return publish_stream

    tasks = []
    for ch in channels:
        publish_report = make_publish_callback(ch.is_simulator)
        publish_stream = make_stream_callback(ch.is_simulator, publish_report)
        tasks.append(
            asyncio.create_task(
                MothChannelClient(ch, publish_report, publish_stream).run(),
                name=f"moth-{ch.name}",
            )
        )
    logger.info("Moth Bridge started — subscribing to %d channel(s)", len(tasks))
    await asyncio.gather(*tasks)


def _position_stream_to_report(message: ParsedStreamMessage) -> ParsedReport | None:
    payload = message.payload
    lat = payload.get("lat")
    lon = payload.get("lon")
    if lat is None or lon is None:
        logger.warning("telemetry.position missing lat/lon for %s", message.device_id)
        return None

    return ParsedReport(
        platform_id=message.device_id,
        timestamp=message.timestamp,
        position=GeoPoint(lat=float(lat), lon=float(lon)),
        depth_m=payload.get("depth_m"),
        altitude_m=payload.get("altitude_m"),
        sog=payload.get("sog"),
        cog=payload.get("cog"),
        heading=payload.get("heading"),
        rot=payload.get("rot"),
        nav_status=payload.get("nav_status"),
        platform_type=message.device_type,
        name=payload.get("name") or message.device_id,
        source_protocol=payload.get("source_protocol", "custom"),
    )


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
    attach_redis(redis)
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
