from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import List, Any

from src.core.models import ConfigRecord
from src.registry.registry_utils import utc_now_iso

logger = logging.getLogger(__name__)

_CREATE_CONFIGS_SQL = """
CREATE TABLE IF NOT EXISTS configs (
    key TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


class ConfigRegistry:
    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or ".data/configs.db"

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
                conn.execute(_CREATE_CONFIGS_SQL)
                conn.commit()
            logger.info(f"ConfigRegistry DB 초기화: {self._db_path}")
        except Exception as e:
            logger.error(f"ConfigRegistry DB 초기화 실패: {e}")

    def _row_to_config(self, row: sqlite3.Row) -> ConfigRecord:
        data = json.loads(row["data"])
        data.setdefault("key", row["key"])
        data.setdefault("updated_at", row["updated_at"])
        return ConfigRecord(**data)

    def _persist_config(self, config: ConfigRecord) -> None:
        data = config.to_dict()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO configs (key, data, updated_at) VALUES (?, ?, ?)",
                (config.key, json.dumps(data), config.updated_at),
            )
            conn.commit()

    def set_config(
        self,
        key: str,
        value: Any,
        type: str = "string",
        scope: str = "SYSTEM",
        description: str | None = None,
        updated_by: dict | None = None,
    ) -> ConfigRecord:
        """설정값 저장 (upsert)"""
        config = ConfigRecord(
            key=key,
            value=value,
            type=type,
            scope=scope,
            description=description,
            updated_by=updated_by or {"type": "SYSTEM", "id": "system"},
            updated_at=utc_now_iso(),
        )
        self._persist_config(config)
        return config

    def get_config(self, key: str) -> ConfigRecord:
        """설정값 조회"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT key, data, updated_at FROM configs WHERE key = ?",
                (key,)
            ).fetchone()
            if not row:
                raise KeyError(f"Config not found: {key}")
            return self._row_to_config(row)

    def get_config_value(self, key: str, default: Any = None) -> Any:
        """설정값만 조회"""
        try:
            config = self.get_config(key)
            return config.value
        except KeyError:
            return default

    def list_configs(self, scope: str | None = None) -> List[ConfigRecord]:
        """설정 목록 조회"""
        configs = []
        with self._connect() as conn:
            rows = conn.execute("SELECT key, data, updated_at FROM configs").fetchall()
            for row in rows:
                config = self._row_to_config(row)
                if scope is None or config.scope == scope:
                    configs.append(config)
        return configs

    def delete_config(self, key: str) -> None:
        """설정값 삭제"""
        with self._connect() as conn:
            conn.execute("DELETE FROM configs WHERE key = ?", (key,))
            conn.commit()

    def reset(self) -> None:
        """모든 설정 삭제 (테스트용)"""
        with self._connect() as conn:
            conn.execute("DELETE FROM configs")
            conn.commit()
        logger.info("ConfigRegistry 초기화 완료")
