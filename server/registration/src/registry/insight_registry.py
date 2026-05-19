from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List
from uuid import uuid4

from src.registry.registry_utils import utc_now_iso

logger = logging.getLogger(__name__)

_CREATE_INSIGHTS_SQL = """
CREATE TABLE IF NOT EXISTS insights (
    insight_id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


@dataclass
class InsightRecord:
    insight_id: str
    summary: str
    reason_summary: str
    severity: str = "INFO"
    recommended_action: str | None = None
    confidence_level: str = "medium"
    related_event_id: str | None = None
    related_alert_id: str | None = None
    related_mission_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "insight_id": self.insight_id,
            "summary": self.summary,
            "reason_summary": self.reason_summary,
            "severity": self.severity,
            "recommended_action": self.recommended_action,
            "confidence_level": self.confidence_level,
            "related_event_id": self.related_event_id,
            "related_alert_id": self.related_alert_id,
            "related_mission_id": self.related_mission_id,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class InsightRegistry:
    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or ".data/insights.db"

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
                conn.execute(_CREATE_INSIGHTS_SQL)
                conn.commit()
            logger.info(f"InsightRegistry DB 초기화: {self._db_path}")
        except Exception as e:
            logger.error(f"InsightRegistry DB 초기화 실패: {e}")

    def _row_to_insight(self, row: sqlite3.Row) -> InsightRecord:
        data = json.loads(row["data"])
        data.setdefault("insight_id", row["insight_id"])
        data.setdefault("created_at", row["created_at"])
        data.setdefault("updated_at", row["updated_at"])
        return InsightRecord(**data)

    def _persist_insight(self, insight: InsightRecord) -> None:
        data = insight.to_dict()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO insights (insight_id, data, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (insight.insight_id, json.dumps(data), insight.created_at, insight.updated_at),
            )
            conn.commit()

    def create_insight(self, payload: dict[str, Any]) -> InsightRecord:
        """Insight 생성"""
        insight_id = str(payload.get("insight_id") or f"insight-{uuid4()}")
        insight = InsightRecord(
            insight_id=insight_id,
            summary=str(payload.get("summary") or ""),
            reason_summary=str(payload.get("reason_summary") or ""),
            severity=str(payload.get("severity") or "INFO"),
            recommended_action=payload.get("recommended_action"),
            confidence_level=str(payload.get("confidence_level") or "medium"),
            related_event_id=payload.get("related_event_id"),
            related_alert_id=payload.get("related_alert_id"),
            related_mission_id=payload.get("related_mission_id"),
            metadata=payload.get("metadata") or {},
        )
        self._persist_insight(insight)
        return insight

    def get_insight(self, insight_id: str) -> InsightRecord:
        """Insight 조회"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT insight_id, data, created_at, updated_at FROM insights WHERE insight_id = ?",
                (insight_id,)
            ).fetchone()
            if not row:
                raise KeyError(f"Insight not found: {insight_id}")
            return self._row_to_insight(row)

    def list_insights(self, limit: int | None = None, offset: int = 0) -> List[InsightRecord]:
        """Insight 목록 조회"""
        query = "SELECT insight_id, data, created_at, updated_at FROM insights ORDER BY created_at, insight_id"
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
        return [self._row_to_insight(row) for row in rows]

    def reset(self) -> None:
        """모든 Insight 삭제 (테스트용)"""
        with self._connect() as conn:
            conn.execute("DELETE FROM insights")
            conn.commit()
        logger.info("InsightRegistry 초기화 완료")
