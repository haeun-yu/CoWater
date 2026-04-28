from __future__ import annotations

from typing import Any

from agent.state import AgentState, utc_now
from skills.catalog import SkillCatalog


class ManifestBuilder:
    def __init__(self, config: dict[str, Any], skills: SkillCatalog) -> None:
        self.config = config
        self.skills = skills

    def base_url(self) -> str:
        server = self.config.get("server", {})
        host = str(server.get("public_host") or server.get("host") or "127.0.0.1")
        port = int(server.get("port") or 9010)
        return f"http://{host}:{port}"

    def agent_card(self, state: AgentState) -> dict[str, Any]:
        return {
            "name": state.agent_id,
            "displayName": state.name,
            "description": self.config.get("agent", {}).get("description") or "CoWater standalone PoC Agent",
            "url": self.base_url(),
            "version": "1.0.0",
            "protocolVersion": "0.2.6",
            "capabilities": {"streaming": False, "pushNotifications": False},
            "defaultInputModes": ["application/json"],
            "defaultOutputModes": ["application/json"],
            "skills": [
                {"id": item, "name": item.replace("_", " ").title()}
                for item in self.skills.list_skills()
            ],
            "metadata": {
                "role": state.role,
                "layer": state.layer,
                "device_type": state.device_type,
                "tools": self.config.get("agent", {}).get("capabilities", {}).get("tools", []),
                "constraints": self.skills.list_constraints(),
            },
        }

    def manifest(self, state: AgentState) -> dict[str, Any]:
        token = state.token or "token"
        return {
            "agent_id": state.agent_id,
            "role": state.role,
            "layer": state.layer,
            "device_type": state.device_type,
            "endpoint": self.base_url(),
            "command_endpoint": f"{self.base_url()}/agents/{token}/command",
            "skills": self.skills.list_skills(),
            "tools": self.config.get("agent", {}).get("capabilities", {}).get("tools", []),
            "available_actions": self.skills.list_actions(),
            "constraints": self.skills.list_constraints(),
            "children_required": bool(self.config.get("agent", {}).get("children_required", False)),
            "updated_at": utc_now(),
        }

