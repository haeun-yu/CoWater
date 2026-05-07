from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

from src.core.models import (
    AlertIngestRequest,
    AlertRecord,
)

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
        self._alerts: Dict[str, AlertRecord] = {}
        self._db_path = db_path or ".data/alerts.db"

        if self._db_path != ":memory:":
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

        self._init_db()
        self._load_from_db()

    def ingest_alert(self, request: AlertIngestRequest) -> AlertRecord:
        metadata = dict(request.metadata)
        fingerprint = str(
            metadata.get("fingerprint")
            or f"{request.event_id}:{request.alert_type}:{metadata.get('cause') or metadata.get('location') or request.message}"
        )
        for existing_alert in self._alerts.values():
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
        existing = self._alerts.get(alert_id)
        if existing is None:
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
            self._alerts[alert.alert_id] = alert
            self._persist_alert(alert)
            return alert
        existing.source_system = request.source_system
        existing.event_id = request.event_id
        existing.source_agent_id = request.source_agent_id
        existing.source_role = request.source_role
        existing.alert_type = request.alert_type
        existing.severity = request.severity
        existing.message = request.message
        existing.status = request.status
        existing.recommended_action = request.recommended_action
        existing.target_agent_id = request.target_agent_id
        existing.requires_user_approval = request.requires_user_approval
        existing.auto_remediated = request.auto_remediated
        existing.route_mode = request.route_mode
        existing.metadata = {**metadata, "fingerprint": fingerprint}
        existing.touch()
        self._persist_alert(existing)
        return existing

    def list_alerts(self) -> List[AlertRecord]:
        return [self._alerts[alert_id] for alert_id in sorted(self._alerts)]

    def get_alert(self, alert_id: str) -> AlertRecord:
        alert = self._alerts.get(alert_id)
        if alert is None:
            raise KeyError(alert_id)
        return alert

    def acknowledge_alert(self, alert_id: str, approved: bool = True, notes: Optional[str] = None) -> AlertRecord:
        alert = self.get_alert(alert_id)
        alert.touch("processing" if approved else "failed")
        if notes:
            alert.metadata["notes"] = notes
        self._persist_alert(alert)
        return alert

    def reset(self) -> None:
        """모든 alert 초기화"""
        self._alerts.clear()
        if self._db_path != ":memory:":
            try:
                with self._connect() as conn:
                    conn.execute("DELETE FROM alerts")
                    conn.commit()
            except Exception as e:
                logger.error(f"Alert reset DB 실패: {e}")

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
                conn.execute(_CREATE_ALERTS_SQL)
                conn.commit()
            logger.info(f"AlertRegistry DB 초기화: {self._db_path}")
        except Exception as e:
            logger.error(f"AlertRegistry DB 초기화 실패: {e}")

    def _load_from_db(self) -> None:
        """시작 시 SQLite에서 alerts 복원"""
        try:
            with self._connect() as conn:
                rows = conn.execute("SELECT alert_id, data FROM alerts").fetchall()
            for row in rows:
                try:
                    data = json.loads(row["data"])
                    alert = AlertRecord(**data)
                    self._alerts[alert.alert_id] = alert
                except Exception as e:
                    logger.warning(f"Alert {row['alert_id']} 복원 실패: {e}")
            logger.info(f"AlertRegistry: {len(self._alerts)}개 alert 복원")
        except Exception as e:
            logger.warning(f"AlertRegistry DB 로드 실패 (계속 진행): {e}")

    def _persist_alert(self, alert: AlertRecord) -> None:
        """Alert를 SQLite에 저장 (INSERT OR REPLACE)"""
        # Skip persistence for in-memory mode
        if self._db_path != ":memory:":
            try:
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
            except Exception as e:
                logger.error(f"Alert {alert.alert_id} 저장 실패: {e}")
