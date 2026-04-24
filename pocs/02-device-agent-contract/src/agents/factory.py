from __future__ import annotations

# 디바이스 타입에 맞는 Agent 구현체를 선택해서 생성한다.

from typing import Any

from .auv import AUVAgent
from .base import DeviceAgentBase
from .rov import ROVAgent
from .usv import USVAgent


def create_agent(device_type: str | None, profiles: dict[str, dict[str, Any]]) -> DeviceAgentBase:
    normalized = (device_type or "usv").lower()
    if normalized == "auv":
        return AUVAgent(profiles)
    if normalized == "rov":
        return ROVAgent(profiles)
    return USVAgent(profiles)
