from __future__ import annotations

from typing import Any

from agent.base_runtime import BaseAgentRuntime
from agent.state import utc_now


class PolicyManagerRuntime(BaseAgentRuntime):
    """PolicyManager 역할: 기존 정책/규칙 평가 및 추천 액션 반환"""

    async def handle_moth_message(self, event_type: str, payload: dict[str, Any], raw_event: dict[str, Any]) -> bool:
        if event_type == "SYS_ANOMALY_DETECTED":
            self.state.remember({"kind": "policy_event_seen", "at": utc_now(), "event_type": event_type, "payload": payload})
            return True
        return False

    async def _execute_role(self, parameters: dict[str, Any]) -> dict[str, Any]:
        return self._execute_policy_manager(parameters)

    def _normalize_query(self, parameters: dict[str, Any]) -> dict[str, Any]:
        return {
            "action": str(parameters.get("action") or parameters.get("command") or parameters.get("policy_action") or "").strip(),
            "risk": str(parameters.get("risk") or parameters.get("severity") or "unknown").strip().lower(),
            "source": parameters.get("source") or {},
            "context": parameters.get("context") or {},
        }

    def _policy_matches(self, policy: dict[str, Any], query: dict[str, Any]) -> bool:
        if not isinstance(policy, dict):
            return False
        if policy.get("enabled") is False:
            return False
        action = query.get("action")
        if action:
            candidates = {
                str(policy.get("name") or "").lower(),
                str(policy.get("policy_name") or "").lower(),
                str(policy.get("action") or "").lower(),
                str((policy.get("metadata") or {}).get("action") or "").lower(),
            }
            if action.lower() not in candidates and action.lower() not in str(policy).lower():
                return False
        return True

    def _decision_from_policy(self, policy: dict[str, Any], query: dict[str, Any]) -> dict[str, Any]:
        risk = query.get("risk")
        policy_mode = str(policy.get("mode") or policy.get("decision") or policy.get("response_mode") or "").lower()
        if any(term in policy_mode for term in ["deny", "block", "escalate"]):
            return {"mode": "escalate", "recommended_action": "escalate", "reason": "policy explicitly escalates"}
        if any(term in policy_mode for term in ["auto", "allow", "execute"]) and risk not in {"high", "critical"}:
            return {"mode": "auto_execute", "recommended_action": "auto_execute", "reason": "existing policy allows automatic execution"}
        return {"mode": "approval_required", "recommended_action": "request_approval", "reason": "policy does not explicitly allow automatic execution"}

    def _execute_policy_manager(self, parameters: dict[str, Any]) -> dict[str, Any]:
        from uuid import uuid4
        import time

        request_id = str(parameters.get("request_id") or "")
        context_id = str(parameters.get("context_id") or f"ctx-{uuid4()}")
        start_time = time.time()

        # Event: SYS_REQUEST_RECEIVED (A2A 요청 수신)
        if request_id:
            self.registry_client.ingest_event({
                "event_type": "SYS_REQUEST_RECEIVED",
                "context_id": context_id,
                "actor_type": "SYSTEM",
                "actor_id": self.state.agent_id,
                "target_type": "AGENT_COMMUNICATION",
                "target_id": request_id,
                "severity": "INFO",
                "data": {
                    "request_id": request_id,
                    "from_agent": "RequestHandler",
                    "to_agent": "PolicyManager",
                    "timestamp": utc_now()
                }
            })

        query = self._normalize_query(parameters)
        try:
            policies = self.registry_client.list_policies()
        except Exception as exc:
            duration_ms = int((time.time() - start_time) * 1000)
            self.registry_client.ingest_agent_log({
                "context_id": context_id,
                "agent_id": self.state.agent_id,
                "agent_role": "POLICY_MANAGER",
                "action": "evaluate_policies",
                "input": {"action": query.get("action"), "risk": query.get("risk")},
                "output": {},
                "status": "FAILED",
                "duration_ms": duration_ms,
            })
            if request_id:
                self.registry_client.ingest_event({
                    "event_type": "SYS_RESPONSE_SENT",
                    "context_id": context_id,
                    "actor_type": "SYSTEM",
                    "actor_id": self.state.agent_id,
                    "target_type": "AGENT_COMMUNICATION",
                    "target_id": request_id,
                    "severity": "ERROR",
                    "data": {
                        "request_id": request_id,
                        "from_agent": "PolicyManager",
                        "to_agent": "RequestHandler",
                        "response_status": "error",
                        "error_type": type(exc).__name__,
                        "timestamp": utc_now()
                    }
                })
            return self._response_envelope(
                status="error",
                response={
                    "decision": {"mode": "approval_required", "recommended_action": "request_approval", "reason": f"정책 조회 실패: {exc}"},
                    "matched_rules": [],
                    "query": query,
                },
                error={"code": "policy_lookup_failed", "message": str(exc), "details": {}},
            )

        matched_rules = [policy for policy in policies if self._policy_matches(policy, query)]
        if not matched_rules:
            duration_ms = int((time.time() - start_time) * 1000)
            self.registry_client.ingest_agent_log({
                "context_id": context_id,
                "agent_id": self.state.agent_id,
                "agent_role": "POLICY_MANAGER",
                "action": "evaluate_policies",
                "input": {"action": query.get("action"), "risk": query.get("risk"), "policies_checked": len(policies)},
                "output": {"decision": "approval_required", "matched_rules_count": 0},
                "reasoning": {
                    "matched_rules": 0,
                    "default_decision": "request_approval",
                },
                "status": "SUCCESS",
                "duration_ms": duration_ms,
            })
            if request_id:
                self.registry_client.ingest_event({
                    "event_type": "SYS_RESPONSE_SENT",
                    "context_id": context_id,
                    "actor_type": "SYSTEM",
                    "actor_id": self.state.agent_id,
                    "target_type": "AGENT_COMMUNICATION",
                    "target_id": request_id,
                    "severity": "INFO",
                    "data": {
                        "request_id": request_id,
                        "from_agent": "PolicyManager",
                        "to_agent": "RequestHandler",
                        "response_status": "ok",
                        "policy_decision": "no_policy_matched",
                        "timestamp": utc_now()
                    }
                })
            return self._response_envelope(
                status="needs_clarification",
                response={
                    "decision": {
                        "mode": "approval_required",
                        "recommended_action": "request_approval",
                        "reason": "매칭되는 기존 정책이 없습니다. 보수적으로 승인 필요로 처리합니다.",
                    },
                    "matched_rules": [],
                    "query": query,
                },
            )

        prioritized = matched_rules[0]
        decision = self._decision_from_policy(prioritized, query)
        if query["risk"] in {"high", "critical"} and decision["mode"] == "auto_execute":
            decision = {
                "mode": "approval_required",
                "recommended_action": "request_approval",
                "reason": "위험도가 높아 자동 실행을 보수적으로 차단합니다.",
            }

        duration_ms = int((time.time() - start_time) * 1000)
        self.registry_client.ingest_agent_log({
            "context_id": context_id,
            "agent_id": self.state.agent_id,
            "agent_role": "POLICY_MANAGER",
            "action": "evaluate_policies",
            "input": {"action": query.get("action"), "risk": query.get("risk"), "policies_checked": len(policies)},
            "output": {"decision": decision.get("mode"), "matched_rules_count": len(matched_rules)},
            "reasoning": {
                "matched_policies": [p.get("name") or p.get("policy_name") for p in matched_rules],
                "decision_reason": decision.get("reason"),
            },
            "status": "SUCCESS",
            "duration_ms": duration_ms,
        })
        if request_id:
            self.registry_client.ingest_event({
                "event_type": "SYS_RESPONSE_SENT",
                "context_id": context_id,
                "actor_type": "SYSTEM",
                "actor_id": self.state.agent_id,
                "target_type": "AGENT_COMMUNICATION",
                "target_id": request_id,
                "severity": "INFO",
                "data": {
                    "request_id": request_id,
                    "from_agent": "PolicyManager",
                    "to_agent": "RequestHandler",
                    "response_status": "ok",
                    "policy_decision": decision.get("mode"),
                    "timestamp": utc_now()
                }
            })

        return self._response_envelope(
            status="ok",
            response={
                "decision": decision,
                "matched_rules": [
                    {
                        "policy_id": policy.get("policy_id") or policy.get("id"),
                        "name": policy.get("name") or policy.get("policy_name"),
                        "mode": policy.get("mode") or policy.get("decision") or policy.get("response_mode"),
                    }
                    for policy in matched_rules
                ],
                "query": query,
            },
        )
