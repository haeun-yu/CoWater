"""Redis에서 Alert 이벤트를 구독하여 DB에 저장하고 WS로 브로드캐스트."""

import json
import logging

import redis.asyncio as aioredis

from db import AsyncSessionLocal
from models import AlertModel
from ws_hub import hub

logger = logging.getLogger(__name__)


async def consume_alerts(redis: aioredis.Redis) -> None:
    pubsub = redis.pubsub()
    await pubsub.psubscribe("alert.created.*")
    logger.info("Alert consumer started — subscribed to alert.created.*")

    async for message in pubsub.listen():
        if message["type"] != "pmessage":
            continue
        try:
            data = json.loads(message["data"])
            await _handle_alert(data)
        except Exception:
            logger.exception("Failed to process alert: %s", message["data"])


async def _handle_alert(data: dict) -> None:
    alert = AlertModel(
        alert_id=data["alert_id"],
        alert_type=data["alert_type"],
        severity=data["severity"],
        status=data.get("status", "new"),
        platform_ids=data.get("platform_ids", []),
        zone_id=data.get("zone_id"),
        generated_by=data["generated_by"],
        message=data["message"],
        recommendation=data.get("recommendation"),
        metadata_=data.get("metadata", {}),
    )

    async with AsyncSessionLocal() as session:
        session.add(alert)
        await session.commit()

    await hub.broadcast("alerts", {
        "type": "alert_created",
        **data,
    })
