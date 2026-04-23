from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn


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
]

CORE_ACTIONS = Literal[
    "SLAM_NAVIGATION",
    "MAP_NAVIGATION",
    "GPS_NAVIGATION",
    "NAVIGATION_3D",
    "TTS",
    "PARKING",
]

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.json"
DEFAULT_SERVER_HOST = "192.168.1.100"
DEFAULT_SERVER_PORT = 9001
DEFAULT_PING_ENDPOINT = "/pang/ping"
DEFAULT_SECRET_KEY = "server-secret"
DEFAULT_AGENT_SCHEME = "ws"
DEFAULT_AGENT_HOST = "127.0.0.1"
DEFAULT_AGENT_PORT = 9010
DEFAULT_AGENT_PATH_PREFIX = "/agents"
DEFAULT_AGENT_COMMAND_SCHEME = "http"
DEFAULT_AGENT_COMMAND_PATH_PREFIX = "/agents"
DEFAULT_CORS_ORIGINS = ["*"]
CONFIG_PATH = Path(os.getenv("COWATER_DEVICE_CONFIG_PATH", str(DEFAULT_CONFIG_PATH)))


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


def _load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_runtime_config(config_path: Path) -> dict[str, Any]:
    raw = _load_json_file(config_path)
    server_cfg = raw.get("server") or {}
    agent_cfg = raw.get("agent") or {}
    device_cfg = raw.get("device") or {}
    cors_cfg = raw.get("cors") or {}

    def pick(env_name: str, value: Any, default: Any) -> Any:
        env_value = os.getenv(env_name)
        if env_value is not None and env_value != "":
            return env_value
        if value is not None:
            return value
        return default

    host = str(pick("COWATER_DEVICE_SERVER_HOST", server_cfg.get("host"), DEFAULT_SERVER_HOST))
    port = int(pick("COWATER_DEVICE_SERVER_PORT", server_cfg.get("port"), DEFAULT_SERVER_PORT))
    ping_endpoint = str(
        pick(
            "COWATER_DEVICE_PING_ENDPOINT",
            server_cfg.get("ping_endpoint"),
            DEFAULT_PING_ENDPOINT,
        )
    )
    agent_scheme = str(
        pick(
            "COWATER_DEVICE_AGENT_SCHEME",
            agent_cfg.get("scheme"),
            DEFAULT_AGENT_SCHEME,
        )
    )
    agent_host = str(
        pick(
            "COWATER_DEVICE_AGENT_HOST",
            agent_cfg.get("host"),
            DEFAULT_AGENT_HOST,
        )
    )
    agent_port = int(
        pick(
            "COWATER_DEVICE_AGENT_PORT",
            agent_cfg.get("port"),
            DEFAULT_AGENT_PORT,
        )
    )
    agent_path_prefix = str(
        pick(
            "COWATER_DEVICE_AGENT_PATH_PREFIX",
            agent_cfg.get("path_prefix"),
            DEFAULT_AGENT_PATH_PREFIX,
        )
    )
    agent_command_scheme = str(
        pick(
            "COWATER_DEVICE_AGENT_COMMAND_SCHEME",
            agent_cfg.get("command_scheme"),
            "http" if agent_scheme == "ws" else "https",
        )
    )
    agent_command_path_prefix = str(
        pick(
            "COWATER_DEVICE_AGENT_COMMAND_PATH_PREFIX",
            agent_cfg.get("command_path_prefix"),
            DEFAULT_AGENT_COMMAND_PATH_PREFIX,
        )
    )
    secret_key = str(
        pick(
            "COWATER_DEVICE_SECRET_KEY",
            device_cfg.get("secret_key"),
            DEFAULT_SECRET_KEY,
        )
    )
    cors_origins = pick(
        "COWATER_DEVICE_CORS_ORIGINS",
        cors_cfg.get("allow_origins"),
        DEFAULT_CORS_ORIGINS,
    )
    if isinstance(cors_origins, str):
        cors_origins = [origin.strip() for origin in cors_origins.split(",") if origin.strip()]
    if not isinstance(cors_origins, list) or not cors_origins:
        cors_origins = list(DEFAULT_CORS_ORIGINS)

    return {
        "config_path": str(config_path),
        "secret_key": secret_key,
        "server": {
            "host": host,
            "port": port,
            "ping_endpoint": ping_endpoint,
        },
        "agent": {
            "scheme": agent_scheme,
            "host": agent_host,
            "port": agent_port,
            "path_prefix": agent_path_prefix,
            "command_scheme": agent_command_scheme,
            "command_path_prefix": agent_command_path_prefix,
        },
        "cors": {
            "allow_origins": cors_origins,
        },
    }


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
    skills: List[str] = field(default_factory=list)
    available_actions: List[str] = field(default_factory=list)
    connected: bool = False
    mode: Optional[str] = None
    connected_at: Optional[str] = None
    last_seen_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DeviceAgentRegistrationRequest(BaseModel):
    secretKey: str
    endpoint: Optional[str] = None
    commandEndpoint: Optional[str] = None
    role: Optional[str] = None
    mode: Optional[str] = None
    skills: List[str] = Field(default_factory=list)
    available_actions: List[str] = Field(default_factory=list)
    connected: bool = True
    last_seen_at: Optional[str] = None


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
        }


