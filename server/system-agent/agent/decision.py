from __future__ import annotations

from typing import Any

from agent.state import AgentState, utc_now
from skills.catalog import SkillCatalog


class DecisionEngine:
    def __init__(self, agent_config: dict[str, Any], skills: SkillCatalog) -> None:
        self.agent_config = agent_config
        self.skills = skills

    def decide(self, state: AgentState, telemetry: dict[str, Any]) -> dict[str, Any]:
        # Handle both telemetry (for lower agents) and alerts (for system agent)
        if telemetry.get("alert_type"):
            return self._decide_on_alert(state, telemetry)
        return self._decide_on_telemetry(state, telemetry)

    def _decide_on_alert(self, state: AgentState, alert: dict[str, Any]) -> dict[str, Any]:
        """Decision engine for system agent processing alerts"""
        recommendations: list[dict[str, Any]] = []
        actions = set(self.skills.list_actions())
        alert_type = alert.get("alert_type", "unknown")
        severity = str(alert.get("severity") or "INFORMATION").upper()
        metadata = alert.get("metadata", {})

        # Mine detection handling
        if alert_type == "mine_detection":
            if "mission.assign" in actions:
                recommendations.append({
                    "action": "mission.assign",
                    "priority": "critical" if severity == "CRITICAL" else "high",
                    "mission_type": "mine_survey_and_removal",
                    "params": {"location": metadata.get("location", {})}
                })

        # Default to recommended action
        if not recommendations and alert.get("recommended_action"):
            recommended = alert.get("recommended_action", "").lower()
            if "survey" in recommended:
                recommendations.append({
                    "action": "task.assign",
                    "priority": severity,
                    "task_type": "survey_depth",
                    "params": {"location": metadata.get("location", {})}
                })
            elif "remove" in recommended:
                recommendations.append({
                    "action": "task.assign",
                    "priority": severity,
                    "task_type": "remove_mine",
                    "params": {"location": metadata.get("location", {})}
                })

        decision = {
            "at": utc_now(),
            "mode": "rule",
            "llm": self.agent_config.get("llm", {}),
            "recommendations": recommendations,
            "alert_type": alert_type,
            "severity": severity,
        }
        state.last_decision = decision
        return decision

    def _decide_on_telemetry(self, state: AgentState, telemetry: dict[str, Any]) -> dict[str, Any]:
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
