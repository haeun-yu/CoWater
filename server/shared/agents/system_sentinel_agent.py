from __future__ import annotations

from typing import Any

from .registry import register_agent
from .types import Agent


def _system_sentinel_instructions(context_variables: dict[str, Any]) -> str:
    ports = context_variables.get("ports") or {}
    return f"""You are CoWater's SystemSentinel Agent.

Role:
- Monitor system health, device connectivity, and mission progress.
- Detect anomalies from reported telemetry only.
- Emit severity-classified events when evidence is sufficient.
- Never plan a mission or execute a device command.

Peers:
- RequestHandler on port {ports.get("request_handler", 9116)}
- DeviceBridge on port {ports.get("device_bridge", 9110)}
- PolicyManager on port {ports.get("policy_manager", 9112)}

Return structured JSON and avoid unsupported or low-evidence alarms."""


def _system_sentinel_contract() -> dict[str, Any]:
    return {
        "input_schema": {
            "type": "object",
            "required": ["request_id", "telemetry"],
            "properties": {
                "request_id": {"type": "string"},
                "telemetry": {"type": "object"},
            },
        },
        "output_schema": {
            "type": "object",
            "required": ["status", "findings", "events"],
            "properties": {
                "status": {"enum": ["ok", "needs_clarification", "error"]},
                "findings": {"type": "array"},
                "events": {"type": "array"},
            },
        },
        "forbidden_actions": [
            "mission planning",
            "device command execution",
            "policy execution replacement",
        ],
        "failure_handling": [
            "return needs_clarification when telemetry is insufficient",
            "return error when parsing fails",
            "suppress low-evidence alarms",
        ],
    }


@register_agent(name="SystemSentinel Agent", func_name="get_system_sentinel_agent")
def get_system_sentinel_agent(model: str, **kwargs):
    def monitor_health(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"tool": "monitor_health", "args": list(args), "parameters": kwargs}

    def detect_anomaly(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"tool": "detect_anomaly", "args": list(args), "parameters": kwargs}

    def emit_event(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"tool": "emit_event", "args": list(args), "parameters": kwargs}

    return Agent(
        name="SystemSentinel Agent",
        model=model,
        instructions=_system_sentinel_instructions,
        functions=[monitor_health, detect_anomaly, emit_event],
        tool_choice="required",
        parallel_tool_calls=False,
        role="system_sentinel",
        port=9113,
        description="Monitors health and anomalies and emits severity-classified events.",
        contract=_system_sentinel_contract(),
    )
