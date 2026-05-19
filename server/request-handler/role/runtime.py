from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from agent.base_runtime import BaseAgentRuntime
from agent.state import utc_now

logger = logging.getLogger(__name__)


class RequestHandlerRuntime(BaseAgentRuntime):
    """RequestHandler 역할: 사용자 의도 분류 및 라우팅"""

    async def handle_moth_message(self, event_type: str, payload: dict[str, Any], raw_event: dict[str, Any]) -> None:
        # request_handler는 이벤트 발행자 역할만 하므로 구독 루프 불필요 (simulation_loop에서 제외됨)
        pass

    async def _execute_role(self, parameters: dict[str, Any]) -> dict[str, Any]:
        return await self._execute_request_handler(parameters)

    async def _execute_request_handler(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """
        RequestHandler 역할:
        - analyze_intent로 MISSION/QUERY/REPORT 분류
        - MISSION → SYS_INTENT_CLASSIFIED 이벤트 발행 후 PENDING 반환
        - QUERY/REPORT → InsightReporter(9114) A2A 호출 후 즉시 응답
        """
        user_input = str(
            parameters.get("user_input") or parameters.get("goal") or parameters.get("message") or ""
        ).strip()

        if not user_input:
            return {"type": "RESPONSE", "status": "ERROR", "message": "사용자 명령이 비어 있습니다."}

        timeout = self.decision_engine.agent_config.get("llm", {}).get("timeout_seconds") or 60
        devices_raw = self.registry_client.list_devices()
        devices = self._summarize_tool_result("get_devices", devices_raw)

        intent_result, error = await self.decision_engine.analyze_intent(
            user_input, devices_raw, self.state
        )

        if error:
            error_msg = f"{error.get('error_type', 'unknown')}: {error.get('message', 'LLM 호출 실패')}"
            return {"type": "RESPONSE", "status": "ERROR", "message": f"처리 실패: {error_msg}"}

        intent_type = str((intent_result or {}).get("intent_type") or "QUERY").upper()
        logger.info(f"[RequestHandler] intent_type={intent_type} | {(intent_result or {}).get('reasoning', '')[:80]}")

        if intent_type == "MISSION":
            goal = user_input
            devices = self._summarize_tool_result("get_devices", self.registry_client.list_devices())
            feasibility = self._check_area_feasibility(goal, devices)
            if not feasibility["feasible"]:
                return {
                    "type": "RESPONSE",
                    "status": "INFEASIBLE",
                    "message": f"미션 수행 불가: {feasibility['reason']}",
                    "reason_code": feasibility.get("reason_code"),
                    "clarification_needed": False,
                }
            intent_id = f"intent-{uuid4()}"
            meb_payload = {
                "intent_type": "MISSION",
                "user_input": user_input,
                "goal": goal,
                "intent_id": intent_id,
                "devices_summary": devices,
            }
            asyncio.create_task(self._publish_to_meb(
                "SYS_INTENT_CLASSIFIED", meb_payload, ["MissionPlanner"]
            ))
            try:
                self.registry_client.ingest_event({
                    "event_type": "SYS_INTENT_CLASSIFIED",
                    "source_system": "request_handler",
                    "source_agent_id": self.state.agent_id,
                    "source_role": "request_handler",
                    "severity": "INFORMATION",
                    "title": "사용자 미션 요청",
                    "message": user_input,
                    "data": meb_payload,
                })
            except Exception:
                pass
            logger.info(f"[RequestHandler] SYS_INTENT_CLASSIFIED MEB 발행 (intent_id={intent_id})")
            return {
                "type": "RESPONSE",
                "status": "PENDING",
                "message": (
                    "미션 계획 요청이 MissionPlanner로 전달됐습니다.\n"
                    "장치 역량 분석 후 실행 가능한 Proposal이 생성됩니다.\n"
                    "UI의 Proposals 목록에서 원하는 계획을 승인해 주세요."
                ),
                "intent_id": intent_id,
            }

        try:
            result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self._call_system_agent_sync(
                        9114, {"user_input": user_input, "intent_type": intent_type}
                    ),
                ),
                timeout=float(timeout),
            )
            report_obj = result.get("report") or {}
            message = report_obj.get("report") or result.get("message") or "리포트를 생성할 수 없습니다."
            return {"type": "RESPONSE", "status": "SUCCESS", "message": message}
        except asyncio.TimeoutError:
            return {"type": "RESPONSE", "status": "ERROR", "message": "InsightReporter 응답 시간 초과."}
        except Exception as e:
            return {"type": "RESPONSE", "status": "ERROR", "message": f"리포트 생성 실패: {e}"}

    async def _execute_tool(self, tool_name: str, tool_input: dict[str, Any]) -> Any:
        if tool_name == "get_devices":
            return self._summarize_tool_result("get_devices", self.registry_client.list_devices())
        if tool_name == "get_missions":
            return self._summarize_tool_result("get_missions", self.registry_client.list_missions())
        if tool_name == "get_insights":
            return self._summarize_tool_result("get_insights", self.registry_client.list_insights())
        if tool_name == "approve_mission":
            approval_id = str(tool_input.get("approval_id") or "")
            if not approval_id:
                return {"error": "approval_id가 필요합니다. plan_mission을 먼저 실행하세요."}
            try:
                result = await asyncio.wait_for(
                    self.decide_approval_flow(approval_id, approved=True, decided_by="user"),
                    timeout=60.0,
                )
                mission = result.get("mission") or {}
                return {
                    "approved": True,
                    "mission_id": mission.get("mission_id"),
                    "title": mission.get("title"),
                    "status": mission.get("status"),
                    "message": "미션이 승인되어 실행을 시작했습니다.",
                }
            except asyncio.TimeoutError:
                return {"error": "미션 실행 시작 시간이 초과됐습니다. 잠시 후 상태를 확인하세요."}
            except Exception as e:
                return {"error": f"미션 승인 실패: {str(e)}"}
        if tool_name == "plan_mission":
            goal = str(tool_input.get("goal") or "")
            devices_raw = self.registry_client.list_devices()
            devices = self._summarize_tool_result("get_devices", devices_raw)
            feasibility = self._check_area_feasibility(goal, devices)
            if not feasibility["feasible"]:
                return {
                    "feasible": False,
                    "reason": feasibility["reason"],
                    "reason_code": feasibility.get("reason_code"),
                    "clarification_needed": False,
                }
            try:
                raw = await asyncio.wait_for(
                    self.generate_mission_proposal({"goal": goal}, allow_suppression=False),
                    timeout=80.0,
                )
            except asyncio.TimeoutError:
                return {
                    "feasible": False,
                    "reason": "미션 계획 생성에 실패했습니다. LLM 응답 시간이 초과됐습니다. 잠시 후 다시 시도해 주세요.",
                }
            return self._summarize_tool_result("plan_mission", raw)
        return {"error": f"알 수 없는 도구: {tool_name}"}
