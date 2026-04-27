from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .config import utc_now_iso


@dataclass
class ChildAgentRecord:
    agent_id: str
    role: str
    endpoint: Optional[str] = None
    command_endpoint: Optional[str] = None
    capabilities: List[str] = field(default_factory=list)
    transport: str = "a2a"
    status: str = "unknown"
    last_seen_at: Optional[str] = None
    notes: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MissionRecord:
    mission_id: str
    title: str
    objective: str
    scope: Optional[str] = None
    priority: str = "normal"
    status: str = "planned"
    assigned_targets: List[dict[str, Any]] = field(default_factory=list)
    task_id: Optional[str] = None
    conversation_id: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    route_hint: Optional[dict[str, Any]] = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    notes: Optional[str] = None

    def touch(self, status: Optional[str] = None) -> None:
        self.updated_at = utc_now_iso()
        if status:
            self.status = status

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MessageRecord:
    message_id: str
    message_type: str
    from_agent_id: str
    to_agent_id: str
    task_id: Optional[str] = None
    conversation_id: Optional[str] = None
    role: Optional[str] = None
    scope: Optional[str] = None
    priority: str = "normal"
    ttl: int = 60
    payload: dict[str, Any] = field(default_factory=dict)
    route_hint: Optional[dict[str, Any]] = None
    received_at: Optional[str] = None
    routed_via: Optional[str] = None
    status: str = "received"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TaskArtifactRecord:
    name: str
    parts: List[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "parts": list(self.parts)}


@dataclass
class TaskRecord:
    id: str
    state: str = "submitted"
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    artifacts: List[TaskArtifactRecord] = field(default_factory=list)
    history: List[dict[str, Any]] = field(default_factory=list)
    message: Optional[dict[str, Any]] = None
    result: Optional[dict[str, Any]] = None

    def touch(self, state: Optional[str] = None) -> None:
        self.updated_at = utc_now_iso()
        if state:
            self.state = state

    def add_artifact(self, name: str, payload: dict[str, Any]) -> None:
        self.artifacts.append(TaskArtifactRecord(name=name, parts=[{"type": "data", "data": payload}]))
        self.updated_at = utc_now_iso()

    def to_dict(self, include_artifacts: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "status": {"state": self.state},
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "history": list(self.history),
        }
        if self.message is not None:
            data["message"] = self.message
        if self.result is not None:
            data["result"] = self.result
        if include_artifacts:
            data["artifacts"] = [artifact.to_dict() for artifact in self.artifacts]
        return data


@dataclass
class SystemEventRecord:
    event_id: str
    event_type: str
    source_id: str
    source_role: str
    severity: str = "info"
    summary: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    flow_id: Optional[str] = None
    causation_id: Optional[str] = None
    decision_strategy: str = "rule"
    recommended_action: Optional[str] = None
    target_agent_id: Optional[str] = None
    route_mode: Optional[str] = None
    user_approval_required: bool = False
    status: str = "new"
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    notes: Optional[str] = None

    def touch(self, status: Optional[str] = None) -> None:
        self.updated_at = utc_now_iso()
        if status:
            self.status = status

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SystemAlertRecord:
    alert_id: str
    event_id: str
    alert_type: str
    severity: str
    message: str
    status: str = "waiting"
    recommended_action: Optional[str] = None
    target_agent_id: Optional[str] = None
    requires_user_approval: bool = False
    auto_remediated: bool = False
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def touch(self, status: Optional[str] = None) -> None:
        self.updated_at = utc_now_iso()
        if status:
            self.status = status

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SystemResponseRecord:
    response_id: str
    alert_id: str
    action: str
    target_agent_id: Optional[str] = None
    target_endpoint: Optional[str] = None
    route_mode: str = "direct"
    status: str = "planned"
    reason: str = ""
    task_id: Optional[str] = None
    dispatch_result: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    notes: Optional[str] = None

    def touch(self, status: Optional[str] = None) -> None:
        self.updated_at = utc_now_iso()
        if status:
            self.status = status

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ControlCenterState:
    agent_id: str
    role: str
    parent_id: str
    parent_endpoint: str
    direct_route_allowed: bool
    mission_prefix: str
    connected: bool = True
    connected_at: str = field(default_factory=utc_now_iso)
    last_seen_at: str = field(default_factory=utc_now_iso)
    agent_manifest: Dict[str, Any] = field(default_factory=dict)
    children: List[ChildAgentRecord] = field(default_factory=list)
    missions: List[MissionRecord] = field(default_factory=list)
    inbox: List[MessageRecord] = field(default_factory=list)
    outbox: List[MessageRecord] = field(default_factory=list)
    dispatches: List[dict[str, Any]] = field(default_factory=list)
    tasks: List[TaskRecord] = field(default_factory=list)
    events: List[SystemEventRecord] = field(default_factory=list)
    alerts: List[SystemAlertRecord] = field(default_factory=list)
    responses: List[SystemResponseRecord] = field(default_factory=list)
    registry_snapshot: Dict[str, Any] = field(default_factory=dict)
    memory: List[dict[str, Any]] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)

    def remember(self, item: dict[str, Any]) -> None:
        self.memory.append(item)
        self.memory = self.memory[-100:]

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "role": self.role,
            "parent_id": self.parent_id,
            "parent_endpoint": self.parent_endpoint,
            "direct_route_allowed": self.direct_route_allowed,
            "mission_prefix": self.mission_prefix,
            "connected": self.connected,
            "connected_at": self.connected_at,
            "last_seen_at": self.last_seen_at,
            "agent_manifest": self.agent_manifest,
            "children": [item.to_dict() for item in self.children],
            "missions": [item.to_dict() for item in self.missions[-50:]],
            "inbox": [item.to_dict() for item in self.inbox[-50:]],
            "outbox": [item.to_dict() for item in self.outbox[-50:]],
            "dispatches": list(self.dispatches[-50:]),
            "tasks": [item.to_dict() for item in self.tasks[-50:]],
            "events": [item.to_dict() for item in self.events[-100:]],
            "alerts": [item.to_dict() for item in self.alerts[-100:]],
            "responses": [item.to_dict() for item in self.responses[-100:]],
            "registry_snapshot": self.registry_snapshot,
            "memory": list(self.memory[-25:]),
            "context": self.context,
        }


