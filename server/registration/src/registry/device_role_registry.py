from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List

from src.registry.registry_utils import utc_now_iso

logger = logging.getLogger(__name__)

_CREATE_DEVICE_ROLES_SQL = """
CREATE TABLE IF NOT EXISTS device_roles (
    device_id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


@dataclass
class DeviceRoleRecord:
    device_id: str
    role_name: str
    responsibility: str = ""
    assigned_by: str = "system"
    status: str = "active"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "role_name": self.role_name,
            "responsibility": self.responsibility,
            "assigned_by": self.assigned_by,
            "status": self.status,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class DeviceRoleRegistry:
    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or ".data/device_roles.db"

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
                conn.execute(_CREATE_DEVICE_ROLES_SQL)
                conn.commit()
            logger.info(f"DeviceRoleRegistry DB 초기화: {self._db_path}")
        except Exception as e:
            logger.error(f"DeviceRoleRegistry DB 초기화 실패: {e}")

    def _row_to_device_role(self, row: sqlite3.Row) -> DeviceRoleRecord:
        data = json.loads(row["data"])
        data.setdefault("device_id", row["device_id"])
        data.setdefault("created_at", row["created_at"])
        data.setdefault("updated_at", row["updated_at"])
        return DeviceRoleRecord(**data)

    def _persist_device_role(self, device_role: DeviceRoleRecord) -> None:
        data = device_role.to_dict()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO device_roles (device_id, data, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (device_role.device_id, json.dumps(data), device_role.created_at, device_role.updated_at),
            )
            conn.commit()

    def upsert_device_role(self, device_id: str, payload: dict[str, Any]) -> DeviceRoleRecord:
        """Device Role 생성 또는 업데이트"""
        try:
            existing = self.get_device_role(device_id)
            data = existing.to_dict()
        except KeyError:
            data = {}

        data.update({
            "device_id": device_id,
            "role_name": str(payload.get("role_name") or payload.get("role") or data.get("role_name") or "unassigned"),
            "responsibility": str(payload.get("responsibility") or data.get("responsibility") or ""),
            "assigned_by": str(payload.get("assigned_by") or data.get("assigned_by") or "system"),
            "status": str(payload.get("status") or data.get("status") or "active"),
            "metadata": payload.get("metadata") or data.get("metadata") or {},
        })

        record = DeviceRoleRecord(**data)
        self._persist_device_role(record)
        return record

    def get_device_role(self, device_id: str) -> DeviceRoleRecord:
        """Device Role 조회"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT device_id, data, created_at, updated_at FROM device_roles WHERE device_id = ?",
                (device_id,)
            ).fetchone()
            if not row:
                raise KeyError(f"Device role not found: {device_id}")
            return self._row_to_device_role(row)

    def list_device_roles(self, limit: int | None = None, offset: int = 0) -> List[DeviceRoleRecord]:
        """Device Role 목록 조회"""
        query = "SELECT device_id, data, created_at, updated_at FROM device_roles ORDER BY created_at, device_id"
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
        return [self._row_to_device_role(row) for row in rows]

    def reset(self) -> None:
        """모든 Device Role 삭제 (테스트용)"""
        with self._connect() as conn:
            conn.execute("DELETE FROM device_roles")
            conn.commit()
        logger.info("DeviceRoleRegistry 초기화 완료")
