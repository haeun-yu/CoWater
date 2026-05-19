from __future__ import annotations

import logging
from typing import Any

from agent.base_runtime import BaseAgentRuntime
from agent.state import utc_now

logger = logging.getLogger(__name__)


class PolicyManagerRuntime(BaseAgentRuntime):
    """PolicyManager 역할: 정책 평가 및 자동 대응"""

    async def handle_moth_message(self, event_type: str, payload: dict[str, Any], raw_event: dict[str, Any]) -> None:
        if event_type in {"SYS_INTENT_CLASSIFIED", "SYS_ANOMALY_DETECTED"}:
            await self._evaluate_and_apply_policies(self.registry_client.list_devices(), logger)

    async def _execute_role(self, parameters: dict[str, Any]) -> dict[str, Any]:
        return self._execute_policy_manager(parameters)

    def _execute_policy_manager(self, parameters: dict[str, Any]) -> dict[str, Any]:
        policy_id = str(parameters.get("policy_id") or parameters.get("id") or "").strip()
        if policy_id:
            policy = self.registry_client.update_policy(policy_id, parameters)
        else:
            policy = self.registry_client.create_policy(parameters)
        return {"type": "RESPONSE", "status": "SUCCESS", "policy": policy}
