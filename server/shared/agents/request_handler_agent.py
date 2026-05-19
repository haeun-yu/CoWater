from __future__ import annotations

from typing import Any

from .mission_planner_agent import get_mission_planner_agent
from .device_bridge_agent import get_device_bridge_agent
from .insight_reporter_agent import get_insight_reporter_agent
from .policy_manager_agent import get_policy_manager_agent
from .system_sentinel_agent import get_system_sentinel_agent
from .registry import register_agent
from .types import Agent, Result


def _request_handler_instructions(context_variables: dict[str, Any]) -> str:
    ports = context_variables.get("ports") or {}
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
def get_request_handler_agent(model: str, **kwargs):
    mission_planner_profile = kwargs.get("mission_planner_profile") or get_mission_planner_agent(model, **kwargs)
    device_bridge_profile = kwargs.get("device_bridge_profile") or get_device_bridge_agent(model, **kwargs)
    insight_reporter_profile = kwargs.get("insight_reporter_profile") or get_insight_reporter_agent(model, **kwargs)
    policy_manager_profile = kwargs.get("policy_manager_profile") or get_policy_manager_agent(model, **kwargs)
    system_sentinel_profile = kwargs.get("system_sentinel_profile") or get_system_sentinel_agent(model, **kwargs)

    def query_devices(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"tool": "get_devices", "args": list(args), "parameters": kwargs}

    def query_missions(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"tool": "get_missions", "args": list(args), "parameters": kwargs}

    def query_insights(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"tool": "get_insights", "args": list(args), "parameters": kwargs}

    def final_answer(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"tool": "final_answer", "args": list(args), "parameters": kwargs}

    def transfer_to_mission_planner(sub_task_description: str) -> Result:
        return Result(value=sub_task_description, agent=mission_planner_profile)

    def transfer_to_device_bridge(sub_task_description: str) -> Result:
        return Result(value=sub_task_description, agent=device_bridge_profile)

    def transfer_to_insight_reporter(sub_task_description: str) -> Result:
        return Result(value=sub_task_description, agent=insight_reporter_profile)

    def transfer_to_policy_manager(sub_task_description: str) -> Result:
        return Result(value=sub_task_description, agent=policy_manager_profile)

    def transfer_to_system_sentinel(sub_task_description: str) -> Result:
        return Result(value=sub_task_description, agent=system_sentinel_profile)

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
        port=9116,
        description="Receives the user's first request, classifies intent, and routes work to specialist agents.",
        contract=_request_handler_contract(),
        agent_teams={
            "MissionPlanner Agent": transfer_to_mission_planner,
            "DeviceBridge Agent": transfer_to_device_bridge,
            "InsightReporter Agent": transfer_to_insight_reporter,
            "PolicyManager Agent": transfer_to_policy_manager,
            "SystemSentinel Agent": transfer_to_system_sentinel,
        },
    )

    def transfer_back_to_request_handler(task_status: str) -> Result:
        return Result(value=task_status, agent=agent)

    for child_agent in (
        mission_planner_profile,
        device_bridge_profile,
        insight_reporter_profile,
        policy_manager_profile,
        system_sentinel_profile,
    ):
        if hasattr(child_agent, "functions"):
            if not any(getattr(func, "__name__", "") == "transfer_back_to_request_handler" for func in child_agent.functions):
                child_agent.functions.append(transfer_back_to_request_handler)
        if hasattr(child_agent, "agent_teams"):
            child_agent.agent_teams[agent.name] = transfer_back_to_request_handler

    return agent