class TrackInput(BaseModel):
    type: TRACK_TYPES
    name: str
    endpoint: Optional[str] = None


class DeviceActionsInput(BaseModel):
    core: List[CORE_ACTIONS] = Field(default_factory=list)
    custom: List[str] = Field(default_factory=list)


class DeviceRegistrationRequest(BaseModel):
    secretKey: str
    name: str
    tracks: List[TrackInput]
    actions: DeviceActionsInput = Field(default_factory=DeviceActionsInput)


class DeviceRenameRequest(BaseModel):
    name: str


class MainVideoTrackRequest(BaseModel):
    name: str


class DeviceRegistry:
    def __init__(
        self,
        *,
        secret_key: str,
        host: str,
        port: int,
        ping_endpoint: str,
        agent_scheme: str,
        agent_host: str,
        agent_port: int,
        agent_path_prefix: str,
        agent_command_scheme: str,
        agent_command_path_prefix: str,
    ) -> None:
        self._secret_key = secret_key
        self._server = DeviceServerInformationRecord(
            host=host,
            port=port,
            ping_endpoint=ping_endpoint,
        )
        self._agent = {
            "scheme": agent_scheme,
            "host": agent_host,
            "port": agent_port,
            "path_prefix": agent_path_prefix,
            "command_scheme": agent_command_scheme,
            "command_path_prefix": agent_command_path_prefix,
        }
        self._devices: Dict[int, DeviceRecord] = {}
        self._next_id = 1

    def list_devices(self) -> List[DeviceRecord]:
        return [self._devices[device_id] for device_id in sorted(self._devices)]

    def get_device(self, device_id: int) -> DeviceRecord:
        device = self._devices.get(device_id)
        if device is None:
            raise KeyError(device_id)
        return device

    def _name_exists(self, name: str, *, exclude_id: Optional[int] = None) -> bool:
        for device in self._devices.values():
            if device.name == name and device.id != exclude_id:
                return True
        return False

    def _get_device_by_name(self, name: str) -> Optional[DeviceRecord]:
        for device in self._devices.values():
            if device.name == name:
                return device
        return None

    def _validate_secret_key(self, secret_key: str) -> None:
        if secret_key != self._secret_key:
            raise PermissionError("secretKey does not match server configuration")

    def _build_device_record(
        self,
        *,
        device_id: int,
        created_at: str,
        device_name: str,
        request: DeviceRegistrationRequest,
    ) -> DeviceRecord:
        token = str(uuid4())
        agent_endpoint = build_agent_endpoint(
            self._agent["scheme"],
            self._agent["host"],
            self._agent["port"],
            self._agent["path_prefix"],
            token,
        )
        agent_command_endpoint = build_agent_command_endpoint(
            self._agent["command_scheme"],
            self._agent["host"],
            self._agent["port"],
            self._agent["command_path_prefix"],
            token,
        )
        seen_track_names = set()
        tracks = []
        for raw_track in request.tracks:
            normalized_track_name = raw_track.name.strip()
            if not normalized_track_name:
                raise ValueError("track name must not be empty")
            stored_track = TrackRecord(
                type=raw_track.type,
                name=normalized_track_name,
                endpoint=build_track_endpoint(token, normalized_track_name, raw_track.type),
            )
            if stored_track.name in seen_track_names:
                raise ValueError("track names must be unique")
            seen_track_names.add(stored_track.name)
            if raw_track.endpoint and raw_track.endpoint != stored_track.endpoint:
                raise ValueError(f"track endpoint mismatch for {stored_track.name}")
            tracks.append(stored_track)

        now = utc_now_iso()
        return DeviceRecord(
            id=device_id,
            token=token,
            name=device_name,
            connected=False,
            created_at=created_at,
            updated_at=now,
            server=self._server,
            agent=DeviceAgentInformationRecord(
                scheme=self._agent["scheme"],
                host=self._agent["host"],
                port=self._agent["port"],
                path_prefix=self._agent["path_prefix"],
                endpoint=agent_endpoint,
                command_endpoint=agent_command_endpoint,
            ),
            tracks=tracks,
            actions=DeviceActionsRecord(
                core=list(request.actions.core),
                custom=list(request.actions.custom),
            ),
            main_video_track_name=resolve_default_main_video_track_name(tracks),
        )

    def register(self, request: DeviceRegistrationRequest) -> DeviceRecord:
        self._validate_secret_key(request.secretKey)
        device_name = request.name.strip()
        if not device_name:
            raise ValueError("device name must not be empty")
        if not request.tracks:
            raise ValueError("tracks must not be empty")

        existing = self._get_device_by_name(device_name)
        if existing is not None:
            device = self._build_device_record(
                device_id=existing.id,
                created_at=existing.created_at,
                device_name=device_name,
                request=request,
            )
            self._devices[existing.id] = device
            return device

        device_id = self._next_id
        self._next_id += 1
        device = self._build_device_record(
            device_id=device_id,
            created_at=utc_now_iso(),
            device_name=device_name,
            request=request,
        )
        self._devices[device_id] = device
        return device

    def rename(self, device_id: int, name: str) -> DeviceRecord:
        device = self.get_device(device_id)
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("device name must not be empty")
        if self._name_exists(normalized_name, exclude_id=device_id):
            raise ValueError("device name already exists")
        device.name = normalized_name
        device.updated_at = utc_now_iso()
        return device

    def update_main_video_track(self, device_id: int, track_name: str) -> DeviceRecord:
        device = self.get_device(device_id)
        normalized_name = track_name.strip()
        if not normalized_name:
            raise ValueError("main video track name must not be empty")
        for track in device.tracks:
            if track.name == normalized_name:
                if track.type != "VIDEO":
                    raise ValueError("main video track must be a VIDEO track")
                device.main_video_track_name = normalized_name
                device.updated_at = utc_now_iso()
                return device
        raise ValueError("specified track does not exist")

    def delete(self, device_id: int) -> None:
        if device_id not in self._devices:
            raise KeyError(device_id)
        del self._devices[device_id]

    def attach_agent(self, device_id: int, request: DeviceAgentRegistrationRequest) -> DeviceRecord:
        self._validate_secret_key(request.secretKey)
        device = self.get_device(device_id)
        now = utc_now_iso()
        if request.endpoint:
            device.agent.endpoint = request.endpoint
        if request.commandEndpoint:
            device.agent.command_endpoint = request.commandEndpoint
        if request.role:
            device.agent.role = request.role
        if request.mode:
            device.agent.mode = request.mode
        if request.skills:
            device.agent.skills = list(request.skills)
        if request.available_actions:
            device.agent.available_actions = list(request.available_actions)
        device.agent.connected = bool(request.connected)
        if device.agent.connected and device.agent.connected_at is None:
            device.agent.connected_at = now
        if not device.agent.connected:
            device.agent.connected_at = device.agent.connected_at or now
        device.agent.last_seen_at = request.last_seen_at or now
        device.updated_at = now
        return device

    def detach_agent(self, device_id: int, secret_key: str) -> DeviceRecord:
        self._validate_secret_key(secret_key)
        device = self.get_device(device_id)
        now = utc_now_iso()
        device.agent.connected = False
        device.agent.last_seen_at = now
        device.updated_at = now
        return device


