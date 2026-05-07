from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Dict, List
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
        self._events: Dict[str, EventRecord] = {}
        self._db_path = db_path or ".data/events.db"

        if self._db_path != ":memory:":
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

        self._init_db()
        self._load_from_db()

    def ingest_event(self, request: EventIngestRequest) -> EventRecord:
        event_id = request.event_id or f"event-{uuid4()}"
        existing = self._events.get(event_id)
        if existing is None:
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
            self._events[event.event_id] = event
            self._persist_event(event)
            return event
        existing.source_system = request.source_system
        existing.source_agent_id = request.source_agent_id
        existing.source_role = request.source_role
        existing.event_type = request.event_type
        existing.severity = request.severity
        existing.message = request.message
        existing.metadata = dict(request.metadata)
        existing.touch()
        self._persist_event(existing)
        return existing

    def list_events(self) -> List[EventRecord]:
        return [self._events[event_id] for event_id in sorted(self._events)]

    def get_event(self, event_id: str) -> EventRecord:
        event = self._events.get(event_id)
        if event is None:
            raise KeyError(event_id)
        return event

    def reset(self) -> None:
        """모든 event 초기화"""
        self._events.clear()
        if self._db_path != ":memory:":
            try:
                with self._connect() as conn:
                    conn.execute("DELETE FROM events")
                    conn.commit()
            except Exception as e:
                logger.error(f"Event reset DB 실패: {e}")

    # ──────────────────────────────────────────────
    # SQLite 저장소 메서드
    # ──────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """SQLite DB 초기화"""
        try:
            with self._connect() as conn:
                conn.execute(_CREATE_EVENTS_SQL)
                conn.commit()
            logger.info(f"EventRegistry DB 초기화: {self._db_path}")
        except Exception as e:
            logger.error(f"EventRegistry DB 초기화 실패: {e}")

    def _load_from_db(self) -> None:
        """시작 시 SQLite에서 events 복원"""
        try:
            with self._connect() as conn:
                rows = conn.execute("SELECT event_id, data FROM events").fetchall()
            for row in rows:
                try:
                    data = json.loads(row["data"])
                    event = EventRecord(**data)
                    self._events[event.event_id] = event
                except Exception as e:
                    logger.warning(f"Event {row['event_id']} 복원 실패: {e}")
            logger.info(f"EventRegistry: {len(self._events)}개 event 복원")
        except Exception as e:
            logger.warning(f"EventRegistry DB 로드 실패 (계속 진행): {e}")

    def _persist_event(self, event: EventRecord) -> None:
        """Event를 SQLite에 저장 (INSERT OR REPLACE)"""
        # Skip persistence for in-memory mode
        if self._db_path != ":memory:":
            try:
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
            except Exception as e:
                logger.error(f"Event {event.event_id} 저장 실패: {e}")
