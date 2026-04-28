from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from agent.state import AgentState, utc_now
from tools.command_executor import CommandExecutor


class CommandRequest(BaseModel):
    action: str
    reason: Optional[str] = None
    priority: str = "normal"
    params: dict[str, Any] = Field(default_factory=dict)


class CommandController:
    def __init__(self, executor: CommandExecutor) -> None:
        self.executor = executor

    def apply(self, state: AgentState, command: dict[str, Any]) -> dict[str, Any]:
        result = self.executor.execute(command)
        state.remember({"kind": "command", "at": utc_now(), "command": command})
        return result

