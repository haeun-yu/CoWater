from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import List
from uuid import uuid4

from src.core.models import SensorRecord
from src.registry.registry_utils import utc_now_iso

logger = logging.getLogger(__name__)

_CREATE_SENSORS_SQL = """
CREATE TABLE IF NOT EXISTS sensors (
    sensor_id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_sensors_device_id ON sensors(device_id)
"""


class SensorRegistry:
    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or ".data/sensors.db"

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
                conn.execute(_CREATE_SENSORS_SQL)
                conn.execute(_CREATE_INDEX_SQL)
                conn.commit()
            logger.info(f"SensorRegistry DB 초기화: {self._db_path}")
        except Exception as e:
            logger.error(f"SensorRegistry DB 초기화 실패: {e}")

    def _row_to_sensor(self, row: sqlite3.Row) -> SensorRecord:
        data = json.loads(row["data"])
        data.setdefault("sensor_id", row["sensor_id"])
        data.setdefault("device_id", row["device_id"])
        data.setdefault("created_at", row["created_at"])
        data.setdefault("updated_at", row["updated_at"])
        return SensorRecord(**data)

    def _persist_sensor(self, sensor: SensorRecord) -> None:
        data = sensor.to_dict()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sensors (sensor_id, device_id, data, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (sensor.sensor_id, sensor.device_id, json.dumps(data), sensor.created_at, sensor.updated_at),
            )
            conn.commit()

    def create_sensor(
        self,
        device_id: str,
        name: str,
        type: str,
        stream_endpoint: str,
    ) -> SensorRecord:
        """새 Sensor 생성"""
        sensor = SensorRecord(
            sensor_id=str(uuid4()),
            device_id=device_id,
            name=name,
            type=type,
            stream_endpoint=stream_endpoint,
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        )
        self._persist_sensor(sensor)
        return sensor

    def get_sensor(self, sensor_id: str) -> SensorRecord:
        """Sensor 조회"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT sensor_id, device_id, data, created_at, updated_at FROM sensors WHERE sensor_id = ?",
                (sensor_id,)
            ).fetchone()
            if not row:
                raise KeyError(f"Sensor not found: {sensor_id}")
            return self._row_to_sensor(row)

    def list_sensors_by_device(self, device_id: str) -> List[SensorRecord]:
        """Device별 Sensor 목록 조회"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT sensor_id, device_id, data, created_at, updated_at FROM sensors WHERE device_id = ?",
                (device_id,)
            ).fetchall()
            return [self._row_to_sensor(row) for row in rows]

    def list_sensors(self, limit: int = 100, offset: int = 0) -> List[SensorRecord]:
        """Sensor 목록 조회"""
        query = "SELECT sensor_id, device_id, data, created_at, updated_at FROM sensors ORDER BY created_at DESC"
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
            return [self._row_to_sensor(row) for row in rows]

    def update_sensor(self, sensor_id: str, **kwargs) -> SensorRecord:
        """Sensor 업데이트"""
        sensor = self.get_sensor(sensor_id)
        for key, value in kwargs.items():
            if hasattr(sensor, key):
                setattr(sensor, key, value)
        sensor.updated_at = utc_now_iso()
        self._persist_sensor(sensor)
        return sensor

    def delete_sensor(self, sensor_id: str) -> None:
        """Sensor 삭제"""
        sensor = self.get_sensor(sensor_id)
        sensor.deleted_at = utc_now_iso()
        self._persist_sensor(sensor)

    def reset(self) -> None:
        """모든 Sensor 삭제 (테스트용)"""
        with self._connect() as conn:
            conn.execute("DELETE FROM sensors")
            conn.commit()
        logger.info("SensorRegistry 초기화 완료")
