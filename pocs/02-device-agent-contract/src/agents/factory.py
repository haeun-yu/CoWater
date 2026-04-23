from __future__ import annotations

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
