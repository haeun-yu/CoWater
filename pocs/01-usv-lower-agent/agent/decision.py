from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from agent.state import AgentState, utc_now
from skills.catalog import SkillCatalog

try:
    from shared.llm_client import make_llm_client
except ImportError:
    make_llm_client = None

logger = logging.getLogger(__name__)


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
                logger.error(f"Failed to initialize LLM client: {e}")
                self.llm_enabled = False

    def decide(self, state: AgentState, telemetry: dict[str, Any]) -> dict[str, Any]:
        """Make decision based on rules and telemetry"""
        actions = set(self.skills.list_actions())
        rules = self.agent_config.get("rules", {})
        battery_warn = float(rules.get("battery_warn_percent", 30))
        max_speed = float(rules.get("max_speed_mps", 999))
        speed = float((telemetry.get("motion") or {}).get("speed") or 0)
        battery = float(telemetry.get("battery_percent") or 100)
        recommendations: list[dict[str, Any]] = []

        # Rule-based decisions (always executed)
        if "slow_down" in actions and speed > max_speed:
            recommendations.append({
                "action": "slow_down",
                "priority": "high",
                "confidence": 0.95,
                "source": "rule",
                "params": {"target_speed_mps": max_speed},
            })
        if "return_to_base" in actions and battery < battery_warn:
            recommendations.append({
                "action": "return_to_base",
                "priority": "high",
                "confidence": 0.95,
                "source": "rule",
                "params": {"battery_percent": battery},
            })
        if state.layer == "middle" and state.children:
            recommendations.append({
                "action": "coordinate_children",
                "priority": "normal",
                "confidence": 0.8,
                "source": "rule",
                "params": {"child_count": len(state.children)},
            })

        decision = {
            "at": utc_now(),
            "mode": "rule",
            "llm_enabled": self.llm_enabled,
            "recommendations": recommendations,
            "llm_analysis": None,
        }

        # LLM analysis (async, non-blocking)
        if self.llm_enabled and self.llm_client and recommendations:
            asyncio.create_task(self._analyze_with_llm(state, telemetry, recommendations, decision))

        state.last_decision = decision
        return decision

    async def _analyze_with_llm(
        self,
        state: AgentState,
        telemetry: dict[str, Any],
        rule_recs: list[dict[str, Any]],
        decision: dict[str, Any],
    ) -> None:
        """Analyze situation with LLM (async, non-blocking)"""
        try:
            prompt = self._build_llm_prompt(state, telemetry, rule_recs)
            timeout = self.agent_config.get("llm", {}).get("timeout_seconds", 30)

            response = await self.llm_client.generate(prompt=prompt, timeout=timeout)

            decision["llm_analysis"] = {
                "timestamp": utc_now(),
                "response": response[:200] if response else "No response",
                "source": "llm",
            }
        except Exception as e:
            logger.debug(f"LLM analysis error: {e}")
            decision["llm_analysis"] = {"error": str(e), "timestamp": utc_now()}

    def _build_llm_prompt(self, state: AgentState, telemetry: dict[str, Any], rule_recs: list[dict[str, Any]]) -> str:
        """Build LLM prompt from current situation"""
        return f"""You are a {state.device_type} agent operating at {state.layer} layer.

Current Status:
- Device: {state.agent_id}
- Battery: {telemetry.get('battery_percent', 'unknown')}%
- Layer: {state.layer}

Telemetry Summary:
- Speed: {(telemetry.get('motion') or {}).get('speed', 0)} m/s
- Battery: {telemetry.get('battery_percent', 100)}%

Rule-Based Recommendations:
{json.dumps(rule_recs, indent=2)}

Analyze briefly: Are there any anomalies? Any additional recommendations? Keep response under 100 words."""
