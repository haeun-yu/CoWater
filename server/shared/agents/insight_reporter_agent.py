from __future__ import annotations

from typing import Any

from .registry import register_agent
from .types import Agent


def _insight_reporter_instructions(context_variables: dict[str, Any]) -> str:
    ports = context_variables.get("ports") or {}
    return f"""You are CoWater's InsightReporter Agent.

Role:
- Combine Registry data into Korean summaries, highlights, and recommendations.
- Handle A2A envelope unwrapping safely.
- Save event-based insights when the data is sufficient.
- Never execute missions or control devices directly.

Peers:
- RequestHandler on port {ports.get("request_handler", 9116)}
- MissionPlanner on port {ports.get("mission_planner", 9111)}

Return structured JSON and never return an empty report as success."""


def _insight_reporter_contract() -> dict[str, Any]:
    return {
        "input_schema": {
            "type": "object",
            "required": ["request_id", "report_request"],
            "properties": {
                "request_id": {"type": "string"},
                "report_request": {"type": "object"},
                "registry_snapshot": {"type": "object"},
                "a2a_envelope": {"type": "object"},
            },
        },
        "output_schema": {
            "type": "object",
            "required": ["status", "report"],
            "properties": {
                "status": {"enum": ["ok", "needs_clarification", "error"]},
                "report": {"type": "object"},
            },
        },
        "forbidden_actions": [
            "mission execution",
            "device control",
            "policy decisions",
        ],
        "failure_handling": [
            "return needs_clarification when data is insufficient",
            "return error on envelope parsing failure",
            "return error for an empty report",
        ],
    }


@register_agent(name="InsightReporter Agent", func_name="get_insight_reporter_agent")
def get_insight_reporter_agent(model: str, **kwargs):
    def generate_report(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"tool": "generate_report", "args": list(args), "parameters": kwargs}

    def store_insight(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"tool": "store_insight", "args": list(args), "parameters": kwargs}

    def unwrap_a2a_envelope(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"tool": "unwrap_a2a_envelope", "args": list(args), "parameters": kwargs}

    return Agent(
        name="InsightReporter Agent",
        model=model,
        instructions=_insight_reporter_instructions,
        functions=[generate_report, store_insight, unwrap_a2a_envelope],
        tool_choice="required",
        parallel_tool_calls=False,
        role="insight_reporter",
        port=9114,
        description="Generates Korean reports and insights from Registry data.",
        contract=_insight_reporter_contract(),
    )
