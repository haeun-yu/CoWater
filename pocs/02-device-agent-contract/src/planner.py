from __future__ import annotations

from typing import Any

from .agents import DeviceAgentBase, create_agent


class AgentPlanner:
    """Compatibility wrapper that delegates planning to a type-specific Agent."""

    def __init__(self, profiles: dict[str, dict[str, Any]]) -> None:
        self._profiles = profiles

    def agent(self, device_type: str | None) -> DeviceAgentBase:
        return create_agent(device_type, self._profiles)

    def profile(self, device_type: str | None) -> dict[str, Any]:
        return self.agent(device_type).profile()

    def apply_profile(self, session, device_type: str | None) -> None:
        self.agent(device_type).apply_profile(session)
