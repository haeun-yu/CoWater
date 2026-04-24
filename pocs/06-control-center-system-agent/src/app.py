from __future__ import annotations

# ────────────────────────────────────────────────────────────────────────────
# 표준 라이브러리 및 서드파티 의존성
# ────────────────────────────────────────────────────────────────────────────
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


# ────────────────────────────────────────────────────────────────────────────
# 설정 기본값
# config.json 파일과 환경변수(COWATER_CONTROL_CENTER_CONFIG_PATH)로 덮어쓸 수 있다.
# ────────────────────────────────────────────────────────────────────────────
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.json"
CONFIG_PATH = Path(os.getenv("COWATER_CONTROL_CENTER_CONFIG_PATH", str(DEFAULT_CONFIG_PATH)))
DEFAULT_SERVER_HOST = "127.0.0.1"
DEFAULT_SERVER_PORT = 9012
DEFAULT_AGENT_ID = "control_center-01"
DEFAULT_AGENT_ROLE = "control_center"
DEFAULT_PARENT_ID = ""              # 최상위 에이전트이므로 부모가 없다
DEFAULT_PARENT_ENDPOINT = ""
DEFAULT_CORS_ORIGINS = ["*"]
DEFAULT_MISSION_PREFIX = "mission"  # 미션 ID 자동 생성 시 사용할 접두어
DEFAULT_A2A_BINDING = "HTTP+JSON"   # A2A 프로토콜 바인딩 방식


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
    }


# ────────────────────────────────────────────────────────────────────────────
# 도메인 데이터 클래스
# 모든 상태는 인메모리로 관리된다 (PoC 수준; 영속화 불필요).
# ────────────────────────────────────────────────────────────────────────────

@dataclass
class ChildAgentRecord:
    """
    하위 에이전트(control_ship 등) 한 개의 등록 정보.
    control_center가 미션을 위임할 수 있는 대상 목록을 구성한다.
    """
    agent_id: str
    role: str
    endpoint: Optional[str] = None           # 하위 에이전트의 HTTP 엔드포인트
    capabilities: List[str] = field(default_factory=list)  # 수행 가능한 액션 목록
    status: str = "unknown"                  # 연결 상태: unknown / registered / online
    last_seen_at: Optional[str] = None
    notes: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MissionRecord:
    """
    최상위 미션(임무) 한 건의 기록.
    control_center가 생성하고, control_ship 또는 하위 에이전트에게 할당한다.
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
class ControlCenterState:
    """
    control_center 에이전트의 전체 런타임 상태.
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


# ────────────────────────────────────────────────────────────────────────────
# ControlCenterHub — control_center 에이전트의 핵심 비즈니스 로직
# ────────────────────────────────────────────────────────────────────────────

