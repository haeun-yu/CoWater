from __future__ import annotations

from typing import Any

from shared.agents.registry import register_agent
from shared.agents.types import Agent


def _policy_manager_instructions(context: dict[str, Any]) -> str:
    ports = context.get("ports") or {}
    return f"""You are CoWater's PolicyManager Agent.

Role:
- Evaluate existing policies and rules only.
- Decide whether a request should be auto_execute, approval_required, or escalate.
- Never invent new policy rules.
- Never control devices directly.

Peers:
- RequestHandler on port {ports.get("request_handler", 9116)}
- MissionPlanner on port {ports.get("mission_planner", 9111)}

Return structured JSON with matched rules and the recommended action."""


def _policy_manager_contract() -> dict[str, Any]:
    return {
        "input_schema": {
            "type": "object",
            "required": ["request_id", "policy_query"],
            "properties": {
                "request_id": {"type": "string"},
                "policy_query": {"type": "object"},
                "existing_rules": {"type": "array"},
            },
        },
        "output_schema": {
            "type": "object",
            "required": ["status", "decision", "matched_rules"],
            "properties": {
                "status": {"enum": ["ok", "needs_clarification", "error"]},
                "decision": {"type": "object"},
                "matched_rules": {"type": "array"},
            },
        },
        "forbidden_actions": [
            "policy invention",
            "device control",
            "mission planning replacement",
        ],
        "failure_handling": [
            "return approval_required when rules are ambiguous",
            "return approval_required when rule sets are missing",
            "return error on parse failure",
        ],
    }


@register_agent(name="PolicyManager Agent", func_name="get_policy_manager_agent")
def get_policy_manager_agent(model: str, **kwargs) -> Agent:
    ports = kwargs.get("ports") or {}

    def evaluate_rules(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"tool": "evaluate_rules", "args": list(args), "parameters": kwargs}

    def decide_auto_execute(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"tool": "decide_auto_execute", "args": list(args), "parameters": kwargs}

    def escalate(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"tool": "escalate", "args": list(args), "parameters": kwargs}

    return Agent(
        name="PolicyManager Agent",
        model=model,
        instructions=_policy_manager_instructions,
        functions=[evaluate_rules, decide_auto_execute, escalate],
        tool_choice="required",
        parallel_tool_calls=False,
        role="policy_manager",
        port=ports.get("policy_manager", 9112),
        description="Evaluates existing policy rules and returns the recommended action.",
        contract=_policy_manager_contract(),
    )
