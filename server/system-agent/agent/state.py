from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AgentState:
    agent_id: str
    role: str
    layer: str
    instance_id: str
    name: str
    device_type: Optional[str] = None
    parent_id: Optional[int] = None
    parent_endpoint: Optional[str] = None
    parent_command_endpoint: Optional[str] = None
    route_mode: str = "direct_to_system"
    force_parent_routing: bool = False
    token: Optional[str] = None
    registry_id: Optional[int] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    connected: bool = False
    registered_at: Optional[str] = None
    last_seen_at: Optional[str] = None
    last_telemetry: dict[str, Any] = field(default_factory=dict)
    last_decision: dict[str, Any] = field(default_factory=dict)
    children: dict[str, dict[str, Any]] = field(default_factory=dict)
    tasks: dict[str, dict[str, Any]] = field(default_factory=dict)
    inbox: list[dict[str, Any]] = field(default_factory=list)
    outbox: list[dict[str, Any]] = field(default_factory=list)
    memory: list[dict[str, Any]] = field(default_factory=list)

    def remember(self, item: dict[str, Any]) -> None:
        self.memory.append(item)
        trim = getattr(self.memory, "trim", None)
        if callable(trim):
            trim(100)
        else:
            self.memory = self.memory[-100:]

    def to_dict(self) -> dict[str, Any]:
        def _snapshot_mapping(value: Any) -> list[dict[str, Any]]:
            snapshot = getattr(value, "snapshot", None)
            if callable(snapshot):
                return list(snapshot().values())
            values = getattr(value, "values", None)
            if callable(values):
                return list(values())
            return list(value)

        def _snapshot_list(value: Any, limit: int) -> list[dict[str, Any]]:
            snapshot = getattr(value, "snapshot", None)
            if callable(snapshot):
                return list(snapshot(limit))
            return list(value[-limit:])

        data = {
            "agent_id": self.agent_id,
            "role": self.role,
            "layer": self.layer,
            "instance_id": self.instance_id,
            "name": self.name,
            "device_type": self.device_type,
            "parent_id": self.parent_id,
            "parent_endpoint": self.parent_endpoint,
            "parent_command_endpoint": self.parent_command_endpoint,
            "route_mode": self.route_mode,
            "force_parent_routing": self.force_parent_routing,
            "token": self.token,
            "registry_id": self.registry_id,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "connected": self.connected,
            "registered_at": self.registered_at,
            "last_seen_at": self.last_seen_at,
            "last_telemetry": self.last_telemetry,
            "last_decision": self.last_decision,
        }
        data["children"] = _snapshot_mapping(self.children)
        data["tasks"] = _snapshot_mapping(self.tasks)
        data["inbox"] = _snapshot_list(self.inbox, 50)
        data["outbox"] = _snapshot_list(self.outbox, 50)
        data["memory"] = _snapshot_list(self.memory, 30)
        return data
