"""Redis에서 Alert 이벤트를 구독하여 DB에 저장하고 WS로 브로드캐스트.

dedup_key가 있으면 동일 문제의 활성(status=new) 경보를 찾아 UPDATE.
없거나 찾지 못하면 INSERT.
"""

import json
import logging

import redis.asyncio as aioredis
from sqlalchemy import select

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
    dedup_key: str | None = data.get("dedup_key") or data.get("metadata", {}).get("dedup_key")

    async with AsyncSessionLocal() as session:
        existing: AlertModel | None = None

        if dedup_key:
            # 같은 dedup_key + 같은 에이전트의 활성 경보 조회
            result = await session.execute(
                select(AlertModel).where(
                    AlertModel.status == "new",
                    AlertModel.generated_by == data["generated_by"],
                    AlertModel.metadata_["dedup_key"].astext == dedup_key,
                ).order_by(AlertModel.created_at.desc()).limit(1)
            )
            existing = result.scalar_one_or_none()

        if existing:
            # 내용 업데이트 (같은 문제, 정보 변경)
            changed = False
            if existing.message != data["message"]:
                existing.message = data["message"]
                changed = True
            if existing.severity != data["severity"]:
                existing.severity = data["severity"]
                changed = True
            if existing.recommendation != data.get("recommendation"):
                existing.recommendation = data.get("recommendation")
                changed = True
            new_meta = data.get("metadata", {})
            if existing.metadata_ != new_meta:
                existing.metadata_ = new_meta
                changed = True

            if not changed:
                # 변경 없으면 DB/WS 작업 스킵
                logger.debug("Alert dedup: no change for key=%s", dedup_key)
                return

            await session.commit()
            await session.refresh(existing)

            # WS: 업데이트 이벤트 (기존 alert_id 유지)
            ws_payload = _to_ws_dict(existing)
            ws_payload["type"] = "alert_updated"
            await hub.broadcast("alerts", ws_payload)
            logger.info("Alert updated: id=%s key=%s", existing.alert_id, dedup_key)

        else:
            # 신규 삽입
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
            session.add(alert)
            await session.commit()

            ws_payload = {**data, "type": "alert_created"}
            await hub.broadcast("alerts", ws_payload)
            logger.info("Alert created: id=%s key=%s", data["alert_id"], dedup_key)


def _to_ws_dict(alert: AlertModel) -> dict:
    return {
        "alert_id": alert.alert_id,
        "alert_type": alert.alert_type,
        "severity": alert.severity,
        "status": alert.status,
        "platform_ids": alert.platform_ids or [],
        "zone_id": alert.zone_id,
        "generated_by": alert.generated_by,
        "message": alert.message,
        "recommendation": alert.recommendation,
        "metadata": alert.metadata_ or {},
        "created_at": alert.created_at.isoformat() if alert.created_at else None,
        "acknowledged_at": alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
        "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
    }
