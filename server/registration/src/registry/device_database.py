"""
DeviceDatabase: SQLite 기반 디바이스 영구 저장소

서버 재시작 후에도 등록된 디바이스 정보를 유지합니다.
DeviceRecord를 JSON 형태로 직렬화하여 SQLite에 저장합니다.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)

_CREATE_DEVICES_SQL = """
CREATE TABLE IF NOT EXISTS devices (
    id         INTEGER PRIMARY KEY,
    name       TEXT    NOT NULL,
    data       TEXT    NOT NULL,
    created_at TEXT    NOT NULL,
    updated_at TEXT    NOT NULL
)
"""

_CREATE_META_SQL = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""


class DeviceDatabase:
    """SQLite 기반 디바이스 영구 저장소"""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(_CREATE_DEVICES_SQL)
            conn.execute(_CREATE_META_SQL)
            conn.commit()
        logger.info(f"DeviceDatabase 초기화: {db_path}")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    # ──────────────────────────────────────────────
    # 디바이스 CRUD
    # ──────────────────────────────────────────────

    def load_all(self) -> Dict[int, dict]:
        """저장된 모든 디바이스를 {id: dict} 형태로 반환"""
        with self._connect() as conn:
            rows = conn.execute("SELECT id, data FROM devices ORDER BY id").fetchall()
        result: Dict[int, dict] = {}
        for row in rows:
            try:
                result[int(row["id"])] = json.loads(row["data"])
            except Exception as e:
                logger.warning(f"디바이스 {row['id']} 로드 실패: {e}")
        return result

    def save_device(self, device_id: int, name: str, data: dict, created_at: str, updated_at: str) -> None:
        """디바이스 데이터를 INSERT OR REPLACE로 저장 (upsert)"""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO devices (id, name, data, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (device_id, name, json.dumps(data, ensure_ascii=False), created_at, updated_at),
            )
            conn.commit()

    def delete_device(self, device_id: int) -> None:
        """디바이스 삭제"""
        with self._connect() as conn:
            conn.execute("DELETE FROM devices WHERE id = ?", (device_id,))
            conn.commit()

    # ──────────────────────────────────────────────
    # next_id 관리 (서버 재시작 후 ID 중복 방지)
    # ──────────────────────────────────────────────

    def load_next_id(self) -> int:
        """저장된 next_id 반환. 없으면 현재 max(id)+1 계산"""
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key = 'next_id'").fetchone()
            if row:
                return int(row["value"])
            # meta에 없으면 devices 테이블의 max id + 1
            row2 = conn.execute("SELECT MAX(id) AS max_id FROM devices").fetchone()
            return (int(row2["max_id"]) + 1) if row2 and row2["max_id"] is not None else 1

    def save_next_id(self, next_id: int) -> None:
        """next_id를 meta 테이블에 저장"""
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('next_id', ?)",
                (str(next_id),),
            )
            conn.commit()
