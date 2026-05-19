from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import List
from uuid import uuid4

from src.core.models import MissionRecord, normalize_mission_status
from src.registry.registry_utils import utc_now_iso

logger = logging.getLogger(__name__)

_CREATE_MISSIONS_SQL = """
CREATE TABLE IF NOT EXISTS missions (
    mission_id TEXT PRIMARY KEY,
    source_event_id TEXT,
    source_proposal_id TEXT,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

_CREATE_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_missions_source_event_id ON missions(source_event_id);
CREATE INDEX IF NOT EXISTS idx_missions_source_proposal_id ON missions(source_proposal_id);
CREATE INDEX IF NOT EXISTS idx_missions_created_at ON missions(created_at);
"""


class MissionRegistry:
    """Mission 실행 계획 관리 (docs 기준)"""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or ".data/missions.db"

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
                conn.execute(_CREATE_MISSIONS_SQL)
                for sql in _CREATE_INDEXES_SQL.split(";"):
                    if sql.strip():
                        conn.execute(sql)
                conn.commit()
            logger.info(f"MissionRegistry DB 초기화: {self._db_path}")
        except Exception as e:
            logger.error(f"MissionRegistry DB 초기화 실패: {e}")

    def _row_to_mission(self, row: sqlite3.Row) -> MissionRecord:
        data = json.loads(row["data"])
        data.setdefault("mission_id", row["mission_id"])
        data.setdefault("source_event_id", row["source_event_id"])
        data.setdefault("source_proposal_id", row["source_proposal_id"])
        data.setdefault("created_at", row["created_at"])
        data.setdefault("updated_at", row["updated_at"])
        return MissionRecord(**data)

    def _persist_mission(self, mission: MissionRecord) -> None:
        data = mission.to_dict()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO missions (mission_id, source_event_id, source_proposal_id, data, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (mission.mission_id, mission.source_event_id, mission.source_proposal_id, json.dumps(data), mission.created_at, mission.updated_at),
            )
            conn.commit()

    def create_mission(
        self,
        title: str,
        type: str,
        source_event_id: str | None = None,
        source_proposal_id: str | None = None,
        status: str = "READY",
        priority: str = "NORMAL",
        **kwargs
    ) -> MissionRecord:
        """새 Mission 생성"""
        mission = MissionRecord(
            mission_id=str(kwargs.get("mission_id") or uuid4()),
            title=title,
            type=type,
            status=normalize_mission_status(status),
            priority=priority,
            source_event_id=source_event_id,
            source_proposal_id=source_proposal_id,
            target_area=kwargs.get("target_area"),
            target_position=kwargs.get("target_position"),
            created_by=kwargs.get("created_by", {"type": "SYSTEM", "id": "system"}),
            approved_by_user_id=kwargs.get("approved_by_user_id"),
            approved_at=kwargs.get("approved_at"),
            approval_id=kwargs.get("approval_id"),
            status_updated_at=utc_now_iso(),
            status_reason=kwargs.get("status_reason"),
            result_summary=kwargs.get("result_summary"),
            steps=list(kwargs.get("steps") or []),
            timeline=list(kwargs.get("timeline") or []),
            final_result=dict(kwargs.get("final_result") or {}),
            metadata=dict(kwargs.get("metadata") or {}),
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        )
        self._persist_mission(mission)
        return mission

    def get_mission(self, mission_id: str) -> MissionRecord:
        """Mission 조회"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT mission_id, source_event_id, source_proposal_id, data, created_at, updated_at FROM missions WHERE mission_id = ?",
                (mission_id,)
            ).fetchone()
            if not row:
                raise KeyError(f"Mission not found: {mission_id}")
            return self._row_to_mission(row)

    def list_missions(self, limit: int = 100, offset: int = 0) -> List[MissionRecord]:
        """Mission 목록 조회"""
        query = "SELECT mission_id, source_event_id, source_proposal_id, data, created_at, updated_at FROM missions ORDER BY created_at DESC"
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
            return [self._row_to_mission(row) for row in rows]

    def list_missions_by_status(self, status: str) -> List[MissionRecord]:
        """상태별 Mission 목록 조회"""
        normalized_status = normalize_mission_status(status)
        missions = []
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT mission_id, source_event_id, source_proposal_id, data, created_at, updated_at FROM missions ORDER BY created_at DESC"
            ).fetchall()
            for row in rows:
                mission = self._row_to_mission(row)
                if mission.status == normalized_status:
                    missions.append(mission)
        return missions

    def update_mission_status(self, mission_id: str, status: str, reason: str | None = None) -> MissionRecord:
        """Mission 상태 업데이트"""
        mission = self.get_mission(mission_id)
        mission.touch(status, reason)
        self._persist_mission(mission)
        return mission

    def update_mission(self, mission_id: str, **kwargs) -> MissionRecord:
        """Mission 정보 업데이트"""
        mission = self.get_mission(mission_id)
        for key, value in kwargs.items():
            if hasattr(mission, key):
                setattr(mission, key, value)
        mission.updated_at = utc_now_iso()
        self._persist_mission(mission)
        return mission

    def get_mission_stats(self) -> dict:
        """Mission 통계"""
        missions = self.list_missions(limit=10000)
        return {
            "total": len(missions),
            "ready": len([m for m in missions if m.status == "READY"]),
            "in_progress": len([m for m in missions if m.status == "IN_PROGRESS"]),
            "completed": len([m for m in missions if m.status == "COMPLETED"]),
            "failed": len([m for m in missions if m.status == "FAILED"]),
            "cancelled": len([m for m in missions if m.status == "CANCELLED"]),
            "expired": len([m for m in missions if m.status == "EXPIRED"]),
        }

    def reset(self) -> None:
        """모든 Mission 삭제 (테스트용)"""
        with self._connect() as conn:
            conn.execute("DELETE FROM missions")
            conn.commit()
        logger.info("MissionRegistry 초기화 완료")
