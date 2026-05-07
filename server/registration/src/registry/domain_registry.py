from __future__ import annotations

import json
import logging
import sqlite3
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypeVar
from uuid import uuid4

from src.db.connection import DatabaseConnection, get_db
from src.db.schema import init_schema


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _loads(raw: str | bytes | None) -> dict[str, Any]:
    if not raw:
        return {}
    return json.loads(raw)


@dataclass
class DomainRecord:
    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self.__dict__)


@dataclass
class DeviceRoleRecord(DomainRecord):
    device_id: str
    role_name: str
    responsibility: str = ""
    assigned_by: str = "system"
    status: str = "active"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)


@dataclass
class OperationPlanRecord(DomainRecord):
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


@dataclass
class InsightRecord(DomainRecord):
    insight_id: str
    summary: str
    reason_summary: str
    severity: str = "INFORMATION"
    recommended_action: str | None = None
    confidence_level: str = "medium"
    related_event_id: str | None = None
    related_alert_id: str | None = None
    related_mission_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)


@dataclass
class ApprovalRecord(DomainRecord):
    approval_id: str
    target_type: str
    target_id: str
    summary: str
    requested_action: str
    status: str = "pending"
    requested_by: str = "system_agent"
    decided_by: str | None = None
    decision_notes: str | None = None
    related_insight_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    decided_at: str | None = None


@dataclass
class MissionProposalRecord(DomainRecord):
    proposal_id: str
    title: str
    mission_type: str
    goal: str
    status: str = "pending_approval"
    summary: str = ""
    source: str = "system_agent"
    alert_id: str | None = None
    event_id: str | None = None
    operation_plan_id: str | None = None
    insight_id: str | None = None
    approval_id: str | None = None
    steps: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)


@dataclass
class MissionRecord(DomainRecord):
    mission_id: str
    title: str
    mission_type: str
    goal: str
    status: str = "pending_approval"
    summary: str = ""
    source: str = "system_agent"
    alert_id: str | None = None
    event_id: str | None = None
    operation_plan_id: str | None = None
    proposal_id: str | None = None
    approval_id: str | None = None
    insight_id: str | None = None
    steps: list[dict[str, Any]] = field(default_factory=list)
    timeline: list[dict[str, Any]] = field(default_factory=list)
    logs: list[dict[str, Any]] = field(default_factory=list)
    device_execution_results: list[dict[str, Any]] = field(default_factory=list)
    final_result: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    approved_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


T = TypeVar("T", bound=DomainRecord)


