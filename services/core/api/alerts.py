import json
import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from models import AlertModel
from redis_client import get_redis
from shared.events import alert_updated_channel, build_event
from ws_hub import hub

router = APIRouter(prefix="/alerts", tags=["alerts"])
logger = logging.getLogger(__name__)


class AlertResponse(BaseModel):
    alert_id: str
    alert_type: str
    severity: str
    status: str
    platform_ids: list[str]
    zone_id: str | None
    generated_by: str
    message: str
    recommendation: str | None
    metadata: dict
    created_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, m: AlertModel) -> "AlertResponse":
        metadata = dict(m.metadata_ or {})
        metadata.setdefault("source", "agent-runtime")
        metadata.setdefault(
            "produced_at",
            m.created_at.isoformat() if m.created_at else None,
        )
        return cls(
            alert_id=m.alert_id,
            alert_type=m.alert_type,
            severity=m.severity,
            status=m.status,
            platform_ids=m.platform_ids,
            zone_id=m.zone_id,
            generated_by=m.generated_by,
            message=m.message,
            recommendation=m.recommendation,
            metadata=metadata,
            created_at=m.created_at,
            acknowledged_at=m.acknowledged_at,
            resolved_at=m.resolved_at,
        )


@router.get("", response_model=list[AlertResponse])
async def list_alerts(
    status: Annotated[str | None, Query()] = None,
    severity: Annotated[str | None, Query()] = None,
    generated_by: Annotated[str | None, Query()] = None,
    workflow_state: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AlertModel).order_by(AlertModel.created_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(AlertModel.status == status)
    if severity:
        stmt = stmt.where(AlertModel.severity == severity)
    if generated_by:
        stmt = stmt.where(AlertModel.generated_by == generated_by)
    if workflow_state:
        stmt = stmt.where(
            AlertModel.metadata_["workflow_state"].astext == workflow_state
        )
    result = await db.execute(stmt)
    return [AlertResponse.from_model(r) for r in result.scalars().all()]


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(alert_id: str, db: Annotated[AsyncSession, Depends(get_db)]):
    row = await db.get(AlertModel, alert_id)
    if row is None:
        raise HTTPException(404, f"Alert '{alert_id}' not found")
    return AlertResponse.from_model(row)


@router.patch("/{alert_id}/acknowledge", response_model=AlertResponse)
async def acknowledge_alert(
    alert_id: str, db: Annotated[AsyncSession, Depends(get_db)]
):
    row = await db.get(AlertModel, alert_id)
    if row is None:
        raise HTTPException(404)
    if row.status != "new":
        raise HTTPException(400, "Alert is not in 'new' state")
    row.status = "acknowledged"
    row.acknowledged_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    await _broadcast_and_publish_alert_update(row)
    return AlertResponse.from_model(row)


@router.patch("/{alert_id}/resolve", response_model=AlertResponse)
async def resolve_alert(alert_id: str, db: Annotated[AsyncSession, Depends(get_db)]):
    row = await db.get(AlertModel, alert_id)
    if row is None:
        raise HTTPException(404)
    row.status = "resolved"
    row.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    await _broadcast_and_publish_alert_update(row)
    return AlertResponse.from_model(row)


class DeleteAlertsBody(BaseModel):
    alert_ids: list[str]

    @field_validator("alert_ids")
    @classmethod
    def validate_count(cls, v: list[str]) -> list[str]:
        if len(v) > 500:
            raise ValueError("한 번에 최대 500개의 alert_id만 삭제할 수 있습니다")
        return v


@router.delete("", status_code=200)
async def delete_alerts(
    body: DeleteAlertsBody, db: Annotated[AsyncSession, Depends(get_db)]
):
    """지정한 alert_ids를 DB에서 삭제한다. 빈 리스트이면 아무것도 하지 않는다."""
    if not body.alert_ids:
        return {"deleted": 0}
    result = await db.execute(
        delete(AlertModel).where(AlertModel.alert_id.in_(body.alert_ids))
    )
    await db.commit()
    return {"deleted": result.rowcount}


class AlertActionBody(BaseModel):
    action: str


def _current_workflow_state(row: AlertModel, metadata: dict) -> str:
    workflow_state = metadata.get("workflow_state")
    if isinstance(workflow_state, str):
        return workflow_state
    if row.status == "resolved":
        return "resolved"
    if row.status == "acknowledged":
        return "acknowledged"
    return "new"


def _validate_action_transition(row: AlertModel, metadata: dict, action: str) -> None:
    workflow_state = _current_workflow_state(row, metadata)

    if action == "acknowledge" and row.status != "new":
        raise HTTPException(400, "Alert is not in 'new' state")

    if action == "resolve" and row.status == "resolved":
        raise HTTPException(400, "Alert is already resolved")

    if action == "start_investigation" and workflow_state in {"resolved", "escalated"}:
        raise HTTPException(400, f"Cannot start investigation from '{workflow_state}'")

    if action == "escalate" and workflow_state == "resolved":
        raise HTTPException(400, "Cannot escalate a resolved alert")


@router.post("/{alert_id}/action", response_model=AlertResponse)
async def run_alert_action(
    alert_id: str,
    body: AlertActionBody,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """경보 권고에 대한 자동 처리 액션 실행.

    지원 액션:
    - acknowledge
    - resolve
    - start_investigation
    - escalate
    - notify_guard
    - request_course_change
    - request_speed_reduction
    - request_zone_exit
    """
    allowed = {
        "acknowledge",
        "resolve",
        "start_investigation",
        "escalate",
        "notify_guard",
        "request_course_change",
        "request_speed_reduction",
        "request_zone_exit",
    }
    if body.action not in allowed:
        raise HTTPException(400, f"Unsupported action: {body.action}")

    row = await db.get(AlertModel, alert_id)
    if row is None:
        raise HTTPException(404, f"Alert '{alert_id}' not found")

    meta = dict(row.metadata_ or {})
    _validate_action_transition(row, meta, body.action)
    actions = list(meta.get("actions", []))
    actions.append(
        {
            "action": body.action,
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "executor": "operator-ui",
        }
    )
    meta["actions"] = actions

    if body.action == "start_investigation":
        meta["workflow_state"] = "investigating"
        meta["workflow_updated_at"] = datetime.now(timezone.utc).isoformat()
    elif body.action == "escalate":
        meta["workflow_state"] = "escalated"
        meta["workflow_updated_at"] = datetime.now(timezone.utc).isoformat()
    elif body.action == "resolve":
        meta["workflow_state"] = "resolved"
        meta["workflow_updated_at"] = datetime.now(timezone.utc).isoformat()

    row.metadata_ = meta

    if body.action == "acknowledge" and row.status == "new":
        row.status = "acknowledged"
        row.acknowledged_at = datetime.now(timezone.utc)
    elif body.action == "resolve":
        row.status = "resolved"
        row.resolved_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(row)
    await _broadcast_and_publish_alert_update(row)
    return AlertResponse.from_model(row)


async def _broadcast_and_publish_alert_update(row: AlertModel) -> None:
    payload = AlertResponse.from_model(row).model_dump(mode="json")
    channel = alert_updated_channel(row.alert_id)
    payload["type"] = "alert_updated"
    payload["event"] = build_event(
        "alert_updated",
        "core",
        channel=channel,
        produced_at=payload.get("created_at"),
    )
    await hub.broadcast("alerts", payload)

    try:
        redis = await get_redis()
        await redis.publish(channel, json.dumps(payload))
    except Exception:
        logger.exception("Failed to publish alert update event: %s", row.alert_id)
