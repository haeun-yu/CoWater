from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from models import AlertModel
from ws_hub import hub

router = APIRouter(prefix="/alerts", tags=["alerts"])


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
            metadata=m.metadata_,
            created_at=m.created_at,
            acknowledged_at=m.acknowledged_at,
            resolved_at=m.resolved_at,
        )


@router.get("", response_model=list[AlertResponse])
async def list_alerts(
    status: Annotated[str | None, Query()] = None,
    severity: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AlertModel).order_by(AlertModel.created_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(AlertModel.status == status)
    if severity:
        stmt = stmt.where(AlertModel.severity == severity)
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
    payload = AlertResponse.from_model(row).model_dump(mode="json")
    await hub.broadcast("alerts", {"type": "alert_updated", **payload})
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
    payload = AlertResponse.from_model(row).model_dump(mode="json")
    await hub.broadcast("alerts", {"type": "alert_updated", **payload})
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
    - notify_guard
    - request_course_change
    - request_speed_reduction
    - request_zone_exit
    """
    allowed = {
        "acknowledge",
        "resolve",
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
    actions = list(meta.get("actions", []))
    actions.append(
        {
            "action": body.action,
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "executor": "operator-ui",
        }
    )
    meta["actions"] = actions
    row.metadata_ = meta

    if body.action == "acknowledge" and row.status == "new":
        row.status = "acknowledged"
        row.acknowledged_at = datetime.now(timezone.utc)
    elif body.action == "resolve":
        row.status = "resolved"
        row.resolved_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(row)
    payload = AlertResponse.from_model(row).model_dump(mode="json")
    await hub.broadcast("alerts", {"type": "alert_updated", **payload})
    return AlertResponse.from_model(row)
