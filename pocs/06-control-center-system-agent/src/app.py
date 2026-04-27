from __future__ import annotations

# ────────────────────────────────────────────────────────────────────────────
# 표준 라이브러리 및 서드파티 의존성
# ────────────────────────────────────────────────────────────────────────────
import asyncio
import argparse
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx                        # 비동기 HTTP 클라이언트 (하위 에이전트 dispatch용)
import uvicorn
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from .core.analysis import analyze_event as core_analyze_event
from .core.analysis import build_event_record as core_build_event_record
from .core.analysis import llm_analyze_event as core_llm_analyze_event
from .core.analysis import llm_enabled as core_llm_enabled
from .core.analysis import rule_analyze_event as core_rule_analyze_event
from .core.alerts import acknowledge_alert as core_acknowledge_alert
from .core.alerts import get_alert as core_get_alert
from .core.alerts import record_alert as core_record_alert
from .core.alerts import record_event as core_record_event
from .core.responses import record_response as core_record_response
from .core.routing import build_message_record as core_build_message_record
from .events.ingest import ingest_system_event as core_ingest_system_event
from .registry.child_registry import child_manifest as core_child_manifest
from .registry.child_registry import heartbeat_child as core_heartbeat_child
from .registry.child_registry import register_child as core_register_child
from .registry.child_registry import sync_children_from_registry as core_sync_children_from_registry
from .registry.manifest import build_agent_card as core_build_agent_card
from .registry.manifest import build_agent_manifest as core_build_agent_manifest
from .transport.http import acknowledge_alert as remote_acknowledge_alert


# ────────────────────────────────────────────────────────────────────────────
# 설정 기본값
# config.json 파일과 환경변수(COWATER_CONTROL_CENTER_CONFIG_PATH)로 덮어쓸 수 있다.
# ────────────────────────────────────────────────────────────────────────────
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.json"
CONFIG_PATH = Path(os.getenv("COWATER_CONTROL_CENTER_CONFIG_PATH", str(DEFAULT_CONFIG_PATH)))
DEFAULT_SERVER_HOST = "127.0.0.1"
DEFAULT_SERVER_PORT = 9012
DEFAULT_AGENT_ID = "system_center-01"
DEFAULT_AGENT_ROLE = "system_center"
DEFAULT_PARENT_ID = ""              # 최상위 에이전트이므로 부모가 없다
DEFAULT_PARENT_ENDPOINT = ""
DEFAULT_CORS_ORIGINS = ["*"]
DEFAULT_MISSION_PREFIX = "mission"  # 미션 ID 자동 생성 시 사용할 접두어
DEFAULT_A2A_BINDING = "HTTP+JSON"   # A2A 프로토콜 바인딩 방식
DEFAULT_DEVICE_REGISTRY_URL = "http://127.0.0.1:8003"
DEFAULT_CONTROL_SHIP_ROLE = "regional_orchestrator"
DEFAULT_DIRECT_DEVICE_ROLES = ["usv", "auv", "rov"]
DEFAULT_AUTO_SYNC_ON_START = True
DEFAULT_SYNC_INTERVAL_SECONDS = 30
DEFAULT_AUTO_RESPONSE = True
DEFAULT_APPROVAL_REQUIRED_ACTIONS = ["mission.abort", "system.shutdown", "task.cancel"]
DEFAULT_LLM_PROVIDER = "ollama"
DEFAULT_LLM_MODEL = "gemma4"
DEFAULT_LLM_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_LLM_TEMPERATURE = 0.2
DEFAULT_ALWAYS_ALERT = True
DEFAULT_NOTIFICATION_RETAIN = 100


def utc_now_iso() -> str:
    """현재 시각을 UTC ISO 8601 문자열로 반환한다."""
    return datetime.now(timezone.utc).isoformat()


# ────────────────────────────────────────────────────────────────────────────
# 설정 파일 로딩
# ────────────────────────────────────────────────────────────────────────────

def _load_json_file(path: Path) -> dict[str, Any]:
    """JSON 설정 파일을 읽어 dict로 반환한다. 파일이 없으면 빈 dict를 반환한다."""
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_runtime_config(config_path: Path) -> dict[str, Any]:
    """
    config.json을 읽어 런타임 설정 dict를 구성한다.
    누락된 키는 DEFAULT_* 상수로 채운다.
    """
    raw = _load_json_file(config_path)
    server_cfg = raw.get("server") or {}
    agent_cfg = raw.get("agent") or {}
    registry_cfg = raw.get("registry") or {}
    analysis_cfg = raw.get("analysis") or {}
    llm_cfg = analysis_cfg.get("llm") or {}
    notifications_cfg = raw.get("notifications") or {}
    cors_cfg = raw.get("cors") or {}

    host = str(server_cfg.get("host") or DEFAULT_SERVER_HOST)
    port = int(server_cfg.get("port") or DEFAULT_SERVER_PORT)
    cors_origins = cors_cfg.get("allow_origins") or DEFAULT_CORS_ORIGINS
    if isinstance(cors_origins, str):
        cors_origins = [origin.strip() for origin in cors_origins.split(",") if origin.strip()]
    if not isinstance(cors_origins, list) or not cors_origins:
        cors_origins = list(DEFAULT_CORS_ORIGINS)

    return {
        "config_path": str(config_path),
        "server": {"host": host, "port": port},
        "cors": {"allow_origins": cors_origins},
        "agent": {
            "id": str(agent_cfg.get("id") or DEFAULT_AGENT_ID),
            "role": str(agent_cfg.get("role") or DEFAULT_AGENT_ROLE),
            "parent_id": str(agent_cfg.get("parent_id") or DEFAULT_PARENT_ID),
            "parent_endpoint": str(agent_cfg.get("parent_endpoint") or DEFAULT_PARENT_ENDPOINT).rstrip("/"),
            "direct_route_allowed": bool(agent_cfg.get("direct_route_allowed", True)),
            "mission_prefix": str(agent_cfg.get("mission_prefix") or DEFAULT_MISSION_PREFIX),
        },
        "registry": {
            "device_registry_url": str(registry_cfg.get("device_registry_url") or DEFAULT_DEVICE_REGISTRY_URL).rstrip("/"),
            "control_ship_role": str(registry_cfg.get("control_ship_role") or DEFAULT_CONTROL_SHIP_ROLE),
            "direct_device_roles": list(registry_cfg.get("direct_device_roles") or DEFAULT_DIRECT_DEVICE_ROLES),
            "auto_sync_on_start": bool(registry_cfg.get("auto_sync_on_start", DEFAULT_AUTO_SYNC_ON_START)),
            "sync_interval_seconds": int(registry_cfg.get("sync_interval_seconds") or DEFAULT_SYNC_INTERVAL_SECONDS),
        },
        "analysis": {
            "auto_response": bool(analysis_cfg.get("auto_response", DEFAULT_AUTO_RESPONSE)),
            "approval_required_actions": list(
                analysis_cfg.get("approval_required_actions") or DEFAULT_APPROVAL_REQUIRED_ACTIONS
            ),
            "llm": {
                "provider": str(llm_cfg.get("provider") or DEFAULT_LLM_PROVIDER).strip(),
                "model": str(llm_cfg.get("model") or DEFAULT_LLM_MODEL).strip(),
                "base_url": str(llm_cfg.get("base_url") or DEFAULT_LLM_BASE_URL).rstrip("/"),
                "temperature": float(llm_cfg.get("temperature") or DEFAULT_LLM_TEMPERATURE),
            },
        },
        "notifications": {
            "retain": int(notifications_cfg.get("retain") or DEFAULT_NOTIFICATION_RETAIN),
            "always_alert": bool(notifications_cfg.get("always_alert", DEFAULT_ALWAYS_ALERT)),
        },
    }


# ────────────────────────────────────────────────────────────────────────────
# 도메인 데이터 클래스
# 모든 상태는 인메모리로 관리된다 (PoC 수준; 영속화 불필요).
# ────────────────────────────────────────────────────────────────────────────

