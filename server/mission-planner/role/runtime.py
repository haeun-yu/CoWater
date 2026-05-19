from __future__ import annotations

import logging
from typing import Any

from agent.base_runtime import BaseAgentRuntime
from agent.state import utc_now

logger = logging.getLogger(__name__)


class MissionPlannerRuntime(BaseAgentRuntime):
    """MissionPlanner 역할: Proposal/Mission 생성 및 승인 흐름 관리"""

    async def handle_moth_message(self, event_type: str, payload: dict[str, Any], raw_event: dict[str, Any]) -> None:
        if event_type == "SYS_INTENT_CLASSIFIED":
            await self._handle_mission_intent_event(payload)
        elif event_type in {
            "SYS_TASK_COMPLETED",
            "SYS_TASK_FAILED",
            "SYS_ANOMALY_DETECTED",
            "SYS_POLICY_DECISION",
            "SYS_AGENT_CONNECTION_CREATED",
            "SYS_AGENT_CONNECTION_DELETED",
        }:
            self.state.remember({"kind": "meb_event_received", "at": utc_now(), "event_type": event_type, "payload": payload})

    async def _execute_role(self, parameters: dict[str, Any]) -> dict[str, Any]:
        return await self.generate_mission_proposal(parameters, allow_suppression=False)

    async def _handle_mission_intent_event(self, payload: dict[str, Any]) -> None:
        """SYS_INTENT_CLASSIFIED (MISSION) 수신 → proposal 생성"""
        goal = str(payload.get("user_input") or payload.get("goal") or "")
        if not goal:
            logger.warning("[MissionPlanner] SYS_INTENT_CLASSIFIED: goal 없음, 스킵")
            return
        logger.info(f"[MissionPlanner] 미션 intent 수신: {goal[:60]}")
        try:
            async with self._mission_lock:
                await self.generate_mission_proposal({"goal": goal}, allow_suppression=False)
            logger.info(f"[MissionPlanner] Proposal 생성 완료: {goal[:40]}")
        except Exception as e:
            logger.error(f"[MissionPlanner] Proposal 생성 실패: {e}")
            self.registry_client.ingest_event({
                "event_type": "SYS_MISSION_UPDATED",
                "source_system": "mission_planner",
                "source_agent_id": self.state.agent_id,
                "source_role": "mission_planner",
                "severity": "WARNING",
                "title": "미션 계획 실패",
                "message": f"Proposal 생성 실패: {e}",
                "data": {"goal": goal, "error": str(e)},
            })
