from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


class DomainRegistry:
    def __init__(self, storage_path: Path | None = None) -> None:
        self._device_roles: dict[str, DeviceRoleRecord] = {}
        self._operation_plans: dict[str, OperationPlanRecord] = {}
        self._insights: dict[str, InsightRecord] = {}
        self._approvals: dict[str, ApprovalRecord] = {}
        self._mission_proposals: dict[str, MissionProposalRecord] = {}
        self._missions: dict[str, MissionRecord] = {}
        self.storage_path = storage_path or Path(__file__).resolve().parents[3] / ".data" / "domain_registry.json"
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._load()

    def reset(self) -> None:
        self._device_roles.clear()
        self._operation_plans.clear()
        self._insights.clear()
        self._approvals.clear()
        self._mission_proposals.clear()
        self._missions.clear()
        self._save()

    def _load(self) -> None:
        if not self.storage_path.exists():
            return
        raw = json.loads(self.storage_path.read_text(encoding="utf-8") or "{}")
        self._device_roles = {
            key: DeviceRoleRecord(**value)
            for key, value in dict(raw.get("device_roles") or {}).items()
        }
        self._operation_plans = {
            key: OperationPlanRecord(**value)
            for key, value in dict(raw.get("operation_plans") or {}).items()
        }
        self._insights = {
            key: InsightRecord(**value)
            for key, value in dict(raw.get("insights") or {}).items()
        }
        self._approvals = {
            key: ApprovalRecord(**value)
            for key, value in dict(raw.get("approvals") or {}).items()
        }
        self._mission_proposals = {
            key: MissionProposalRecord(**value)
            for key, value in dict(raw.get("mission_proposals") or {}).items()
        }
        self._missions = {
            key: MissionRecord(**value)
            for key, value in dict(raw.get("missions") or {}).items()
        }

    def _save(self) -> None:
        payload = {
            "device_roles": {key: value.to_dict() for key, value in self._device_roles.items()},
            "operation_plans": {key: value.to_dict() for key, value in self._operation_plans.items()},
            "insights": {key: value.to_dict() for key, value in self._insights.items()},
            "approvals": {key: value.to_dict() for key, value in self._approvals.items()},
            "mission_proposals": {key: value.to_dict() for key, value in self._mission_proposals.items()},
            "missions": {key: value.to_dict() for key, value in self._missions.items()},
        }
        self.storage_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def upsert_device_role(self, device_id: str, payload: dict[str, Any]) -> DeviceRoleRecord:
        existing = self._device_roles.get(device_id)
        if existing is None:
            record = DeviceRoleRecord(
                device_id=device_id,
                role_name=str(payload.get("role_name") or payload.get("role") or "unassigned"),
                responsibility=str(payload.get("responsibility") or ""),
                assigned_by=str(payload.get("assigned_by") or "system"),
                status=str(payload.get("status") or "active"),
                metadata=deepcopy(payload.get("metadata") or {}),
            )
            self._device_roles[device_id] = record
            self._save()
            return record
        existing.role_name = str(payload.get("role_name") or payload.get("role") or existing.role_name)
        existing.responsibility = str(payload.get("responsibility") or existing.responsibility)
        existing.assigned_by = str(payload.get("assigned_by") or existing.assigned_by)
        existing.status = str(payload.get("status") or existing.status)
        existing.metadata = deepcopy(payload.get("metadata") or existing.metadata)
        existing.updated_at = utc_now_iso()
        self._save()
        return existing

    def list_device_roles(self) -> list[DeviceRoleRecord]:
        return [self._device_roles[key] for key in sorted(self._device_roles)]

    def get_device_role(self, device_id: str) -> DeviceRoleRecord:
        if device_id not in self._device_roles:
            raise KeyError(device_id)
        return self._device_roles[device_id]

    def create_operation_plan(self, payload: dict[str, Any]) -> OperationPlanRecord:
        plan_id = str(payload.get("operation_plan_id") or f"op-{uuid4()}")
        existing = self._operation_plans.get(plan_id)
        if existing is None:
            record = OperationPlanRecord(
                operation_plan_id=plan_id,
                name=str(payload.get("name") or "Operation Plan"),
                goal=str(payload.get("goal") or ""),
                status=str(payload.get("status") or "draft"),
                summary=str(payload.get("summary") or ""),
                triggers=deepcopy(payload.get("triggers") or []),
                device_roles=deepcopy(payload.get("device_roles") or []),
                mission_templates=deepcopy(payload.get("mission_templates") or []),
                recommended_by=str(payload.get("recommended_by") or "system_agent"),
                metadata=deepcopy(payload.get("metadata") or {}),
            )
            self._operation_plans[plan_id] = record
            self._save()
            return record
        existing.name = str(payload.get("name") or existing.name)
        existing.goal = str(payload.get("goal") or existing.goal)
        existing.status = str(payload.get("status") or existing.status)
        existing.summary = str(payload.get("summary") or existing.summary)
        existing.triggers = deepcopy(payload.get("triggers") or existing.triggers)
        existing.device_roles = deepcopy(payload.get("device_roles") or existing.device_roles)
        existing.mission_templates = deepcopy(payload.get("mission_templates") or existing.mission_templates)
        existing.recommended_by = str(payload.get("recommended_by") or existing.recommended_by)
        existing.metadata = deepcopy(payload.get("metadata") or existing.metadata)
        existing.updated_at = utc_now_iso()
        self._save()
        return existing

    def list_operation_plans(self) -> list[OperationPlanRecord]:
        return [self._operation_plans[key] for key in sorted(self._operation_plans)]

    def get_operation_plan(self, plan_id: str) -> OperationPlanRecord:
        if plan_id not in self._operation_plans:
            raise KeyError(plan_id)
        return self._operation_plans[plan_id]

    def create_insight(self, payload: dict[str, Any]) -> InsightRecord:
        insight_id = str(payload.get("insight_id") or f"insight-{uuid4()}")
        existing = self._insights.get(insight_id)
        if existing is None:
            record = InsightRecord(
                insight_id=insight_id,
                summary=str(payload.get("summary") or ""),
                reason_summary=str(payload.get("reason_summary") or ""),
                severity=str(payload.get("severity") or "INFORMATION").upper(),
                recommended_action=payload.get("recommended_action"),
                confidence_level=str(payload.get("confidence_level") or "medium"),
                related_event_id=payload.get("related_event_id"),
                related_alert_id=payload.get("related_alert_id"),
                related_mission_id=payload.get("related_mission_id"),
                metadata=deepcopy(payload.get("metadata") or {}),
            )
            self._insights[insight_id] = record
            self._save()
            return record
        existing.summary = str(payload.get("summary") or existing.summary)
        existing.reason_summary = str(payload.get("reason_summary") or existing.reason_summary)
        existing.severity = str(payload.get("severity") or existing.severity).upper()
        existing.recommended_action = payload.get("recommended_action") or existing.recommended_action
        existing.confidence_level = str(payload.get("confidence_level") or existing.confidence_level)
        existing.related_event_id = payload.get("related_event_id") or existing.related_event_id
        existing.related_alert_id = payload.get("related_alert_id") or existing.related_alert_id
        existing.related_mission_id = payload.get("related_mission_id") or existing.related_mission_id
        existing.metadata = deepcopy(payload.get("metadata") or existing.metadata)
        existing.updated_at = utc_now_iso()
        self._save()
        return existing

    def list_insights(self) -> list[InsightRecord]:
        return [self._insights[key] for key in sorted(self._insights)]

    def get_insight(self, insight_id: str) -> InsightRecord:
        if insight_id not in self._insights:
            raise KeyError(insight_id)
        return self._insights[insight_id]

    def create_approval(self, payload: dict[str, Any]) -> ApprovalRecord:
        approval_id = str(payload.get("approval_id") or f"approval-{uuid4()}")
        existing = self._approvals.get(approval_id)
        if existing is None:
            record = ApprovalRecord(
                approval_id=approval_id,
                target_type=str(payload.get("target_type") or "mission_proposal"),
                target_id=str(payload.get("target_id") or ""),
                summary=str(payload.get("summary") or ""),
                requested_action=str(payload.get("requested_action") or "review"),
                status=str(payload.get("status") or "pending"),
                requested_by=str(payload.get("requested_by") or "system_agent"),
                decided_by=payload.get("decided_by"),
                decision_notes=payload.get("decision_notes"),
                related_insight_id=payload.get("related_insight_id"),
                metadata=deepcopy(payload.get("metadata") or {}),
                decided_at=payload.get("decided_at"),
            )
            self._approvals[approval_id] = record
            self._save()
            return record
        existing.target_type = str(payload.get("target_type") or existing.target_type)
        existing.target_id = str(payload.get("target_id") or existing.target_id)
        existing.summary = str(payload.get("summary") or existing.summary)
        existing.requested_action = str(payload.get("requested_action") or existing.requested_action)
        existing.status = str(payload.get("status") or existing.status)
        existing.requested_by = str(payload.get("requested_by") or existing.requested_by)
        existing.decided_by = payload.get("decided_by") or existing.decided_by
        existing.decision_notes = payload.get("decision_notes") or existing.decision_notes
        existing.related_insight_id = payload.get("related_insight_id") or existing.related_insight_id
        existing.metadata = deepcopy(payload.get("metadata") or existing.metadata)
        existing.decided_at = payload.get("decided_at") or existing.decided_at
        existing.updated_at = utc_now_iso()
        self._save()
        return existing

    def list_approvals(self) -> list[ApprovalRecord]:
        return [self._approvals[key] for key in sorted(self._approvals)]

    def get_approval(self, approval_id: str) -> ApprovalRecord:
        if approval_id not in self._approvals:
            raise KeyError(approval_id)
        return self._approvals[approval_id]

    def decide_approval(self, approval_id: str, approved: bool, *, decided_by: str, notes: str | None = None) -> ApprovalRecord:
        approval = self.get_approval(approval_id)
        approval.status = "approved" if approved else "rejected"
        approval.decided_by = decided_by
        approval.decision_notes = notes
        approval.decided_at = utc_now_iso()
        approval.updated_at = approval.decided_at
        self._save()
        return approval

    def create_mission_proposal(self, payload: dict[str, Any]) -> MissionProposalRecord:
        proposal_id = str(payload.get("proposal_id") or f"proposal-{uuid4()}")
        existing = self._mission_proposals.get(proposal_id)
        if existing is None:
            record = MissionProposalRecord(
                proposal_id=proposal_id,
                title=str(payload.get("title") or "Mission Proposal"),
                mission_type=str(payload.get("mission_type") or "generic_mission"),
                goal=str(payload.get("goal") or ""),
                status=str(payload.get("status") or "pending_approval"),
                summary=str(payload.get("summary") or ""),
                source=str(payload.get("source") or "system_agent"),
                alert_id=payload.get("alert_id"),
                event_id=payload.get("event_id"),
                operation_plan_id=payload.get("operation_plan_id"),
                insight_id=payload.get("insight_id"),
                approval_id=payload.get("approval_id"),
                steps=deepcopy(payload.get("steps") or []),
                metadata=deepcopy(payload.get("metadata") or {}),
            )
            self._mission_proposals[proposal_id] = record
            self._save()
            return record
        existing.title = str(payload.get("title") or existing.title)
        existing.mission_type = str(payload.get("mission_type") or existing.mission_type)
        existing.goal = str(payload.get("goal") or existing.goal)
        existing.status = str(payload.get("status") or existing.status)
        existing.summary = str(payload.get("summary") or existing.summary)
        existing.source = str(payload.get("source") or existing.source)
        existing.alert_id = payload.get("alert_id") or existing.alert_id
        existing.event_id = payload.get("event_id") or existing.event_id
        existing.operation_plan_id = payload.get("operation_plan_id") or existing.operation_plan_id
        existing.insight_id = payload.get("insight_id") or existing.insight_id
        existing.approval_id = payload.get("approval_id") or existing.approval_id
        existing.steps = deepcopy(payload.get("steps") or existing.steps)
        existing.metadata = deepcopy(payload.get("metadata") or existing.metadata)
        existing.updated_at = utc_now_iso()
        self._save()
        return existing

    def list_mission_proposals(self) -> list[MissionProposalRecord]:
        return [self._mission_proposals[key] for key in sorted(self._mission_proposals)]

    def get_mission_proposal(self, proposal_id: str) -> MissionProposalRecord:
        if proposal_id not in self._mission_proposals:
            raise KeyError(proposal_id)
        return self._mission_proposals[proposal_id]

    def create_mission(self, payload: dict[str, Any]) -> MissionRecord:
        mission_id = str(payload.get("mission_id") or f"mission-{uuid4()}")
        existing = self._missions.get(mission_id)
        if existing is None:
            record = MissionRecord(
                mission_id=mission_id,
                title=str(payload.get("title") or "Mission"),
                mission_type=str(payload.get("mission_type") or "generic_mission"),
                goal=str(payload.get("goal") or ""),
                status=str(payload.get("status") or "pending_approval"),
                summary=str(payload.get("summary") or ""),
                source=str(payload.get("source") or "system_agent"),
                alert_id=payload.get("alert_id"),
                event_id=payload.get("event_id"),
                operation_plan_id=payload.get("operation_plan_id"),
                proposal_id=payload.get("proposal_id"),
                approval_id=payload.get("approval_id"),
                insight_id=payload.get("insight_id"),
                steps=deepcopy(payload.get("steps") or []),
                timeline=deepcopy(payload.get("timeline") or []),
                logs=deepcopy(payload.get("logs") or []),
                device_execution_results=deepcopy(payload.get("device_execution_results") or []),
                final_result=deepcopy(payload.get("final_result") or {}),
                metadata=deepcopy(payload.get("metadata") or {}),
                approved_at=payload.get("approved_at"),
                started_at=payload.get("started_at"),
                completed_at=payload.get("completed_at"),
            )
            self._missions[mission_id] = record
            self._save()
            return record
        existing.title = str(payload.get("title") or existing.title)
        existing.mission_type = str(payload.get("mission_type") or existing.mission_type)
        existing.goal = str(payload.get("goal") or existing.goal)
        existing.status = str(payload.get("status") or existing.status)
        existing.summary = str(payload.get("summary") or existing.summary)
        existing.source = str(payload.get("source") or existing.source)
        existing.alert_id = payload.get("alert_id") or existing.alert_id
        existing.event_id = payload.get("event_id") or existing.event_id
        existing.operation_plan_id = payload.get("operation_plan_id") or existing.operation_plan_id
        existing.proposal_id = payload.get("proposal_id") or existing.proposal_id
        existing.approval_id = payload.get("approval_id") or existing.approval_id
        existing.insight_id = payload.get("insight_id") or existing.insight_id
        existing.steps = deepcopy(payload.get("steps") or existing.steps)
        existing.timeline = deepcopy(payload.get("timeline") or existing.timeline)
        existing.logs = deepcopy(payload.get("logs") or existing.logs)
        existing.device_execution_results = deepcopy(payload.get("device_execution_results") or existing.device_execution_results)
        existing.final_result = deepcopy(payload.get("final_result") or existing.final_result)
        existing.metadata = deepcopy(payload.get("metadata") or existing.metadata)
        existing.approved_at = payload.get("approved_at") or existing.approved_at
        existing.started_at = payload.get("started_at") or existing.started_at
        existing.completed_at = payload.get("completed_at") or existing.completed_at
        existing.updated_at = utc_now_iso()
        self._save()
        return existing

    def list_missions(self) -> list[MissionRecord]:
        return [self._missions[key] for key in sorted(self._missions)]

    def get_mission(self, mission_id: str) -> MissionRecord:
        if mission_id not in self._missions:
            raise KeyError(mission_id)
        return self._missions[mission_id]

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
            mission.append_timeline_event(event)
        except Exception as e:
            logging.getLogger(__name__).debug(f"Failed to append timeline event: {e}")
