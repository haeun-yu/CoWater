from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import List
from uuid import uuid4

from src.core.models import EventIngestRequest, EventRecord

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
            "event_type": event.event_type,
            "severity": event.severity,
            "message": event.message,
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

    def ingest_event(self, request: EventIngestRequest) -> EventRecord:
        event_id = request.event_id or f"event-{uuid4()}"
        existing_row = self._get_row(event_id)
        if existing_row is None:
            event = EventRecord(
                event_id=event_id,
                source_system=request.source_system,
                source_agent_id=request.source_agent_id,
                source_role=request.source_role,
                event_type=request.event_type,
                severity=request.severity,
                message=request.message,
                metadata=dict(request.metadata),
            )
            self._persist_event(event)
            return event

        event = self._row_to_event(existing_row)
        event.source_system = request.source_system
        event.source_agent_id = request.source_agent_id
        event.source_role = request.source_role
        event.event_type = request.event_type
        event.severity = request.severity
        event.message = request.message
        event.metadata = dict(request.metadata)
        event.touch()
        self._persist_event(event)
        return event

    def list_events(self) -> List[EventRecord]:
        with self._connect() as conn:
            rows = conn.execute("SELECT event_id, data, created_at, updated_at FROM events ORDER BY created_at, event_id").fetchall()
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
