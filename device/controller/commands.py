from __future__ import annotations

import logging
from typing import Any, Optional

from pydantic import BaseModel, Field

from agent.state import utc_now

logger = logging.getLogger(__name__)


class CommandRequest(BaseModel):
    action: str
    reason: Optional[str] = None
    priority: str = "normal"
    params: dict[str, Any] = Field(default_factory=dict)


class CommandController:
    def __init__(self, executor: Any) -> None:
        self.executor = executor

    def execute(self, command: dict[str, Any]) -> dict[str, Any]:
        """Execute a command and normalize the raw executor result."""
        try:
            execution_result = self.executor.execute(command)
            if isinstance(execution_result, dict):
                status = "success" if execution_result.get("delivered", True) else "failed"
            else:
                status = "success"
                execution_result = {"result": execution_result}

            result = {
                "status": status,
                "action": command.get("action", "unknown"),
                "result": execution_result,
                "reason": command.get("reason"),
                "timestamp": utc_now(),
            }
            return result

        except Exception as e:
            logger.error(f"Command execution failed: {e}", exc_info=True)
            error_result = {
                "status": "failed",
                "action": command.get("action", "unknown"),
                "error": str(e),
                "reason": command.get("reason"),
                "timestamp": utc_now(),
            }
            return error_result

    def apply(self, command: dict[str, Any]) -> dict[str, Any]:
        """Backward-compatible alias for execute()."""
        return self.execute(command)
