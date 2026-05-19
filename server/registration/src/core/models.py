from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import quote
from urllib.parse import urlparse
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

TRACK_TYPES = Literal[
    "VIDEO",
    "LIDAR",
    "AUDIO",
    "CONTROL",
    "BATTERY",
    "SPEAKER",
    "TOPIC",
    "MAP",
    "ODOMETRY",
    "GPS",
    "TRAJECTORY",
    "DEPTH",
    "PRESSURE",
    "A2A",
]

DEVICE_TYPES = Literal["USV", "AUV", "ROV", "OTHER"]
LAYERS = Literal["lower", "middle", "system"]
EVENT_SEVERITIES = Literal["CRITICAL", "WARNING", "INFO"]
EVENT_STATUSES = Literal["OPEN", "HANDLED", "RESOLVED"]

MISSION_TYPES = Literal["OPERATION", "RESPONSE", "RECOVERY", "SURVEY", "INSPECTION", "MONITORING", "RETURN", "EMERGENCY"]
PROPOSAL_STATUSES = Literal["PROPOSED", "APPROVED", "CANCELLED", "EXPIRED"]

TASK_STATES = Literal["PENDING", "ASSIGNED", "IN_PROGRESS", "COMPLETED", "FAILED", "CANCELLED", "ABORTED"]
FAILURE_CATEGORIES = Literal["device", "communication", "sensor", "mission", "policy", "user", "unknown"]
TIMELINE_EVENT_TYPES = Literal[
    "PROPOSAL_CREATED",
    "PROPOSAL_APPROVED",
    "PROPOSAL_REJECTED",
    "TASK_STATUS_CHANGED",
    "MISSION_STATUS_CHANGED",
    "MISSION_RETRY_REQUEST",
    "TASK_ABORTED",
    "USER_COMMAND",
    "USER_COMMAND_FAILED",
    "SYS_MISSION_REPLAN_REQUESTED",
    "SYS_TASK_DISPATCHED",
    "SYS_TASK_COMPLETED",
    "SYS_TASK_FAILED",
    "SYS_MISSION_UPDATED",
    "SYS_MISSION_COMPLETED",
    "SYS_AGENT_CONNECTION_CREATED",
    "SYS_AGENT_CONNECTION_DELETED",
    "LOW_BATTERY",
    "DEVICE_OFFLINE",
    "HEARTBEAT_LOST",
    "CRITICAL_HAZARD",
    "CONFIG_CHANGED",
    "USER_MODIFIED",
    "USER_FEEDBACK",
    "DEVICE_REMOVED",
    "MISSION_CREATED",
    "MISSION_STARTED",
    "MISSION_APPROVED",
    "MISSION_REJECTED",
    "MISSION_UPDATED",
    "MISSION_COMPLETED",
    "MISSION_FAILED",
    "MISSION_CANCELED",
    "USER_APPROVAL",
    "USER_REAPPROVAL",
    "USER_REAPPROVAL_REQUESTED",
    "STEP_STARTED",
    "TASK_ASSIGNED",
    "TASK_ACCEPTED",
    "TASK_REJECTED",
    "TASK_STARTED",
    "TASK_DISPATCHED",
    "DISPATCH_FAILED",
    "TASK_RUNNING",
    "TASK_COMPLETED",
    "TASK_FAILED",
    "TASK_CANCELED",
    "TASK_FAILURE",
    "TASK_RESULT_REPORTED",
    "DEVICE_RESULT_REPORTED",
    "ALERT_CREATED",
    "ALERT_UPDATED",
    "EVENT_REPORTED",
    "AGENT_JUDGMENT",
    "PLAN_CHANGED",
    "WARNING",
]