@dataclass
class ChildAgentRecord:
    """
    하위 에이전트(regional_orchestrator 등) 한 개의 등록 정보.
    system_center가 미션을 위임할 수 있는 대상 목록을 구성한다.
    """
    agent_id: str
    role: str
    endpoint: Optional[str] = None           # 하위 에이전트의 HTTP 엔드포인트
    command_endpoint: Optional[str] = None    # 디바이스 명령용 HTTP 엔드포인트
    capabilities: List[str] = field(default_factory=list)  # 수행 가능한 액션 목록
    transport: str = "a2a"                   # a2a / command
    status: str = "unknown"                  # 연결 상태: unknown / registered / online
    last_seen_at: Optional[str] = None
    notes: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MissionRecord:
    """
    최상위 미션(임무) 한 건의 기록.
    system_center가 생성하고, regional_orchestrator 또는 하위 에이전트에게 할당한다.
    """
    mission_id: str
    title: str
    objective: str                           # 미션 목표 서술
    scope: Optional[str] = None             # 미션 범위 (예: "zone-A")
    priority: str = "normal"
    status: str = "planned"                 # planned → assigned → completed / failed
    assigned_targets: List[dict[str, Any]] = field(default_factory=list)  # 할당 대상 에이전트 목록
    task_id: Optional[str] = None           # 연관 A2A Task ID
    conversation_id: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    route_hint: Optional[dict[str, Any]] = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    notes: Optional[str] = None

    def touch(self, status: Optional[str] = None) -> None:
        """updated_at을 갱신하고, status가 주어지면 함께 변경한다."""
        self.updated_at = utc_now_iso()
        if status:
            self.status = status

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MessageRecord:
    """
    수신·발신 A2A 메시지 한 건의 기록.
    inbox / outbox / dispatches 로그에 저장되어 감사 추적(audit trail)을 제공한다.
    """
    message_id: str           # uuid4 기반 고유 ID
    message_type: str         # task.assign / task.accept / status.report 등
    from_agent_id: str
    to_agent_id: str
    task_id: Optional[str] = None
    conversation_id: Optional[str] = None
    role: Optional[str] = None
    scope: Optional[str] = None
    priority: str = "normal"
    ttl: int = 60             # 메시지 유효 시간(초)
    payload: dict[str, Any] = field(default_factory=dict)
    route_hint: Optional[dict[str, Any]] = None
    received_at: Optional[str] = None
    routed_via: Optional[str] = None        # 라우팅 경로 추적용
    status: str = "received"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TaskArtifactRecord:
    """
    Task 처리 결과로 생성된 아티팩트 한 건.
    A2A 표준의 Task.artifacts 필드에 대응한다.
    """
    name: str
    parts: List[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "parts": list(self.parts)}


@dataclass
class TaskRecord:
    """
    A2A 표준 Task 객체.
    /message:send 수신 시 생성되며, 처리 결과(artifacts)와 상태 변천을 기록한다.

    상태 값: submitted → working → completed / failed / canceled
    """
    id: str
    state: str = "submitted"
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    artifacts: List[TaskArtifactRecord] = field(default_factory=list)
    history: List[dict[str, Any]] = field(default_factory=list)
    message: Optional[dict[str, Any]] = None   # 원본 요청 메시지
    result: Optional[dict[str, Any]] = None    # 최종 처리 결과

    def touch(self, state: Optional[str] = None) -> None:
        """updated_at을 갱신하고, state가 주어지면 함께 변경한다."""
        self.updated_at = utc_now_iso()
        if state:
            self.state = state

    def add_artifact(self, name: str, payload: dict[str, Any]) -> None:
        """처리 결과 아티팩트를 추가한다."""
        self.artifacts.append(TaskArtifactRecord(name=name, parts=[{"type": "data", "data": payload}]))
        self.updated_at = utc_now_iso()

    def to_dict(self, include_artifacts: bool = True) -> dict[str, Any]:
        """A2A 표준 Task 응답 형식으로 직렬화한다."""
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
    """
    시스템 단에서 수집한 실시간 이벤트 한 건.
    03/04/05/02 및 사용자 입력을 모두 같은 형태로 정규화한다.
    """
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
        """updated_at을 갱신하고, 필요하면 상태를 함께 바꾼다."""
        self.updated_at = utc_now_iso()
        if status:
            self.status = status

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SystemAlertRecord:
    """
    이벤트 분석 결과로 생성되는 알림 한 건.
    사람 승인 필요 여부와 자동 대응 가능 여부를 함께 기록한다.
    """
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
        """updated_at을 갱신하고, 필요하면 상태를 함께 바꾼다."""
        self.updated_at = utc_now_iso()
        if status:
            self.status = status

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SystemResponseRecord:
    """
    알림에 대한 대응 기록.
    자동 대응, 사용자 승인 대기, 디스패치 결과를 모두 담는다.
    """
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
        """updated_at을 갱신하고, 필요하면 상태를 함께 바꾼다."""
        self.updated_at = utc_now_iso()
        if status:
            self.status = status

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ControlCenterState:
    """
    system_center/system agent의 전체 런타임 상태.
    ControlCenterHub 내부에서 단일 인스턴스로 관리된다.
    """
    agent_id: str
    role: str
    parent_id: str                          # 상위 에이전트 ID (최상위이면 빈 문자열)
    parent_endpoint: str                    # 상위 에이전트 HTTP 주소 (최상위이면 빈 문자열)
    direct_route_allowed: bool              # 하위 에이전트에 직접 dispatch 허용 여부
    mission_prefix: str                     # 미션 ID 자동 생성 시 접두어
    connected: bool = True
    connected_at: str = field(default_factory=utc_now_iso)
    last_seen_at: str = field(default_factory=utc_now_iso)
    agent_manifest: Dict[str, Any] = field(default_factory=dict)  # 자신의 능력 명세
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
    memory: List[dict[str, Any]] = field(default_factory=list)    # 최근 100건 이벤트 로그
    context: Dict[str, Any] = field(default_factory=dict)

    def remember(self, item: dict[str, Any]) -> None:
        """이벤트 로그를 기록한다. 최대 100건만 유지한다."""
        self.memory.append(item)
        self.memory = self.memory[-100:]

    def to_dict(self) -> dict[str, Any]:
        """API 응답용으로 직렬화한다. inbox/outbox 등은 최근 50건만 포함한다."""
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


# ────────────────────────────────────────────────────────────────────────────
# Pydantic 입력 모델 (API 요청 검증)
# ────────────────────────────────────────────────────────────────────────────

class ChildAgentInput(BaseModel):
    """하위 에이전트 등록 요청 바디. /children/register 에서 사용한다."""
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
    capabilities: List[str] = Field(default_factory=list)  # available_actions 의 대체 필드
    notes: Optional[str] = None


class AgentManifestInput(BaseModel):
    """
    에이전트 매니페스트 등록 요청 바디. /agents/register 에서 사용한다.
    ChildAgentInput과 동일한 구조이며, parent 정보를 추가로 포함한다.
    """
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
    """POST /missions 요청 바디. 미션 생성에 필요한 정보를 담는다."""
    mission_id: Optional[str] = None           # 미지정 시 자동 생성
    title: str
    objective: str                             # 미션 목표 서술
    scope: Optional[str] = None
    priority: str = "normal"
    task_id: Optional[str] = None
    conversation_id: Optional[str] = None
    assigned_targets: List[dict[str, Any]] = Field(default_factory=list)  # 할당 대상 목록
    payload: Dict[str, Any] = Field(default_factory=dict)
    route_hint: Optional[dict[str, Any]] = None
    auto_dispatch: bool = True                 # True이면 생성 즉시 대상 에이전트에게 dispatch
    notes: Optional[str] = None


