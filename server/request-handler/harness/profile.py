from __future__ import annotations

from typing import Any

from shared.agents.registry import register_agent
from shared.agents.types import Agent, Result


def _request_handler_instructions(context: dict[str, Any]) -> str:
    ports = context.get("ports") or {}
    return f"""You are CoWater's RequestHandler Agent.

Role:
- Receive user natural-language commands first.
- Classify intent into QUERY, REPORT, MISSION, or SYSTEM_CONTROL.
- Answer directly only when the request is a simple read-only query.
- Delegate mission, reporting, policy, and device-control work to the specialized agents.
- Always return structured JSON.

Hard constraints:
- Do not control devices directly.
- Do not create a mission alone.
- Do not invent policy.
- Do not guess when evidence is missing; return needs_clarification or error.

Peers:
- MissionPlanner on port {ports.get("mission_planner", 9111)}
- DeviceBridge on port {ports.get("device_bridge", 9110)}
- InsightReporter on port {ports.get("insight_reporter", 9114)}
- PolicyManager on port {ports.get("policy_manager", 9112)}
- SystemSentinel on port {ports.get("system_sentinel", 9113)}

Return the final user-facing response after the correct specialist has been used."""


def _request_handler_contract() -> dict[str, Any]:
    return {
        "input_schema": {
            "type": "object",
            "required": ["request_id", "user_message"],
            "properties": {
                "request_id": {"type": "string"},
                "user_message": {"type": "string"},
                "context": {"type": "object"},
            },
        },
        "output_schema": {
            "type": "object",
            "required": ["status", "intent", "response"],
            "properties": {
                "status": {"enum": ["ok", "needs_clarification", "error"]},
                "intent": {"enum": ["QUERY", "REPORT", "MISSION", "SYSTEM_CONTROL", "UNKNOWN"]},
                "response": {"type": "object"},
                "error": {"type": "object"},
            },
        },
        "forbidden_actions": [
            "direct device control",
            "mission creation without MissionPlanner",
            "policy invention",
        ],
        "failure_handling": [
            "return needs_clarification when intent is ambiguous",
            "return error when envelope parsing fails",
            "unwrap A2A envelopes before summarizing specialist results",
        ],
    }


@register_agent(name="RequestHandler Agent", func_name="get_request_handler_agent")
def get_request_handler_agent(model: str, **kwargs) -> Agent:
    ports = kwargs.get("ports") or {}

    def query_devices(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"tool": "get_devices", "args": list(args), "parameters": kwargs}

    def query_missions(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"tool": "get_missions", "args": list(args), "parameters": kwargs}

    def query_insights(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"tool": "get_insights", "args": list(args), "parameters": kwargs}

    def transfer_to_mission_planner(sub_task_description: str) -> Result:
        return Result(value=sub_task_description, agent=None)

    def transfer_to_device_bridge(sub_task_description: str) -> Result:
        return Result(value=sub_task_description, agent=None)

    def transfer_to_insight_reporter(sub_task_description: str) -> Result:
        return Result(value=sub_task_description, agent=None)

    def transfer_to_policy_manager(sub_task_description: str) -> Result:
        return Result(value=sub_task_description, agent=None)

    def transfer_to_system_sentinel(sub_task_description: str) -> Result:
        return Result(value=sub_task_description, agent=None)

    def final_answer(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"tool": "final_answer", "args": list(args), "parameters": kwargs}

    agent = Agent(
        name="RequestHandler Agent",
        model=model,
        instructions=_request_handler_instructions,
        functions=[
            query_devices,
            query_missions,
            query_insights,
            transfer_to_mission_planner,
            transfer_to_device_bridge,
            transfer_to_insight_reporter,
            transfer_to_policy_manager,
            transfer_to_system_sentinel,
            final_answer,
        ],
        tool_choice="required",
        parallel_tool_calls=False,
        role="request_handler",
        port=ports.get("request_handler", 9116),
        description="Receives the user's first request, classifies intent, and routes work to specialist agents.",
        contract=_request_handler_contract(),
        agent_teams={
            "MissionPlanner": ports.get("mission_planner", 9111),
            "DeviceBridge": ports.get("device_bridge", 9110),
            "InsightReporter": ports.get("insight_reporter", 9114),
            "PolicyManager": ports.get("policy_manager", 9112),
            "SystemSentinel": ports.get("system_sentinel", 9113),
        },
    )

    return agent
