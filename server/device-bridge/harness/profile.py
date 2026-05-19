from __future__ import annotations

from typing import Any

from shared.agents.registry import register_agent
from shared.agents.types import Agent


def _device_bridge_instructions(context: dict[str, Any]) -> str:
    ports = context.get("ports") or {}
    return f"""You are CoWater's DeviceBridge Agent.

Role:
- Relay task dispatch, result collection, and healthcheck state.
- Normalize connection state and task result payloads.
- Never design missions or decide policy.
- Never infer device internals from partial data.

Peers:
- RequestHandler on port {ports.get("request_handler", 9116)}
- MissionPlanner on port {ports.get("mission_planner", 9111)}
- SystemSentinel on port {ports.get("system_sentinel", 9113)}

Return only structured JSON for forwarding, collection, and normalization."""


def _device_bridge_contract() -> dict[str, Any]:
    return {
        "input_schema": {
            "type": "object",
            "required": ["request_id", "action", "target_device"],
            "properties": {
                "request_id": {"type": "string"},
                "action": {"enum": ["dispatch_task", "relay_healthcheck", "collect_result", "ping"]},
                "target_device": {"type": "object"},
            },
        },
        "output_schema": {
            "type": "object",
            "required": ["status", "connection", "payload"],
            "properties": {
                "status": {"enum": ["ok", "error"]},
                "connection": {"type": "object"},
                "payload": {"type": "object"},
            },
        },
        "forbidden_actions": [
            "mission design",
            "policy decision",
            "report writing",
            "device-state inference beyond reported data",
        ],
        "failure_handling": [
            "return error on connection failure",
            "return error on malformed payloads",
            "normalize timeouts explicitly",
        ],
    }


@register_agent(name="DeviceBridge Agent", func_name="get_device_bridge_agent")
def get_device_bridge_agent(model: str, **kwargs) -> Agent:
    ports = kwargs.get("ports") or {}

    def dispatch_task(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"tool": "dispatch_task", "args": list(args), "parameters": kwargs}

    def collect_result(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"tool": "collect_result", "args": list(args), "parameters": kwargs}

    def relay_healthcheck(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"tool": "relay_healthcheck", "args": list(args), "parameters": kwargs}

    return Agent(
        name="DeviceBridge Agent",
        model=model,
        instructions=_device_bridge_instructions,
        functions=[dispatch_task, collect_result, relay_healthcheck],
        tool_choice="required",
        parallel_tool_calls=False,
        role="device_bridge",
        port=ports.get("device_bridge", 9110),
        description="Relays tasks and healthchecks between system agents and devices.",
        contract=_device_bridge_contract(),
    )
