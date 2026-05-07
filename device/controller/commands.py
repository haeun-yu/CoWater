from __future__ import annotations

import logging
from typing import Any, Optional

from pydantic import BaseModel, Field

from agent.state import AgentState, utc_now

logger = logging.getLogger(__name__)


class CommandRequest(BaseModel):
    action: str
    reason: Optional[str] = None
    priority: str = "normal"
    params: dict[str, Any] = Field(default_factory=dict)


class CommandController:
    def __init__(self, executor: Any) -> None:
        self.executor = executor

    def apply(self, state: AgentState, command: dict[str, Any]) -> dict[str, Any]:
        """Apply command with error handling.
        
        Returns:
            dict with keys:
            - status: 'success' or 'failed'
            - action: command action name
            - result: execution result or error message
            - timestamp: execution time
        """
        try:
            execution_result = self.executor.execute(command)
            # Normalize result format
            if isinstance(execution_result, dict):
                # Check if execution was successful
                status = 'success' if execution_result.get('delivered', True) else 'failed'
            else:
                status = 'success'
                execution_result = {'result': execution_result}
            
            result = {
                'status': status,
                'action': command.get('action', 'unknown'),
                'result': execution_result,
                'reason': command.get('reason'),
                'timestamp': utc_now()
            }
            
            state.remember({
                'kind': 'command_executed',
                'at': utc_now(),
                'command': command,
                'status': status,
                'result': execution_result
            })
            return result
            
        except Exception as e:
            logger.error(f"Command execution failed: {e}", exc_info=True)
            error_result = {
                'status': 'failed',
                'action': command.get('action', 'unknown'),
                'error': str(e),
                'reason': command.get('reason'),
                'timestamp': utc_now()
            }
            state.remember({
                'kind': 'command_failed',
                'at': utc_now(),
                'command': command,
                'error': str(e)
            })
            return error_result

