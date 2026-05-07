from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from src.core.models import AlertIngestRequest, AlertRecord

logger = logging.getLogger(__name__)

_CREATE_ALERTS_SQL = """
CREATE TABLE IF NOT EXISTS alerts (
    alert_id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


class AlertRegistry:
    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or ".data/alerts.db"

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
                conn.execute(_CREATE_ALERTS_SQL)
                conn.commit()
            logger.info(f"AlertRegistry DB 초기화: {self._db_path}")
        except Exception as e:
            logger.error(f"AlertRegistry DB 초기화 실패: {e}")

    def _row_to_alert(self, row: sqlite3.Row) -> AlertRecord:
        data = json.loads(row["data"])
        data.setdefault("alert_id", row["alert_id"])
        data.setdefault("created_at", row["created_at"])
        data.setdefault("updated_at", row["updated_at"])
        return AlertRecord(**data)

    def _get_row(self, alert_id: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute("SELECT alert_id, data, created_at, updated_at FROM alerts WHERE alert_id = ?", (alert_id,)).fetchone()

    def _persist_alert(self, alert: AlertRecord) -> None:
        data = {
            "alert_id": alert.alert_id,
            "source_system": alert.source_system,
            "event_id": alert.event_id,
            "source_agent_id": alert.source_agent_id,
            "source_role": alert.source_role,
            "alert_type": alert.alert_type,
            "severity": alert.severity,
            "message": alert.message,
            "status": alert.status,
            "recommended_action": alert.recommended_action,
            "target_agent_id": alert.target_agent_id,
            "requires_user_approval": alert.requires_user_approval,
            "auto_remediated": alert.auto_remediated,
            "route_mode": alert.route_mode,
            "metadata": alert.metadata,
            "created_at": alert.created_at,
            "updated_at": alert.updated_at,
        }
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO alerts (alert_id, data, created_at, updated_at)
                   VALUES (?, ?, ?, ?)""",
                (alert.alert_id, json.dumps(data, ensure_ascii=False), alert.created_at, alert.updated_at),
            )
            conn.commit()

    def ingest_alert(self, request: AlertIngestRequest) -> AlertRecord:
        metadata = dict(request.metadata)
        fingerprint = str(
            metadata.get("fingerprint")
            or f"{request.event_id}:{request.alert_type}:{metadata.get('cause') or metadata.get('location') or request.message}"
        )

        for existing_alert in self.list_alerts():
            if str((existing_alert.metadata or {}).get("fingerprint") or "") == fingerprint:
                existing_alert.source_system = request.source_system
                existing_alert.event_id = request.event_id
                existing_alert.source_agent_id = request.source_agent_id
                existing_alert.source_role = request.source_role
                existing_alert.alert_type = request.alert_type
                existing_alert.severity = request.severity
                existing_alert.message = request.message
                existing_alert.recommended_action = request.recommended_action
                existing_alert.target_agent_id = request.target_agent_id
                existing_alert.requires_user_approval = request.requires_user_approval
                existing_alert.auto_remediated = request.auto_remediated
                existing_alert.route_mode = request.route_mode
                existing_alert.metadata = {**metadata, "fingerprint": fingerprint}
                existing_alert.touch()
                self._persist_alert(existing_alert)
                return existing_alert

        alert_id = request.alert_id or f"alert-{uuid4()}"
        existing_row = self._get_row(alert_id)
        if existing_row is None:
            alert = AlertRecord(
                alert_id=alert_id,
                source_system=request.source_system,
                event_id=request.event_id,
                source_agent_id=request.source_agent_id,
                source_role=request.source_role,
                alert_type=request.alert_type,
                severity=request.severity,
                message=request.message,
                status=request.status,
                recommended_action=request.recommended_action,
                target_agent_id=request.target_agent_id,
                requires_user_approval=request.requires_user_approval,
                auto_remediated=request.auto_remediated,
                route_mode=request.route_mode,
                metadata={**metadata, "fingerprint": fingerprint},
            )
            self._persist_alert(alert)
            return alert

        alert = self._row_to_alert(existing_row)
        alert.source_system = request.source_system
        alert.event_id = request.event_id
        alert.source_agent_id = request.source_agent_id
        alert.source_role = request.source_role
        alert.alert_type = request.alert_type
        alert.severity = request.severity
        alert.message = request.message
        alert.status = request.status
        alert.recommended_action = request.recommended_action
        alert.target_agent_id = request.target_agent_id
        alert.requires_user_approval = request.requires_user_approval
        alert.auto_remediated = request.auto_remediated
        alert.route_mode = request.route_mode
        alert.metadata = {**metadata, "fingerprint": fingerprint}
        alert.touch()
        self._persist_alert(alert)
        return alert

    def list_alerts(self, limit: int | None = None, offset: int = 0) -> List[AlertRecord]:
        query = "SELECT alert_id, data, created_at, updated_at FROM alerts ORDER BY created_at, alert_id"
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
        return [self._row_to_alert(row) for row in rows]

    def get_alert(self, alert_id: str) -> AlertRecord:
        row = self._get_row(alert_id)
        if row is None:
            raise KeyError(alert_id)
        return self._row_to_alert(row)

    def acknowledge_alert(self, alert_id: str, approved: bool = True, notes: Optional[str] = None) -> AlertRecord:
        alert = self.get_alert(alert_id)
        alert.touch("processing" if approved else "failed")
        if notes:
            alert.metadata["notes"] = notes
        self._persist_alert(alert)
        return alert

    def complete_alert(self, alert_id: str, notes: Optional[str] = None) -> AlertRecord:
        alert = self.get_alert(alert_id)
        alert.touch("completed")
        if notes:
            alert.metadata["notes"] = notes
        self._persist_alert(alert)
        return alert

    def reset(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM alerts")
            conn.commit()
