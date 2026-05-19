from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Optional, Union

AgentFunction = Callable[..., Any]


@dataclass
class Agent:
    name: str = "Agent"
    model: str = "gpt-4o"
    instructions: Union[str, Callable[[dict[str, Any]], str]] = "You are a helpful agent."
    functions: list[AgentFunction] = field(default_factory=list)
    tool_choice: str | None = None
    parallel_tool_calls: bool = False
    examples: Union[list[tuple[dict[str, Any], str]], Callable[[dict[str, Any]], str], None] = field(default_factory=list)
    handle_mm_func: Callable[..., Any] | None = None
    agent_teams: dict[str, int] = field(default_factory=dict)
    role: str = ""
    port: int | None = None
    description: str = ""
    contract: dict[str, Any] = field(default_factory=dict)

    def render_instructions(self, context_variables: dict[str, Any] | None = None) -> str:
        context_variables = context_variables or {}
        if callable(self.instructions):
            return str(self.instructions(context_variables))
        return str(self.instructions)

    def to_dict(self, context_variables: dict[str, Any] | None = None) -> dict[str, Any]:
        context_variables = context_variables or {}
        return {
            "name": self.name,
            "model": self.model,
            "instructions": self.render_instructions(context_variables),
            "functions": [getattr(func, "__name__", repr(func)) for func in self.functions],
            "tool_choice": self.tool_choice,
            "parallel_tool_calls": self.parallel_tool_calls,
            "examples": self._serialize_examples(context_variables),
            "handle_mm_func": getattr(self.handle_mm_func, "__name__", None) if self.handle_mm_func else None,
            "agent_teams": self.agent_teams,
            "role": self.role,
            "port": self.port,
            "description": self.description,
            "contract": asdict(self.contract) if hasattr(self.contract, "__dataclass_fields__") else self.contract,
        }

    def _serialize_examples(self, context_variables: dict[str, Any]) -> Any:
        if callable(self.examples):
            return self.examples(context_variables)
        return self.examples


@dataclass
class Response:
    messages: list[Any] = field(default_factory=list)
    agent: Optional[Agent] = None
    context_variables: dict[str, Any] = field(default_factory=dict)


@dataclass
class Result:
    """
    AutoAgent 호환 전이 결과 표현.
    """

    value: str = ""
    agent: Optional[Agent] = None
    context_variables: dict[str, Any] = field(default_factory=dict)
    image: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "agent": self.agent.to_dict() if self.agent else None,
            "context_variables": self.context_variables,
            "image": self.image,
        }
