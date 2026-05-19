from __future__ import annotations

import logging
from typing import Any

from agent.base_runtime import BaseAgentRuntime
from agent.state import utc_now

logger = logging.getLogger(__name__)


class SystemSentinelRuntime(BaseAgentRuntime):
    """SystemSentinel 역할: 시스템 건강 상태, 디바이스 및 에이전트 연결 모니터링"""

    async def handle_moth_message(self, event_type: str, payload: dict[str, Any], raw_event: dict[str, Any]) -> None:
        if event_type in {
            "DEVICE_HEALTHCHECK",
            "ENV_STATE_CHANGED",
            "SYS_TASK_DISPATCHED",
            "SYS_TASK_COMPLETED",
            "SYS_TASK_FAILED",
        }:
            await self._evaluate_and_apply_policies(self.registry_client.list_devices(), logger)

    async def _execute_role(self, parameters: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "STATE",
            "status": "SUCCESS",
            "devices": self.registry_client.list_devices(),
        }

    async def _process_waiting_queue(self, devices: list[dict[str, Any]], logger: Any) -> None:
        return
