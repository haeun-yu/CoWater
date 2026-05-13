from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import List
from uuid import uuid4

from src.core.models import UserRecord

logger = logging.getLogger(__name__)

_CREATE_USERS_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


class UserRegistry:
    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or ".data/users.db"

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
                conn.execute(_CREATE_USERS_SQL)
                conn.commit()
            logger.info(f"UserRegistry DB 초기화: {self._db_path}")
        except Exception as e:
            logger.error(f"UserRegistry DB 초기화 실패: {e}")

    def _row_to_user(self, row: sqlite3.Row) -> UserRecord:
        data = json.loads(row["data"])
        data.setdefault("user_id", row["user_id"])
        data.setdefault("created_at", row["created_at"])
        data.setdefault("updated_at", row["updated_at"])
        return UserRecord(**data)

    def _persist_user(self, user: UserRecord) -> None:
        data = {
            "user_id": user.user_id,
            "name": user.name,
            "role": user.role,
            "status": user.status,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
        }
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO users (user_id, data, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (user.user_id, json.dumps(data), user.created_at, user.updated_at),
            )
            conn.commit()

    def create_user(self, name: str, role: str, status: str = "ACTIVE") -> UserRecord:
        """새 사용자 생성"""
        user = UserRecord(
            user_id=str(uuid4()),
            name=name,
            role=role,
            status=status,
            created_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            updated_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        )
        self._persist_user(user)
        return user

    def get_user(self, user_id: str) -> UserRecord:
        """사용자 조회"""
        with self._connect() as conn:
            row = conn.execute("SELECT user_id, data, created_at, updated_at FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if not row:
                raise KeyError(f"User not found: {user_id}")
            return self._row_to_user(row)

    def list_users(self, limit: int = 100, offset: int = 0) -> List[UserRecord]:
        """사용자 목록 조회"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT user_id, data, created_at, updated_at FROM users LIMIT ? OFFSET ?",
                (limit, offset)
            ).fetchall()
            return [self._row_to_user(row) for row in rows]

    def update_user(self, user_id: str, **kwargs) -> UserRecord:
        """사용자 정보 업데이트"""
        user = self.get_user(user_id)
        for key, value in kwargs.items():
            if hasattr(user, key):
                setattr(user, key, value)
        user.updated_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        self._persist_user(user)
        return user

    def delete_user(self, user_id: str) -> None:
        """사용자 삭제"""
        with self._connect() as conn:
            conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
            conn.commit()

    def reset(self) -> None:
        """모든 사용자 삭제 (테스트용)"""
        with self._connect() as conn:
            conn.execute("DELETE FROM users")
            conn.commit()
        logger.info("UserRegistry 초기화 완료")
