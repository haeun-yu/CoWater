"""Redis 이벤트 구독 및 WebSocket 브로드캐스트."""

import json
import logging

import redis.asyncio as aioredis

from ws_hub import hub

logger = logging.getLogger(__name__)


async def consume_events(redis: aioredis.Redis) -> None:
    """이벤트 채널 구독 및 WebSocket 브로드캐스트.

    detect.*, analyze.*, respond.*, learn.*, system.* 패턴의 모든 이벤트를 수집하여
    프론트엔드에 실시간으로 스트림.
    """
    pubsub = redis.pubsub()

    # 모든 이벤트 채널 패턴 구독
    patterns = [
        "detect.*",
        "analyze.*",
        "respond.*",
        "learn.*",
        "system.*",
    ]

    for pattern in patterns:
        await pubsub.psubscribe(pattern)

    logger.info("Event consumer: subscribed to event channels")

    async for message in pubsub.listen():
        if message["type"] != "pmessage":
            continue

        try:
            channel = message["channel"]
            data = message["data"]

            # 문자열인 경우 JSON 파싱
            if isinstance(data, str):
                event_data = json.loads(data)
            else:
                event_data = data

            # WebSocket 브로드캐스트
            await hub.broadcast("events", {
                "type": "event",
                "channel": channel,
                "timestamp": message.get("timestamp"),
                "event": event_data,
            })

        except json.JSONDecodeError:
            logger.warning("Failed to parse event JSON from channel %s", message["channel"])
        except Exception as e:
            logger.exception("Error processing event: %s", e)
