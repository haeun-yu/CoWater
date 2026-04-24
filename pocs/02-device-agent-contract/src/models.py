from __future__ import annotations

# 02 에이전트 허브에서 주고받는 상태, 추천, 명령의 데이터 구조를 정의한다.

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AgentRecommendationRecord:
    action: str
    reason: str
    priority: str = "normal"
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DeviceAgentStateRecord:
    token: str
    device_id: Optional[str] = None
    device_name: Optional[str] = None
    device_type: Optional[str] = None
    registry_id: Optional[int] = None
    registry_token: Optional[str] = None
    registry_endpoint: Optional[str] = None
    registry_command_endpoint: Optional[str] = None
    agent_mode: str = "dynamic"
    llm_optional: bool = True
    supported_modes: List[str] = field(default_factory=list)
    available_actions: List[str] = field(default_factory=list)
    skills: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    connected: bool = False
    connected_at: Optional[str] = None
    last_seen_at: Optional[str] = None
    last_stream: Optional[str] = None
    last_payload: Optional[dict[str, Any]] = None
    home_position: Optional[dict[str, Any]] = None
    context: Dict[str, Any] = field(default_factory=dict)
    memory: List[dict[str, Any]] = field(default_factory=list)
    recommendations: List[AgentRecommendationRecord] = field(default_factory=list)
    pending_commands: List[dict[str, Any]] = field(default_factory=list)
    websocket: Any = field(default=None, repr=False, compare=False)

    def remember(self, item: dict[str, Any]) -> None:
        self.memory.append(item)
        self.memory = self.memory[-50:]

    def to_dict(self) -> dict[str, Any]:
        return {
            "token": self.token,
            "device_id": self.device_id,
            "device_name": self.device_name,
            "device_type": self.device_type,
            "registry_id": self.registry_id,
            "registry_token": self.registry_token,
            "registry_endpoint": self.registry_endpoint,
            "registry_command_endpoint": self.registry_command_endpoint,
            "agent_mode": self.agent_mode,
            "llm_optional": self.llm_optional,
            "supported_modes": list(self.supported_modes),
            "available_actions": list(self.available_actions),
            "skills": list(self.skills),
            "tools": list(self.tools),
            "constraints": list(self.constraints),
            "connected": self.connected,
            "connected_at": self.connected_at,
            "last_seen_at": self.last_seen_at,
            "last_stream": self.last_stream,
            "last_payload": self.last_payload,
            "home_position": self.home_position,
            "context": self.context,
            "memory": list(self.memory[-10:]),
            "recommendations": [item.to_dict() for item in self.recommendations[-20:]],
            "pending_commands": list(self.pending_commands[-20:]),
        }


class DeviceCommandRequest(BaseModel):
    action: str
    reason: Optional[str] = None
    priority: str = "normal"
    params: Dict[str, Any] = Field(default_factory=dict)
