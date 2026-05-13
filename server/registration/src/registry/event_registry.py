from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import List
from uuid import uuid4

from src.core.models import EventIngestRequest, EventRecord, normalize_event_type

logger = logging.getLogger(__name__)

_CREATE_EVENTS_SQL = """
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


class EventRegistry:
    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or ".data/events.db"

        if self._db_path != ":memory:":
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        try:
            with self._connect() as conn:
                conn.execute(_CREATE_EVENTS_SQL)
                conn.commit()
            logger.info(f"EventRegistry DB 초기화: {self._db_path}")
        except Exception as e:
            logger.error(f"EventRegistry DB 초기화 실패: {e}")

    def _row_to_event(self, row: sqlite3.Row) -> EventRecord:
        data = json.loads(row["data"])
        data.setdefault("event_id", row["event_id"])
        data.setdefault("created_at", row["created_at"])
        data.setdefault("updated_at", row["updated_at"])
        return EventRecord(**data)

    def _get_row(self, event_id: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute("SELECT event_id, data, created_at, updated_at FROM events WHERE event_id = ?", (event_id,)).fetchone()

    def _persist_event(self, event: EventRecord) -> None:
        data = {
            "event_id": event.event_id,
            "source_system": event.source_system,
            "source_agent_id": event.source_agent_id,
            "source_role": event.source_role,
            "actor_type": getattr(event, "actor_type", None),
            "actor_id": getattr(event, "actor_id", None),
            "event_type": event.event_type,
            "severity": event.severity,
            "status": getattr(event, "status", "OPEN"),
            "message": event.message,
            "title": event.title,
            "description": event.description,
            "target_type": event.target_type,
            "target_id": event.target_id,
            "data": event.data,
            "target_agents": event.target_agents,
            "status_reason": getattr(event, "status_reason", None),
            "status_updated_at": getattr(event, "status_updated_at", None),
            "metadata": event.metadata,
            "created_at": event.created_at,
            "updated_at": event.updated_at,
        }
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO events (event_id, data, created_at, updated_at)
                   VALUES (?, ?, ?, ?)""",
                (event.event_id, json.dumps(data, ensure_ascii=False), event.created_at, event.updated_at),
            )
            conn.commit()

    def _normalized_event_payload(self, request: EventIngestRequest) -> tuple[str, dict[str, object]]:
        normalized_type = normalize_event_type(request.event_type)
        payload = dict(request.data)
        original_type = str(request.event_type or "").strip()
        if original_type and original_type != normalized_type:
            payload.setdefault("original_event_type", original_type)

        legacy_type = original_type.upper()
        if normalized_type == "SYS_TASK_RESULT":
            if legacy_type.endswith("COMPLETED"):
                payload.setdefault("status", "COMPLETED")
            elif legacy_type.endswith("FAILED"):
                payload.setdefault("status", "FAILED")
            elif legacy_type.endswith("ABORTED") or legacy_type.endswith("REJECTED"):
                payload.setdefault("status", "ABORTED")
        elif normalized_type == "SYS_MISSION_UPDATED":
            if legacy_type.startswith("MISSION_"):
                payload.setdefault("status", legacy_type.removeprefix("MISSION_"))
            elif legacy_type.startswith("PROPOSAL_"):
                payload.setdefault("proposal_status", legacy_type.removeprefix("PROPOSAL_"))
            elif legacy_type.startswith("USER_"):
                payload.setdefault("request_status", legacy_type.removeprefix("USER_"))
        elif normalized_type == "SYS_ANOMALY_DETECTED" and legacy_type:
            payload.setdefault("anomaly_type", legacy_type)

        return normalized_type, payload

    def ingest_event(self, request: EventIngestRequest) -> EventRecord:
        event_id = request.event_id or f"event-{uuid4()}"
        existing_row = self._get_row(event_id)
        normalized_event_type, normalized_data = self._normalized_event_payload(request)
        if existing_row is None:
            message = request.message or request.title or request.description or request.event_type
            event = EventRecord(
                event_id=event_id,
                source_system=request.source_system,
                source_agent_id=request.source_agent_id,
                source_role=request.source_role,
                actor_type=request.actor_type,
                actor_id=request.actor_id,
                event_type=normalized_event_type,
                severity=request.severity,
                status=request.status,
                message=message,
                title=request.title,
                description=request.description,
                target_type=request.target_type,
                target_id=request.target_id,
                data=normalized_data,
                target_agents=list(request.target_agents),
                status_reason=request.status_reason,
                metadata=dict(request.metadata),
            )
            event.touch(event.status, event.status_reason)
            self._persist_event(event)
            return event

        event = self._row_to_event(existing_row)
        event.source_system = request.source_system
        event.source_agent_id = request.source_agent_id
        event.source_role = request.source_role
        event.actor_type = request.actor_type
        event.actor_id = request.actor_id
        event.event_type = normalized_event_type
        event.severity = request.severity
        event.status = request.status
        event.message = request.message or request.title or request.description or request.event_type
        event.title = request.title
        event.description = request.description
        event.target_type = request.target_type
        event.target_id = request.target_id
        event.data = normalized_data
        event.target_agents = list(request.target_agents)
        event.status_reason = request.status_reason
        if request.status_updated_at is not None:
            event.status_updated_at = request.status_updated_at
        event.metadata = dict(request.metadata)
        event.touch(event.status, event.status_reason)
        self._persist_event(event)
        return event

    def list_events(self, limit: int | None = None, offset: int = 0) -> List[EventRecord]:
        query = "SELECT event_id, data, created_at, updated_at FROM events ORDER BY created_at, event_id"
        params: list[int] = []
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
            if offset:
                query += " OFFSET ?"
                params.append(offset)
        elif offset:
            query += " LIMIT -1 OFFSET ?"
            params.append(offset)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_event(row) for row in rows]

    def get_event(self, event_id: str) -> EventRecord:
        row = self._get_row(event_id)
        if row is None:
            raise KeyError(event_id)
        return self._row_to_event(row)

    def reset(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM events")
            conn.commit()