class A2AMessageInput(BaseModel):
    """
    내부 A2A 메시지 구조체.
    ingest_message() 직접 호출 시 사용한다.
    """
    message_type: str        # task.assign / status.report / task.complete / task.fail 등
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
    """수동 dispatch 요청 바디. /dispatch 에서 사용한다."""
    target_agent_id: str
    target_endpoint: Optional[str] = None  # 미지정 시 하위 에이전트 레지스트리에서 조회
    transport: str = "a2a"
    message: A2AMessageInput


class A2APartInput(BaseModel):
    """A2A 메시지의 parts 배열 한 요소. type은 'text' 또는 'data'."""
    type: str
    text: Optional[str] = None
    data: Optional[dict[str, Any]] = None
    mime_type: Optional[str] = Field(default=None, alias="mimeType")


class A2AMessageEnvelopeInput(BaseModel):
    """A2A 표준 메시지 래퍼. role과 parts 배열로 구성된다."""
    role: str    # 발신자 역할 (예: "agent", "user")
    parts: List[A2APartInput]


class SendMessageRequest(BaseModel):
    """
    POST /message:send 의 요청 바디.
    A2A 표준 send message 바인딩에 대응한다.
    taskId / contextId는 camelCase alias를 통해 수신한다.
    """
    model_config = ConfigDict(populate_by_name=True)

    message: A2AMessageEnvelopeInput
    task_id: Optional[str] = Field(default=None, alias="taskId")
    context_id: Optional[str] = Field(default=None, alias="contextId")


class SystemEventInput(BaseModel):
    """
    03/04/05/02 또는 사용자 입력에서 들어오는 시스템 이벤트 바디.
    event.report / system.event / user.command 형태 모두 이 모델로 수렴시킨다.
    """
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
    """사용자 승인 후 알림 대응을 진행할 때 사용하는 바디."""
    approved: bool = True
    notes: Optional[str] = None


# ────────────────────────────────────────────────────────────────────────────
# SystemCenterHub — system_center 에이전트의 핵심 비즈니스 로직
# ────────────────────────────────────────────────────────────────────────────

