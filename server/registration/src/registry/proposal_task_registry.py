from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import List, Dict, Any
from uuid import uuid4

from src.core.models import ProposalTaskRecord
from src.registry.registry_utils import utc_now_iso

logger = logging.getLogger(__name__)

_CREATE_PROPOSAL_TASKS_SQL = """
CREATE TABLE IF NOT EXISTS proposal_tasks (
    task_id TEXT PRIMARY KEY,
    proposal_id TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_proposal_tasks_proposal_id ON proposal_tasks(proposal_id)
"""


class ProposalTaskRegistry:
    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or ".data/proposal_tasks.db"

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
                conn.execute(_CREATE_PROPOSAL_TASKS_SQL)
                conn.execute(_CREATE_INDEX_SQL)
                conn.commit()
            logger.info(f"ProposalTaskRegistry DB 초기화: {self._db_path}")
        except Exception as e:
            logger.error(f"ProposalTaskRegistry DB 초기화 실패: {e}")

    def _row_to_task(self, row: sqlite3.Row) -> ProposalTaskRecord:
        data = json.loads(row["data"])
        data.setdefault("task_id", row["task_id"])
        data.setdefault("proposal_id", row["proposal_id"])
        data.setdefault("created_at", row["created_at"])
        data.setdefault("updated_at", row["updated_at"])
        return ProposalTaskRecord(**data)

    def _persist_task(self, task: ProposalTaskRecord) -> None:
        data = task.to_dict()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO proposal_tasks (task_id, proposal_id, data, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (task.task_id, task.proposal_id, json.dumps(data), task.created_at, task.updated_at),
            )
            conn.commit()

    def create_task(
        self,
        proposal_id: str,
        title: str,
        type: str,
        required_action: str,
        sequence: int,
        **kwargs
    ) -> ProposalTaskRecord:
        """새 ProposalTask 생성"""
        task = ProposalTaskRecord(
            task_id=str(uuid4()),
            proposal_id=proposal_id,
            title=title,
            type=type,
            required_action=required_action,
            sequence=sequence,
            target_area=kwargs.get("target_area"),
            target_position=kwargs.get("target_position"),
            recommended_device_id=kwargs.get("recommended_device_id"),
            recommended_agent_id=kwargs.get("recommended_agent_id"),
            alternative_device_ids=kwargs.get("alternative_device_ids", []),
            recommendation_reason=kwargs.get("recommendation_reason"),
            parameters=kwargs.get("parameters", {}),
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        )
        self._persist_task(task)
        return task

    def get_task(self, task_id: str) -> ProposalTaskRecord:
        """ProposalTask 조회"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT task_id, proposal_id, data, created_at, updated_at FROM proposal_tasks WHERE task_id = ?",
                (task_id,)
            ).fetchone()
            if not row:
                raise KeyError(f"ProposalTask not found: {task_id}")
            return self._row_to_task(row)

    def list_tasks_by_proposal(self, proposal_id: str) -> List[ProposalTaskRecord]:
        """Proposal별 Task 목록 조회"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT task_id, proposal_id, data, created_at, updated_at FROM proposal_tasks WHERE proposal_id = ? ORDER BY data->'$.sequence'",
                (proposal_id,)
            ).fetchall()
            return [self._row_to_task(row) for row in rows]

    def update_task(self, task_id: str, **kwargs) -> ProposalTaskRecord:
        """ProposalTask 업데이트"""
        task = self.get_task(task_id)
        for key, value in kwargs.items():
            if hasattr(task, key):
                setattr(task, key, value)
        task.updated_at = utc_now_iso()
        self._persist_task(task)
        return task

    def delete_task(self, task_id: str) -> None:
        """ProposalTask 삭제"""
        with self._connect() as conn:
            conn.execute("DELETE FROM proposal_tasks WHERE task_id = ?", (task_id,))
            conn.commit()

    def reset(self) -> None:
        """모든 ProposalTask 삭제 (테스트용)"""
        with self._connect() as conn:
            conn.execute("DELETE FROM proposal_tasks")
            conn.commit()
        logger.info("ProposalTaskRegistry 초기화 완료")
