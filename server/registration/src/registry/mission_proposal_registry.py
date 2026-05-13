from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, List
from uuid import uuid4

from src.registry.registry_utils import utc_now_iso
from src.core.models import normalize_proposal_status

logger = logging.getLogger(__name__)

_CREATE_MISSION_PROPOSALS_SQL = """
CREATE TABLE IF NOT EXISTS mission_proposals (
    proposal_id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


@dataclass
class MissionProposalRecord:
    proposal_id: str
    title: str
    mission_type: str
    goal: str
    status: str = "PROPOSED"
    selected: bool = False
    priority: str | None = "NORMAL"
    source_event_id: str | None = None
    target_area: str | None = None
    target_position: dict[str, Any] | None = None
    requires_approval: bool = True
    reason: str | None = None
    limitations: str | None = None
    created_by: dict[str, Any] = field(default_factory=lambda: {"type": "SYSTEM", "id": "system"})
    approved_by_user_id: str | None = None
    approved_at: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "id": self.proposal_id,
            "title": self.title,
            "mission_type": self.mission_type,
            "type": self.mission_type,
            "goal": self.goal,
            "status": str(self.status).upper(),
            "selected": self.selected,
            "priority": self.priority,
            "source_event_id": self.source_event_id,
            "target_area": self.target_area,
            "target_position": self.target_position,
            "requires_approval": self.requires_approval,
            "reason": self.reason,
            "limitations": self.limitations,
            "created_by": self.created_by,
            "approved_by_user_id": self.approved_by_user_id,
            "approved_at": self.approved_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class MissionProposalRegistry:
    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or ".data/mission_proposals.db"

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
                conn.execute(_CREATE_MISSION_PROPOSALS_SQL)
                conn.commit()
            logger.info(f"MissionProposalRegistry DB 초기화: {self._db_path}")
        except Exception as e:
            logger.error(f"MissionProposalRegistry DB 초기화 실패: {e}")

    def _row_to_mission_proposal(self, row: sqlite3.Row) -> MissionProposalRecord:
        data = json.loads(row["data"])
        data.setdefault("proposal_id", row["proposal_id"])
        data.setdefault("created_at", row["created_at"])
        data.setdefault("updated_at", row["updated_at"])
        allowed_fields = {item.name for item in fields(MissionProposalRecord)}
        data = {key: value for key, value in data.items() if key in allowed_fields}
        return MissionProposalRecord(**data)

    def _persist_mission_proposal(self, mission_proposal: MissionProposalRecord) -> None:
        data = mission_proposal.to_dict()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO mission_proposals (proposal_id, data, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (mission_proposal.proposal_id, json.dumps(data), mission_proposal.created_at, mission_proposal.updated_at),
            )
            conn.commit()

    def create_mission_proposal(self, payload: dict[str, Any]) -> MissionProposalRecord:
        """Mission Proposal 생성"""
        proposal_id = str(payload.get("proposal_id") or f"proposal-{uuid4()}")
        mission_proposal = MissionProposalRecord(
            proposal_id=proposal_id,
            title=str(payload.get("title") or "Mission Proposal"),
            mission_type=str(payload.get("mission_type") or payload.get("type") or "generic_mission"),
            goal=str(payload.get("goal") or ""),
            status=normalize_proposal_status(payload.get("status") or "PROPOSED"),
            selected=bool(payload.get("selected", False)),
            priority=str(payload.get("priority") or "NORMAL").upper(),
            source_event_id=payload.get("source_event_id") or payload.get("event_id"),
            target_area=payload.get("target_area"),
            target_position=payload.get("target_position"),
            requires_approval=bool(payload.get("requires_approval", True)),
            reason=payload.get("reason"),
            limitations=payload.get("limitations"),
            created_by=payload.get("created_by") or {"type": "SYSTEM", "id": "system"},
            approved_by_user_id=payload.get("approved_by_user_id"),
            approved_at=payload.get("approved_at"),
        )
        self._persist_mission_proposal(mission_proposal)
        return mission_proposal

    def get_mission_proposal(self, proposal_id: str) -> MissionProposalRecord:
        """Mission Proposal 조회"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT proposal_id, data, created_at, updated_at FROM mission_proposals WHERE proposal_id = ?",
                (proposal_id,)
            ).fetchone()
            if not row:
                raise KeyError(f"Mission proposal not found: {proposal_id}")
            return self._row_to_mission_proposal(row)

    def list_mission_proposals(self, limit: int | None = None, offset: int = 0) -> List[MissionProposalRecord]:
        """Mission Proposal 목록 조회"""
        query = "SELECT proposal_id, data, created_at, updated_at FROM mission_proposals ORDER BY created_at, proposal_id"
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
        return [self._row_to_mission_proposal(row) for row in rows]

    def reset(self) -> None:
        """모든 Mission Proposal 삭제 (테스트용)"""
        with self._connect() as conn:
            conn.execute("DELETE FROM mission_proposals")
            conn.commit()
        logger.info("MissionProposalRegistry 초기화 완료")
