"""Device stream Redis consumer.

Consumes normalized device streams from moth-bridge, keeps a latest-value cache
in Redis, and broadcasts updates to Core WebSocket clients.
"""

from __future__ import annotations

import json
import logging

import redis.asyncio as aioredis

from shared.schemas.device_stream import DeviceStreamMessage
from ws_hub import hub

logger = logging.getLogger(__name__)

DEVICE_STREAM_PATTERNS = [
    "telemetry.*",
    "sensor.*",
]


def latest_stream_key(device_id: str, stream: str) -> str:
    return f"device_stream:latest:{device_id}:{stream}"


def device_streams_key(device_id: str) -> str:
    return f"device_stream:{device_id}:streams"


async def consume_device_streams(redis: aioredis.Redis) -> None:
    pubsub = redis.pubsub()
    for pattern in DEVICE_STREAM_PATTERNS:
        await pubsub.psubscribe(pattern)
    logger.info("Device stream consumer: subscribed to %s", DEVICE_STREAM_PATTERNS)

    async for message in pubsub.listen():
        if message["type"] != "pmessage":
            continue

        try:
            channel = message["channel"]
            raw = message["data"]
            data = json.loads(raw) if isinstance(raw, str) else raw
            stream_message = DeviceStreamMessage.from_dict(data)
            await _handle_stream(redis, channel, stream_message, data)
        except json.JSONDecodeError:
            logger.warning(
                "Failed to parse device stream JSON from channel %s",
                message.get("channel"),
            )
        except Exception as exc:
            logger.exception("Failed to process device stream: %s", exc)


async def _handle_stream(
    redis: aioredis.Redis,
    channel: str,
    message: DeviceStreamMessage,
    original: dict,
) -> None:
    envelope = message.envelope
    if not envelope.device_id or not envelope.stream:
        logger.warning("Device stream missing device_id or stream on %s", channel)
        return

    payload = json.dumps(original)
    await redis.set(latest_stream_key(envelope.device_id, envelope.stream), payload, ex=300)
    await redis.sadd("device_stream:devices", envelope.device_id)
    await redis.sadd(device_streams_key(envelope.device_id), envelope.stream)

    await hub.broadcast(
        "device_streams",
        {
            "type": "device_stream",
            "channel": channel,
            "envelope": envelope.to_dict(),
            "payload": message.payload,
        },
    )
