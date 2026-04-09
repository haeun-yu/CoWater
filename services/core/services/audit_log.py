from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from db import AsyncSessionLocal
from models import AuditLogModel


async def append_audit_log(
    *,
    event_type: str,
    actor: str | None,
    entity_type: str | None,
    entity_id: str | None,
    payload: dict,
) -> str:
    async with AsyncSessionLocal() as session:
        row = AuditLogModel(
            event_type=event_type,
            actor=actor,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row.log_id


async def append_audit_log_in_session(
    db: AsyncSession,
    *,
    event_type: str,
    actor: str | None,
    entity_type: str | None,
    entity_id: str | None,
    payload: dict,
) -> None:
    db.add(
        AuditLogModel(
            event_type=event_type,
            actor=actor,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
        )
    )
    await db.flush()
