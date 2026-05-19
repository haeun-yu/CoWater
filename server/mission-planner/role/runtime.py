from __future__ import annotations

import logging
from typing import Any

from agent.base_runtime import BaseAgentRuntime
from agent.state import utc_now

logger = logging.getLogger(__name__)


class MissionPlannerRuntime(BaseAgentRuntime):
    """MissionPlanner 역할: Proposal/Mission 생성 및 승인 흐름 관리"""

    async def handle_moth_message(self, event_type: str, payload: dict[str, Any], raw_event: dict[str, Any]) -> bool:
        if event_type in {
            "SYS_TASK_COMPLETED",
            "SYS_TASK_FAILED",
            "SYS_ANOMALY_DETECTED",
            "SYS_POLICY_DECISION",
            "SYS_AGENT_CONNECTION_CREATED",
            "SYS_AGENT_CONNECTION_DELETED",
        }:
            self.state.remember({"kind": "meb_event_received", "at": utc_now(), "event_type": event_type, "payload": payload})
            return True
        return False

    async def _execute_role(self, parameters: dict[str, Any]) -> dict[str, Any]:
        from uuid import uuid4

        request_id = str(parameters.get("request_id") or "")
        context_id = str(parameters.get("context_id") or f"ctx-{uuid4()}")
        goal = str(parameters.get("goal") or parameters.get("mission_request") or parameters.get("user_input") or "").strip()

        # Event: SYS_REQUEST_RECEIVED (요청 수신)
        if request_id:
            self.registry_client.ingest_event({
                "event_type": "SYS_REQUEST_RECEIVED",
                "actor_type": "SYSTEM",
                "actor_id": self.state.agent_id,
                "target_type": "AGENT_COMMUNICATION",
                "target_id": request_id,
                "severity": "INFO",
                "data": {
                    "request_id": request_id,
                    "from_agent": "RequestHandler",
                    "to_agent": "MissionPlanner",
                    "goal": goal,
                    "timestamp": utc_now()
                }
            })

        if not goal:
            if request_id:
                self.registry_client.ingest_event({
                    "event_type": "SYS_RESPONSE_SENT",
                    "actor_type": "SYSTEM",
                    "actor_id": self.state.agent_id,
                    "target_type": "AGENT_COMMUNICATION",
                    "target_id": request_id,
                    "severity": "INFO",
                    "data": {
                        "request_id": request_id,
                        "from_agent": "MissionPlanner",
                        "to_agent": "RequestHandler",
                        "response_status": "error",
                        "error_code": "missing_goal",
                        "timestamp": utc_now()
                    }
                })
            return self._response_envelope(
                status="needs_clarification",
                response={
                    "proposal_state": "draft",
                    "proposals": [],
                },
                error={"code": "missing_goal", "message": "미션 목표가 없습니다.", "details": {}},
            )

        try:
            import time
            start_time = time.time()

            bundle = await self.generate_multiple_mission_proposals({
                "goal": goal,
                "location": parameters.get("location") or {},
                "title": parameters.get("title"),
                "summary": parameters.get("summary"),
                "request_id": request_id,
                "context_id": context_id,
            })

            duration_ms = int((time.time() - start_time) * 1000)

            # AgentLog: Proposal 생성
            self.registry_client.ingest_agent_log({
                "context_id": context_id,
                "agent_id": self.state.agent_id,
                "agent_role": "MISSION_PLANNER",
                "action": "generate_proposals",
                "input": {"goal": goal},
                "output": {
                    "proposal_count": len(bundle.get("proposals") or []),
                    "proposal_ids": [p.get("id") for p in (bundle.get("proposals") or [])]
                },
                "reasoning": {
                    "strategy": bundle.get("strategy_source")
                },
                "status": "SUCCESS",
                "duration_ms": duration_ms
            })

            proposals = bundle.get("proposals") or []
            approvals = bundle.get("approvals") or []

            if not proposals:
                if request_id:
                    self.registry_client.ingest_event({
                        "event_type": "SYS_RESPONSE_SENT",
                        "actor_type": "SYSTEM",
                        "actor_id": self.state.agent_id,
                        "target_type": "AGENT_COMMUNICATION",
                        "target_id": request_id,
                        "severity": "WARNING",
                        "data": {
                            "request_id": request_id,
                            "from_agent": "MissionPlanner",
                            "to_agent": "RequestHandler",
                            "response_status": "no_proposal",
                            "timestamp": utc_now()
                        }
                    })
                return self._response_envelope(
                    status="needs_clarification",
                    response={
                        "proposal_state": "not_executable",
                        "proposals": [],
                    },
                    error={"code": "no_proposal_generated", "message": "생성 가능한 Proposal이 없습니다.", "details": bundle},
                )

            # Event: SYS_RESPONSE_SENT (응답 전송, 성공)
            if request_id:
                self.registry_client.ingest_event({
                    "event_type": "SYS_RESPONSE_SENT",
                    "actor_type": "SYSTEM",
                    "actor_id": self.state.agent_id,
                    "target_type": "AGENT_COMMUNICATION",
                    "target_id": request_id,
                    "severity": "INFO",
                    "data": {
                        "request_id": request_id,
                        "from_agent": "MissionPlanner",
                        "to_agent": "RequestHandler",
                        "response_status": "ok",
                        "proposal_count": len(proposals),
                        "timestamp": utc_now()
                    }
                })

            return self._response_envelope(
                status="ok",
                response={
                    "proposal_state": "awaiting_approval",
                    "proposals": proposals,
                    "approvals": approvals,
                    "insights": bundle.get("insights") or [],
                    "strategy_source": bundle.get("strategy_source"),
                },
            )

        except Exception as exc:
            if request_id:
                self.registry_client.ingest_event({
                    "event_type": "SYS_RESPONSE_SENT",
                    "actor_type": "SYSTEM",
                    "actor_id": self.state.agent_id,
                    "target_type": "AGENT_COMMUNICATION",
                    "target_id": request_id,
                    "severity": "ERROR",
                    "data": {
                        "request_id": request_id,
                        "from_agent": "MissionPlanner",
                        "to_agent": "RequestHandler",
                        "response_status": "error",
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                        "timestamp": utc_now()
                    }
                })
            return self._response_envelope(
                status="error",
                response={
                    "proposal_state": "not_executable",
                    "proposals": [],
                },
                error={"code": "mission_planning_failed", "message": str(exc), "details": {}},
            )