class DomainRegistry:
    def __init__(self, db_path: str | None = None) -> None:
        self.db: DatabaseConnection = get_db(db_path)
        init_schema(self.db.get_connection())

    def _save(self, record_type: str, record_id: str, payload: dict[str, Any], created_at: str | None = None) -> None:
        now = utc_now_iso()
        data = _dumps(payload)
        self.db.execute(
            """
            INSERT OR REPLACE INTO domain_records (record_type, record_id, data, created_at, updated_at)
            VALUES (?, ?, ?, COALESCE((SELECT created_at FROM domain_records WHERE record_id = ?), ?), ?)
            """,
            (record_type, record_id, data, record_id, created_at or now, now),
        )
        self.db.commit()

    def _fetch_row(self, record_type: str, record_id: str) -> sqlite3.Row | None:
        cursor = self.db.execute(
            "SELECT record_type, record_id, data, created_at, updated_at FROM domain_records WHERE record_type = ? AND record_id = ?",
            (record_type, record_id),
        )
        return cursor.fetchone()

    def _load(self, record_type: str, record_id: str, factory: Callable[[dict[str, Any]], T]) -> T:
        row = self._fetch_row(record_type, record_id)
        if row is None:
            raise KeyError(record_id)
        data = _loads(row["data"])
        data.setdefault("created_at", row["created_at"])
        data.setdefault("updated_at", row["updated_at"])
        data = self._apply_record_defaults(record_type, data)
        return factory(**data)

    def _list(self, record_type: str, factory: Callable[[dict[str, Any]], T]) -> list[T]:
        cursor = self.db.execute(
            "SELECT record_id, data, created_at, updated_at FROM domain_records WHERE record_type = ? ORDER BY created_at, record_id",
            (record_type,),
        )
        rows = cursor.fetchall()
        records: list[T] = []
        for row in rows:
            data = _loads(row["data"])
            data.setdefault("created_at", row["created_at"])
            data.setdefault("updated_at", row["updated_at"])
            try:
                records.append(factory(**self._apply_record_defaults(record_type, data)))
            except TypeError as exc:
                logging.getLogger(__name__).warning("Skipping malformed %s row %s: %s", record_type, row["record_id"], exc)
        return records

    def _apply_record_defaults(self, record_type: str, data: dict[str, Any]) -> dict[str, Any]:
        payload = deepcopy(data)
        if record_type == "device_roles":
            payload["device_id"] = payload.get("device_id") or payload.get("record_id") or ""
            payload["role_name"] = payload.get("role_name") or "unassigned"
            payload["responsibility"] = payload.get("responsibility") or ""
            payload["assigned_by"] = payload.get("assigned_by") or "system"
            payload["status"] = payload.get("status") or "active"
        elif record_type == "operation_plans":
            payload["operation_plan_id"] = payload.get("operation_plan_id") or payload.get("record_id") or ""
            payload["name"] = payload.get("name") or "Operation Plan"
            payload["goal"] = payload.get("goal") or ""
        elif record_type == "insights":
            payload["insight_id"] = payload.get("insight_id") or payload.get("record_id") or ""
            payload["summary"] = payload.get("summary") or ""
            payload["reason_summary"] = payload.get("reason_summary") or ""
        elif record_type == "approvals":
            payload["approval_id"] = payload.get("approval_id") or payload.get("record_id") or ""
            payload["target_type"] = payload.get("target_type") or "mission_proposal"
            payload["target_id"] = payload.get("target_id") or ""
            payload["summary"] = payload.get("summary") or ""
            payload["requested_action"] = payload.get("requested_action") or "review"
        elif record_type == "mission_proposals":
            payload["proposal_id"] = payload.get("proposal_id") or payload.get("record_id") or ""
            payload["title"] = payload.get("title") or "Mission Proposal"
            payload["mission_type"] = payload.get("mission_type") or "generic_mission"
            payload["goal"] = payload.get("goal") or ""
        elif record_type == "missions":
            payload["mission_id"] = payload.get("mission_id") or payload.get("record_id") or ""
            payload["title"] = payload.get("title") or "Mission"
            payload["mission_type"] = payload.get("mission_type") or "generic_mission"
            payload["goal"] = payload.get("goal") or ""
        return payload

    def reset(self) -> None:
        self.db.execute("DELETE FROM domain_records")
        self.db.commit()

    def upsert_device_role(self, device_id: str, payload: dict[str, Any]) -> DeviceRoleRecord:
        record_id = str(device_id)
        try:
            existing = self.get_device_role(record_id)
            data = existing.to_dict()
        except KeyError:
            data = {}
        data.update(
            {
                "device_id": record_id,
                "role_name": str(payload.get("role_name") or payload.get("role") or data.get("role_name") or "unassigned"),
                "responsibility": str(payload.get("responsibility") or data.get("responsibility") or ""),
                "assigned_by": str(payload.get("assigned_by") or data.get("assigned_by") or "system"),
                "status": str(payload.get("status") or data.get("status") or "active"),
                "metadata": deepcopy(payload.get("metadata") or data.get("metadata") or {}),
                "created_at": data.get("created_at") or utc_now_iso(),
            }
        )
        record = DeviceRoleRecord(**data)
        self._save("device_roles", record_id, record.to_dict(), created_at=record.created_at)
        return record

    def list_device_roles(self) -> list[DeviceRoleRecord]:
        return self._list("device_roles", DeviceRoleRecord)

    def get_device_role(self, device_id: str) -> DeviceRoleRecord:
        return self._load("device_roles", str(device_id), DeviceRoleRecord)

    def create_operation_plan(self, payload: dict[str, Any]) -> OperationPlanRecord:
        plan_id = str(payload.get("operation_plan_id") or f"op-{uuid4()}")
        try:
            existing = self.get_operation_plan(plan_id)
            data = existing.to_dict()
        except KeyError:
            data = {}
        data.update(
            {
                "operation_plan_id": plan_id,
                "name": str(payload.get("name") or data.get("name") or "Operation Plan"),
                "goal": str(payload.get("goal") or data.get("goal") or ""),
                "status": str(payload.get("status") or data.get("status") or "draft"),
                "summary": str(payload.get("summary") or data.get("summary") or ""),
                "triggers": deepcopy(payload.get("triggers") or data.get("triggers") or []),
                "device_roles": deepcopy(payload.get("device_roles") or data.get("device_roles") or []),
                "mission_templates": deepcopy(payload.get("mission_templates") or data.get("mission_templates") or []),
                "recommended_by": str(payload.get("recommended_by") or data.get("recommended_by") or "system_agent"),
                "metadata": deepcopy(payload.get("metadata") or data.get("metadata") or {}),
                "created_at": data.get("created_at") or utc_now_iso(),
            }
        )
        record = OperationPlanRecord(**data)
        self._save("operation_plans", plan_id, record.to_dict(), created_at=record.created_at)
        return record

    def list_operation_plans(self) -> list[OperationPlanRecord]:
        return self._list("operation_plans", OperationPlanRecord)

    def get_operation_plan(self, plan_id: str) -> OperationPlanRecord:
        return self._load("operation_plans", str(plan_id), OperationPlanRecord)

    def create_insight(self, payload: dict[str, Any]) -> InsightRecord:
        insight_id = str(payload.get("insight_id") or f"insight-{uuid4()}")
        try:
            existing = self.get_insight(insight_id)
            data = existing.to_dict()
        except KeyError:
            data = {}
        data.update(
            {
                "insight_id": insight_id,
                "summary": str(payload.get("summary") or data.get("summary") or ""),
                "reason_summary": str(payload.get("reason_summary") or data.get("reason_summary") or ""),
                "severity": str(payload.get("severity") or data.get("severity") or "INFORMATION").upper(),
                "recommended_action": payload.get("recommended_action", data.get("recommended_action")),
                "confidence_level": str(payload.get("confidence_level") or data.get("confidence_level") or "medium"),
                "related_event_id": payload.get("related_event_id", data.get("related_event_id")),
                "related_alert_id": payload.get("related_alert_id", data.get("related_alert_id")),
                "related_mission_id": payload.get("related_mission_id", data.get("related_mission_id")),
                "metadata": deepcopy(payload.get("metadata") or data.get("metadata") or {}),
                "created_at": data.get("created_at") or utc_now_iso(),
            }
        )
        record = InsightRecord(**data)
        self._save("insights", insight_id, record.to_dict(), created_at=record.created_at)
        return record

    def list_insights(self) -> list[InsightRecord]:
        return self._list("insights", InsightRecord)

    def get_insight(self, insight_id: str) -> InsightRecord:
        return self._load("insights", str(insight_id), InsightRecord)

    def create_approval(self, payload: dict[str, Any]) -> ApprovalRecord:
        approval_id = str(payload.get("approval_id") or f"approval-{uuid4()}")
        try:
            existing = self.get_approval(approval_id)
            data = existing.to_dict()
        except KeyError:
            data = {}
        data.update(
            {
                "approval_id": approval_id,
                "target_type": str(payload.get("target_type") or data.get("target_type") or "mission_proposal"),
                "target_id": str(payload.get("target_id") or data.get("target_id") or ""),
                "summary": str(payload.get("summary") or data.get("summary") or ""),
                "requested_action": str(payload.get("requested_action") or data.get("requested_action") or "review"),
                "status": str(payload.get("status") or data.get("status") or "pending"),
                "requested_by": str(payload.get("requested_by") or data.get("requested_by") or "system_agent"),
                "decided_by": payload.get("decided_by", data.get("decided_by")),
                "decision_notes": payload.get("decision_notes", data.get("decision_notes")),
                "related_insight_id": payload.get("related_insight_id", data.get("related_insight_id")),
                "metadata": deepcopy(payload.get("metadata") or data.get("metadata") or {}),
                "decided_at": payload.get("decided_at", data.get("decided_at")),
                "created_at": data.get("created_at") or utc_now_iso(),
            }
        )
        record = ApprovalRecord(**data)
        self._save("approvals", approval_id, record.to_dict(), created_at=record.created_at)
        return record

    def list_approvals(self) -> list[ApprovalRecord]:
        return self._list("approvals", ApprovalRecord)

    def get_approval(self, approval_id: str) -> ApprovalRecord:
        return self._load("approvals", str(approval_id), ApprovalRecord)

    def decide_approval(self, approval_id: str, approved: bool, *, decided_by: str, notes: str | None = None) -> ApprovalRecord:
        approval = self.get_approval(approval_id)
        approval.status = "approved" if approved else "rejected"
        approval.decided_by = decided_by
        approval.decision_notes = notes
        approval.decided_at = utc_now_iso()
        approval.updated_at = approval.decided_at
        self._save("approvals", approval_id, approval.to_dict(), created_at=approval.created_at)
        return approval

    def create_mission_proposal(self, payload: dict[str, Any]) -> MissionProposalRecord:
        proposal_id = str(payload.get("proposal_id") or f"proposal-{uuid4()}")
        try:
            existing = self.get_mission_proposal(proposal_id)
            data = existing.to_dict()
        except KeyError:
            data = {}
        data.update(
            {
                "proposal_id": proposal_id,
                "title": str(payload.get("title") or data.get("title") or "Mission Proposal"),
                "mission_type": str(payload.get("mission_type") or data.get("mission_type") or "generic_mission"),
                "goal": str(payload.get("goal") or data.get("goal") or ""),
                "status": str(payload.get("status") or data.get("status") or "pending_approval"),
                "summary": str(payload.get("summary") or data.get("summary") or ""),
                "source": str(payload.get("source") or data.get("source") or "system_agent"),
                "alert_id": payload.get("alert_id", data.get("alert_id")),
                "event_id": payload.get("event_id", data.get("event_id")),
                "operation_plan_id": payload.get("operation_plan_id", data.get("operation_plan_id")),
                "insight_id": payload.get("insight_id", data.get("insight_id")),
                "approval_id": payload.get("approval_id", data.get("approval_id")),
                "steps": deepcopy(payload.get("steps") or data.get("steps") or []),
                "metadata": deepcopy(payload.get("metadata") or data.get("metadata") or {}),
                "created_at": data.get("created_at") or utc_now_iso(),
            }
        )
        record = MissionProposalRecord(**data)
        self._save("mission_proposals", proposal_id, record.to_dict(), created_at=record.created_at)
        return record

    def list_mission_proposals(self) -> list[MissionProposalRecord]:
        return self._list("mission_proposals", MissionProposalRecord)

    def get_mission_proposal(self, proposal_id: str) -> MissionProposalRecord:
        return self._load("mission_proposals", str(proposal_id), MissionProposalRecord)

    def create_mission(self, payload: dict[str, Any]) -> MissionRecord:
        mission_id = str(payload.get("mission_id") or f"mission-{uuid4()}")
        try:
            existing = self.get_mission(mission_id)
            data = existing.to_dict()
        except KeyError:
            data = {}
        data.update(
            {
                "mission_id": mission_id,
                "title": str(payload.get("title") or data.get("title") or "Mission"),
                "mission_type": str(payload.get("mission_type") or data.get("mission_type") or "generic_mission"),
                "goal": str(payload.get("goal") or data.get("goal") or ""),
                "status": str(payload.get("status") or data.get("status") or "pending_approval"),
                "summary": str(payload.get("summary") or data.get("summary") or ""),
                "source": str(payload.get("source") or data.get("source") or "system_agent"),
                "alert_id": payload.get("alert_id", data.get("alert_id")),
                "event_id": payload.get("event_id", data.get("event_id")),
                "operation_plan_id": payload.get("operation_plan_id", data.get("operation_plan_id")),
                "proposal_id": payload.get("proposal_id", data.get("proposal_id")),
                "approval_id": payload.get("approval_id", data.get("approval_id")),
                "insight_id": payload.get("insight_id", data.get("insight_id")),
                "steps": deepcopy(payload.get("steps") or data.get("steps") or []),
                "timeline": deepcopy(payload.get("timeline") or data.get("timeline") or []),
                "logs": deepcopy(payload.get("logs") or data.get("logs") or []),
                "device_execution_results": deepcopy(payload.get("device_execution_results") or data.get("device_execution_results") or []),
                "final_result": deepcopy(payload.get("final_result") or data.get("final_result") or {}),
                "metadata": deepcopy(payload.get("metadata") or data.get("metadata") or {}),
                "approved_at": payload.get("approved_at", data.get("approved_at")),
                "started_at": payload.get("started_at", data.get("started_at")),
                "completed_at": payload.get("completed_at", data.get("completed_at")),
                "created_at": data.get("created_at") or utc_now_iso(),
            }
        )
        record = MissionRecord(**data)
        self._save("missions", mission_id, record.to_dict(), created_at=record.created_at)
        return record

    def list_missions(self) -> list[MissionRecord]:
        return self._list("missions", MissionRecord)

    def get_mission(self, mission_id: str) -> MissionRecord:
        return self._load("missions", str(mission_id), MissionRecord)

    def append_mission_timeline_event(
        self,
        mission_id: str,
        event_type: str,
        actor: str | None = None,
        details: dict | None = None,
        task_id: str | None = None,
        step_index: int | None = None,
    ) -> None:
        """Mission timeline에 이벤트 추가 (Ch.18-20)"""
        try:
            from src.core.models import TimelineEvent

            mission = self.get_mission(mission_id)
            event = TimelineEvent(
                event_type=event_type,
                timestamp=utc_now_iso(),
                actor=actor or "system",
                details=details or {},
                related_task_id=task_id,
                related_step_index=step_index,
            )
            mission.timeline.append(event.to_dict())
            mission.updated_at = utc_now_iso()
            self._save("missions", mission_id, mission.to_dict(), created_at=mission.created_at)
        except Exception as e:
            logging.getLogger(__name__).debug(f"Failed to append timeline event: {e}")
