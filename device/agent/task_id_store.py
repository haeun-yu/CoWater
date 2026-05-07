"""
TaskIdStore: SQLite 기반 처리된 task_id 이력 관리

Device Agent가 처리한 task_id를 기억하여 통신 복구 후 중복 실행을 방지합니다.
서버 재시작 후에도 이력이 유지됩니다.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS processed_tasks (
    task_id TEXT PRIMARY KEY,
    result_json TEXT NOT NULL,
    processed_at TEXT NOT NULL
)
"""


class TaskIdStore:
    """SQLite 기반 task_id 처리 이력 저장소"""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or ".runtime/processed_tasks.db"

        if self._db_path != ":memory:":
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """SQLite DB 초기화"""
        try:
            with self._connect() as conn:
                conn.execute(_CREATE_TABLE_SQL)
                conn.commit()
        except Exception as e:
            logger.error(f"TaskIdStore DB 초기화 실패: {e}")

    def is_processed(self, task_id: str) -> dict[str, Any] | None:
        """이미 처리된 task_id면 기존 결과 반환, 없으면 None"""
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT result_json FROM processed_tasks WHERE task_id = ?",
                    (task_id,),
                ).fetchone()
            if row:
                return json.loads(row["result_json"])
            return None
        except Exception as e:
            logger.warning(f"TaskIdStore 조회 실패 (task_id={task_id}): {e}")
            return None

    def record(self, task_id: str, result: dict[str, Any]) -> None:
        """처리 완료 후 결과 저장"""
        if self._db_path == ":memory:":
            return  # in-memory 모드에서는 저장하지 않음

        try:
            with self._connect() as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO processed_tasks (task_id, result_json, processed_at)
                       VALUES (?, ?, ?)""",
                    (task_id, json.dumps(result, ensure_ascii=False), datetime.now(timezone.utc).isoformat()),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"TaskIdStore 저장 실패 (task_id={task_id}): {e}")

    def cleanup_expired(self, ttl_hours: int = 24) -> None:
        """TTL 이상 된 레코드 정리 (기본 24시간)"""
        if self._db_path == ":memory:":
            return  # in-memory 모드에서는 정리하지 않음

        try:
            cutoff_time = (datetime.now(timezone.utc) - timedelta(hours=ttl_hours)).isoformat()
            with self._connect() as conn:
                conn.execute("DELETE FROM processed_tasks WHERE processed_at < ?", (cutoff_time,))
                conn.commit()
            logger.debug(f"TaskIdStore cleanup: {ttl_hours}시간 이상 된 레코드 정리 완료")
        except Exception as e:
            logger.error(f"TaskIdStore cleanup 실패: {e}")
