from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import List
from uuid import uuid4

from src.core.models import EventRecord
from src.registry.registry_utils import utc_now_iso

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
        data = event.to_dict()
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO events (event_id, data, created_at, updated_at)
                   VALUES (?, ?, ?, ?)""",
                (event.event_id, json.dumps(data, ensure_ascii=False), event.created_at, event.updated_at),
            )
            conn.commit()

    def create_event(
        self,
        actor_type: str,
        actor_id: str,
        type: str,
        severity: str,
        title: str,
        description: str,
        target_type: str,
        target_id: str,
        data: dict | None = None,
        status: str = "OPEN",
    ) -> EventRecord:
        """새 Event 생성"""
        event = EventRecord(
            event_id=f"event-{uuid4()}",
            actor_type=actor_type,
            actor_id=actor_id,
            type=type,
            severity=severity,
            status=status,
            title=title,
            description=description,
            target_type=target_type,
            target_id=target_id,
            data=data or {},
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        )
        self._persist_event(event)
        return event

    def update_event_status(self, event_id: str, status: str) -> EventRecord:
        """Event 상태 업데이트"""
        event = self.get_event(event_id)
        event.status = status
        event.updated_at = utc_now_iso()
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
