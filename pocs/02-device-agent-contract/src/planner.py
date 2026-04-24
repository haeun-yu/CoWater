from __future__ import annotations

# 타입별 Agent에게 계획 생성을 위임하는 호환 래퍼를 제공한다.

from typing import Any

from .agents import DeviceAgentBase, create_agent


class AgentPlanner:
    """타입별 Agent에게 계획 생성을 위임하는 호환 래퍼."""

    def __init__(self, profiles: dict[str, dict[str, Any]]) -> None:
        self._profiles = profiles

    def agent(self, device_type: str | None) -> DeviceAgentBase:
        return create_agent(device_type, self._profiles)

    def profile(self, device_type: str | None) -> dict[str, Any]:
        return self.agent(device_type).profile()

    def apply_profile(self, session, device_type: str | None) -> None:
        self.agent(device_type).apply_profile(session)