APP_SETTINGS = load_runtime_config(CONFIG_PATH)

registry = DeviceRegistry(
    secret_key=APP_SETTINGS["secret_key"],
    host=APP_SETTINGS["server"]["host"],
    port=APP_SETTINGS["server"]["port"],
    ping_endpoint=APP_SETTINGS["server"]["ping_endpoint"],
    agent_scheme=APP_SETTINGS["agent"]["scheme"],
    agent_host=APP_SETTINGS["agent"]["host"],
    agent_port=APP_SETTINGS["agent"]["port"],
    agent_path_prefix=APP_SETTINGS["agent"]["path_prefix"],
    agent_command_scheme=APP_SETTINGS["agent"]["command_scheme"],
    agent_command_path_prefix=APP_SETTINGS["agent"]["command_path_prefix"],
)

app = FastAPI(title="CoWater Device Registration Server", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=APP_SETTINGS["cors"]["allow_origins"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/meta")
def meta() -> dict[str, Any]:
    return {
        "server": registry._server.to_dict(),
        "agent": registry._agent,
        "track_types": list(TRACK_TYPES.__args__),
        "core_actions": list(CORE_ACTIONS.__args__),
        "config_path": APP_SETTINGS["config_path"],
        "cors": APP_SETTINGS["cors"],
    }


@app.post("/devices", status_code=status.HTTP_201_CREATED)
def register_device(request: DeviceRegistrationRequest) -> dict[str, Any]:
    try:
        device = registry.register(request)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return device.to_dict()


@app.get("/devices")
def list_devices() -> List[dict[str, Any]]:
    return [device.to_dict() for device in registry.list_devices()]


@app.get("/devices/{device_id}")
def get_device(device_id: int) -> dict[str, Any]:
    try:
        return registry.get_device(device_id).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="device not found") from exc


@app.patch("/devices/{device_id}")
def rename_device(device_id: int, request: DeviceRenameRequest) -> Response:
    try:
        registry.rename(device_id, request.name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="device not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.patch("/devices/{device_id}/main-video-track")
def update_main_video_track(device_id: int, request: MainVideoTrackRequest) -> Response:
    try:
        registry.update_main_video_track(device_id, request.name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="device not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.delete("/devices/{device_id}")
def delete_device(device_id: int) -> Response:
    try:
        registry.delete(device_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="device not found") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.put("/devices/{device_id}/agent")
def upsert_device_agent(device_id: int, request: DeviceAgentRegistrationRequest) -> dict[str, Any]:
    try:
        device = registry.attach_agent(device_id, request)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="device not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return device.to_dict()


@app.delete("/devices/{device_id}/agent")
def detach_device_agent(device_id: int, secretKey: str) -> dict[str, Any]:
    try:
        device = registry.detach_agent(device_id, secretKey)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="device not found") from exc
    return device.to_dict()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", help="Override bind host from config/env")
    parser.add_argument("--port", type=int, help="Override bind port from config/env")
    args = parser.parse_args()
    bind_host = args.host or APP_SETTINGS["server"]["host"]
    bind_port = args.port or APP_SETTINGS["server"]["port"]
    uvicorn.run(
        "device_registration_server:app",
        host=bind_host,
        port=bind_port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
