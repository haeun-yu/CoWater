"""
PolicyRegistry: 정책 저장소 및 평가 엔진

사전 정의된 정책이 있는 Critical 상황에서 제한적 자동 대응이 가능.
(아키텍처 Ch.17.1)
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


class PolicyRegistry:
    """정책 메모리 저장소 (임시: JSON 파일 또는 메모리)"""

    def __init__(self) -> None:
        self.policies: dict[str, dict[str, Any]] = {}
        self._load_default_policies()

    def _load_default_policies(self) -> None:
        """기본 정책 로드"""
        # 예시: 디바이스 LOST 시 Return to Base
        self.policies["auto_rtb_on_lost"] = {
            "policy_id": "auto_rtb_on_lost",
            "policy_name": "Lost Device Return to Base",
            "enabled": True,
            "trigger_condition": {
                "event_type": "device_connectivity_changed",
                "new_status": "lost",
            },
            "action": {
                "task_type": "return_to_base",
                "priority": "critical",
            },
        }

        # 예시: 배터리 부족 시 경고
        self.policies["alert_low_battery"] = {
            "policy_id": "alert_low_battery",
            "policy_name": "Low Battery Alert",
            "enabled": True,
            "trigger_condition": {
                "event_type": "battery_low",
                "threshold": 20,
            },
            "action": {
                "type": "alert_only",  # 자동 대응 없음, Alert만
            },
        }

    def get_policies(self) -> list[dict[str, Any]]:
        """모든 정책 조회"""
        return list(self.policies.values())

    def get_policy(self, policy_id: str) -> Optional[dict[str, Any]]:
        """정책 조회"""
        return self.policies.get(policy_id)

    def create_policy(self, policy: dict[str, Any]) -> dict[str, Any]:
        """정책 생성"""
        policy_id = policy.get("policy_id") or str(uuid4())
        policy["policy_id"] = policy_id
        self.policies[policy_id] = policy
        logger.info(f"Policy created: {policy_id} - {policy.get('policy_name')}")
        return policy

    def update_policy(self, policy_id: str, policy: dict[str, Any]) -> dict[str, Any]:
        """정책 업데이트"""
        policy["policy_id"] = policy_id
        self.policies[policy_id] = policy
        logger.info(f"Policy updated: {policy_id}")
        return policy

    def delete_policy(self, policy_id: str) -> None:
        """정책 삭제"""
        if policy_id in self.policies:
            del self.policies[policy_id]
            logger.info(f"Policy deleted: {policy_id}")

    def find_policies_by_trigger(self, event_type: str) -> list[dict[str, Any]]:
        """Event type으로 정책 조회"""
        matched = []
        for policy in self.policies.values():
            if not policy.get("enabled"):
                continue
            trigger = policy.get("trigger_condition") or {}
            if trigger.get("event_type") == event_type:
                matched.append(policy)
        return matched

    def evaluate_condition(self, condition: dict[str, Any], event: dict[str, Any]) -> bool:
        """정책 조건 평가"""
        event_type = condition.get("event_type")
        if event.get("event_type") != event_type:
            return False

        # 추가 조건 확인
        for key, expected_value in condition.items():
            if key == "event_type":
                continue
            event_value = event.get(key)
            if event_value != expected_value:
                return False

        return True
