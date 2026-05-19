from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List
from uuid import uuid4

from src.registry.registry_utils import utc_now_iso
from src.core.models import normalize_approval_status

logger = logging.getLogger(__name__)

_CREATE_APPROVALS_SQL = """
CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


@dataclass
class ApprovalRecord:
    approval_id: str
    target_type: str
    target_id: str
    summary: str
    requested_action: str
    status: str = "PENDING"
    requested_by: str = "system_agent"
    decided_by: str | None = None
    decision_notes: str | None = None
    related_insight_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    status_reason: str | None = None
    status_updated_at: str = field(default_factory=utc_now_iso)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    decided_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "summary": self.summary,
            "requested_action": self.requested_action,
            "status": self.status,
            "requested_by": self.requested_by,
            "decided_by": self.decided_by,
            "decision_notes": self.decision_notes,
            "related_insight_id": self.related_insight_id,
            "metadata": self.metadata,
            "status_reason": self.status_reason,
            "status_updated_at": self.status_updated_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "decided_at": self.decided_at,
        }


class ApprovalRegistry:
    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or ".data/approvals.db"

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
                conn.execute(_CREATE_APPROVALS_SQL)
                conn.commit()
            logger.info(f"ApprovalRegistry DB 초기화: {self._db_path}")
        except Exception as e:
            logger.error(f"ApprovalRegistry DB 초기화 실패: {e}")

    def _row_to_approval(self, row: sqlite3.Row) -> ApprovalRecord:
        data = json.loads(row["data"])
        data.setdefault("approval_id", row["approval_id"])
        data.setdefault("created_at", row["created_at"])
        data.setdefault("updated_at", row["updated_at"])
        return ApprovalRecord(**data)

    def _persist_approval(self, approval: ApprovalRecord) -> None:
        data = approval.to_dict()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO approvals (approval_id, data, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (approval.approval_id, json.dumps(data), approval.created_at, approval.updated_at),
            )
            conn.commit()

    def create_approval(self, payload: dict[str, Any]) -> ApprovalRecord:
        """Approval 생성"""
        approval_id = str(payload.get("approval_id") or f"approval-{uuid4()}")
        approval = ApprovalRecord(
            approval_id=approval_id,
            target_type=str(payload.get("target_type") or "mission_proposal"),
            target_id=str(payload.get("target_id") or ""),
            summary=str(payload.get("summary") or ""),
            requested_action=str(payload.get("requested_action") or "review"),
            status=normalize_approval_status(payload.get("status") or "PENDING"),
            requested_by=str(payload.get("requested_by") or "system_agent"),
            decided_by=payload.get("decided_by"),
            decision_notes=payload.get("decision_notes"),
            related_insight_id=payload.get("related_insight_id"),
            metadata=payload.get("metadata") or {},
            decided_at=payload.get("decided_at"),
        )
        self._persist_approval(approval)
        return approval

    def get_approval(self, approval_id: str) -> ApprovalRecord:
        """Approval 조회"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT approval_id, data, created_at, updated_at FROM approvals WHERE approval_id = ?",
                (approval_id,)
            ).fetchone()
            if not row:
                raise KeyError(f"Approval not found: {approval_id}")
            return self._row_to_approval(row)

    def list_approvals(self, limit: int | None = None, offset: int = 0) -> List[ApprovalRecord]:
        """Approval 목록 조회"""
        query = "SELECT approval_id, data, created_at, updated_at FROM approvals ORDER BY created_at, approval_id"
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
        return [self._row_to_approval(row) for row in rows]

    def decide_approval(self, approval_id: str, approved: bool, *, decided_by: str, notes: str | None = None) -> ApprovalRecord:
        """Approval 결정"""
        approval = self.get_approval(approval_id)
        approval.status = normalize_approval_status("APPROVED" if approved else "REJECTED")
        approval.decided_by = decided_by
        approval.decision_notes = notes
        approval.decided_at = utc_now_iso()
        approval.updated_at = approval.decided_at
        self._persist_approval(approval)
        return approval

    def reset(self) -> None:
        """모든 Approval 삭제 (테스트용)"""
        with self._connect() as conn:
            conn.execute("DELETE FROM approvals")
            conn.commit()
        logger.info("ApprovalRegistry 초기화 완료")
