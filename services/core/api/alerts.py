import json
import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4

from auth import require_command_role
from db import get_db
from models import AlertModel
from redis_client import get_redis
from shared.events import alert_updated_channel, build_event
from shared.command_auth import CommandActor
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


class CreateAlertBody(BaseModel):
    alert_type: str
    severity: str
    platform_ids: list[str] = []
    zone_id: str | None = None
    generated_by: str
    message: str
    recommendation: str | None = None
    metadata: dict = {}
    dedup_key: str | None = None
    resolve_dedup_key: str | None = None
    resolve_only: bool = False
    status: str = "new"


@router.post("")
async def create_alert(
    body: CreateAlertBody,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    created_row: AlertModel | None = None
    updated_row: AlertModel | None = None
    resolved_rows: list[AlertModel] = []

    async with db.begin():
        if body.dedup_key and not body.resolve_only:
            result = await db.execute(
                select(AlertModel)
                .where(
                    AlertModel.status == "new",
                    AlertModel.generated_by == body.generated_by,
                    AlertModel.dedup_key == body.dedup_key,
                )
                .order_by(AlertModel.created_at.desc())
                .limit(1)
                .with_for_update()
            )
            updated_row = result.scalar_one_or_none()

        if updated_row:
            updated_row.alert_type = body.alert_type
            updated_row.severity = body.severity
            updated_row.platform_ids = body.platform_ids
            updated_row.zone_id = body.zone_id
            updated_row.message = body.message
            updated_row.recommendation = body.recommendation
            updated_row.metadata_ = body.metadata
        elif not body.resolve_only:
            created_row = AlertModel(
                alert_id=str(uuid4()),
                alert_type=body.alert_type,
                severity=body.severity,
                status=body.status,
                platform_ids=body.platform_ids,
                zone_id=body.zone_id,
                generated_by=body.generated_by,
                message=body.message,
                recommendation=body.recommendation,
                metadata_=body.metadata,
                dedup_key=body.dedup_key,
            )
            db.add(created_row)

        if body.resolve_dedup_key:
            resolve_result = await db.execute(
                select(AlertModel)
                .where(
                    AlertModel.status.in_(["new", "acknowledged"]),
                    AlertModel.generated_by == body.generated_by,
                    AlertModel.dedup_key == body.resolve_dedup_key,
                )
                .with_for_update()
            )
            for row in resolve_result.scalars().all():
                row.status = "resolved"
                row.resolved_at = datetime.now(timezone.utc)
                resolved_rows.append(row)

    if created_row:
        await db.refresh(created_row)
        await _broadcast_alert_create(created_row)
        return {"alert_id": created_row.alert_id, "status": "created"}
    if updated_row:
        await db.refresh(updated_row)
        await _broadcast_and_publish_alert_update(updated_row)
        return {"alert_id": updated_row.alert_id, "status": "updated"}
    for row in resolved_rows:
        await db.refresh(row)
        await _broadcast_and_publish_alert_update(row)
    return {"alert_id": None, "status": "resolved", "resolved_count": len(resolved_rows)}


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
    alert_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[CommandActor, Depends(require_command_role("operator"))],
):
    row = await execute_alert_action(
        db,
        alert_id,
        "acknowledge",
        executor=actor.actor,
        source="api",
    )
    await db.commit()
    await db.refresh(row)
    await _broadcast_and_publish_alert_update(row)
    return AlertResponse.from_model(row)


@router.patch("/{alert_id}/resolve", response_model=AlertResponse)
async def resolve_alert(
    alert_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[CommandActor, Depends(require_command_role("operator"))],
):
    row = await execute_alert_action(
        db,
        alert_id,
        "resolve",
        executor=actor.actor,
        source="api",
    )
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
    body: DeleteAlertsBody,
    db: Annotated[AsyncSession, Depends(get_db)],
    actor: Annotated[CommandActor, Depends(require_command_role("admin"))],
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
    actor: Annotated[CommandActor, Depends(require_command_role("operator"))],
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
    row = await execute_alert_action(
        db,
        alert_id,
        body.action,
        executor=actor.actor,
        source="api",
    )

    await db.commit()
    await db.refresh(row)
    await _broadcast_and_publish_alert_update(row)
    return AlertResponse.from_model(row)


async def execute_alert_action(
    db: AsyncSession,
    alert_id: str,
    action: str,
    *,
    executor: str,
    source: str,
) -> AlertModel:
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
    if action not in allowed:
        raise HTTPException(400, f"Unsupported action: {action}")

    row = await db.get(AlertModel, alert_id)
    if row is None:
        raise HTTPException(404, f"Alert '{alert_id}' not found")

    meta = dict(row.metadata_ or {})
    _validate_action_transition(row, meta, action)
    actions = list(meta.get("actions", []))
    actions.append(
        {
            "action": action,
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "executor": executor,
            "source": source,
        }
    )
    meta["actions"] = actions

    if action == "start_investigation":
        meta["workflow_state"] = "investigating"
        meta["workflow_updated_at"] = datetime.now(timezone.utc).isoformat()
    elif action == "escalate":
        meta["workflow_state"] = "escalated"
        meta["workflow_updated_at"] = datetime.now(timezone.utc).isoformat()
    elif action == "resolve":
        meta["workflow_state"] = "resolved"
        meta["workflow_updated_at"] = datetime.now(timezone.utc).isoformat()
    elif action == "acknowledge":
        meta["workflow_state"] = "acknowledged"
        meta["workflow_updated_at"] = datetime.now(timezone.utc).isoformat()

    row.metadata_ = meta

    if action == "acknowledge" and row.status == "new":
        row.status = "acknowledged"
        row.acknowledged_at = datetime.now(timezone.utc)
    elif action == "resolve":
        row.status = "resolved"
        row.resolved_at = datetime.now(timezone.utc)

    return row


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


async def _broadcast_alert_create(row: AlertModel) -> None:
    payload = AlertResponse.from_model(row).model_dump(mode="json")
    payload["type"] = "alert_created"
    payload["event"] = build_event(
        "alert_created",
        "core",
        produced_at=payload.get("created_at"),
    )
    await hub.broadcast("alerts", payload)
