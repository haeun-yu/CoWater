from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

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
]

CORE_ACTIONS = Literal[
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


def build_track_endpoint(token: str, track_name: str, track_type: str) -> str:
    return (
        "/pang/ws/meb"
        f"?channel=instant&name={token}&source=base&track={normalize_track_name(track_name)}"
    )


def build_agent_endpoint(scheme: str, host: str, port: int, path_prefix: str, token: str) -> str:
    prefix = path_prefix.rstrip("/")
    return f"{scheme}://{host}:{port}{prefix}/{token}"


def build_agent_command_endpoint(scheme: str, host: str, port: int, path_prefix: str, token: str) -> str:
    prefix = path_prefix.rstrip("/")
    return f"{scheme}://{host}:{port}{prefix}/{token}/command"


def resolve_default_main_video_track_name(tracks: List["TrackRecord"]) -> Optional[str]:
    for track in tracks:
        if track.type == "VIDEO":
            return track.name
    return None


@dataclass
class TrackRecord:
    type: str
    name: str
    endpoint: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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
    role: Optional[str] = None
    llm_enabled: bool = False
    skills: List[str] = field(default_factory=list)
    available_actions: List[str] = field(default_factory=list)
    connected: bool = False
    connected_at: Optional[str] = None
    last_seen_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DeviceAgentRegistrationRequest(BaseModel):
    secretKey: str
    endpoint: Optional[str] = None
    commandEndpoint: Optional[str] = None
    role: Optional[str] = None
    llm_enabled: bool = False
    skills: List[str] = Field(default_factory=list)
    available_actions: List[str] = Field(default_factory=list)
    connected: bool = True
    last_seen_at: Optional[str] = None


@dataclass
class AlertRecord:
    alert_id: str
    source_system: str
    event_id: str
    source_agent_id: Optional[str]
    source_role: Optional[str]
    alert_type: str
    severity: str
    message: str
    status: str = "waiting"
    recommended_action: Optional[str] = None
    target_agent_id: Optional[str] = None
    requires_user_approval: bool = False
    auto_remediated: bool = False
    route_mode: str = "direct"
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
class ResponseRecord:
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


class AlertIngestRequest(BaseModel):
    alert_id: Optional[str] = None
    source_system: str = "control_center"
    event_id: str
    source_agent_id: Optional[str] = None
    source_role: Optional[str] = None
    alert_type: str
    severity: str = "info"
    message: str
    status: str = "waiting"
    recommended_action: Optional[str] = None
    target_agent_id: Optional[str] = None
    requires_user_approval: bool = False
    auto_remediated: bool = False
    route_mode: str = "direct"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AlertAckRequest(BaseModel):
    approved: bool = True
    notes: Optional[str] = None


class ResponseIngestRequest(BaseModel):
    response_id: Optional[str] = None
    alert_id: str
    action: str
    target_agent_id: Optional[str] = None
    target_endpoint: Optional[str] = None
    route_mode: str = "direct"
    status: str = "planned"
    reason: str = ""
    task_id: Optional[str] = None
    dispatch_result: Dict[str, Any] = Field(default_factory=dict)
    notes: Optional[str] = None


@dataclass
class DeviceRecord:
    id: int
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
    # ← NEW: Device hierarchy & location
    device_type: Optional[str] = None
    layer: Optional[str] = None
    connectivity: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    parent_id: Optional[int] = None
    last_location_update: Optional[str] = None
    last_error: Optional[str] = None
    # ← NEW: Moth topics for telemetry & heartbeat
    heartbeat_topic: Optional[str] = None
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "token": self.token,
            "name": self.name,
            "connected": self.connected,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "main_video_track_name": self.resolved_main_video_track_name(),
            "server": self.server.to_dict(),
            "agent": self.agent.to_dict(),
            "tracks": [track.to_dict() for track in self.tracks],
            "actions": self.actions.to_dict(),
            # ← NEW
            "device_type": self.device_type,
            "layer": self.layer,
            "connectivity": self.connectivity,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "parent_id": self.parent_id,
            "last_location_update": self.last_location_update,
            # ← NEW: Moth topics
            "heartbeat_topic": self.heartbeat_topic,
            "telemetry_topics": self.telemetry_topics,
            # ← NEW: AUV submersion state
            "is_submerged": self.is_submerged,
            "submerged_at": self.submerged_at,
            "surfaced_at": self.surfaced_at,
            "force_parent_routing": self.force_parent_routing,
        }


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
    device_type: Optional[str] = None
    layer: Optional[str] = None
    connectivity: Optional[str] = None
    location: Optional[dict] = None
    requires_parent: bool = False
    parent_id: Optional[int] = None


class DeviceRenameRequest(BaseModel):
    name: str


class MainVideoTrackRequest(BaseModel):
    name: str


# ← NEW: Heartbeat & Topic Models
class TelemetryTopicInfo(BaseModel):
    track_type: str
    track_name: str
    topic: str


class DeviceRegistrationResponse(BaseModel):
    id: int
    token: str
    agent_id: str
    name: str
    parent_id: Optional[int] = None
    parent_endpoint: Optional[str] = None
    parent_command_endpoint: Optional[str] = None
    heartbeat_topic: str
    telemetry_topics: List[TelemetryTopicInfo] = Field(default_factory=list)
    registered_at: str
    last_seen_at: str


class HeartbeatUpdate(BaseModel):
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
    parent_id: Optional[int] = None  # ROV wired connection through middle layer
    force_parent_routing: bool = False  # ROV: always route through parent