CORE_ACTIONS = Literal[
    "MOVE_TO",
    "HIGH_RES_SCAN",
    "SURFACE_SCAN",
    "SONAR_SCAN",
    "SAMPLE_COLLECTION",
    "RETURN_TO_BASE",
    "HOLD_POSITION",
    "SLAM_NAVIGATION",
    "MAP_NAVIGATION",
    "GPS_NAVIGATION",
    "NAVIGATION_3D",
    "TTS",
    "PARKING",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_track_name(name: str) -> str:
    return name.strip().lower()


def build_track_endpoint(
    device_id: int,
    track_name: str,
    track_type: str,
    *,
    mode: Literal["sub", "pub"] = "sub",
) -> str:
    channel_name = f"device-{device_id}"
    normalized_track = normalize_track_name(track_name or track_type)
    return (
        f"/pang/ws/{mode}"
        f"?channel=instant&name={quote(channel_name)}"
        f"&source=base&track={quote(normalized_track)}"
    )


def as_pub_track_endpoint(endpoint: str) -> str:
    if not endpoint:
        return endpoint
    return endpoint.replace("/pang/ws/sub", "/pang/ws/pub")


def build_healthcheck_endpoint(device_id: int) -> str:
    return (
        "/pang/ws/meb"
        "?channel=instant&name=agents&source=base&track=base"
    )


def build_agent_endpoint(scheme: str, host: str, port: int, path_prefix: str, token: str) -> str:
    prefix = path_prefix.rstrip("/")
    return f"{scheme}://{host}:{port}{prefix}/{token}"


def build_agent_command_endpoint(scheme: str, host: str, port: int, path_prefix: str, token: str) -> str:
    prefix = path_prefix.rstrip("/")
    return f"{scheme}://{host}:{port}{prefix}/{token}/command"


def parse_endpoint_value(endpoint: Optional[str]) -> Optional[dict[str, Any]]:
    if not endpoint:
        return None
    if isinstance(endpoint, dict):
        return endpoint
    parsed = urlparse(endpoint)
    if not parsed.scheme or not parsed.hostname:
        return {"raw": endpoint}
    return {
        "host": parsed.hostname,
        "port": parsed.port,
        "protocol": parsed.scheme.upper(),
        "path": parsed.path or None,
        "auth_token_ref": None,
    }


def resolve_default_main_video_track_name(tracks: List["TrackRecord"]) -> Optional[str]:
    for track in tracks:
        if track.type == "VIDEO":
            return track.name
    return None


def _upper_status_fields(value: Any) -> Any:
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if key in {"status", "state", "execution_status", "dispatch_status", "acceptance_status"} and item is not None:
                normalized[key] = str(item).upper()
            else:
                normalized[key] = _upper_status_fields(item)
        return normalized
    if isinstance(value, list):
        return [_upper_status_fields(item) for item in value]
    return value


MISSION_STATUS_ALIASES: dict[str, str] = {
    "PENDING_APPROVAL": "READY",
    "APPROVED": "READY",
    "RUNNING": "IN_PROGRESS",
    "IN_PROGRESS": "IN_PROGRESS",
    "COMPLETED": "COMPLETED",
    "FAILED": "FAILED",
    "CANCELED": "CANCELLED",
    "CANCELLED": "CANCELLED",
    "REJECTED": "FAILED",
    "NEEDS_REVIEW": "FAILED",
    "PENDING": "READY",
    "EXPIRED": "EXPIRED",
}

PROPOSAL_STATUS_ALIASES: dict[str, str] = {
    "PENDING_APPROVAL": "PROPOSED",
    "PENDING": "PROPOSED",
    "PROPOSED": "PROPOSED",
    "APPROVED": "APPROVED",
    "REJECTED": "CANCELLED",
    "CANCELED": "CANCELLED",
    "CANCELLED": "CANCELLED",
    "EXPIRED": "EXPIRED",
}

APPROVAL_STATUS_ALIASES: dict[str, str] = {
    "PENDING": "PENDING",
    "APPROVED": "APPROVED",
    "REJECTED": "REJECTED",
}

TASK_STATUS_ALIASES: dict[str, str] = {
    "PENDING": "PENDING",
    "ASSIGNED": "ASSIGNED",
    "RUNNING": "IN_PROGRESS",
    "IN_PROGRESS": "IN_PROGRESS",
    "COMPLETED": "COMPLETED",
    "FAILED": "FAILED",
    "CANCELED": "CANCELLED",
    "CANCELLED": "CANCELLED",
    "ABORTED": "ABORTED",
    "REJECTED": "ABORTED",
}

# schema.md §5 기준 canonical 이벤트 타입
CANONICAL_EVENT_TYPES: frozenset[str] = frozenset({
    "SYS_INTENT_CLASSIFIED",
    "SYS_INTENT_REJECTED",
    "SYS_TASK_DISPATCHED",
    "SYS_TASK_COMPLETED",
    "SYS_TASK_FAILED",
    "SYS_ANOMALY_DETECTED",
    "SYS_POLICY_DECISION",
    "SYS_MISSION_UPDATED",
    "SYS_MISSION_COMPLETED",
    "SYS_MISSION_REPLAN_REQUESTED",
    "SYS_INSIGHT_REPORT",
    "SYS_REQUEST_PROCESSED",
    "SYS_AGENT_CONNECTION_CREATED",
    "SYS_AGENT_CONNECTION_DELETED",
    "DEVICE_HEALTHCHECK",
    "ENV_STATE_CHANGED",
})

# 레거시/약식 표기 → canonical 매핑
EVENT_TYPE_ALIASES: dict[str, str] = {
    "SYS.TASK.EXECUTED": "SYS_TASK_COMPLETED",
    "SYS.MISSION.STATE_CHANGED": "SYS_MISSION_UPDATED",
    "SYS.RECOVERY.ACTION": "SYS_MISSION_UPDATED",
    "SYS.ALERT.GENERATED": "SYS_ANOMALY_DETECTED",
    "SYS.DEVICE.STATUS_CHANGED": "SYS_ANOMALY_DETECTED",
    "STEP_EVALUATION": "SYS_MISSION_UPDATED",
    "RECOVERY_ACTION": "SYS_MISSION_UPDATED",
    "MISSION_STATE_CHANGE": "SYS_MISSION_UPDATED",
    "DEVICE_STATUS_CHANGE": "SYS_ANOMALY_DETECTED",
    "POLICY_DECISION": "SYS_POLICY_DECISION",
    "USER_COMMAND": "SYS_INTENT_CLASSIFIED",
    "TASK_COMPLETED": "SYS_TASK_COMPLETED",
    "TASK_FAILED": "SYS_TASK_FAILED",
    "MISSION_COMPLETED": "SYS_MISSION_COMPLETED",
    "LOW_BATTERY": "SYS_ANOMALY_DETECTED",
    "DEVICE_OFFLINE": "SYS_ANOMALY_DETECTED",
    "HEARTBEAT_LOST": "SYS_ANOMALY_DETECTED",
    "CRITICAL_HAZARD": "SYS_ANOMALY_DETECTED",
}


def _normalize_enum(value: Any, aliases: dict[str, str], default: str) -> str:
    normalized = str(value or default).strip().upper()
    return aliases.get(normalized, normalized or default)


def normalize_mission_status(value: Any) -> str:
    return _normalize_enum(value, MISSION_STATUS_ALIASES, "READY")


def normalize_proposal_status(value: Any) -> str:
    return _normalize_enum(value, PROPOSAL_STATUS_ALIASES, "PROPOSED")


def normalize_approval_status(value: Any) -> str:
    return _normalize_enum(value, APPROVAL_STATUS_ALIASES, "PENDING")


def normalize_task_status(value: Any) -> str:
    return _normalize_enum(value, TASK_STATUS_ALIASES, "PENDING")


def normalize_event_type(value: Any) -> str:
    """이벤트 타입을 canonical 형식으로 정규화"""
    normalized = str(value or "SYS_MISSION_UPDATED").strip().upper().replace(".", "_")
    # canonical 타입이면 그대로 반환
    if normalized in CANONICAL_EVENT_TYPES:
        return normalized
    # alias 매핑
    if normalized in EVENT_TYPE_ALIASES:
        return EVENT_TYPE_ALIASES[normalized]
    # SYS_ 접두어 붙여서 canonical 재확인
    with_prefix = f"SYS_{normalized}" if not normalized.startswith("SYS_") else normalized
    if with_prefix in CANONICAL_EVENT_TYPES:
        return with_prefix
    return normalized


@dataclass
class TrackRecord:
    type: str
    name: str
    endpoint: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_device_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["endpoint"] = as_pub_track_endpoint(self.endpoint)
        return payload


@dataclass
class DeviceActionsRecord:
    core: List[str] = field(default_factory=list)
    custom: List[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DeviceServerInformationRecord:
    host: str
    port: int
    ping_endpoint: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DeviceAgentInformationRecord:
    scheme: str
    host: str
    port: int
    path_prefix: str
    endpoint: str
    command_endpoint: str
    agent_id: Optional[str] = None
    role: Optional[str] = None
    llm_enabled: bool = False
    skills: List[str] = field(default_factory=list)
    available_actions: List[str] = field(default_factory=list)
    connected: bool = False
    connected_at: Optional[str] = None
    last_seen_at: Optional[str] = None
    # P3 (보고 기반): Device가 주기적으로 보고한 위치와 배터리 정보
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    battery_percent: Optional[float] = None
    gateway_agent_id: Optional[str] = None
    environment_state: Optional[str] = None
    active_mediums: List[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["endpoint"] = parse_endpoint_value(self.endpoint)
        result["command_endpoint"] = parse_endpoint_value(self.command_endpoint)
        return result


class DeviceAgentRegistrationRequest(BaseModel):
    secretKey: str
    device_id: Optional[int | str] = None
    agent_id: Optional[str] = None
    endpoint: Optional[str] = None
    commandEndpoint: Optional[str] = None
    role: Optional[str] = None
    llm_enabled: bool = False
    skills: List[str] = Field(default_factory=list)
    available_actions: List[str] = Field(default_factory=list)
    connected: bool = True
    last_seen_at: Optional[str] = None
    # P3 (보고 기반): Device가 주기적으로 보고한 위치와 배터리
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    battery_percent: Optional[float] = None
    gateway_agent_id: Optional[str] = None
    environment_state: Optional[str] = None
    active_mediums: List[str] = Field(default_factory=list)


@dataclass
class SensorStatus:
    """센서 상태 정보 (아키텍처 Ch.15)"""
    sensor_id: str
    sensor_type: str
    status: str  # "healthy", "degraded", "failed"
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TaskResult:
    """Task 실행 결과 (아키텍처 Ch.10)"""
    task_id: str
    status: TASK_STATES
    result_summary: Optional[str] = None
    output_refs: List[str] = field(default_factory=list)
    failure_category: Optional[FAILURE_CATEGORIES] = None
    failure_message: Optional[str] = None
    reported_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        return _upper_status_fields(result)


@dataclass
class TimelineEvent:
    """Mission Timeline 이벤트 (아키텍처 Ch.18-20)"""
    event_type: TIMELINE_EVENT_TYPES
    timestamp: str
    actor: Optional[str] = None  # "system", "device_{id}", "user"
    details: Dict[str, Any] = field(default_factory=dict)
    related_task_id: Optional[str] = None
    related_step_index: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["event_type"] = str(self.event_type).upper()
        return result


@dataclass
class MissionRecord:
    """Mission 실행 계획 (docs 기준)"""
    mission_id: str
    title: str
    type: str  # OPERATION | RESPONSE | RECOVERY | SURVEY | INSPECTION | MONITORING | RETURN | EMERGENCY
    status: str  # READY | IN_PROGRESS | COMPLETED | FAILED | CANCELLED | EXPIRED
    priority: str = "NORMAL"  # LOW | NORMAL | HIGH | EMERGENCY
    source_event_id: Optional[str] = None
    source_proposal_id: Optional[str] = None
    target_area: Optional[str] = None
    target_position: Optional[Dict[str, Any]] = None
    created_by: Dict[str, Any] = field(default_factory=lambda: {"type": "SYSTEM", "id": "system"})
    approved_by_user_id: Optional[str] = None
    approved_at: Optional[str] = None
    approval_id: Optional[str] = None
    status_updated_at: str = field(default_factory=utc_now_iso)
    status_reason: Optional[str] = None
    result_summary: Optional[str] = None
    steps: List[Dict[str, Any]] = field(default_factory=list)
    timeline: List[Dict[str, Any]] = field(default_factory=list)
    final_result: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def touch(self, status: Optional[str] = None, reason: Optional[str] = None) -> None:
        """상태 업데이트 및 타임스탐프 갱신"""
        self.updated_at = utc_now_iso()
        if status:
            self.status = normalize_mission_status(status)
            self.status_updated_at = self.updated_at
        if reason is not None:
            self.status_reason = reason

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["id"] = self.mission_id
        return payload


@dataclass
class EventRecord:
    event_id: str
    type: str  # SYS_INTENT_CLASSIFIED | SYS_TASK_COMPLETED | SYS_TASK_FAILED | SYS_ANOMALY_DETECTED | SYS_MISSION_UPDATED | SYS_MISSION_COMPLETED | DEVICE_HEALTHCHECK | ENV_STATE_CHANGED etc.
    severity: EVENT_SEVERITIES
    actor_type: Optional[str] = None
    actor_id: Optional[str] = None
    status: str = "OPEN"
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    title: str = ""
    description: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def touch(self, status: Optional[str] = None) -> None:
        self.updated_at = utc_now_iso()
        if status is not None:
            self.status = str(status).upper()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["id"] = self.event_id
        return payload


def normalize_severity_value(value: Any) -> str:
    if value is None:
        return "INFO"
    normalized = str(value).strip().upper()
    aliases = {
        "INFO": "INFO",
        "INFORMATION": "INFO",
        "WARNING": "WARNING",
        "WARN": "WARNING",
        "ERROR": "CRITICAL",
        "CRITICAL": "CRITICAL",
    }
    if normalized in aliases:
        return aliases[normalized]
    raise ValueError("severity must be one of CRITICAL, WARNING, INFO")


class EventIngestRequest(BaseModel):
    event_id: Optional[str] = None
    actor_type: Optional[str] = None
    actor_id: Optional[str] = None
    event_type: str
    severity: EVENT_SEVERITIES = "INFO"
    status: str = "OPEN"
    title: str = ""
    description: Optional[str] = None
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("severity", mode="before")
    @classmethod
    def normalize_severity(cls, value: Any) -> str:
        return normalize_severity_value(value)


@dataclass
class DeviceRecord:
    id: int
    public_id: str
    token: str
    name: str
    connected: bool
    created_at: str
    updated_at: str
    server: DeviceServerInformationRecord
    agent: DeviceAgentInformationRecord
    tracks: List[TrackRecord]
    actions: DeviceActionsRecord
    main_video_track_name: Optional[str] = None
    # ← NEW: Device connectivity status (online | offline)
    connectivity_status: str = "offline"
    # ← NEW: Device hierarchy & location
    device_type: Optional[str] = None
    layer: Optional[str] = None
    connectivity: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    last_battery_percent: Optional[float] = None
    last_battery_update: Optional[str] = None
    parent_id: Optional[int] = None
    last_location_update: Optional[str] = None
    last_error: Optional[str] = None
    target_type: Optional[str] = None   # "MISSION" | "TASK" | null — DeviceBridge가 갱신 책임
    target_id: Optional[str] = None     # 현재 배정된 Mission/Task ID — DeviceBridge가 갱신 책임
    # ← NEW: Moth topics for telemetry & healthcheck
    healthcheck_topic: Optional[str] = None
    healthcheck_endpoint: Optional[str] = None
    telemetry_topics: List[Dict[str, str]] = field(default_factory=list)
    # ← NEW: AUV submersion state & connectivity constraints
    is_submerged: bool = False  # AUV 수중 여부
    submerged_at: Optional[str] = None  # 잠수 시간
    surfaced_at: Optional[str] = None  # 수면 시간
    force_parent_routing: bool = False  # ROV: 항상 parent를 통한 라우팅

    def resolved_main_video_track_name(self) -> Optional[str]:
        if self.main_video_track_name:
            for track in self.tracks:
                if track.type == "VIDEO" and track.name == self.main_video_track_name:
                    return self.main_video_track_name
        return resolve_default_main_video_track_name(self.tracks)

    def physical_interfaces(self) -> list[dict[str, Any]]:
        if self.device_type == "ROV":
            types = ["WIRED"]
        elif self.device_type == "AUV":
            types = ["ACOUSTIC", "RF", "INTERNET"]
        elif self.device_type == "USV":
            types = ["WIRED", "RF", "INTERNET", "ACOUSTIC"]
        else:
            types = list(self.agent.active_mediums or [])
        return [{"type": item, "hardware": item, "specs": None} for item in dict.fromkeys(types)]

    def to_dict(self) -> dict[str, Any]:
        action_list = list(self.actions.core) + list(self.actions.custom)
        return {
            "id": self.public_id,
            "registry_id": self.id,
            "token": self.token,
            "name": self.name,
            "type": self.device_type if self.device_type in {"USV", "AUV", "ROV"} else "OTHER",
            "status": "ONLINE" if self.connected else "OFFLINE",
            "position": {"latitude": self.latitude, "longitude": self.longitude},
            "physical_interfaces": self.physical_interfaces(),
            "battery_percent": self.last_battery_percent,
            "device_agent_id": self.agent.agent_id,
            "last_seen_at": self.agent.last_seen_at,
            "deleted_at": None,
            "connected": self.connected,
            "connectivity_status": self.connectivity_status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "main_video_track_name": self.resolved_main_video_track_name(),
            "server": self.server.to_dict(),
            "agent": self.agent.to_dict(),
            "tracks": [track.to_dict() for track in self.tracks],
            "actions": action_list,
            "action_catalog": self.actions.to_dict(),
            # ← NEW
            "device_type": self.device_type,
            "layer": self.layer,
            "connectivity": self.connectivity,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "last_battery_percent": self.last_battery_percent,
            "last_battery_update": self.last_battery_update,
            "parent_id": self.parent_id,
            "last_location_update": self.last_location_update,
            "target_type": self.target_type,
            "target_id": self.target_id,
            # ← NEW: Moth topics
            "healthcheck_topic": self.healthcheck_topic,
            "healthcheck_endpoint": self.healthcheck_endpoint,
            "telemetry_topics": self.telemetry_topics,
            # ← NEW: AUV submersion state
            "is_submerged": self.is_submerged,
            "submerged_at": self.submerged_at,
            "surfaced_at": self.surfaced_at,
            "force_parent_routing": self.force_parent_routing,
        }

    def to_device_registration_dict(self) -> dict[str, Any]:
        payload = self.to_dict()
        payload["tracks"] = [track.to_device_dict() for track in self.tracks]
        return payload


class TrackInput(BaseModel):
    type: TRACK_TYPES
    name: str
    endpoint: Optional[str] = None
    frequency_hz: Optional[float] = None  # ← NEW


class DeviceActionsInput(BaseModel):
    core: List[CORE_ACTIONS] = Field(default_factory=list)
    custom: List[str] = Field(default_factory=list)


class DeviceRegistrationRequest(BaseModel):
    secretKey: str
    name: str
    tracks: List[TrackInput]
    actions: DeviceActionsInput = Field(default_factory=DeviceActionsInput)
    # ← NEW: Device hierarchy & location
    device_type: Optional[DEVICE_TYPES] = None
    layer: Optional[LAYERS] = None
    connectivity: Optional[str] = None
    location: Optional[dict] = None
    requires_parent: bool = False
    parent_id: Optional[str] = None
    physical_interfaces: List[Dict[str, Any]] = Field(default_factory=list)
    battery_percent: Optional[float] = None
    gateway_agent_id: Optional[str] = None
    environment_state: Optional[str] = None
    active_mediums: List[str] = Field(default_factory=list)


class DeviceRenameRequest(BaseModel):
    name: str


class MainVideoTrackRequest(BaseModel):
    name: str


# ← NEW: Healthcheck & Topic Models
class TelemetryTopicInfo(BaseModel):
    track_type: str
    track_name: str
    topic: str


class DeviceRegistrationResponse(BaseModel):
    id: str
    token: str
    agent_id: str
    name: str
    parent_id: Optional[str] = None
    parent_endpoint: Optional[str] = None
    parent_command_endpoint: Optional[str] = None
    healthcheck_topic: str
    telemetry_topics: List[TelemetryTopicInfo] = Field(default_factory=list)
    registered_at: str
    last_seen_at: str


class HealthcheckUpdate(BaseModel):
    device_id: int
    agent_id: str
    layer: str
    timestamp: str
    status: str
    battery_percent: float


class LocationUpdate(BaseModel):
    latitude: float
    longitude: float


class AUVSubmersionRequest(BaseModel):
    """AUV submersion state update request"""
    is_submerged: bool


class DeviceConnectivityStateRequest(BaseModel):
    """Device connectivity state update (for ROV wired/wireless, AUV surface/submerged routing)"""
    parent_id: Optional[str] = None  # ROV wired connection through middle layer
    force_parent_routing: bool = False  # ROV: always route through parent


def device_record_from_dict(data: dict) -> "DeviceRecord":
    """JSON dict에서 DeviceRecord 재구성 (SQLite 로드 시 사용)"""
    server_d = data.get("server") or {}
    server = DeviceServerInformationRecord(
        host=server_d.get("host", ""),
        port=int(server_d.get("port", 0)),
        ping_endpoint=server_d.get("ping_endpoint", ""),
    )

    agent_d = data.get("agent") or {}
    agent_id = agent_d.get("agent_id")
    if agent_id is not None:
        agent_id = str(agent_id)
    gateway_agent_id = agent_d.get("gateway_agent_id")
    if gateway_agent_id is not None:
        gateway_agent_id = str(gateway_agent_id)
    agent = DeviceAgentInformationRecord(
        scheme=agent_d.get("scheme", "http"),
        host=agent_d.get("host", ""),
        port=int(agent_d.get("port", 0)),
        path_prefix=agent_d.get("path_prefix", ""),
        endpoint=agent_d.get("endpoint", ""),
        command_endpoint=agent_d.get("command_endpoint", ""),
        agent_id=agent_id,
        role=agent_d.get("role"),
        llm_enabled=bool(agent_d.get("llm_enabled", False)),
        skills=list(agent_d.get("skills") or []),
        available_actions=list(agent_d.get("available_actions") or []),
        connected=bool(agent_d.get("connected", False)),
        connected_at=agent_d.get("connected_at"),
        last_seen_at=agent_d.get("last_seen_at"),
        latitude=agent_d.get("latitude"),
        longitude=agent_d.get("longitude"),
        battery_percent=agent_d.get("battery_percent"),
        gateway_agent_id=gateway_agent_id,
        environment_state=agent_d.get("environment_state"),
        active_mediums=list(agent_d.get("active_mediums") or []),
    )

    tracks = [
        TrackRecord(
            type=t.get("type", ""),
            name=t.get("name", ""),
            endpoint=t.get("endpoint", ""),
        )
        for t in (data.get("tracks") or [])
    ]

    actions_d = data.get("action_catalog") or data.get("actions") or {}
    if isinstance(actions_d, list):
        actions_d = {"core": [], "custom": actions_d}
    actions = DeviceActionsRecord(
        core=list(actions_d.get("core") or []),
        custom=list(actions_d.get("custom") or []),
    )

    raw_id = data.get("id")
    raw_registry_id = data.get("registry_id")

    numeric_id = raw_registry_id if raw_registry_id is not None else raw_id
    if numeric_id is None:
        raise ValueError("device id is missing")

    if isinstance(numeric_id, str):
        if not numeric_id.isdigit():
            raise ValueError("numeric registry_id is invalid")
        numeric_id = int(numeric_id)

    public_id_value = data.get("public_id")
    if not public_id_value:
        if isinstance(raw_id, str) and raw_id and not raw_id.isdigit():
            public_id_value = raw_id
        else:
            public_id_value = str(uuid4())
    public_id_value = str(public_id_value)

    record = DeviceRecord(
        id=int(numeric_id),
        public_id=public_id_value,
        token=str(data["token"]),
        name=str(data["name"]),
        connected=bool(data.get("connected", False)),
        created_at=str(data["created_at"]),
        updated_at=str(data["updated_at"]),
        server=server,
        agent=agent,
        tracks=tracks,
        actions=actions,
        main_video_track_name=data.get("main_video_track_name"),
        device_type=data.get("device_type"),
        layer=data.get("layer"),
        connectivity=data.get("connectivity"),
        latitude=data.get("latitude"),
        longitude=data.get("longitude"),
        last_battery_percent=data.get("last_battery_percent"),
        last_battery_update=data.get("last_battery_update"),
        parent_id=data.get("parent_id"),
        last_location_update=data.get("last_location_update"),
        target_type=data.get("target_type"),
        target_id=data.get("target_id"),
        healthcheck_topic=data.get("healthcheck_topic") or data.get("healthcheck_topic"),
        healthcheck_endpoint=data.get("healthcheck_endpoint") or data.get("healthcheck_endpoint"),
        telemetry_topics=list(data.get("telemetry_topics") or []),
        is_submerged=bool(data.get("is_submerged", False)),
        submerged_at=data.get("submerged_at"),
        surfaced_at=data.get("surfaced_at"),
        force_parent_routing=bool(data.get("force_parent_routing", False)),
    )

    if not record.agent.environment_state:
        record.agent.environment_state = "UNDERWATER" if record.is_submerged else "SURFACE"
    if not record.agent.active_mediums:
        record.agent.active_mediums = ["ACOUSTIC"] if record.is_submerged else ["RF", "INTERNET", "ACOUSTIC"]
    return record


# ===== 새로운 도메인 모델들 (docs 기준) =====


@dataclass
class UserRecord:
    user_id: str
    name: str
    role: str  # ADMIN | OPERATOR | VIEWER
    status: str  # ACTIVE | DISABLED
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentRecord:
    agent_id: str
    name: str
    type: str  # SYSTEM_AGENT | DEVICE_AGENT
    role: str  # REQUEST_HANDLER | DEVICE_BRIDGE | MISSION_PLANNER | POLICY_MANAGER | SYSTEM_SENTINEL | INSIGHT_REPORTER | DEVICE_CONTROL
    device_id: Optional[str]
    endpoint: Dict[str, Any]  # {host, port, protocol, path, auth_token_ref}
    capabilities: List[str]  # WIRED | ACOUSTIC | RF | INTERNET
    gateway_agent_id: Optional[str] = None
    environment_state: str = "SURFACE"  # SURFACE | UNDERWATER
    active_mediums: List[str] = field(default_factory=list)
    last_heartbeat_at: Optional[str] = None
    deleted_at: Optional[str] = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProposalTaskRecord:
    task_id: str
    proposal_id: str
    title: str
    type: str  # DEVICE_TASK | SYSTEM_TASK | REPORT_TASK | NOTIFY_TASK
    required_action: str
    sequence: int
    target_area: Optional[str] = None
    target_position: Optional[Dict[str, Any]] = None
    recommended_device_id: Optional[str] = None
    recommended_agent_id: Optional[str] = None
    alternative_device_ids: List[str] = field(default_factory=list)
    recommendation_reason: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["id"] = self.task_id
        return payload


@dataclass
class TaskRecord:
    task_id: str
    mission_id: str
    title: str
    type: str  # DEVICE_TASK | SYSTEM_TASK | REPORT_TASK | NOTIFY_TASK
    required_action: str
    status: str  # PENDING | ASSIGNED | IN_PROGRESS | COMPLETED | FAILED | CANCELLED | ABORTED
    sequence: int
    source_proposal_task_id: Optional[str] = None
    assigned_device_id: Optional[str] = None
    assigned_agent_id: Optional[str] = None
    target_area: Optional[str] = None
    target_position: Optional[Dict[str, Any]] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    result: Dict[str, Any] = field(default_factory=dict)
    status_updated_at: str = field(default_factory=utc_now_iso)
    status_reason: Optional[str] = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["id"] = self.task_id
        return payload

    def touch(self, status: Optional[str] = None, reason: Optional[str] = None) -> None:
        self.updated_at = utc_now_iso()
        if status:
            self.status = normalize_task_status(status)
            self.status_updated_at = self.updated_at
        if reason is not None:
            self.status_reason = reason


@dataclass
class ReportRecord:
    report_id: str
    type: str  # MISSION_REPORT | EVENT_REPORT | DAILY_REPORT | DEVICE_REPORT
    target_type: str  # MISSION | EVENT | DEVICE | TASK
    target_id: str
    title: str
    summary: str
    details: Dict[str, Any] = field(default_factory=dict)
    created_by: Dict[str, Any] = field(default_factory=lambda: {"type": "SYSTEM", "id": "system"})
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RuleRecord:
    rule_id: str
    rule_type: str  # PROBLEM_DETECTION | AUTO_RESPONSE | RECOMMENDATION | APPROVAL | AGENT_CONNECTION
    name: str
    enabled: bool
    priority: int
    conditions: List[Dict[str, Any]] = field(default_factory=list)
    action: Dict[str, Any] = field(default_factory=dict)
    severity: str = "INFO"  # INFO | WARNING | CRITICAL
    policy_id: Optional[str] = None
    created_by: Dict[str, Any] = field(default_factory=lambda: {"type": "SYSTEM", "id": "system"})
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ConfigRecord:
    key: str
    value: Any
    type: str  # string | number | boolean | json
    scope: str  # SYSTEM | PROBLEM_DETECTION | AUTO_RESPONSE | RECOMMENDATION | APPROVAL | AGENT_CONNECTION
    description: Optional[str] = None
    updated_by: Dict[str, Any] = field(default_factory=lambda: {"type": "SYSTEM", "id": "system"})
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SensorRecord:
    sensor_id: str
    device_id: str
    name: str
    type: str  # CAMERA | SONAR | LIDAR | RADAR | GPS | IMU | DEPTH | TEMPERATURE | WATER_QUALITY | OTHER
    stream_endpoint: str
    deleted_at: Optional[str] = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
