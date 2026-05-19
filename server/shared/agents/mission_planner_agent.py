from __future__ import annotations

from typing import Any

from .registry import register_agent
from .toolkit import make_tool
from .types import Agent


def _mission_planner_instructions(context_variables: dict[str, Any]) -> str:
    ports = context_variables.get("ports") or {}
    return f"""You are CoWater's MissionPlanner Agent.

Role:
- Accept a mission request and design executable proposals.
- Split the mission into tasks.
- Match tasks to devices using reported inventory only.
- Manage approval before execution.
- Never control devices directly.

Peers:
- RequestHandler on port {ports.get("request_handler", 9116)}
- DeviceBridge on port {ports.get("device_bridge", 9110)}

Return structured JSON with proposals, tasks, device mapping, and approval state."""


def _mission_planner_contract() -> dict[str, Any]:
    return {
        "input_schema": {
            "type": "object",
            "required": ["request_id", "mission_request"],
            "properties": {
                "request_id": {"type": "string"},
                "mission_request": {"type": "string"},
                "registry_snapshot": {"type": "object"},
            },
        },
        "output_schema": {
            "type": "object",
            "required": ["status", "proposals", "approval_state"],
            "properties": {
                "status": {"enum": ["ok", "needs_clarification", "error"]},
                "approval_state": {"enum": ["draft", "awaiting_approval", "approved", "rejected", "not_executable"]},
                "proposals": {"type": "array"},
            },
        },
        "forbidden_actions": [
            "direct device control",
            "acting without approval",
            "inventing device capabilities",
        ],
        "failure_handling": [
            "return needs_clarification when the mission goal is missing",
            "return not_executable when no safe device mapping exists",
            "return error when proposal generation fails",
        ],
    }


@register_agent(name="MissionPlanner Agent", func_name="get_mission_planner_agent")
def get_mission_planner_agent(model: str, **kwargs):
    def generate_proposals(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"tool": "generate_proposals", "args": list(args), "parameters": kwargs}

    def split_tasks(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"tool": "split_tasks", "args": list(args), "parameters": kwargs}

    def match_devices(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"tool": "match_devices", "args": list(args), "parameters": kwargs}

    def request_approval(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"tool": "request_approval", "args": list(args), "parameters": kwargs}

    return Agent(
        name="MissionPlanner Agent",
        model=model,
        instructions=_mission_planner_instructions,
        functions=[generate_proposals, split_tasks, match_devices, request_approval],
        tool_choice="required",
        parallel_tool_calls=False,
        role="mission_planner",
        port=9111,
        description="Designs proposals, tasks, and approval flow for executable missions.",
        contract=_mission_planner_contract(),
    )