class ChildAgentInput(BaseModel):
    agent_id: str
    role: str
    endpoint: Optional[str] = None
    command_endpoint: Optional[str] = None
    mode: str = "dynamic"
    skills: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    available_actions: List[str] = Field(default_factory=list)
    supported_inputs: List[str] = Field(default_factory=list)
    supported_outputs: List[str] = Field(default_factory=list)
    capabilities: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class AgentManifestInput(BaseModel):
    agent_id: str
    role: str
    endpoint: Optional[str] = None
    command_endpoint: Optional[str] = None
    mode: str = "dynamic"
    skills: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    available_actions: List[str] = Field(default_factory=list)
    supported_inputs: List[str] = Field(default_factory=list)
    supported_outputs: List[str] = Field(default_factory=list)
    capabilities: List[str] = Field(default_factory=list)
    parent_id: Optional[str] = None
    parent_endpoint: Optional[str] = None
    notes: Optional[str] = None


class MissionInput(BaseModel):
    mission_id: Optional[str] = None
    title: str
    objective: str
    scope: Optional[str] = None
    priority: str = "normal"
    task_id: Optional[str] = None
    conversation_id: Optional[str] = None
    assigned_targets: List[dict[str, Any]] = Field(default_factory=list)
    payload: Dict[str, Any] = Field(default_factory=dict)
    route_hint: Optional[dict[str, Any]] = None
    auto_dispatch: bool = True
    notes: Optional[str] = None


class A2AMessageInput(BaseModel):
    message_type: str
    message_id: Optional[str] = None
    conversation_id: Optional[str] = None
    task_id: Optional[str] = None
    from_agent_id: str
    to_agent_id: str
    role: Optional[str] = None
    scope: Optional[str] = None
    priority: str = "normal"
    ttl: int = 60
    payload: Dict[str, Any] = Field(default_factory=dict)
    route_hint: Optional[dict[str, Any]] = None


class DispatchInput(BaseModel):
    target_agent_id: str
    target_endpoint: Optional[str] = None
    transport: str = "a2a"
    message: A2AMessageInput


class A2APartInput(BaseModel):
    type: str
    text: Optional[str] = None
    data: Optional[dict[str, Any]] = None
    mime_type: Optional[str] = Field(default=None, alias="mimeType")


class A2AMessageEnvelopeInput(BaseModel):
    role: str
    parts: List[A2APartInput]


class SendMessageRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    message: A2AMessageEnvelopeInput
    task_id: Optional[str] = Field(default=None, alias="taskId")
    context_id: Optional[str] = Field(default=None, alias="contextId")


class SystemEventInput(BaseModel):
    event_type: str
    source_id: str
    source_role: str = "unknown"
    severity: str = "info"
    summary: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    flow_id: Optional[str] = None
    causation_id: Optional[str] = None
    target_agent_id: Optional[str] = None
    target_role: Optional[str] = None
    requires_user_approval: bool = False
    auto_response: Optional[bool] = None


class ResponseApprovalInput(BaseModel):
    approved: bool = True
    notes: Optional[str] = None
