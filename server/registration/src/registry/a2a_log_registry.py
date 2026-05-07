"""
A2ALogRegistry: A2A 메시지 로깅 저장소 (SQLite 기반)

모든 Agent 간 직접 통신(A2A)을 기록하여 추적 및 분석이 가능하도록 함.
아키텍처 Ch.14.1 (A2A 규칙) 준수: "모든 A2A 메시지는 로깅되어야 한다"
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS a2a_logs (
    log_id TEXT PRIMARY KEY,
    direction TEXT NOT NULL,        -- "inbound" | "outbound"
    from_agent_id TEXT,
    to_agent_id TEXT,
    message_type TEXT,             -- "task.assign", "mission.result", "event.report", etc
    task_id TEXT,
    mission_id TEXT,
    payload_json TEXT NOT NULL,
    logged_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_a2a_logs_mission_id ON a2a_logs(mission_id);
CREATE INDEX IF NOT EXISTS idx_a2a_logs_task_id ON a2a_logs(task_id);
CREATE INDEX IF NOT EXISTS idx_a2a_logs_from_agent ON a2a_logs(from_agent_id);
CREATE INDEX IF NOT EXISTS idx_a2a_logs_to_agent ON a2a_logs(to_agent_id);
CREATE INDEX IF NOT EXISTS idx_a2a_logs_message_type ON a2a_logs(message_type);
"""


class A2ALogRegistry:
    """A2A 메시지 로깅 저장소"""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or ".data/a2a_logs.db"

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
                for sql in _CREATE_TABLE_SQL.split(";"):
                    sql = sql.strip()
                    if sql:
                        conn.execute(sql)
                conn.commit()
        except Exception as e:
            logger.error(f"A2ALogRegistry DB 초기화 실패: {e}")

    def log_message(
        self,
        direction: str,
        from_agent_id: str,
        to_agent_id: str,
        message_type: str,
        task_id: str | None,
        mission_id: str | None,
        payload: dict[str, Any],
    ) -> str:
        """A2A 메시지 로깅"""
        if self._db_path == ":memory:":
            return ""  # in-memory 모드에서는 저장하지 않음

        log_id = str(uuid4())
        try:
            with self._connect() as conn:
                conn.execute(
                    """INSERT INTO a2a_logs
                       (log_id, direction, from_agent_id, to_agent_id, message_type, task_id, mission_id, payload_json, logged_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        log_id,
                        direction,
                        from_agent_id,
                        to_agent_id,
                        message_type,
                        task_id,
                        mission_id,
                        json.dumps(payload, ensure_ascii=False, default=str),
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                conn.commit()
            logger.debug(f"A2A message logged: {message_type} from {from_agent_id} to {to_agent_id}")
        except Exception as e:
            logger.error(f"A2A 로깅 실패 (message_type={message_type}): {e}")

        return log_id

    def get_logs(
        self,
        mission_id: str | None = None,
        task_id: str | None = None,
        from_agent_id: str | None = None,
        to_agent_id: str | None = None,
        message_type: str | None = None,
        direction: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """A2A 로그 조회 (필터링 지원)"""
        try:
            filters = []
            params = []

            if mission_id:
                filters.append("mission_id = ?")
                params.append(mission_id)

            if task_id:
                filters.append("task_id = ?")
                params.append(task_id)

            if from_agent_id:
                filters.append("from_agent_id = ?")
                params.append(from_agent_id)

            if to_agent_id:
                filters.append("to_agent_id = ?")
                params.append(to_agent_id)

            if message_type:
                filters.append("message_type = ?")
                params.append(message_type)

            if direction:
                filters.append("direction = ?")
                params.append(direction)

            where_clause = " AND ".join(filters) if filters else "1=1"
            query = f"""
                SELECT log_id, direction, from_agent_id, to_agent_id, message_type, task_id, mission_id, payload_json, logged_at
                FROM a2a_logs
                WHERE {where_clause}
                ORDER BY logged_at DESC
                LIMIT ? OFFSET ?
            """
            params.append(limit)
            params.append(offset)

            with self._connect() as conn:
                rows = conn.execute(query, params).fetchall()

            result = []
            for row in rows:
                try:
                    payload = json.loads(row["payload_json"])
                except Exception:
                    payload = {"raw": row["payload_json"]}

                result.append(
                    {
                        "log_id": row["log_id"],
                        "direction": row["direction"],
                        "from_agent_id": row["from_agent_id"],
                        "to_agent_id": row["to_agent_id"],
                        "message_type": row["message_type"],
                        "task_id": row["task_id"],
                        "mission_id": row["mission_id"],
                        "payload": payload,
                        "logged_at": row["logged_at"],
                    }
                )

            return result
        except Exception as e:
            logger.error(f"A2A 로그 조회 실패: {e}")
            return []

    def delete_logs_before(self, cutoff_iso: str) -> int:
        """특정 시간 이전의 로그 삭제"""
        if self._db_path == ":memory:":
            return 0

        try:
            with self._connect() as conn:
                cursor = conn.execute("DELETE FROM a2a_logs WHERE logged_at < ?", (cutoff_iso,))
                conn.commit()
                return cursor.rowcount
        except Exception as e:
            logger.error(f"A2A 로그 삭제 실패: {e}")
            return 0

    def reset(self) -> None:
        if self._db_path == ":memory:":
            return
        try:
            with self._connect() as conn:
                conn.execute("DELETE FROM a2a_logs")
                conn.commit()
        except Exception as e:
            logger.error(f"A2A 로그 초기화 실패: {e}")