class ControlCenterHub:
    """
    system_center 에이전트의 중앙 허브. 플릿 전체의 최상위 조율자.

    역할:
    - 미션(Mission) 생성 및 하위 에이전트(regional_orchestrator 등)에게 할당
    - direct_route_allowed가 True이면 regional_orchestrator를 거치지 않고 디바이스 에이전트에 직접 dispatch
    - 하위 에이전트로부터 수신한 status.report를 미션 레코드에 반영
    - 하위 에이전트 등록·heartbeat 관리
    - A2A Task 생명주기(submitted→working→completed/failed) 추적
    """

    def __init__(self, settings: dict[str, Any]) -> None:
        agent = settings["agent"]
        self.settings = settings
        self.registry_settings = settings.get("registry") or {}
        self.analysis_settings = settings.get("analysis") or {}
        self.notification_settings = settings.get("notifications") or {}
        self.state = ControlCenterState(
            agent_id=agent["id"],
            role=agent["role"],
            parent_id=agent["parent_id"],
            parent_endpoint=agent["parent_endpoint"],
            direct_route_allowed=agent["direct_route_allowed"],
            mission_prefix=agent["mission_prefix"],
        )
        self._child_index: Dict[str, ChildAgentRecord] = {}     # agent_id → 레코드
        self._manual_child_ids: set[str] = set()
        self._registry_child_ids: set[str] = set()
        self._mission_index: Dict[str, MissionRecord] = {}       # mission_id → 레코드
        self._task_index: Dict[str, TaskRecord] = {}              # task_id → 레코드
        # 자신의 능력 명세를 초기화한다
        self.state.agent_manifest = self._build_agent_manifest()
        self.state.registry_snapshot = {
            "device_registry_url": self.registry_settings.get("device_registry_url"),
            "control_ship_role": self.registry_settings.get("control_ship_role"),
            "direct_device_roles": list(self.registry_settings.get("direct_device_roles") or []),
            "auto_sync_on_start": bool(self.registry_settings.get("auto_sync_on_start", True)),
            "sync_interval_seconds": int(self.registry_settings.get("sync_interval_seconds") or 30),
        }

    # ── 하위 에이전트 등록·heartbeat ───────────────────────────────────────

    def register_child(self, payload: ChildAgentInput) -> ChildAgentRecord:
        """
        하위 에이전트를 레지스트리에 등록(또는 갱신)한다.
        agent_manifest의 children 섹션도 함께 업데이트한다.
        """
        return core_register_child(self, payload)

    def _child_manifest(self, payload: ChildAgentInput | AgentManifestInput) -> dict[str, Any]:
        """
        등록 요청 바디로부터 하위 에이전트의 능력 명세(manifest) dict를 생성한다.
        미션 할당 시 대상 에이전트의 능력 확인에 사용한다.
        """
        return core_child_manifest(self, payload)

    def heartbeat_child(self, agent_id: str) -> ChildAgentRecord:
        """하위 에이전트의 생존 신호를 갱신하고 상태를 'online'으로 표시한다."""
        return core_heartbeat_child(self, agent_id)

    # ── 메시지 기록 헬퍼 ───────────────────────────────────────────────────

    def _record_message(self, payload: A2AMessageInput, routed_via: Optional[str] = None, status_text: str = "received") -> MessageRecord:
        """
        A2AMessageInput을 MessageRecord로 변환한다.
        message_id가 없으면 uuid4를 자동 생성한다.
        """
        return core_build_message_record(self, payload, routed_via=routed_via, status_text=status_text)

    # ── Agent Card / Manifest 빌더 ─────────────────────────────────────────

    def _build_agent_manifest(self) -> dict[str, Any]:
        """
        내부 능력 명세(manifest)를 구성한다.
        하위 에이전트가 이 에이전트를 상위로 등록할 때 참조한다.

        capabilities 키는 A2A Agent Card와 동일하게 camelCase를 사용한다.
        """
        return core_build_agent_manifest(self)

    def _build_agent_card(self) -> dict[str, Any]:
        """
        A2A 표준 Agent Card를 구성한다.
        /.well-known/agent-card.json 에서 반환한다.
        외부 에이전트가 이 에이전트의 능력을 discovery할 때 사용한다.
        """
        return core_build_agent_card(self)

    # ── Task 생명주기 관리 ─────────────────────────────────────────────────

    def _new_task(self, state: str = "submitted") -> TaskRecord:
        """새 Task를 생성하고 인덱스에 등록한다."""
        task = TaskRecord(id=f"task-{uuid4()}", state=state)
        self._task_index[task.id] = task
        self.state.tasks = list(self._task_index.values())
        return task

    def _get_task(self, task_id: str) -> TaskRecord:
        """task_id로 Task를 조회한다. 없으면 KeyError."""
        task = self._task_index.get(task_id)
        if task is None:
            raise KeyError(task_id)
        return task

    def _attach_task_artifacts(self, task: TaskRecord, result: dict[str, Any]) -> None:
        """
        ingest_message 처리 결과를 Task 아티팩트로 저장하고
        성공/실패에 따라 Task 상태를 completed 또는 failed로 전환한다.
        """
        task.result = result
        task.add_artifact("a2a_result", result)
        if result.get("outbox"):
            task.add_artifact("dispatches", {"dispatches": result["outbox"]})
        task.touch("completed" if result.get("status") != "failed" else "failed")

    # ── 메시지 파싱 헬퍼 ──────────────────────────────────────────────────

    def _extract_message_data(self, parts: List[A2APartInput]) -> dict[str, Any]:
        """
        A2A parts 배열에서 실제 데이터를 추출한다.
        type='data' 파트를 우선하고, 없으면 type='text' 파트를 사용한다.
        """
        for part in parts:
            if part.type == "data" and isinstance(part.data, dict):
                return part.data
        for part in parts:
            if part.type == "text" and part.text:
                return {"text": part.text}
        return {}

    # ── 미션 ID 생성 헬퍼 ─────────────────────────────────────────────────

    def _mission_id(self, requested: Optional[str] = None) -> str:
        """
        미션 ID를 반환한다.
        요청에 ID가 있으면 그대로 사용하고, 없으면 'mission-001' 형식으로 자동 생성한다.
        """
        if requested:
            return requested
        return f"{self.state.mission_prefix}-{len(self._mission_index) + 1:03d}"

    def _extract_targets(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """
        payload에서 dispatch 대상 에이전트 목록을 추출한다.
        'targets' 또는 'assigned_targets' 키를 순서대로 탐색한다.
        """
        targets = payload.get("targets")
        if isinstance(targets, list):
            return [target for target in targets if isinstance(target, dict)]
        assigned = payload.get("assigned_targets")
        if isinstance(assigned, list):
            return [target for target in assigned if isinstance(target, dict)]
        return []

    def _llm_enabled(self) -> bool:
        """LLM 설정이 실제로 채워져 있는지 확인한다."""
        return core_llm_enabled(self)

    def _find_child_by_role(self, role: str) -> Optional[ChildAgentRecord]:
        """등록된 하위 에이전트 중 role이 일치하는 첫 번째 항목을 찾는다."""
        for child in self._child_index.values():
            if child.role == role:
                return child
        return None

    def _find_child_by_agent_id(self, agent_id: str) -> Optional[ChildAgentRecord]:
        """등록된 하위 에이전트 중 agent_id가 일치하는 항목을 찾는다."""
        return self._child_index.get(agent_id)

    def _event_summary(self, payload: SystemEventInput) -> str:
        """이벤트의 사람이 읽을 수 있는 요약 문장을 만든다."""
        if payload.summary:
            return payload.summary.strip()
        return f"{payload.event_type} from {payload.source_id}"

    def _build_event_record(self, payload: SystemEventInput) -> SystemEventRecord:
        """입력 이벤트를 내부 정규화 레코드로 변환한다."""
        return core_build_event_record(self, payload)

    def _rule_analyze_event(self, event: SystemEventRecord) -> dict[str, Any]:
        """
        규칙 기반 분석을 수행한다.
        애매하지 않은 사건은 이 단계에서 바로 알림과 대응 권고를 생성한다.
        """
        return core_rule_analyze_event(self, event)

    async def _llm_analyze_event(self, event: SystemEventRecord) -> Optional[dict[str, Any]]:
        """
        Ollama 계열 LLM이 설정되어 있으면 보조 판단을 요청한다.
        실패하면 None을 반환하고 규칙 기반 판단으로 폴백한다.
        """
        return await core_llm_analyze_event(self, event)

    async def _analyze_event(self, event: SystemEventRecord) -> dict[str, Any]:
        """
        이벤트를 분석해 알림 및 대응 권고를 만든다.
        규칙이 먼저 적용되고, 애매한 경우 LLM 보조를 사용한다.
        """
        return await core_analyze_event(self, event)

    def _record_event(self, event: SystemEventRecord) -> SystemEventRecord:
        """이벤트를 상태에 저장하고 최신 흔적을 남긴다."""
        return core_record_event(self, event)

    def _record_alert(self, alert: SystemAlertRecord) -> SystemAlertRecord:
        """알림을 상태에 저장한다."""
        return core_record_alert(self, alert)

    def _record_response(self, response: SystemResponseRecord) -> SystemResponseRecord:
        """대응 결과를 상태에 저장한다."""
        return core_record_response(self, response)

    def _get_alert(self, alert_id: str) -> SystemAlertRecord:
        """alert_id로 알림을 찾는다. 없으면 KeyError."""
        return core_get_alert(self, alert_id)

    def acknowledge_alert(self, alert_id: str, approved: bool = True, notes: Optional[str] = None) -> SystemAlertRecord:
        """
        사용자 승인을 기록한다.
        승인된 알림은 status를 approved 또는 rejected로 전환한다.
        """
        return core_acknowledge_alert(self, alert_id, approved=approved, notes=notes)

    async def sync_children_from_registry(self) -> dict[str, Any]:
        """
        03 디바이스 등록 서버에서 현재 Agent 목록을 가져와 하위 에이전트 레지스트리를 갱신한다.
        regional_orchestrator가 없으면 direct route가 가능하도록 빈 목록도 허용한다.
        """
        return await core_sync_children_from_registry(self)

    # ── A2A 표준 메시지 처리 ──────────────────────────────────────────────

    async def send_message(self, request: SendMessageRequest) -> dict[str, Any]:
        """
        POST /message:send 핸들러의 비즈니스 로직.

        1. 새 Task를 생성하고 'working' 상태로 전환한다.
        2. 요청 envelope에서 내부 A2AMessageInput을 역직렬화한다.
        3. ingest_message()로 메시지를 처리한다.
        4. 처리 결과를 Task 아티팩트로 저장하고 반환한다.
        """
        task = self._new_task("working")
        task.message = request.message.model_dump(by_alias=True)
        data = self._extract_message_data(request.message.parts)
        payload = A2AMessageInput(
            message_type=str(data.get("message_type") or data.get("type") or "task.assign"),
            message_id=str(data.get("message_id") or task.id),
            conversation_id=str(data.get("conversation_id") or request.context_id or task.id),
            task_id=str(data.get("task_id") or request.task_id or task.id),
            from_agent_id=str(data.get("from_agent_id") or data.get("sender_id") or request.message.role or "a2a-client"),
            to_agent_id=self.state.agent_id,
            role=request.message.role,
            scope=data.get("scope"),
            priority=str(data.get("priority") or "normal"),
            ttl=int(data.get("ttl") or 60),
            payload=data,
            route_hint=data.get("route_hint") if isinstance(data.get("route_hint"), dict) else None,
        )
        result = await self.ingest_message(payload, routed_via="a2a/message:send")
        self._attach_task_artifacts(task, result)
        return {"task": task.to_dict()}

    def get_task(self, task_id: str) -> dict[str, Any]:
        """Task를 ID로 조회한다."""
        return {"task": self._get_task(task_id).to_dict()}

    def list_tasks(self, status_filter: Optional[str] = None) -> dict[str, Any]:
        """Task 목록을 반환한다. status_filter로 상태별 필터링이 가능하다."""
        tasks = list(self._task_index.values())
        if status_filter:
            tasks = [task for task in tasks if task.state == status_filter]
        return {"tasks": [task.to_dict(include_artifacts=False) for task in tasks], "nextPageToken": ""}

    def cancel_task(self, task_id: str) -> dict[str, Any]:
        """Task를 canceled 상태로 전환한다."""
        task = self._get_task(task_id)
        task.touch("canceled")
        task.add_artifact("task_canceled", {"task_id": task.id, "state": task.state})
        return {"task": task.to_dict()}

    # ── 미션 관리 ─────────────────────────────────────────────────────────

    async def create_mission(self, payload: MissionInput) -> dict[str, Any]:
        """
        새 미션을 생성하고, auto_dispatch가 True이면 즉시 대상 에이전트에게 dispatch한다.

        미션 생성 흐름:
        1. MissionRecord를 생성하고 _mission_index에 저장한다.
        2. auto_dispatch=True이면 assigned_targets 목록을 순회하며 task.assign을 발송한다.
        """
        mission = MissionRecord(
            mission_id=self._mission_id(payload.mission_id),
            title=payload.title,
            objective=payload.objective,
            scope=payload.scope,
            priority=payload.priority,
            status="planned",
            assigned_targets=list(payload.assigned_targets),
            task_id=payload.task_id,
            conversation_id=payload.conversation_id,
            payload=payload.payload,
            route_hint=payload.route_hint,
            notes=payload.notes,
        )
        self._mission_index[mission.mission_id] = mission
        self.state.missions = list(self._mission_index.values())
        self.state.remember({"kind": "mission.created", "at": utc_now_iso(), "mission": mission.to_dict()})
        result = {"mission": mission.to_dict(), "dispatched": []}
        if payload.auto_dispatch and mission.assigned_targets:
            result["dispatched"] = await self._dispatch_targets(mission, mission.assigned_targets)
        return result

    async def _dispatch_targets(self, mission: MissionRecord, targets: list[dict[str, Any]], source_message: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
        """
        미션의 대상 에이전트 목록에 task.assign 메시지를 순차 발송한다.
        direct_route_allowed 설정에 따라 라우팅 힌트를 포함한다.
        """
        dispatches: list[dict[str, Any]] = []
        for target in targets:
            target_id = str(target.get("agent_id") or target.get("id") or "")
            if not target_id:
                continue
            target_transport = str(target.get("transport") or ("command" if target.get("command_endpoint") else "a2a"))
            target_endpoint = target.get("command_endpoint") if target_transport == "command" else target.get("endpoint")
            message = A2AMessageInput(
                message_type="task.assign",
                message_id=str(uuid4()),
                conversation_id=mission.conversation_id,
                task_id=mission.task_id or mission.mission_id,
                from_agent_id=self.state.agent_id,
                to_agent_id=target_id,
                role=target.get("role"),
                scope=mission.scope,
                priority=mission.priority,
                payload={
                    "mission": mission.to_dict(),
                    "command": target.get("command") or target.get("action") or {},
                    "source": source_message or mission.to_dict(),
                },
                route_hint={"preferred_route": "direct" if self.state.direct_route_allowed else "parent"},
            )
            dispatch = await self._dispatch_message(
                message,
                target_id=target_id,
                target_endpoint=target_endpoint,
                transport=target_transport,
            )
            dispatches.append(dispatch)
        return dispatches

    async def ingest_message(self, payload: A2AMessageInput, routed_via: Optional[str] = None) -> dict[str, Any]:
        """
        수신된 A2A 메시지를 처리하는 핵심 메서드.

        처리 흐름:
        - task.assign  : payload에서 미션 정보를 추출하여 MissionRecord를 생성 또는 조회하고,
                         assigned_targets를 대상으로 dispatch한다. task.accept ACK를 생성한다.
        - status.report: 해당 미션의 상태를 업데이트하고 reports 배열에 추가한다.
        - task.complete : 미션을 completed 상태로 전환한다.
        - task.fail     : 미션을 failed 상태로 전환하고 실패 이유를 기록한다.

        처리 후 _report_upstream()으로 상위 에이전트(있으면)에 결과를 보고한다.
        """
        if payload.message_type in {"event.report", "system.event", "alert.report"}:
            event_payload = payload.payload if isinstance(payload.payload, dict) else {}
            event = SystemEventInput(
                event_type=str(event_payload.get("event_type") or payload.message_type),
                source_id=str(event_payload.get("source_id") or payload.from_agent_id),
                source_role=str(event_payload.get("source_role") or payload.role or "unknown"),
                severity=str(event_payload.get("severity") or "info"),
                summary=event_payload.get("summary"),
                payload=event_payload,
                flow_id=payload.conversation_id,
                causation_id=payload.message_id,
                target_agent_id=event_payload.get("target_agent_id"),
                target_role=event_payload.get("target_role"),
                requires_user_approval=bool(event_payload.get("requires_user_approval", False)),
                auto_response=event_payload.get("auto_response"),
            )
            return await self.ingest_system_event(event, routed_via=routed_via)

        record = self._record_message(payload, routed_via=routed_via)
        self.state.inbox.append(record)
        self.state.last_seen_at = utc_now_iso()
        self.state.remember({"kind": "a2a.inbox", "at": utc_now_iso(), "message": record.to_dict()})

        response_status = "accepted"
        out_messages: List[MessageRecord] = []
        mission_ref = payload.task_id or str(payload.payload.get("mission_id") or "")
        mission = self._mission_index.get(mission_ref) if mission_ref else None

        if payload.message_type == "task.assign":
            # payload 안의 mission 객체를 꺼내 MissionRecord를 생성한다.
            mission_payload = payload.payload.get("mission")
            if isinstance(mission_payload, dict):
                created = await self.create_mission(
                    MissionInput(
                        mission_id=str(mission_payload.get("mission_id") or payload.task_id or ""),
                        title=str(mission_payload.get("title") or payload.payload.get("title") or "Untitled mission"),
                        objective=str(mission_payload.get("objective") or payload.payload.get("objective") or "Coordinate child agents"),
                        scope=mission_payload.get("scope") or payload.scope,
                        priority=str(mission_payload.get("priority") or payload.priority),
                        task_id=payload.task_id,
                        conversation_id=payload.conversation_id,
                        assigned_targets=self._extract_targets(mission_payload) or self._extract_targets(payload.payload),
                        payload=mission_payload,
                        route_hint=payload.route_hint,
                        auto_dispatch=False,  # 아래에서 직접 dispatch하므로 여기서는 비활성
                    )
                )
                mission = self._mission_index.get(created["mission"]["mission_id"])

            # mission 객체가 없으면 payload에서 직접 MissionRecord를 생성한다.
            if mission is None:
                mission = MissionRecord(
                    mission_id=self._mission_id(payload.task_id or str(payload.payload.get("mission_id") or "")),
                    title=str(payload.payload.get("title") or "Assigned mission"),
                    objective=str(payload.payload.get("objective") or "Coordinate child agents"),
                    scope=payload.scope,
                    priority=payload.priority,
                    status="planned",
                    assigned_targets=self._extract_targets(payload.payload),
                    task_id=payload.task_id,
                    conversation_id=payload.conversation_id,
                    payload=dict(payload.payload),
                    route_hint=payload.route_hint,
                )
                self._mission_index[mission.mission_id] = mission
                self.state.missions = list(self._mission_index.values())

            # 대상 에이전트들에게 task.assign을 발송한다.
            if mission.assigned_targets:
                await self._dispatch_targets(mission, mission.assigned_targets, source_message=record.to_dict())

            # 발신자에게 수락 ACK를 생성한다.
            ack = MessageRecord(
                message_id=str(uuid4()),
                message_type="task.accept",
                from_agent_id=self.state.agent_id,
                to_agent_id=payload.from_agent_id,
                task_id=payload.task_id or mission.mission_id,
                conversation_id=payload.conversation_id,
                role=self.state.role,
                scope=payload.scope,
                priority=payload.priority,
                ttl=payload.ttl,
                payload={"accepted": True, "mission_id": mission.mission_id},
                received_at=utc_now_iso(),
                routed_via=self.state.agent_id,
                status="accepted",
            )
            out_messages.append(ack)
            mission.touch("assigned")

        elif payload.message_type == "status.report":
            # 하위 에이전트가 보낸 상태 보고를 미션에 반영한다.
            response_status = "reported"
            if mission is not None:
                mission.touch(str(payload.payload.get("status") or "reported"))
                mission.payload = dict(mission.payload)
                mission.payload.setdefault("reports", []).append(payload.payload)

        elif payload.message_type == "task.complete":
            response_status = "completed"
            if mission is not None:
                mission.touch("completed")

        elif payload.message_type == "task.fail":
            response_status = "failed"
            if mission is not None:
                mission.touch("failed")
                mission.notes = str(payload.payload.get("reason") or mission.notes or "")

        self.state.outbox.extend(out_messages)
        # 상위 에이전트가 있으면 처리 결과를 보고한다 (최상위이면 생략).
        await self._report_upstream(record, out_messages)
        return {
            "status": response_status,
            "agent": self.state.to_dict(),
            "accepted": record.to_dict(),
            "outbox": [msg.to_dict() for msg in out_messages],
        }

    async def _report_upstream(self, record: MessageRecord, out_messages: List[MessageRecord]) -> None:
        """
        상위 에이전트에 status.report 메시지를 발송한다.
        system_center는 최상위이므로 parent_endpoint가 보통 비어 있다.
        parent_endpoint가 설정된 경우에만 발송하며, 실패해도 예외를 전파하지 않는다.
        """
        if not self.state.parent_endpoint:
            return
        report = {
            "message_type": "status.report",
            "message_id": str(uuid4()),
            "conversation_id": record.conversation_id,
            "task_id": record.task_id,
            "from_agent_id": self.state.agent_id,
            "to_agent_id": self.state.parent_id,
            "role": self.state.role,
            "scope": record.scope,
            "priority": record.priority,
            "ttl": record.ttl,
            "payload": {
                "status": record.status,
                "accepted": record.message_type == "task.assign",
                "dispatches": [msg.to_dict() for msg in out_messages],
                "original": record.to_dict(),
            },
            "route_hint": {"preferred_route": "upstream"},
        }
        try:
            await _send_a2a_message(self.state.parent_endpoint, report)
            self.state.remember({"kind": "a2a.report", "at": utc_now_iso(), "target": self.state.parent_endpoint, "payload": report})
        except Exception as exc:
            self.state.remember({"kind": "a2a.report_failed", "at": utc_now_iso(), "error": str(exc)})

    async def _dispatch_command(self, payload: A2AMessageInput, target_id: str, command_endpoint: str) -> dict[str, Any]:
        """
        디바이스 agent의 command endpoint로 명령을 발송한다.
        command API는 A2A가 아니라 action/reason/priority/params 형태를 사용한다.
        """
        command = payload.payload.get("command") if isinstance(payload.payload, dict) else {}
        if not isinstance(command, dict):
            command = {}
        body = {
            "action": command.get("action") or payload.message_type,
            "reason": command.get("reason") or payload.payload.get("reason") or "system remediation",
            "priority": payload.priority,
            "params": command.get("params") or {
                "event": payload.payload.get("event"),
                "alert": payload.payload.get("alert"),
                "response": payload.payload.get("response"),
            },
        }
        await _post_json(command_endpoint, body)
        self.state.remember({"kind": "command.dispatch", "at": utc_now_iso(), "target": target_id, "status": "sent"})
        return {"status": "sent", "target_agent_id": target_id, "target_endpoint": command_endpoint, "body": body}

    async def _dispatch_message(self, payload: A2AMessageInput, target_id: str, target_endpoint: Optional[str] = None, transport: Optional[str] = None) -> dict[str, Any]:
        """
        단일 에이전트에게 A2A 메시지를 발송하는 내부 메서드.
        target_endpoint가 없으면 _child_index에서 조회한다.
        주소를 찾지 못하면 status를 'queued'로 표시한다.
        """
        record = self._record_message(payload, routed_via=self.state.agent_id, status_text="dispatching")
        self.state.dispatches.append(record.to_dict())
        child = self._child_index.get(target_id)
        transport_mode = transport or (child.transport if child else "a2a")
        if transport_mode == "command" and child and child.command_endpoint:
            await self._dispatch_command(payload, target_id, child.command_endpoint)
            record.status = "sent"
        else:
            target = target_endpoint or (child.endpoint if child else None)
            if target:
                await _send_a2a_message(target, payload.model_dump())
                record.status = "sent"
            else:
                record.status = "queued"
        self.state.outbox.append(record)
        self.state.remember({"kind": "dispatch", "at": utc_now_iso(), "target": target_id, "status": record.status})
        return record.to_dict()

    async def dispatch(self, payload: DispatchInput) -> dict[str, Any]:
        """수동 dispatch 요청을 처리한다. _dispatch_message()의 공개 래퍼."""
        return await self._dispatch_message(payload.message, payload.target_agent_id, payload.target_endpoint, transport=payload.transport)

    async def assign_mission(self, mission_id: str, targets: list[dict[str, Any]], auto_dispatch: bool = True) -> dict[str, Any]:
        """
        기존 미션에 대상 에이전트를 할당하고, auto_dispatch가 True이면 즉시 dispatch한다.
        미션이 없으면 KeyError.
        """
        mission = self._mission_index.get(mission_id)
        if mission is None:
            raise KeyError(mission_id)
        mission.assigned_targets = list(targets)
        mission.touch("assigned")
        self.state.missions = list(self._mission_index.values())
        dispatches: list[dict[str, Any]] = []
        if auto_dispatch and targets:
            dispatches = await self._dispatch_targets(mission, targets)
        self.state.remember({"kind": "mission.assigned", "at": utc_now_iso(), "mission_id": mission_id, "targets": targets})
        return {"mission": mission.to_dict(), "dispatched": dispatches}

    async def ingest_system_event(self, payload: SystemEventInput, routed_via: Optional[str] = None) -> dict[str, Any]:
        """
        시스템 이벤트를 수집하고 알림/대응을 생성한다.
        03/04/05/02 또는 사용자 입력에서 들어온 이벤트를 같은 흐름으로 처리한다.
        """
        event = self._build_event_record(payload)
        self._record_event(event)
        analysis = await self._analyze_event(event)
        event.decision_strategy = str(analysis.get("analysis_source") or event.decision_strategy)
        event.recommended_action = analysis.get("recommended_action")
        event.target_agent_id = analysis.get("target_agent_id") or event.target_agent_id
        event.route_mode = analysis.get("route_mode")
        event.user_approval_required = bool(analysis.get("requires_user_approval", event.user_approval_required))
        event.touch("analyzed")

        alert = SystemAlertRecord(
            alert_id=f"alert-{uuid4()}",
            event_id=event.event_id,
            alert_type=str(analysis.get("alert_type") or "system_event"),
            severity=str(analysis.get("severity") or event.severity),
            message=str(analysis.get("message") or event.summary),
            status="waiting" if event.user_approval_required else "planned",
            recommended_action=event.recommended_action,
            target_agent_id=event.target_agent_id,
            requires_user_approval=event.user_approval_required,
            auto_remediated=False,
            metadata={
                "flow_id": event.flow_id,
                "causation_id": event.causation_id,
                "source_role": event.source_role,
                "analysis_strategy": event.decision_strategy,
                "analysis": analysis,
                "routed_via": routed_via,
            },
        )
        self._record_alert(alert)

        response: Optional[SystemResponseRecord] = None
        auto_response_allowed = bool(self.analysis_settings.get("auto_response", True))
        if payload.auto_response is not None:
            auto_response_allowed = bool(payload.auto_response)
        if event.recommended_action and event.recommended_action != "alert_operator" and auto_response_allowed and not event.user_approval_required:
            target = self._find_child_by_agent_id(event.target_agent_id or "") if event.target_agent_id else None
            if target is None and analysis.get("target_role"):
                target = self._find_child_by_role(str(analysis.get("target_role")))
            if target is None:
                direct_roles = set(self.registry_settings.get("direct_device_roles") or [])
                if event.source_role in direct_roles:
                    target = self._find_child_by_role(event.source_role)
                if target is None and analysis.get("target_role") in direct_roles:
                    target = self._find_child_by_role(str(analysis.get("target_role")))
            if target is None:
                control_ship_role = str(self.registry_settings.get("control_ship_role") or DEFAULT_CONTROL_SHIP_ROLE)
                target = self._find_child_by_role(control_ship_role)

            if target is not None:
                route_mode = "via_regional_orchestrator" if target.role == str(self.registry_settings.get("control_ship_role") or DEFAULT_CONTROL_SHIP_ROLE) else "direct"
                response = SystemResponseRecord(
                    response_id=f"response-{uuid4()}",
                    alert_id=alert.alert_id,
                    action=str(event.recommended_action),
                    target_agent_id=target.agent_id,
                    target_endpoint=target.endpoint,
                    route_mode=route_mode,
                    status="dispatching",
                    reason=str(analysis.get("llm_reason") or event.summary or "rule-based remediation"),
                    task_id=event.flow_id or event.event_id,
                    dispatch_result={},
                    notes="auto response" if auto_response_allowed else "manual response",
                )
                response = self._record_response(response)
                message = A2AMessageInput(
                    message_type="task.assign",
                    message_id=str(uuid4()),
                    conversation_id=event.flow_id,
                    task_id=response.task_id,
                    from_agent_id=self.state.agent_id,
                    to_agent_id=target.agent_id,
                    role=target.role,
                    scope=event.source_role,
                    priority="high" if event.severity in {"warning", "critical"} else "normal",
                    payload={
                        "event": event.to_dict(),
                        "alert": alert.to_dict(),
                        "response": response.to_dict(),
                        "command": {
                            "action": event.recommended_action,
                            "reason": response.reason,
                            "target_role": analysis.get("target_role") or target.role,
                        },
                    },
                    route_hint={"preferred_route": route_mode},
                )
                dispatch_result = await self._dispatch_message(message, target_id=target.agent_id, target_endpoint=target.endpoint)
                response.dispatch_result = dispatch_result
                response.touch("dispatched" if dispatch_result.get("status") == "sent" else "queued")
                alert.auto_remediated = dispatch_result.get("status") == "sent"
                alert.touch("in_progress" if alert.auto_remediated else "queued")
                event.touch("responding")
            else:
                event.touch("waiting_user")
        else:
            event.touch("waiting_user" if event.user_approval_required else "analyzed")
            if event.recommended_action == "alert_operator" or self.notification_settings.get("always_alert", True):
                alert.touch("waiting_user" if event.user_approval_required else "notified")

        self.state.registry_snapshot["last_event_at"] = utc_now_iso()
        self.state.context["last_event"] = event.to_dict()
        self.state.context["last_alert"] = alert.to_dict()
        if response is not None:
            self.state.context["last_response"] = response.to_dict()
        self.state.remember(
            {
                "kind": "system.ingested",
                "at": utc_now_iso(),
                "event": event.to_dict(),
                "alert": alert.to_dict(),
                "response": response.to_dict() if response else None,
            }
        )
        result: dict[str, Any] = {
            "event": event.to_dict(),
            "alert": alert.to_dict(),
            "response": response.to_dict() if response else None,
            "analysis": analysis,
            "agent": self.state.to_dict(),
        }
        return result

    def reset(self) -> None:
        """인메모리 상태를 초기화한다. 개발·테스트 전용."""
        self.state.children = []
        self.state.missions = []
        self.state.inbox = []
        self.state.outbox = []
        self.state.dispatches = []
        self.state.tasks = []
        self.state.events = []
        self.state.alerts = []
        self.state.responses = []
        self.state.registry_snapshot = {
            "device_registry_url": self.registry_settings.get("device_registry_url"),
            "control_ship_role": self.registry_settings.get("control_ship_role"),
            "direct_device_roles": list(self.registry_settings.get("direct_device_roles") or []),
            "auto_sync_on_start": bool(self.registry_settings.get("auto_sync_on_start", True)),
            "sync_interval_seconds": int(self.registry_settings.get("sync_interval_seconds") or 30),
        }
        self.state.memory = []
        self.state.context = {}
        self._child_index = {}
        self._manual_child_ids = set()
        self._registry_child_ids = set()
        self._mission_index = {}
        self._task_index = {}


# ────────────────────────────────────────────────────────────────────────────
# 비동기 HTTP 유틸리티
# A2A 메시지를 하위 에이전트로 dispatch할 때 사용한다.
# ────────────────────────────────────────────────────────────────────────────

async def _post_json(url: str, payload: dict[str, Any], timeout: float = 5.0) -> dict[str, Any]:
    """
    주어진 URL로 JSON POST 요청을 비동기로 발송한다.
    HTTP 오류는 RuntimeError로 변환하여 호출자가 처리할 수 있도록 한다.
    """
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            if not resp.content:
                return {}
            return resp.json()
    except httpx.HTTPStatusError as exc:
        detail = ""
        try:
            detail = exc.response.json().get("detail", "")
        except Exception:
            pass
        raise RuntimeError(detail or f"HTTP {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise RuntimeError(str(exc)) from exc


async def _send_a2a_message(url: str, payload: dict[str, Any], timeout: float = 5.0) -> dict[str, Any]:
    """
    A2A 표준 메시지 형식으로 래핑하여 POST /message:send 로 발송한다.
    payload는 parts[0].data 안에 포함된다.
    """
    body = {
        "message": {
            "role": "agent",
            "parts": [{"type": "data", "data": payload}],
        }
    }
    return await _post_json(f"{url.rstrip('/')}/message:send", body, timeout=timeout)


# ────────────────────────────────────────────────────────────────────────────
# 애플리케이션 초기화
# ────────────────────────────────────────────────────────────────────────────

APP_SETTINGS = load_runtime_config(CONFIG_PATH)
hub = ControlCenterHub(APP_SETTINGS)

app = FastAPI(title="CoWater System Center Agent", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=APP_SETTINGS["cors"]["allow_origins"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_registry_sync_task: Optional[asyncio.Task] = None


@app.on_event("startup")
async def startup_sync() -> None:
    """시작 시 03 등록 서버와 동기화해 최신 child manifest를 불러온다."""
    global _registry_sync_task
    registry_cfg = APP_SETTINGS.get("registry", {})
    if registry_cfg.get("auto_sync_on_start", True):
        try:
            await hub.sync_children_from_registry()
        except Exception:
            # 시작 실패가 전체 서버 실패로 이어지지 않도록 조용히 넘긴다.
            pass
    interval = int(registry_cfg.get("sync_interval_seconds") or 0)
    if interval > 0 and _registry_sync_task is None:
        async def _poll_registry() -> None:
            while True:
                try:
                    await asyncio.sleep(interval)
                    await hub.sync_children_from_registry()
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    hub.state.remember({"kind": "registry.poll_failed", "at": utc_now_iso(), "error": str(exc)})
        _registry_sync_task = asyncio.create_task(_poll_registry())


@app.on_event("shutdown")
async def shutdown_sync() -> None:
    """백그라운드 registry polling task를 종료한다."""
    global _registry_sync_task
    if _registry_sync_task is not None:
        _registry_sync_task.cancel()
        try:
            await _registry_sync_task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
        _registry_sync_task = None


# ────────────────────────────────────────────────────────────────────────────
# API 라우트
# ────────────────────────────────────────────────────────────────────────────

# ── 상태 확인 ──────────────────────────────────────────────────────────────

@app.get("/health")
def health() -> dict[str, str]:
    """서비스 생존 여부를 확인한다."""
    return {"status": "ok"}


# ── A2A Discovery ──────────────────────────────────────────────────────────

@app.get("/.well-known/agent-card.json")
def agent_card() -> dict[str, Any]:
    """A2A 표준 Agent Card를 반환한다. 외부 에이전트의 discovery 진입점."""
    return hub._build_agent_card()


@app.get("/.well-known/agent.json")
def agent_card_legacy() -> dict[str, Any]:
    """하위 호환용 alias. agent-card.json과 동일한 내용을 반환한다."""
    return hub._build_agent_card()


# ── 메타 정보 ──────────────────────────────────────────────────────────────

@app.get("/meta")
def meta() -> dict[str, Any]:
    """서버 설정, 지원 메시지 타입, A2A 엔드포인트 목록을 반환한다."""
    return {
        "server": APP_SETTINGS["server"],
        "agent": APP_SETTINGS["agent"],
        "registry": APP_SETTINGS.get("registry", {}),
        "analysis": {
            "auto_response": APP_SETTINGS.get("analysis", {}).get("auto_response", True),
            "llm_enabled": bool((APP_SETTINGS.get("analysis", {}).get("llm") or {}).get("provider") and (APP_SETTINGS.get("analysis", {}).get("llm") or {}).get("model")),
            "strategy": "hybrid" if bool((APP_SETTINGS.get("analysis", {}).get("llm") or {}).get("provider") and (APP_SETTINGS.get("analysis", {}).get("llm") or {}).get("model")) else "rule",
        },
        "notifications": APP_SETTINGS.get("notifications", {}),
        "config_path": APP_SETTINGS["config_path"],
        "cors": APP_SETTINGS["cors"],
        "a2a": {
            "agent_card": "/.well-known/agent-card.json",
            "send_message": "/message:send",
            "tasks": "/tasks",
        },
        "message_types": [
            "task.assign",
            "task.accept",
            "task.progress",
            "task.complete",
            "task.fail",
            "task.escalate",
            "status.report",
            "event.report",
            "system.event",
            "system.alert",
            "user.command",
        ],
    }


@app.get("/state")
def state() -> dict[str, Any]:
    """에이전트의 전체 런타임 상태(inbox·outbox·missions·memory 등)를 반환한다."""
    return hub.state.to_dict()


@app.get("/registry")
def registry() -> dict[str, Any]:
    """동기화된 child registry snapshot을 반환한다."""
    return hub.state.registry_snapshot


@app.get("/manifest")
def manifest() -> dict[str, Any]:
    """에이전트의 능력 명세(manifest)를 반환한다."""
    return hub.state.agent_manifest


# ── A2A 표준 메시지 수신 ───────────────────────────────────────────────────

@app.post("/message:send")
async def message_send(request: SendMessageRequest) -> dict[str, Any]:
    """
    A2A 표준 메시지 수신 엔드포인트.
    메시지를 처리하고 Task 응답을 반환한다.
    """
    return await hub.send_message(request)


# ── Task 관리 ──────────────────────────────────────────────────────────────

@app.get("/tasks")
def list_tasks(status: Optional[str] = None) -> dict[str, Any]:
    """Task 목록을 반환한다. ?status=working 등으로 필터링 가능하다."""
    return hub.list_tasks(status_filter=status)


@app.get("/tasks/{task_id}")
def get_task(task_id: str) -> dict[str, Any]:
    """특정 Task의 상세 정보를 반환한다."""
    try:
        return hub.get_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="task not found") from exc


@app.post("/tasks/{task_id}:cancel")
def cancel_task(task_id: str) -> dict[str, Any]:
    """Task를 canceled 상태로 전환한다."""
    try:
        return hub.cancel_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="task not found") from exc


# ── 하위 에이전트 관리 ─────────────────────────────────────────────────────

@app.get("/children")
def list_children() -> list[dict[str, Any]]:
    """등록된 하위 에이전트 목록을 반환한다."""
    return [child.to_dict() for child in hub.state.children]


@app.post("/children/register", status_code=status.HTTP_201_CREATED)
def register_child(request: ChildAgentInput) -> dict[str, Any]:
    """하위 에이전트를 등록한다."""
    return hub.register_child(request).to_dict()


@app.post("/agents/register", status_code=status.HTTP_201_CREATED)
def register_agent(request: AgentManifestInput) -> dict[str, Any]:
    """
    에이전트 매니페스트 방식 등록 엔드포인트.
    /children/register 와 동일한 처리를 수행한다.
    """
    return hub.register_child(request).to_dict()


@app.post("/children/{agent_id}/heartbeat")
def heartbeat_child(agent_id: str) -> dict[str, Any]:
    """하위 에이전트의 생존 신호를 갱신한다."""
    try:
        return hub.heartbeat_child(agent_id).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="child agent not found") from exc


# ── 시스템 이벤트 / 알림 / 대응 ───────────────────────────────────────────

@app.get("/events")
def list_events() -> list[dict[str, Any]]:
    """수집된 시스템 이벤트 목록을 반환한다."""
    return [event.to_dict() for event in hub.state.events]


@app.get("/alerts")
def list_alerts() -> list[dict[str, Any]]:
    """분석 결과로 생성된 알림 목록을 반환한다."""
    return [alert.to_dict() for alert in hub.state.alerts]


@app.get("/responses")
def list_responses() -> list[dict[str, Any]]:
    """알림에 대한 대응 기록을 반환한다."""
    return [response.to_dict() for response in hub.state.responses]


@app.post("/events/ingest", status_code=status.HTTP_201_CREATED)
async def ingest_event(request: SystemEventInput) -> dict[str, Any]:
    """외부 시스템에서 들어온 실시간 이벤트를 분석하고 필요한 대응을 생성한다."""
    return await hub.ingest_system_event(request)


@app.post("/events/ingest/a2a", status_code=status.HTTP_201_CREATED)
async def ingest_event_a2a(request: SendMessageRequest) -> dict[str, Any]:
    """
    A2A 메시지 형태로 들어오는 시스템 이벤트를 수신한다.
    message.parts 안의 data가 event payload 역할을 한다.
    """
    return await hub.send_message(request)


@app.post("/registry/sync")
async def sync_registry() -> dict[str, Any]:
    """03 디바이스 등록 서버와 동기화하여 최신 child manifest를 불러온다."""
    return await hub.sync_children_from_registry()


@app.post("/alerts/{alert_id}/ack")
async def acknowledge_alert(alert_id: str, request: ResponseApprovalInput) -> dict[str, Any]:
    """사용자 승인을 알림 상태에 기록한다."""
    try:
        alert = hub.acknowledge_alert(alert_id, approved=request.approved, notes=request.notes)
        store_url = str(APP_SETTINGS.get("notifications", {}).get("notification_store_url") or "").rstrip("/")
        if store_url:
            try:
                await remote_acknowledge_alert(store_url, alert_id, {"approved": request.approved, "notes": request.notes})
            except Exception as exc:
                hub.state.remember({"kind": "alert.store_ack_failed", "at": utc_now_iso(), "error": str(exc), "alert_id": alert_id})
        return alert.to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="alert not found") from exc


# ── 미션 관리 ──────────────────────────────────────────────────────────────

@app.get("/missions")
def list_missions() -> list[dict[str, Any]]:
    """전체 미션 목록을 반환한다."""
    return [mission.to_dict() for mission in hub.state.missions]


@app.post("/missions", status_code=status.HTTP_201_CREATED)
async def create_mission(request: MissionInput) -> dict[str, Any]:
    """
    새 미션을 생성한다.
    auto_dispatch=True(기본값)이면 생성 즉시 assigned_targets에게 task.assign을 발송한다.
    """
    return await hub.create_mission(request)


@app.post("/missions/{mission_id}/assign")
async def assign_mission(mission_id: str, request: dict[str, Any]) -> dict[str, Any]:
    """
    기존 미션에 대상 에이전트를 할당하고 dispatch한다.
    request body: { "targets": [...], "auto_dispatch": true }
    """
    targets = request.get("targets") if isinstance(request.get("targets"), list) else []
    auto_dispatch = bool(request.get("auto_dispatch", True))
    try:
        return await hub.assign_mission(
            mission_id,
            [target for target in targets if isinstance(target, dict)],
            auto_dispatch=auto_dispatch,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="mission not found") from exc


# ── 메시지 로그 조회 ───────────────────────────────────────────────────────

@app.get("/inbox")
def inbox() -> list[dict[str, Any]]:
    """수신된 메시지 전체 목록을 반환한다."""
    return [item.to_dict() for item in hub.state.inbox]


@app.get("/outbox")
def outbox() -> list[dict[str, Any]]:
    """발신된 메시지 전체 목록을 반환한다."""
    return [item.to_dict() for item in hub.state.outbox]


@app.get("/dispatches")
def dispatches() -> list[dict[str, Any]]:
    """하위 에이전트로 dispatch된 메시지 목록을 반환한다."""
    return list(hub.state.dispatches)


# ── 수동 Dispatch ──────────────────────────────────────────────────────────

@app.post("/dispatch")
async def dispatch(request: DispatchInput) -> dict[str, Any]:
    """
    특정 에이전트에게 수동으로 메시지를 dispatch한다.
    대상 에이전트에 연결 실패 시 502를 반환한다.
    """
    try:
        return await hub.dispatch(request)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ── 개발·테스트 유틸리티 ───────────────────────────────────────────────────

@app.post("/reset")
def reset() -> dict[str, str]:
    """인메모리 상태를 초기화한다. 개발·테스트 전용."""
    hub.reset()
    return {"status": "reset"}


# ────────────────────────────────────────────────────────────────────────────
# 진입점
# ────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", help="Override bind host from config/env")
    parser.add_argument("--port", type=int, help="Override bind port from config/env")
    args = parser.parse_args()
    uvicorn.run(
        "src.app:app",
        host=args.host or APP_SETTINGS["server"]["host"],
        port=args.port or APP_SETTINGS["server"]["port"],
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
