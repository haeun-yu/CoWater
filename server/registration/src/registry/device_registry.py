from __future__ import annotations

import json
import logging
import os
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional
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
    build_healthcheck_endpoint,
    build_track_endpoint,
    device_record_from_dict,
    resolve_default_main_video_track_name,
    utc_now_iso,
)
from src.registry.device_database import DeviceDatabase
from src.registry.healthcheck_monitor import HealthcheckMonitor

logger = logging.getLogger(__name__)


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
        healthcheck_interval_seconds: int = 1,
        healthcheck_timeout_seconds: int = 10,
        healthcheck_timeout_by_device_type: Optional[Dict[str, int]] = None,
        healthcheck_topic_template: str = "agents",
        telemetry_topic_template: str = "device.telemetry.{device_id}.{track_type}",
        db_path: Optional[Path] = None,
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
        self._healthcheck_topic_template = healthcheck_topic_template
        self._telemetry_topic_template = telemetry_topic_template
        self.healthcheck_monitor = HealthcheckMonitor(
            registry=self,
            interval_seconds=healthcheck_interval_seconds,
            timeout_seconds=healthcheck_timeout_seconds,
            timeout_by_device_type=healthcheck_timeout_by_device_type or {},
        )

        # SQLite 영구 저장소
        configured_db_path = os.getenv("COWATER_DEVICE_DB_PATH")
        resolved_db_path = (
            db_path
            or (Path(configured_db_path).expanduser() if configured_db_path else None)
            or Path(__file__).resolve().parents[2] / ".data" / "devices.db"
        )
        self._db = DeviceDatabase(resolved_db_path)

        # DB에서 기존 디바이스 로드
        self._devices: Dict[int, DeviceRecord] = {}
        self._next_id = self._db.load_next_id()
        self._load_from_db()

    def _load_from_db(self) -> None:
        """서버 시작 시 SQLite에서 기존 디바이스 복원"""
        rows = self._db.load_all()
        for device_id, data in rows.items():
            try:
                if "registry_id" not in data:
                    data["registry_id"] = device_id
                device = device_record_from_dict(data)
                # 재시작 후 연결 상태는 offline으로 초기화
                device.connected = False
                device.agent.connected = False
                normalized_healthcheck_topic = "agents"
                normalized_healthcheck_endpoint = build_healthcheck_endpoint(device.id)
                public_id_changed = False
                if not getattr(device, "public_id", None):
                    device.public_id = str(uuid4())
                    public_id_changed = True

                if (
                    public_id_changed
                    or device.healthcheck_topic != normalized_healthcheck_topic
                    or device.healthcheck_endpoint != normalized_healthcheck_endpoint
                ):
                    device.healthcheck_topic = normalized_healthcheck_topic
                    device.healthcheck_endpoint = normalized_healthcheck_endpoint
                    self._persist_device(device)
                self._devices[device_id] = device
            except Exception as e:
                logger.warning(f"디바이스 {device_id} 복원 실패: {e}")
        if self._devices:
            logger.info(f"DB에서 {len(self._devices)}개 디바이스 복원됨")
        # next_id를 DB + 현재 최대 id 기준으로 재계산
        if self._devices:
            self._next_id = max(self._next_id, max(self._devices.keys()) + 1)

    def _persist_device(self, device: DeviceRecord) -> None:
        """디바이스를 SQLite에 저장 (upsert)"""
        try:
            self._db.save_device(
                device_id=device.id,
                name=device.name,
                data=device.to_dict(),
                created_at=device.created_at,
                updated_at=device.updated_at,
            )
        except Exception as e:
            logger.error(f"디바이스 {device.id} DB 저장 실패: {e}")

    def server_dict(self) -> dict[str, object]:
        return self._server.to_dict()

    def agent_dict(self) -> dict[str, object]:
        return dict(self._agent)

    def list_devices(self, limit: int | None = None, offset: int = 0) -> List[DeviceRecord]:
        devices = [self._devices[device_id] for device_id in sorted(self._devices)]
        if offset:
            devices = devices[offset:]
        if limit is not None:
            devices = devices[:limit]
        return devices

    def get_device(self, device_id: Any) -> DeviceRecord:
        internal_id: Optional[int] = None

        if isinstance(device_id, int):
            internal_id = device_id
        elif isinstance(device_id, str):
            if device_id.isdigit() and int(device_id) in self._devices:
                internal_id = int(device_id)
            else:
                for d in self._devices.values():
                    if d.public_id == device_id:
                        return d

        device = self._devices.get(internal_id) if internal_id is not None else None
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
                endpoint=build_track_endpoint(device_id, normalized_track_name, raw_track.type),
            )
            if stored_track.name in seen_track_names:
                raise ValueError("track names must be unique")
            seen_track_names.add(stored_track.name)
            if raw_track.endpoint and raw_track.endpoint != stored_track.endpoint:
                raise ValueError(f"track endpoint mismatch for {stored_track.name}")
            tracks.append(stored_track)

        now = utc_now_iso()
        # 요청에서 위치 정보 추출
        latitude = None
        longitude = None
        if request.location and isinstance(request.location, dict):
            latitude = request.location.get("latitude")
            longitude = request.location.get("longitude")
        altitude = None
        if request.location and isinstance(request.location, dict):
            altitude = request.location.get("altitude")

        # Moth topics 생성 (템플릿 사용) 및 healthcheck endpoint
        healthcheck_topic = self._healthcheck_topic_template.format(device_id=device_id)
        healthcheck_endpoint = build_healthcheck_endpoint(device_id)
        is_submerged = bool(
            request.device_type == "AUV" and isinstance(altitude, (int, float)) and altitude < 0
        )
        environment_state = str(request.environment_state or ("UNDERWATER" if is_submerged else "SURFACE"))
        active_mediums = list(
            request.active_mediums
            or (["ACOUSTIC"] if is_submerged else ["RF", "INTERNET", "ACOUSTIC"])
        )
        parent_gateway_agent_id = None
        if request.parent_id is not None:
            parent_device = self.get_device(request.parent_id)
            if parent_device is not None:
                parent_gateway_agent_id = parent_device.agent.agent_id
        gateway_agent_id = request.gateway_agent_id or parent_gateway_agent_id
        telemetry_topics = [
            {
                "track_type": track.type,
                "track_name": track.name,
                "topic": self._telemetry_topic_template.format(device_id=device_id, track_type=track.type)
            }
            for track in tracks
        ]

        return DeviceRecord(
            id=device_id,
            public_id=str(uuid4()),
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
                agent_id=None,
                latitude=latitude,
                longitude=longitude,
                battery_percent=getattr(request, "battery_percent", None),
                gateway_agent_id=gateway_agent_id,
                environment_state=environment_state,
                active_mediums=active_mediums,
            ),
            tracks=tracks,
            actions=DeviceActionsRecord(
                core=list(request.actions.core),
                custom=list(request.actions.custom),
            ),
            main_video_track_name=resolve_default_main_video_track_name(tracks),
            device_type=request.device_type,
            layer=request.layer,
            connectivity=request.connectivity,
            latitude=latitude,
            longitude=longitude,
            parent_id=request.parent_id,
            last_location_update=now if (latitude is not None or longitude is not None) else None,
            target_type=None,
            target_id=None,
            healthcheck_topic=healthcheck_topic,
            healthcheck_endpoint=healthcheck_endpoint,
            telemetry_topics=telemetry_topics,
            is_submerged=is_submerged,
            force_parent_routing=bool(request.device_type == "ROV"),
        )

    def _find_middle_parent(self, child: DeviceRecord, *, exclude_id: Optional[int] = None) -> Optional[DeviceRecord]:
        candidates = [
            device
            for device in self.list_devices()
            if device.layer == "middle" and device.connected and device.id != exclude_id
        ]
        if not candidates:
            return None
        if child.latitude is None or child.longitude is None:
            return candidates[0]

        def distance_key(parent: DeviceRecord) -> float:
            if parent.latitude is None or parent.longitude is None:
                return float("inf")
            lat_delta = child.latitude - parent.latitude
            lon_delta = child.longitude - parent.longitude
            return lat_delta * lat_delta + lon_delta * lon_delta

        return min(candidates, key=distance_key)

    def _apply_server_parent_assignment(self, device: DeviceRecord) -> None:
        if device.layer != "lower":
            device.parent_id = None
            device.force_parent_routing = False
            device.agent.gateway_agent_id = None
            return

        if device.device_type == "AUV" and not device.is_submerged:
            device.parent_id = None
            device.force_parent_routing = False
            device.agent.gateway_agent_id = None
            device.agent.environment_state = "SURFACE"
            device.agent.active_mediums = ["RF", "INTERNET", "ACOUSTIC"]
            return

        parent = self._find_middle_parent(device)
        device.parent_id = parent.id if parent else None
        device.force_parent_routing = device.device_type == "ROV"
        device.agent.gateway_agent_id = parent.agent.agent_id if parent and parent.agent.agent_id else None
        device.agent.environment_state = "UNDERWATER" if device.is_submerged else "SURFACE"
        device.agent.active_mediums = ["ACOUSTIC"] if device.is_submerged else ["RF", "INTERNET", "ACOUSTIC"]

    def _routing_assignment(self, device: DeviceRecord) -> dict[str, Any]:
        parent = self._devices.get(device.parent_id) if device.parent_id is not None else None
        route_mode = "via_parent" if parent else "direct_to_system"
        if device.device_type == "ROV" and parent is None:
            route_mode = "parent_required_unassigned"
        elif device.device_type == "AUV" and device.is_submerged and parent is None:
            route_mode = "acoustic_parent_unassigned"
        return {
            "message_type": "layer.assignment",
            "device_id": device.id,
            "device_name": device.name,
            "device_type": device.device_type,
            "layer": device.layer,
            "environment_state": device.agent.environment_state,
            "active_mediums": list(device.agent.active_mediums or []),
            "gateway_agent_id": device.agent.gateway_agent_id,
            "route_mode": route_mode,
            "parent_id": parent.id if parent else None,
            "parent_name": parent.name if parent else None,
            "parent_agent_id": parent.agent.agent_id if parent and parent.agent.agent_id else None,
            "parent_endpoint": parent.agent.endpoint if parent else None,
            "parent_command_endpoint": parent.agent.command_endpoint if parent else None,
            "force_parent_routing": device.force_parent_routing,
            "is_submerged": device.is_submerged,
            "a2a": {
                "endpoint": device.agent.endpoint,
                "command_endpoint": device.agent.command_endpoint,
            },
        }

    def assignment_for(self, device_id: Any) -> dict[str, Any]:
        return self._routing_assignment(self.get_device(device_id))

    def notify_assignment(self, assignment: dict[str, Any]) -> None:
        endpoint = assignment.get("a2a", {}).get("endpoint")
        if not endpoint:
            return
        body = {
            "message": {
                "role": "server",
                "parts": [{"type": "data", "data": assignment}],
            },
            "metadata": {"source": "device-registration-server"},
        }
        try:
            req = urllib.request.Request(
                f"{str(endpoint).rstrip('/')}/message:send",
                data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=0.5).close()
        except Exception:
            pass

    def _refresh_lower_assignments(self, *, exclude_parent_id: Optional[int] = None) -> list[dict[str, Any]]:
        changed: list[dict[str, Any]] = []
        for device in self.list_devices():
            if device.layer != "lower":
                continue
            previous_parent_id = device.parent_id
            previous_force = device.force_parent_routing
            if device.device_type == "AUV" and not device.is_submerged:
                parent = None
            else:
                parent = self._find_middle_parent(device, exclude_id=exclude_parent_id)
            device.parent_id = parent.id if parent else None
            device.force_parent_routing = device.device_type == "ROV"
            device.agent.gateway_agent_id = parent.agent.agent_id if parent and parent.agent.agent_id else None
            if previous_parent_id != device.parent_id or previous_force != device.force_parent_routing:
                device.updated_at = utc_now_iso()
                self._persist_device(device)
                changed.append(self._routing_assignment(device))
        return changed

    def register(self, request: DeviceRegistrationRequest) -> DeviceRecord:
        self._validate_secret_key(request.secretKey)
        device_name = request.name.strip()
        if not device_name:
            raise ValueError("device name must not be empty")
        # System layer는 센서를 가지지 않을 수 있으므로 tracks 검증을 스킵
        is_system_layer = str(request.layer or "").lower() == "system"
        if not request.tracks and not is_system_layer:
            raise ValueError("tracks must not be empty")

        existing = self._get_device_by_name(device_name)
        if existing is not None:
            device = self._build_device_record(
                device_id=existing.id,
                created_at=existing.created_at,
                device_name=device_name,
                request=request,
            )
            self._apply_server_parent_assignment(device)
            self._devices[existing.id] = device
            self._persist_device(device)
            if device.layer == "middle":
                self._refresh_lower_assignments()
            return device

        device_id = self._next_id
        self._next_id += 1
        self._db.save_next_id(self._next_id)
        device = self._build_device_record(
            device_id=device_id,
            created_at=utc_now_iso(),
            device_name=device_name,
            request=request,
        )
        self._apply_server_parent_assignment(device)
        self._devices[device_id] = device
        self._persist_device(device)
        if device.layer == "middle":
            self._refresh_lower_assignments()
        return device

    def rename(self, device_id: Any, name: str) -> DeviceRecord:
        device = self.get_device(device_id)
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("device name must not be empty")
        if self._name_exists(normalized_name, exclude_id=device.id):
            raise ValueError("device name already exists")
        device.name = normalized_name
        device.updated_at = utc_now_iso()
        self._persist_device(device)
        return device

    def update_main_video_track(self, device_id: Any, track_name: str) -> DeviceRecord:
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
                self._persist_device(device)
                return device
        raise ValueError("specified track does not exist")

    def delete(self, device_id: Any) -> None:
        device = self.get_device(device_id)
        del self._devices[device.id]
        self._db.delete_device(device.id)
        if device.layer == "middle":
            for assignment in self._refresh_lower_assignments(exclude_parent_id=device.id):
                self.notify_assignment(assignment)

    def attach_agent(self, device_id: Any, request: DeviceAgentRegistrationRequest) -> DeviceRecord:
        self._validate_secret_key(request.secretKey)
        device = self.get_device(device_id)
        now = utc_now_iso()
        if request.agent_id:
            device.agent.agent_id = request.agent_id
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
        if device.agent.connected:
            device.connectivity_status = "online"
            if device.agent.connected_at is None:
                device.agent.connected_at = now
        device.agent.last_seen_at = request.last_seen_at or now
        
        # P3 (보고 기반): Device가 주기적으로 보고한 위치와 배터리 정보를 저장
        if request.latitude is not None:
            device.agent.latitude = request.latitude
            device.latitude = request.latitude
            device.last_location_update = now
        if request.longitude is not None:
            device.agent.longitude = request.longitude
            device.longitude = request.longitude
            device.last_location_update = now
        if request.battery_percent is not None:
            device.agent.battery_percent = request.battery_percent
            device.last_battery_percent = request.battery_percent
            device.last_battery_update = now
        if request.gateway_agent_id is not None:
            device.agent.gateway_agent_id = request.gateway_agent_id
        if request.environment_state is not None:
            device.agent.environment_state = request.environment_state
        if request.active_mediums:
            device.agent.active_mediums = list(request.active_mediums)
        
        device.updated_at = now
        self._persist_device(device)
        assignments = [self._routing_assignment(device)]
        if device.layer == "middle":
            assignments.extend(self._refresh_lower_assignments())
        for assignment in assignments:
            self.notify_assignment(assignment)
        return device

    def detach_agent(self, device_id: Any, secret_key: str) -> DeviceRecord:
        self._validate_secret_key(secret_key)
        device = self.get_device(device_id)
        now = utc_now_iso()
        device.agent.connected = False
        device.connected = False
        device.connectivity_status = "offline"
        device.agent.last_seen_at = now
        device.updated_at = now
        self._persist_device(device)
        return device

    def update_device_location(self, device_id: Any, latitude: float, longitude: float) -> DeviceRecord:
        """디바이스 위치 정보 업데이트 (POC 01-05 에이전트의 텔레메트리 기반)"""
        device = self.get_device(device_id)
        device.latitude = latitude
        device.longitude = longitude
        device.last_location_update = utc_now_iso()
        device.updated_at = device.last_location_update
        if device.layer == "lower":
            self._apply_server_parent_assignment(device)
        self._persist_device(device)
        if device.layer == "middle":
            for assignment in self._refresh_lower_assignments():
                self.notify_assignment(assignment)
        elif device.layer == "lower":
            self.notify_assignment(self._routing_assignment(device))
        return device

    def update_device_metadata(self, device_id: Any, *, device_type: Optional[str] = None,
                              layer: Optional[str] = None, connectivity: Optional[str] = None) -> DeviceRecord:
        """디바이스 메타데이터 업데이트"""
        device = self.get_device(device_id)
        if device_type is not None:
            device.device_type = device_type
        if layer is not None:
            device.layer = layer
        if connectivity is not None:
            device.connectivity = connectivity
        device.updated_at = utc_now_iso()
        self._apply_server_parent_assignment(device)
        self._persist_device(device)
        return device

    def update_auv_submersion(self, device_id: Any, is_submerged: bool) -> DeviceRecord:
        """AUV 수중/수면 상태 업데이트"""
        device = self.get_device(device_id)
        if device.device_type != "AUV":
            raise ValueError("Only AUV devices can be marked as submerged")

        now = utc_now_iso()
        device.is_submerged = is_submerged
        if is_submerged:
            device.submerged_at = now
            parent = self._find_middle_parent(device)
            device.parent_id = parent.id if parent else None
            device.agent.environment_state = "UNDERWATER"
            device.agent.active_mediums = ["ACOUSTIC"]
            device.agent.gateway_agent_id = parent.agent.agent_id if parent and parent.agent.agent_id else None
        else:
            device.surfaced_at = now
            device.parent_id = None
            device.agent.environment_state = "SURFACE"
            device.agent.active_mediums = ["RF", "INTERNET", "ACOUSTIC"]
            device.agent.gateway_agent_id = None
        device.force_parent_routing = False
        device.updated_at = now
        self._persist_device(device)
        return device

    def update_device_connectivity_state(
        self,
        device_id: Any,
        *,
        parent_id: Optional[Any] = None,
        force_parent_routing: bool = False
    ) -> DeviceRecord:
        """
        디바이스 연결 상태 업데이트

        - ROV: 반드시 parent_id를 통한 유선 연결
          → parent_id는 어떤 middle layer 에이전트든 가능 (Control Ship, Control USV 등)
          → force_parent_routing=True로 설정되어 모든 통신이 parent를 통함
        - AUV: 수중 시에만 parent_id를 통한 연결 (자동으로 관리됨)
        """
        device = self.get_device(device_id)

        # ROV: 유선 연결 강제 (parent는 어떤 middle layer든 가능)
        if device.device_type == "ROV":
            if parent_id is None:
                raise ValueError("ROV must have parent_id for wired connection")
            parent_device = self.get_device(parent_id)
            if parent_device.layer != "middle":
                raise ValueError("ROV parent must be a middle layer device")
            device.parent_id = parent_id
            device.force_parent_routing = True
            device.agent.gateway_agent_id = parent_device.agent.agent_id if parent_device.agent.agent_id else None
            device.agent.environment_state = "UNDERWATER" if device.is_submerged else "SURFACE"
            device.agent.active_mediums = ["WIRED"]

        # AUV: 수중 시만 parent 연결
        elif device.device_type == "AUV":
            if device.is_submerged:
                if parent_id is None:
                    parent = self._find_middle_parent(device)
                    device.parent_id = parent.id if parent else None
                    parent_device = parent
                else:
                    parent_device = self.get_device(parent_id)
                    if parent_device.layer != "middle":
                        raise ValueError("AUV acoustic parent must be a middle layer device")
                    device.parent_id = parent_id
                device.agent.gateway_agent_id = parent_device.agent.agent_id if parent_device.agent.agent_id else None
                device.agent.environment_state = "UNDERWATER"
                device.agent.active_mediums = ["ACOUSTIC"]
            else:
                device.parent_id = None
                device.agent.gateway_agent_id = None
                device.agent.environment_state = "SURFACE"
                device.agent.active_mediums = ["RF", "INTERNET", "ACOUSTIC"]

        # 기타 디바이스
        else:
            if parent_id is not None:
                device.parent_id = parent_id
                parent_device = self.get_device(parent_id)
                device.agent.gateway_agent_id = parent_device.agent.agent_id if parent_device.agent.agent_id else None
            else:
                device.agent.gateway_agent_id = None
            device.agent.environment_state = "SURFACE"
            device.agent.active_mediums = ["RF", "INTERNET", "ACOUSTIC"]

        if device.device_type != "ROV":
            device.force_parent_routing = force_parent_routing
        device.updated_at = utc_now_iso()
        self._persist_device(device)
        return device

    def reset(self) -> None:
        """모든 디바이스 초기화 (데이터베이스 삭제)"""
        self._devices.clear()
        self._db.clear()
        self._next_id = 1
