from __future__ import annotations

from typing import Dict, List, Optional
from uuid import uuid4

from src.core.models import (
    DeviceActionsRecord,
    DeviceAgentInformationRecord,
    DeviceAgentRegistrationRequest,
    DeviceRecord,
    DeviceRegistrationRequest,
    DeviceServerInformationRecord,
    TrackRecord,
    build_agent_command_endpoint,
    build_agent_endpoint,
    build_track_endpoint,
    resolve_default_main_video_track_name,
    utc_now_iso,
)


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
        self._server = DeviceServerInformationRecord(host=host, port=port, ping_endpoint=ping_endpoint)
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

    def server_dict(self) -> dict[str, object]:
        return self._server.to_dict()

    def agent_dict(self) -> dict[str, object]:
        return dict(self._agent)

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
        tracks: List[TrackRecord] = []
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
        device.agent.llm_enabled = bool(request.llm_enabled)
        if request.skills:
            device.agent.skills = list(request.skills)
        if request.available_actions:
            device.agent.available_actions = list(request.available_actions)
        device.agent.connected = bool(request.connected)
        device.connected = bool(request.connected)
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
        device.connected = False
        device.agent.last_seen_at = now
        device.updated_at = now
        return device