class ControlCenterHub:
    """
    control_center 에이전트의 중앙 허브. 플릿 전체의 최상위 조율자.

    역할:
    - 미션(Mission) 생성 및 하위 에이전트(control_ship 등)에게 할당
    - direct_route_allowed가 True이면 control_ship을 거치지 않고 디바이스 에이전트에 직접 dispatch
    - 하위 에이전트로부터 수신한 status.report를 미션 레코드에 반영
    - 하위 에이전트 등록·heartbeat 관리
    - A2A Task 생명주기(submitted→working→completed/failed) 추적
    """

    def __init__(self, settings: dict[str, Any]) -> None:
        agent = settings["agent"]
        self.settings = settings
        self.state = ControlCenterState(
            agent_id=agent["id"],
            role=agent["role"],
            parent_id=agent["parent_id"],
            parent_endpoint=agent["parent_endpoint"],
            direct_route_allowed=agent["direct_route_allowed"],
            mission_prefix=agent["mission_prefix"],
        )
        self._child_index: Dict[str, ChildAgentRecord] = {}     # agent_id → 레코드
        self._mission_index: Dict[str, MissionRecord] = {}       # mission_id → 레코드
        self._task_index: Dict[str, TaskRecord] = {}              # task_id → 레코드
        # 자신의 능력 명세를 초기화한다
        self.state.agent_manifest = self._build_agent_manifest()

    # ── 하위 에이전트 등록·heartbeat ───────────────────────────────────────

    def register_child(self, payload: ChildAgentInput) -> ChildAgentRecord:
        """
        하위 에이전트를 레지스트리에 등록(또는 갱신)한다.
        agent_manifest의 children 섹션도 함께 업데이트한다.
        """
        child = ChildAgentRecord(
            agent_id=payload.agent_id,
            role=payload.role,
            endpoint=payload.endpoint,
            capabilities=list(payload.capabilities or payload.available_actions),
            status="registered",
            last_seen_at=utc_now_iso(),
            notes=payload.notes,
        )
        self._child_index[child.agent_id] = child
        self.state.children = list(self._child_index.values())
        self.state.agent_manifest.setdefault("children", {})
        self.state.agent_manifest["children"][child.agent_id] = self._child_manifest(payload)
        self.state.remember({"kind": "child.registered", "at": utc_now_iso(), "child": child.to_dict()})
        return child

    def _child_manifest(self, payload: ChildAgentInput | AgentManifestInput) -> dict[str, Any]:
        """
        등록 요청 바디로부터 하위 에이전트의 능력 명세(manifest) dict를 생성한다.
        미션 할당 시 대상 에이전트의 능력 확인에 사용한다.
        """
        available_actions = list(payload.available_actions or payload.capabilities)
        skills = list(payload.skills or available_actions)
        return {
            "agent_id": payload.agent_id,
            "role": payload.role,
            "mode": payload.mode,
            "endpoint": payload.endpoint,
            "command_endpoint": payload.command_endpoint,
            "skills": skills,
            "tools": list(payload.tools),
            "constraints": list(payload.constraints),
            "available_actions": available_actions,
            "supported_inputs": list(payload.supported_inputs),
            "supported_outputs": list(payload.supported_outputs),
            "capabilities": list(payload.capabilities),
            "parent_id": getattr(payload, "parent_id", None) or self.state.agent_id,
            "parent_endpoint": getattr(payload, "parent_endpoint", None) or self.state.parent_endpoint,
            "notes": payload.notes,
            "last_seen_at": utc_now_iso(),
        }

    def heartbeat_child(self, agent_id: str) -> ChildAgentRecord:
        """하위 에이전트의 생존 신호를 갱신하고 상태를 'online'으로 표시한다."""
        child = self._child_index.get(agent_id)
        if child is None:
            raise KeyError(agent_id)
        child.status = "online"
        child.last_seen_at = utc_now_iso()
        self.state.children = list(self._child_index.values())
        if agent_id in self.state.agent_manifest.get("children", {}):
            self.state.agent_manifest["children"][agent_id]["status"] = "online"
            self.state.agent_manifest["children"][agent_id]["last_seen_at"] = child.last_seen_at
        self.state.remember({"kind": "child.heartbeat", "at": utc_now_iso(), "agent_id": agent_id})
        return child

    # ── 메시지 기록 헬퍼 ───────────────────────────────────────────────────

    def _record_message(self, payload: A2AMessageInput, routed_via: Optional[str] = None, status_text: str = "received") -> MessageRecord:
        """
        A2AMessageInput을 MessageRecord로 변환한다.
        message_id가 없으면 uuid4를 자동 생성한다.
        """
        return MessageRecord(
            message_id=payload.message_id or str(uuid4()),
            message_type=payload.message_type,
            from_agent_id=payload.from_agent_id,
            to_agent_id=payload.to_agent_id,
            task_id=payload.task_id,
            conversation_id=payload.conversation_id,
            role=payload.role,
            scope=payload.scope,
            priority=payload.priority,
            ttl=payload.ttl,
            payload=payload.payload,
            route_hint=payload.route_hint,
            received_at=utc_now_iso(),
            routed_via=routed_via,
            status=status_text,
        )

    # ── Agent Card / Manifest 빌더 ─────────────────────────────────────────

    def _build_agent_manifest(self) -> dict[str, Any]:
        """
        내부 능력 명세(manifest)를 구성한다.
        하위 에이전트가 이 에이전트를 상위로 등록할 때 참조한다.

        capabilities 키는 A2A Agent Card와 동일하게 camelCase를 사용한다.
        """
        base_url = f"http://{self.settings['server']['host']}:{self.settings['server']['port']}"
        return {
            "agent_id": self.state.agent_id,
            "role": self.state.role,
            "mode": "dynamic",
            "endpoint": base_url,
            "command_endpoint": f"{base_url}/message:send",
            "skills": [
                "plan_mission",            # 미션 생성 및 목표 분해
                "assign_control_ship",     # control_ship에 미션 위임
                "direct_route_override",   # 권한 있을 때 하위 에이전트 직접 제어
            ],
            "tools": [
                "mission_store",    # 미션 레코드 관리
                "child_registry",   # 하위 에이전트 레지스트리
                "route_planner",    # 라우팅 경로 결정
            ],
            "constraints": [
                "prefer_mid_tier_routing",           # 기본적으로 control_ship 경유 우선
                "direct_route_requires_authority",   # 직접 라우팅은 권한 필요
            ],
            "available_actions": [
                "task.assign",
                "task.accept",
                "task.complete",
                "task.fail",
                "status.report",
                "task.escalate",
            ],
            "supported_inputs": ["application/json", "text/plain"],
            "supported_outputs": ["application/json", "text/plain"],
            "capabilities": {
                "streaming": False,
                "pushNotifications": False,
                "direct_route_allowed": self.state.direct_route_allowed,
            },
            "parent_id": self.state.parent_id,
            "parent_endpoint": self.state.parent_endpoint,
            "children": {},
            "updated_at": utc_now_iso(),
        }

    def _build_agent_card(self) -> dict[str, Any]:
        """
        A2A 표준 Agent Card를 구성한다.
        /.well-known/agent-card.json 에서 반환한다.
        외부 에이전트가 이 에이전트의 능력을 discovery할 때 사용한다.
        """
        base_url = f"http://{self.settings['server']['host']}:{self.settings['server']['port']}"
        return {
            "name": self.state.agent_id,
            "displayName": "CoWater Control Center System Agent",
            "description": "Top-tier control_center A2A agent for mission planning, routing, and direct child coordination.",
            "url": base_url,
            "version": "1.0.0",
            "protocolVersion": "1.0.0",
            "supportedInterfaces": [
                {
                    "url": base_url,
                    "protocolBinding": DEFAULT_A2A_BINDING,
                    "protocolVersion": "1.0.0",
                }
            ],
            "capabilities": {
                "streaming": False,
                "pushNotifications": False,
                "extendedAgentCard": False,
            },
            "defaultInputModes": ["application/json", "text/plain"],
            "defaultOutputModes": ["application/json", "text/plain"],
            "skills": [
                {
                    "id": "plan_mission",
                    "name": "Plan Mission",
                    "description": "Create and manage mission records for downstream agents.",
                },
                {
                    "id": "assign_control_ship",
                    "name": "Assign Control Ship",
                    "description": "Delegate mission scope to a control_ship layer or direct child agent.",
                },
                {
                    "id": "direct_route_override",
                    "name": "Direct Route Override",
                    "description": "Bypass the mid-tier when scope and authority allow direct control.",
                },
            ],
        }

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
            dispatch = await self._dispatch_message(message, target_id=target_id, target_endpoint=target.get("endpoint"))
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
        control_center는 최상위이므로 parent_endpoint가 보통 비어 있다.
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

    async def _dispatch_message(self, payload: A2AMessageInput, target_id: str, target_endpoint: Optional[str] = None) -> dict[str, Any]:
        """
        단일 에이전트에게 A2A 메시지를 발송하는 내부 메서드.
        target_endpoint가 없으면 _child_index에서 조회한다.
        주소를 찾지 못하면 status를 'queued'로 표시한다.
        """
        record = self._record_message(payload, routed_via=self.state.agent_id, status_text="dispatching")
        self.state.dispatches.append(record.to_dict())
        target = target_endpoint or self._child_index.get(
            target_id,
            ChildAgentRecord(target_id, "unknown"),
        ).endpoint
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
        return await self._dispatch_message(payload.message, payload.target_agent_id, payload.target_endpoint)

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

    def reset(self) -> None:
        """인메모리 상태를 초기화한다. 개발·테스트 전용."""
        self.state.children = []
        self.state.missions = []
        self.state.inbox = []
        self.state.outbox = []
        self.state.dispatches = []
        self.state.tasks = []
        self.state.memory = []
        self.state.context = {}
        self._child_index = {}
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

app = FastAPI(title="CoWater Control Center System Agent", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=APP_SETTINGS["cors"]["allow_origins"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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
        ],
    }


@app.get("/state")
def state() -> dict[str, Any]:
    """에이전트의 전체 런타임 상태(inbox·outbox·missions·memory 등)를 반환한다."""
    return hub.state.to_dict()


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
