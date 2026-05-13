from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List
from uuid import uuid4

from src.registry.registry_utils import utc_now_iso

logger = logging.getLogger(__name__)

_CREATE_OPERATION_PLANS_SQL = """
CREATE TABLE IF NOT EXISTS operation_plans (
    operation_plan_id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


@dataclass
class OperationPlanRecord:
    operation_plan_id: str
    name: str
    goal: str
    status: str = "draft"
    summary: str = ""
    triggers: list[dict[str, Any]] = field(default_factory=list)
    device_roles: list[dict[str, Any]] = field(default_factory=list)
    mission_templates: list[dict[str, Any]] = field(default_factory=list)
    recommended_by: str = "system_agent"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_plan_id": self.operation_plan_id,
            "name": self.name,
            "goal": self.goal,
            "status": self.status,
            "summary": self.summary,
            "triggers": self.triggers,
            "device_roles": self.device_roles,
            "mission_templates": self.mission_templates,
            "recommended_by": self.recommended_by,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class OperationPlanRegistry:
    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or ".data/operation_plans.db"

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
                conn.execute(_CREATE_OPERATION_PLANS_SQL)
                conn.commit()
            logger.info(f"OperationPlanRegistry DB 초기화: {self._db_path}")
        except Exception as e:
            logger.error(f"OperationPlanRegistry DB 초기화 실패: {e}")

    def _row_to_operation_plan(self, row: sqlite3.Row) -> OperationPlanRecord:
        data = json.loads(row["data"])
        data.setdefault("operation_plan_id", row["operation_plan_id"])
        data.setdefault("created_at", row["created_at"])
        data.setdefault("updated_at", row["updated_at"])
        return OperationPlanRecord(**data)

    def _persist_operation_plan(self, operation_plan: OperationPlanRecord) -> None:
        data = operation_plan.to_dict()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO operation_plans (operation_plan_id, data, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (operation_plan.operation_plan_id, json.dumps(data), operation_plan.created_at, operation_plan.updated_at),
            )
            conn.commit()

    def create_operation_plan(self, payload: dict[str, Any]) -> OperationPlanRecord:
        """Operation Plan 생성"""
        plan_id = str(payload.get("operation_plan_id") or f"op-{uuid4()}")
        operation_plan = OperationPlanRecord(
            operation_plan_id=plan_id,
            name=str(payload.get("name") or "Operation Plan"),
            goal=str(payload.get("goal") or ""),
            status=str(payload.get("status") or "draft"),
            summary=str(payload.get("summary") or ""),
            triggers=payload.get("triggers") or [],
            device_roles=payload.get("device_roles") or [],
            mission_templates=payload.get("mission_templates") or [],
            recommended_by=str(payload.get("recommended_by") or "system_agent"),
            metadata=payload.get("metadata") or {},
        )
        self._persist_operation_plan(operation_plan)
        return operation_plan

    def get_operation_plan(self, plan_id: str) -> OperationPlanRecord:
        """Operation Plan 조회"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT operation_plan_id, data, created_at, updated_at FROM operation_plans WHERE operation_plan_id = ?",
                (plan_id,)
            ).fetchone()
            if not row:
                raise KeyError(f"Operation plan not found: {plan_id}")
            return self._row_to_operation_plan(row)

    def list_operation_plans(self, limit: int | None = None, offset: int = 0) -> List[OperationPlanRecord]:
        """Operation Plan 목록 조회"""
        query = "SELECT operation_plan_id, data, created_at, updated_at FROM operation_plans ORDER BY created_at, operation_plan_id"
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
        return [self._row_to_operation_plan(row) for row in rows]

    def reset(self) -> None:
        """모든 Operation Plan 삭제 (테스트용)"""
        with self._connect() as conn:
            conn.execute("DELETE FROM operation_plans")
            conn.commit()
        logger.info("OperationPlanRegistry 초기화 완료")
