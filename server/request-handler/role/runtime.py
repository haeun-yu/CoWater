from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from agent.base_runtime import BaseAgentRuntime
from agent.state import utc_now


class RequestHandlerRuntime(BaseAgentRuntime):
    """RequestHandler 역할: intent 분류, 직접 조회, 전문 Agent 위임, 최종 응답 조립"""

    _QUERY_KEYWORDS = {
        "조회", "확인", "상태", "목록", "몇", "몇개", "count", "list", "status", "health", "device",
        "devices", "mission", "missions", "insight", "insights", "battery", "policy", "approval",
    }
    _REPORT_KEYWORDS = {"리포트", "보고", "요약", "분석", "현황", "report", "summary", "insight"}
    _MISSION_KEYWORDS = {"미션", "작전", "계획", "수행", "탐지", "제거", "survey", "plan", "mission", "task"}
    _SYSTEM_CONTROL_KEYWORDS = {"재시작", "중지", "정지", "shutdown", "restart", "system_control", "policy", "health", "연결", "connector"}

    async def handle_moth_message(self, event_type: str, payload: dict[str, Any], raw_event: dict[str, Any]) -> bool:
        # RequestHandler는 이벤트 루프에서 구독하지 않는다.
        return False

    async def _execute_role(self, parameters: dict[str, Any]) -> dict[str, Any]:
        return await self._execute_request_handler(parameters)

    def _normalize_text(self, value: Any) -> str:
        return str(value or "").strip()

    def _classify_intent(self, text: str) -> str:
        lowered = text.lower()
        if any(keyword in text for keyword in self._MISSION_KEYWORDS) or any(keyword in lowered for keyword in self._MISSION_KEYWORDS):
            return "MISSION"
        if any(keyword in text for keyword in self._REPORT_KEYWORDS) or any(keyword in lowered for keyword in self._REPORT_KEYWORDS):
            return "REPORT"
        if any(keyword in text for keyword in self._SYSTEM_CONTROL_KEYWORDS) or any(keyword in lowered for keyword in self._SYSTEM_CONTROL_KEYWORDS):
            return "SYSTEM_CONTROL"
        return "QUERY"

    def _registry_snapshot(self) -> dict[str, Any]:
        try:
            devices = self.registry_client.list_devices()
        except Exception:
            devices = []
        try:
            missions = self.registry_client.list_missions()
        except Exception:
            missions = []
        try:
            insights = self.registry_client.list_insights()
        except Exception:
            insights = []
        try:
            policies = self.registry_client.list_policies()
        except Exception:
            policies = []
        try:
            approvals = self.registry_client.list_approvals()
        except Exception:
            approvals = []
        return {
            "devices": devices,
            "missions": missions,
            "insights": insights,
            "policies": policies,
            "approvals": approvals,
        }

    def _summarize_query(self, text: str, snapshot: dict[str, Any]) -> dict[str, Any]:
        devices = list(snapshot.get("devices") or [])
        missions = list(snapshot.get("missions") or [])
        insights = list(snapshot.get("insights") or [])
        online_devices = [item for item in devices if str(item.get("connectivity_status") or "").lower() == "online" or bool(item.get("connected"))]
        in_progress = [item for item in missions if str(item.get("status") or "").upper() == "IN_PROGRESS"]
        failed = [item for item in missions if str(item.get("status") or "").upper() == "FAILED"]
        summary = (
            f"장치 {len(devices)}개, 연결됨 {len(online_devices)}개, "
            f"진행 중 미션 {len(in_progress)}개, 실패 미션 {len(failed)}개, "
            f"인사이트 {len(insights)}개입니다."
        )
        answer = summary
        if any(token in text.lower() for token in ["battery", "배터리"]):
            batteries = [item.get("last_battery_percent") or item.get("battery_percent") for item in devices if item.get("last_battery_percent") is not None or item.get("battery_percent") is not None]
            if batteries:
                answer = f"배터리 정보가 있는 장치 {len(batteries)}개가 있고, 평균은 {round(sum(float(v) for v in batteries if v is not None) / max(1, len([v for v in batteries if v is not None])), 1)}%입니다."
        return {
            "summary": summary,
            "answer": answer,
            "data": {
                "device_count": len(devices),
                "online_device_count": len(online_devices),
                "mission_count": len(missions),
                "in_progress_mission_count": len(in_progress),
                "failed_mission_count": len(failed),
                "insight_count": len(insights),
            },
            "raw": {
                "devices": devices[:10],
                "missions": missions[:10],
                "insights": insights[:10],
            },
        }

    def _route_for_system_control(self, text: str) -> tuple[int, str]:
        lowered = text.lower()
        if any(keyword in lowered for keyword in ["health", "상태", "점검", "sentinel", "감시"]):
            return 9113, "SystemSentinel"
        if any(keyword in lowered for keyword in ["policy", "정책", "승인", "approval", "자동"]):
            return 9112, "PolicyManager"
        if any(keyword in lowered for keyword in ["device", "디바이스", "긴급정지", "command", "control", "bridge"]):
            return 9110, "DeviceBridge"
        return 9112, "PolicyManager"

    def _unwrap_agent_response(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {"raw": payload}
        if isinstance(payload.get("response"), dict):
            inner = payload["response"]
            if inner:
                return inner
        if "result" in payload and isinstance(payload["result"], dict):
            return payload["result"]
        if "report" in payload or "proposal" in payload or "decision" in payload:
            return payload
        artifacts = (((payload.get("artifacts") or [])[0].get("parts") or [])[0].get("data") if isinstance(payload.get("artifacts"), list) and payload.get("artifacts") else None)
        if isinstance(artifacts, dict):
            return artifacts
        return payload

    async def _analyze_intent(self, user_input: str, snapshot: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
        try:
            llm_intent, llm_error = await self.decision_engine.analyze_intent(user_input, snapshot.get("devices") or [], self.state)
            if llm_error:
                return self._classify_intent(user_input), llm_error
            if isinstance(llm_intent, dict):
                intent = str(llm_intent.get("intent_type") or "").upper().strip()
                if intent in {"QUERY", "REPORT", "MISSION", "SYSTEM_CONTROL"}:
                    return intent, llm_intent
        except Exception as exc:
            return self._classify_intent(user_input), {"error_type": "intent_analysis_failed", "message": str(exc)}
        return self._classify_intent(user_input), None

    async def _execute_request_handler(self, parameters: dict[str, Any]) -> dict[str, Any]:
        # Context ID 생성 (이 사용자 명령의 흐름 ID)
        context_id = f"ctx-{uuid4()}"

        user_input = self._normalize_text(
            parameters.get("user_input") or parameters.get("goal") or parameters.get("message") or parameters.get("text")
        )
        if not user_input:
            return self._response_envelope(
                status="needs_clarification",
                intent="UNKNOWN",
                response={
                    "summary": "입력이 비어 있습니다.",
                    "answer": "무엇을 하길 원하는지 한 문장으로 다시 말해 주세요.",
                },
                reasoning=None,
            )

        # Event: USER_COMMAND_RECEIVED (사용자 명령 수신)
        self.registry_client.ingest_event({
            "event_type": "USER_COMMAND_RECEIVED",
            "context_id": context_id,
            "actor_type": "USER",
            "actor_id": parameters.get("user_id") or "unknown",
            "severity": "INFO",
            "data": {
                "command": user_input,
                "timestamp": utc_now()
            }
        })

        snapshot = self._registry_snapshot()
        intent, intent_meta = await self._analyze_intent(user_input, snapshot)
        self.state.remember({
            "kind": "request_handler_intent",
            "at": utc_now(),
            "intent": intent,
            "text": user_input,
            "intent_meta": intent_meta,
        })

        # AgentLog: 의도 분류
        self.registry_client.ingest_agent_log({
            "context_id": context_id,
            "agent_id": self.state.agent_id,
            "agent_role": "REQUEST_HANDLER",
            "action": "classify_intent",
            "input": user_input,
            "output": {
                "intent": intent,
                "meta": intent_meta
            },
            "reasoning": {
                "confidence": (intent_meta or {}).get("confidence") if isinstance(intent_meta, dict) else None,
                "method": "llm_analysis" if not intent_meta else "keyword_matching"
            },
            "status": "SUCCESS"
        })

        if intent == "QUERY":
            response = self._summarize_query(user_input, snapshot)

            # AgentLog: 쿼리 응답 생성
            self.registry_client.ingest_agent_log({
                "context_id": context_id,
                "agent_id": self.state.agent_id,
                "agent_role": "REQUEST_HANDLER",
                "action": "summarize_query",
                "input": user_input,
                "output": response,
                "status": "SUCCESS"
            })

            return self._response_envelope(
                status="ok",
                intent="QUERY",
                response={
                    "summary": response["summary"],
                    "answer": response["answer"],
                    "data": response["data"],
                    "delegated_to": None,
                    "source": "registry",
                },
                reasoning=(intent_meta or {}).get("reasoning") if isinstance(intent_meta, dict) else None,
            )

        if intent == "REPORT":
            try:
                request_id = parameters.get("request_id") or f"req-{uuid4()}"
                payload = {
                    "request_id": request_id,
                    "context_id": context_id,
                    "report_request": {"mode": "summary", "time_range": parameters.get("time_range") or {}, "filters": parameters.get("filters") or {}},
                    "registry_snapshot": snapshot,
                    "a2a_envelope": parameters.get("a2a_envelope"),
                }

                # Event: SYS_REQUEST_SENT
                self.registry_client.ingest_event({
                    "event_type": "SYS_REQUEST_SENT",
                    "actor_type": "SYSTEM",
                    "actor_id": self.state.agent_id,
                    "target_type": "AGENT_COMMUNICATION",
                    "target_id": request_id,
                    "severity": "INFO",
                    "data": {
                        "request_id": request_id,
                        "from_agent": "RequestHandler",
                        "to_agent": "InsightReporter",
                        "intent": "REPORT",
                        "timestamp": utc_now()
                    }
                })

                # A2A 호출 (Timeout: 300초)
                start_time = utc_now()
                result = await asyncio.wait_for(
                    asyncio.to_thread(self._call_system_agent_sync, 9114, payload),
                    timeout=300.0
                )
                duration_ms = int((utc_now() - start_time).total_seconds() * 1000) if isinstance(start_time, str) else 0
                report = self._unwrap_agent_response(result)

                # AgentLog: InsightReporter A2A 호출
                self.registry_client.ingest_agent_log({
                    "context_id": context_id,
                    "agent_id": self.state.agent_id,
                    "agent_role": "REQUEST_HANDLER",
                    "action": "call_insight_reporter_a2a",
                    "input": payload,
                    "output": report,
                    "status": "SUCCESS",
                    "duration_ms": duration_ms
                })

                if not isinstance(report, dict) or not report:
                    # Event: SYS_RESPONSE_RECEIVED (빈 응답)
                    self.registry_client.ingest_event({
                        "event_type": "SYS_RESPONSE_RECEIVED",
                        "actor_type": "SYSTEM",
                        "actor_id": self.state.agent_id,
                        "target_type": "AGENT_COMMUNICATION",
                        "target_id": request_id,
                        "severity": "WARNING",
                        "data": {
                            "request_id": request_id,
                            "from_agent": "InsightReporter",
                            "to_agent": "RequestHandler",
                            "response_status": "empty_response",
                            "timestamp": utc_now()
                        }
                    })
                    return self._response_envelope(
                        status="error",
                        intent="REPORT",
                        error={"code": "empty_report", "message": "InsightReporter가 비어 있는 결과를 반환했습니다.", "details": result},
                    )

                # Event: SYS_RESPONSE_RECEIVED
                self.registry_client.ingest_event({
                    "event_type": "SYS_RESPONSE_RECEIVED",
                    "actor_type": "SYSTEM",
                    "actor_id": self.state.agent_id,
                    "target_type": "AGENT_COMMUNICATION",
                    "target_id": request_id,
                    "severity": "INFO",
                    "data": {
                        "request_id": request_id,
                        "from_agent": "InsightReporter",
                        "to_agent": "RequestHandler",
                        "response_status": "ok",
                        "report_id": report.get("report_id") if isinstance(report, dict) else None,
                        "timestamp": utc_now()
                    }
                })

                return self._response_envelope(
                    status="ok",
                    intent="REPORT",
                    response={
                        "summary": str(report.get("report", {}).get("summary") or report.get("summary") or "리포트를 생성했습니다."),
                        "answer": str(report.get("report", {}).get("summary") or report.get("summary") or ""),
                        "delegated_to": "InsightReporter",
                        "data": report,
                        "source": "InsightReporter",
                    },
                    reasoning=(intent_meta or {}).get("reasoning") if isinstance(intent_meta, dict) else None,
                )
            except asyncio.TimeoutError:
                request_id = payload.get("request_id")
                self.registry_client.ingest_event({
                    "event_type": "SYS_A2A_TIMEOUT",
                    "actor_type": "SYSTEM",
                    "actor_id": self.state.agent_id,
                    "target_type": "AGENT_COMMUNICATION",
                    "target_id": request_id,
                    "severity": "WARNING",
                    "data": {
                        "request_id": request_id,
                        "from_agent": "RequestHandler",
                        "to_agent": "InsightReporter",
                        "timeout_seconds": 300,
                        "timestamp": utc_now()
                    }
                })
                return self._response_envelope(
                    status="needs_clarification",
                    intent="REPORT",
                    response={"summary": "리포트 생성이 지연 중입니다"},
                    error={"code": "report_timeout", "message": "300초 타임아웃", "details": {}},
                )
            except Exception as exc:
                request_id = payload.get("request_id")
                self.registry_client.ingest_event({
                    "event_type": "SYS_A2A_FAILED",
                    "actor_type": "SYSTEM",
                    "actor_id": self.state.agent_id,
                    "target_type": "AGENT_COMMUNICATION",
                    "target_id": request_id,
                    "severity": "ERROR",
                    "data": {
                        "request_id": request_id,
                        "from_agent": "RequestHandler",
                        "to_agent": "InsightReporter",
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                        "timestamp": utc_now()
                    }
                })
                return self._response_envelope(
                    status="error",
                    intent="REPORT",
                    error={"code": "report_failed", "message": str(exc), "details": {}},
                )

        if intent == "MISSION":
            goal = user_input
            feasibility = self._check_area_feasibility(goal, self._summarize_tool_result("get_devices", snapshot["devices"]))
            if not feasibility.get("feasible"):
                return self._response_envelope(
                    status="needs_clarification",
                    intent="MISSION",
                    response={
                        "summary": feasibility.get("reason", "미션 수행 조건이 부족합니다."),
                        "answer": feasibility.get("reason", "미션 수행 조건이 부족합니다."),
                        "delegated_to": "MissionPlanner",
                    },
                    error={"code": feasibility.get("reason_code") or "not_feasible", "message": feasibility.get("reason", ""), "details": feasibility},
                    reasoning=(intent_meta or {}).get("reasoning") if isinstance(intent_meta, dict) else None,
                )
            try:
                request_id = parameters.get("request_id") or f"req-{uuid4()}"
                payload = {
                    "request_id": request_id,
                    "context_id": context_id,
                    "goal": goal,
                    "location": parameters.get("location") or {},
                    "registry_snapshot": snapshot,
                }

                # Event: SYS_REQUEST_SENT (요청 전송)
                self.registry_client.ingest_event({
                    "event_type": "SYS_REQUEST_SENT",
                    "actor_type": "SYSTEM",
                    "actor_id": self.state.agent_id,
                    "target_type": "AGENT_COMMUNICATION",
                    "target_id": request_id,
                    "severity": "INFO",
                    "data": {
                        "request_id": request_id,
                        "from_agent": "RequestHandler",
                        "to_agent": "MissionPlanner",
                        "intent": "MISSION",
                        "goal": goal,
                        "timestamp": utc_now()
                    }
                })

                # A2A 호출 (Timeout: 300초)
                import time
                start_time = time.time()
                result = await asyncio.wait_for(
                    asyncio.to_thread(self._call_system_agent_sync, 9111, payload),
                    timeout=300.0
                )
                duration_ms = int((time.time() - start_time) * 1000)
                proposal = self._unwrap_agent_response(result)

                # AgentLog: MissionPlanner A2A 호출
                self.registry_client.ingest_agent_log({
                    "context_id": context_id,
                    "agent_id": self.state.agent_id,
                    "agent_role": "REQUEST_HANDLER",
                    "action": "call_mission_planner_a2a",
                    "input": payload,
                    "output": proposal,
                    "status": "SUCCESS",
                    "duration_ms": duration_ms
                })

                # Event: SYS_RESPONSE_RECEIVED (응답 수신)
                self.registry_client.ingest_event({
                    "event_type": "SYS_RESPONSE_RECEIVED",
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
                        "proposal_id": proposal.get("id") if isinstance(proposal, dict) else None,
                        "timestamp": utc_now()
                    }
                })

                return self._response_envelope(
                    status="ok",
                    intent="MISSION",
                    response={
                        "summary": "미션 계획 요청을 MissionPlanner로 위임했습니다.",
                        "answer": "미션 계획 요청을 MissionPlanner로 전달했습니다. 생성된 Proposal을 확인해 주세요.",
                        "delegated_to": "MissionPlanner",
                        "data": proposal,
                        "source": "MissionPlanner",
                    },
                    reasoning=(intent_meta or {}).get("reasoning") if isinstance(intent_meta, dict) else None,
                )
            except asyncio.TimeoutError:
                request_id = payload.get("request_id")
                # Event: SYS_A2A_TIMEOUT (요청 타임아웃)
                self.registry_client.ingest_event({
                    "event_type": "SYS_A2A_TIMEOUT",
                    "actor_type": "SYSTEM",
                    "actor_id": self.state.agent_id,
                    "target_type": "AGENT_COMMUNICATION",
                    "target_id": request_id,
                    "severity": "WARNING",
                    "data": {
                        "request_id": request_id,
                        "from_agent": "RequestHandler",
                        "to_agent": "MissionPlanner",
                        "timeout_seconds": 300,
                        "message": "MissionPlanner 응답 시간 초과 (300초)",
                        "timestamp": utc_now()
                    }
                })
                return self._response_envelope(
                    status="needs_clarification",
                    intent="MISSION",
                    response={
                        "summary": "미션 계획 생성이 지연 중입니다",
                        "answer": "MissionPlanner 응답 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.",
                        "delegated_to": "MissionPlanner",
                    },
                    error={"code": "mission_planner_timeout", "message": "300초 타임아웃", "details": {}},
                )
            except Exception as exc:
                request_id = payload.get("request_id")
                # Event: SYS_A2A_FAILED (요청 실패)
                self.registry_client.ingest_event({
                    "event_type": "SYS_A2A_FAILED",
                    "actor_type": "SYSTEM",
                    "actor_id": self.state.agent_id,
                    "target_type": "AGENT_COMMUNICATION",
                    "target_id": request_id,
                    "severity": "ERROR",
                    "data": {
                        "request_id": request_id,
                        "from_agent": "RequestHandler",
                        "to_agent": "MissionPlanner",
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                        "timestamp": utc_now()
                    }
                })
                return self._response_envelope(
                    status="error",
                    intent="MISSION",
                    error={"code": "mission_delegate_failed", "message": str(exc), "details": {}},
                )

        if intent == "SYSTEM_CONTROL":
            try:
                proposal_payload = {
                    "type": "SYSTEM_CONTROL",
                    "title": user_input[:100],
                    "status": "PROPOSED",
                    "priority": "NORMAL",
                    "requires_approval": True,
                    "category_data": {
                        "action": parameters.get("action") or "unknown",
                        "target_system": "cowater_system",
                    },
                    "created_by": {
                        "type": "USER",
                        "id": "system",
                    },
                }
                result = self.registry_client.create_proposal(proposal_payload)
                proposal_id = result.get("id")

                # AgentLog: 시스템 제어 제안 생성
                self.registry_client.ingest_agent_log({
                    "context_id": context_id,
                    "agent_id": self.state.agent_id,
                    "agent_role": "REQUEST_HANDLER",
                    "action": "create_system_control_proposal",
                    "input": proposal_payload,
                    "output": result,
                    "status": "SUCCESS"
                })

                # Event: SYS_PROPOSAL_GENERATED (시스템 제어 제안 생성)
                self.registry_client.ingest_event({
                    "event_type": "SYS_PROPOSAL_GENERATED",
                    "actor_type": "SYSTEM",
                    "actor_id": self.state.agent_id,
                    "target_type": "PROPOSAL",
                    "target_id": proposal_id,
                    "severity": "INFO",
                    "data": {
                        "proposal_id": proposal_id,
                        "type": "SYSTEM_CONTROL",
                        "title": user_input[:100],
                        "requires_approval": True,
                        "reasoning": (intent_meta or {}).get("reasoning") if isinstance(intent_meta, dict) else None,
                        "timestamp": utc_now()
                    }
                })

                return self._response_envelope(
                    status="needs_approval",
                    intent="SYSTEM_CONTROL",
                    response={
                        "summary": "시스템 제어 작업은 사용자 승인이 필요합니다.",
                        "answer": f"다음 작업을 확인해주세요: {user_input}",
                        "proposal_id": proposal_id,
                        "requires_approval": True,
                    },
                    reasoning=(intent_meta or {}).get("reasoning") if isinstance(intent_meta, dict) else None,
                )
            except Exception as exc:
                return self._response_envelope(
                    status="error",
                    intent="SYSTEM_CONTROL",
                    error={"code": "proposal_creation_failed", "message": str(exc), "details": {}},
                )

        return self._response_envelope(
            status="needs_clarification",
            intent="UNKNOWN",
            response={
                "summary": "요청 의도를 분류할 수 없습니다.",
                "answer": "조회, 리포트, 미션, 시스템 제어 중 하나로 다시 말해 주세요.",
            },
            reasoning=(intent_meta or {}).get("reasoning") if isinstance(intent_meta, dict) else None,
        )

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
