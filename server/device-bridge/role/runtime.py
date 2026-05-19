from __future__ import annotations

import logging
from typing import Any

from agent.base_runtime import BaseAgentRuntime
from agent.state import utc_now

logger = logging.getLogger(__name__)


class DeviceBridgeRuntime(BaseAgentRuntime):
    """DeviceBridge 역할: Device Agent에 A2A Task 디스패치 및 결과 수집"""

    async def handle_moth_message(self, event_type: str, payload: dict[str, Any], raw_event: dict[str, Any]) -> None:
        # DeviceBridge는 MEB 이벤트를 직접 구독하지 않고 A2A 수신에 집중
        self.state.remember({"kind": "meb_event_received", "at": utc_now(), "event_type": event_type, "payload": payload})

    async def _execute_role(self, parameters: dict[str, Any]) -> dict[str, Any]:
        steps = list(parameters.get("steps") or [])
        mission_id = str(parameters.get("mission_id") or "")
        if steps and mission_id:
            devices = self.registry_client.list_devices()
            response_like = {
                "response_id": mission_id,
                "mission_id": mission_id,
                "alert_id": parameters.get("alert_id"),
                "reason": parameters.get("reason") or "DeviceBridge task dispatch",
                "dispatch_result": {"steps": []},
            }
            dispatch = await self._dispatch_next_step(
                response_like, steps, devices, logging.getLogger(__name__)
            )
            return {
                "type": "COMMAND",
                "status": "SUCCESS",
                "delivered": dispatch.get("delivered"),
                "dispatch": dispatch,
            }
        command = {
            "action": parameters.get("action") or parameters.get("command") or "hold_position",
            "params": parameters.get("params") or {},
            "reason": parameters.get("reason") or "DeviceBridge execute request",
        }
        result = await self.handle_command_with_llm(command)
        return {"type": "COMMAND", "status": "SUCCESS", "result": result}
