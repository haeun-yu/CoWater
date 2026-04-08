"""Redis에서 Alert 이벤트를 구독하여 DB에 저장하고 WS로 브로드캐스트.

dedup_key가 있으면 동일 문제의 활성(status=new) 경보를 찾아 UPDATE.
없거나 찾지 못하면 INSERT.

Race Condition 방지: SELECT ... FOR UPDATE로 행 잠금 후 UPDATE/INSERT 결정.
동일 dedup_key를 가진 두 경보가 동시에 도착해도 중복 삽입되지 않는다.
"""

import json
import logging
from datetime import datetime, timezone

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
    dedup_key: str | None = data.get("dedup_key") or data.get("metadata", {}).get(
        "dedup_key"
    )
    created_at_raw = data.get("created_at")
    created_at = None
    if created_at_raw:
        created_at = datetime.fromisoformat(created_at_raw)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        else:
            created_at = created_at.astimezone(timezone.utc)

    updated_alert: AlertModel | None = None
    new_alert: AlertModel | None = None

    async with AsyncSessionLocal() as session:
        # SELECT FOR UPDATE로 트랜잭션 내 행 잠금 → 동시 요청 간 race condition 방지
        async with session.begin():
            existing: AlertModel | None = None

            if dedup_key:
                # 같은 dedup_key + 같은 에이전트의 활성 경보 조회 (잠금 획득)
                result = await session.execute(
                    select(AlertModel)
                    .where(
                        AlertModel.status == "new",
                        AlertModel.generated_by == data["generated_by"],
                        AlertModel.metadata_["dedup_key"].astext == dedup_key,
                    )
                    .order_by(AlertModel.created_at.desc())
                    .limit(1)
                    .with_for_update()
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

                if changed:
                    updated_alert = existing
                else:
                    # 변경 없으면 DB/WS 작업 스킵 (트랜잭션은 정상 커밋)
                    logger.debug("Alert dedup: no change for key=%s", dedup_key)

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
                    created_at=created_at,
                )
                session.add(alert)
                new_alert = alert
        # session.begin().__aexit__ → 자동 커밋

        # 커밋 이후 refresh 및 WS 브로드캐스트
        if updated_alert:
            await session.refresh(updated_alert)
            ws_payload = _to_ws_dict(updated_alert)
            ws_payload["type"] = "alert_updated"
            await hub.broadcast("alerts", ws_payload)
            logger.info(
                "Alert updated: id=%s key=%s", updated_alert.alert_id, dedup_key
            )
        elif new_alert:
            await session.refresh(new_alert)
            ws_payload = _to_ws_dict(new_alert)
            ws_payload["type"] = "alert_created"
            await hub.broadcast("alerts", ws_payload)
            logger.info("Alert created: id=%s key=%s", data["alert_id"], dedup_key)


def _to_ws_dict(alert: AlertModel) -> dict:
    metadata = alert.metadata_ or {}
    metadata.setdefault("source", "agent-runtime")
    metadata.setdefault(
        "produced_at",
        alert.created_at.isoformat() if alert.created_at else None,
    )
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
        "metadata": metadata,
        "schema_version": metadata.get("schema_version", 1),
        "created_at": alert.created_at.isoformat() if alert.created_at else None,
        "acknowledged_at": alert.acknowledged_at.isoformat()
        if alert.acknowledged_at
        else None,
        "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
    }
