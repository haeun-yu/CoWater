from __future__ import annotations

import logging
from typing import Any

from agent.base_runtime import BaseAgentRuntime
from agent.state import utc_now

logger = logging.getLogger(__name__)


class PolicyManagerRuntime(BaseAgentRuntime):
    """PolicyManager 역할: 기존 정책/규칙 평가 및 추천 액션 반환"""

    async def handle_moth_message(self, event_type: str, payload: dict[str, Any], raw_event: dict[str, Any]) -> None:
        # 정책을 새로 실행하거나 미션을 만들지 않는다. 관찰된 이벤트만 기록한다.
        self.state.remember({"kind": "policy_event_seen", "at": utc_now(), "event_type": event_type, "payload": payload})

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
        query = self._normalize_query(parameters)
        try:
            policies = self.registry_client.list_policies()
        except Exception as exc:
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
