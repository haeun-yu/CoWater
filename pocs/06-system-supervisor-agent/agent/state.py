from __future__ import annotations

from dataclasses import asdict, dataclass, field
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
    token: Optional[str] = None
    registry_id: Optional[int] = None
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
        self.memory = self.memory[-100:]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["children"] = list(self.children.values())
        data["tasks"] = list(self.tasks.values())
        data["inbox"] = self.inbox[-50:]
        data["outbox"] = self.outbox[-50:]
        data["memory"] = self.memory[-30:]
        return data

