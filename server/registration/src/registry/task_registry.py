from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import List
from uuid import uuid4

from src.core.models import TaskRecord, normalize_task_status
from src.registry.registry_utils import utc_now_iso

logger = logging.getLogger(__name__)

_CREATE_TASKS_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_tasks_mission_id ON tasks(mission_id)
"""


class TaskRegistry:
    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or ".data/tasks.db"

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
                conn.execute(_CREATE_TASKS_SQL)
                conn.execute(_CREATE_INDEX_SQL)
                conn.commit()
            logger.info(f"TaskRegistry DB 초기화: {self._db_path}")
        except Exception as e:
            logger.error(f"TaskRegistry DB 초기화 실패: {e}")

    def _row_to_task(self, row: sqlite3.Row) -> TaskRecord:
        data = json.loads(row["data"])
        data.setdefault("task_id", row["task_id"])
        data.setdefault("mission_id", row["mission_id"])
        data.setdefault("created_at", row["created_at"])
        data.setdefault("updated_at", row["updated_at"])
        return TaskRecord(**data)

    def _persist_task(self, task: TaskRecord) -> None:
        data = task.to_dict()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO tasks (task_id, mission_id, data, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (task.task_id, task.mission_id, json.dumps(data), task.created_at, task.updated_at),
            )
            conn.commit()

    def create_task(
        self,
        mission_id: str,
        title: str,
        type: str,
        required_action: str,
        status: str = "PENDING",
        sequence: int = 0,
        **kwargs
    ) -> TaskRecord:
        """새 Task 생성"""
        task = TaskRecord(
            task_id=str(uuid4()),
            mission_id=mission_id,
            title=title,
            type=type,
            required_action=required_action,
            status=normalize_task_status(status),
            sequence=sequence,
            source_proposal_task_id=kwargs.get("source_proposal_task_id"),
            assigned_device_id=kwargs.get("assigned_device_id"),
            assigned_agent_id=kwargs.get("assigned_agent_id"),
            target_area=kwargs.get("target_area"),
            target_position=kwargs.get("target_position"),
            parameters=kwargs.get("parameters", {}),
            result={},
            status_updated_at=utc_now_iso(),
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        )
        self._persist_task(task)
        return task

    def get_task(self, task_id: str) -> TaskRecord:
        """Task 조회"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT task_id, mission_id, data, created_at, updated_at FROM tasks WHERE task_id = ?",
                (task_id,)
            ).fetchone()
            if not row:
                raise KeyError(f"Task not found: {task_id}")
            return self._row_to_task(row)

    def list_tasks_by_mission(self, mission_id: str) -> List[TaskRecord]:
        """Mission별 Task 목록 조회"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT task_id, mission_id, data, created_at, updated_at FROM tasks WHERE mission_id = ? ORDER BY data->'$.sequence'",
                (mission_id,)
            ).fetchall()
            return [self._row_to_task(row) for row in rows]

    def list_tasks_by_status(self, status: str) -> List[TaskRecord]:
        """상태별 Task 목록 조회"""
        tasks = []
        normalized_status = normalize_task_status(status)
        with self._connect() as conn:
            rows = conn.execute("SELECT task_id, mission_id, data, created_at, updated_at FROM tasks").fetchall()
            for row in rows:
                task = self._row_to_task(row)
                if task.status == normalized_status:
                    tasks.append(task)
        return tasks

    def update_task_status(self, task_id: str, status: str, reason: str | None = None) -> TaskRecord:
        """Task 상태 업데이트"""
        task = self.get_task(task_id)
        task.touch(status, reason)
        self._persist_task(task)
        return task

    def update_task(self, task_id: str, **kwargs) -> TaskRecord:
        """Task 정보 업데이트"""
        task = self.get_task(task_id)
        for key, value in kwargs.items():
            if hasattr(task, key):
                setattr(task, key, value)
        task.updated_at = utc_now_iso()
        self._persist_task(task)
        return task

    def reset(self) -> None:
        """모든 Task 삭제 (테스트용)"""
        with self._connect() as conn:
            conn.execute("DELETE FROM tasks")
            conn.commit()
        logger.info("TaskRegistry 초기화 완료")
