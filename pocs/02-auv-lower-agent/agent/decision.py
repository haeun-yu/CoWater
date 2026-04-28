from __future__ import annotations

import asyncio
import json
import logging

from typing import Any

from agent.state import AgentState, utc_now
from skills.catalog import SkillCatalog

try:
    from shared.llm_client import make_llm_client
except ImportError:
    make_llm_client = None


class DecisionEngine:
    def __init__(self, agent_config: dict[str, Any], skills: SkillCatalog) -> None:
        self.agent_config = agent_config
        self.skills = skills
        self.llm_enabled = agent_config.get("llm", {}).get("enabled", False)
        self.llm_client = None

        if self.llm_enabled and make_llm_client:
            try:
                self.llm_client = make_llm_client(agent_config.get("llm", {}))
            except Exception as e:
                self.llm_enabled = False

    def decide(self, state: AgentState, telemetry: dict[str, Any]) -> dict[str, Any]:
        actions = set(self.skills.list_actions())
        rules = self.agent_config.get("rules", {})
        battery_warn = float(rules.get("battery_warn_percent", 30))
        max_speed = float(rules.get("max_speed_mps", 999))
        speed = float((telemetry.get("motion") or {}).get("speed") or 0)
        battery = float(telemetry.get("battery_percent") or 100)
        recommendations: list[dict[str, Any]] = []

        if "slow_down" in actions and speed > max_speed:
            recommendations.append(
                {"action": "slow_down", "priority": "high", "params": {"target_speed_mps": max_speed}}
            )
        if "return_to_base" in actions and battery < battery_warn:
            recommendations.append(
                {"action": "return_to_base", "priority": "high", "params": {"battery_percent": battery}}
            )
        if state.layer == "middle" and state.children:
            recommendations.append(
                {"action": "coordinate_children", "priority": "normal", "params": {"child_count": len(state.children)}}
            )

        decision = {
            "at": utc_now(),
            "mode": "rule",
            "llm": self.agent_config.get("llm", {}),
            "recommendations": recommendations,
        }
        state.last_decision = decision
        return decision

