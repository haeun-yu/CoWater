"""
Learning Agent

사용자 피드백 기반으로 시스템을 지속적으로 개선.
- 거짓 경보율(FP rate) 추적
- Detection Agent의 threshold 자동 조정
- 규칙 개선 제안
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

import httpx
import redis.asyncio as aioredis

from shared.events import Event, EventType

logger = logging.getLogger(__name__)


class LearningAgent:
    """
    피드백 기반 학습 Agent.

    흐름:
    1. system.alert_acknowledge 이벤트 수신 (사용자 피드백)
    2. Agent별 거짓 경보율 계산
    3. 규칙 개선 제안 및 learn.rule_update 이벤트 발행
    """

    agent_id = "learning-feedback"

    def __init__(self, redis: aioredis.Redis, core_api_url: str) -> None:
        self._redis = redis
        self._core_api_url = core_api_url

    async def on_alert_feedback(self, event: Event) -> None:
        """
        Alert acknowledge 이벤트 수신 (사용자 피드백).

        payload: {
            "alert_id": "...",
            "feedback": "false_positive" | "confirmed" | "partial",
            "reason": "...",
            "user_id": "..."
        }
        """

        payload = event.payload
        alert_id = payload.get("alert_id")
        feedback = payload.get("feedback")
        reason = payload.get("reason", "")

        logger.info("Alert feedback: %s = %s (reason: %s)", alert_id, feedback, reason)

        if feedback not in ("false_positive", "confirmed", "partial"):
            logger.warning("Unknown feedback type: %s", feedback)
            return

        # Alert 정보 조회 (모든 피드백 타입에서 에이전트 특정)
        alert_info = await self._get_alert_info(alert_id)
        if not alert_info:
            logger.warning("Alert not found: %s", alert_id)
            return

        agent_id = alert_info.get("generated_by")
        await self.track_feedback(agent_id, feedback)

        if feedback == "false_positive":
            # 해당 Agent의 거짓 경보율 계산
            fp_rate = await self._calculate_fp_rate(agent_id)

            logger.info(
                "FP rate for %s: %.1f%% (feedback on %s)",
                agent_id,
                fp_rate * 100,
                alert_id,
            )

            # FP rate가 높으면 규칙 조정 제안
            if fp_rate > 0.3:  # 30% 이상
                await self._propose_rule_update(agent_id, fp_rate, reason)

    async def _get_alert_info(self, alert_id: str) -> dict | None:
        """Core API에서 Alert 정보 조회"""
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(
                    f"{self._core_api_url}/alerts/{alert_id}",
                    timeout=2.0,
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.error("Failed to fetch alert info: %s", e)
            return None

    async def _calculate_fp_rate(self, agent_id: str) -> float:
        """
        최근 N개 경보 중 거짓 경보 비율 계산.

        Redis에 agent:fp_feedback 해시로 추적:
        - false_positive: count
        - confirmed: count
        - total: count
        """
        try:
            key = f"agent:fp_feedback:{agent_id}"
            data = await self._redis.hgetall(key)

            total = int(data.get(b"total", 0))
            false_positives = int(data.get(b"false_positive", 0))

            if total == 0:
                return 0.0

            return false_positives / total

        except Exception as e:
            logger.error("Failed to calculate FP rate for %s: %s", agent_id, e)
            return 0.0

    async def _propose_rule_update(
        self,
        agent_id: str,
        fp_rate: float,
        reason: str,
    ) -> None:
        """규칙 조정 제안"""

        # Agent별 조정 전략
        adjustments = {
            "detection-cpa": {
                "old_config": {"critical_cpa_nm": 0.5},
                "new_config": {"critical_cpa_nm": 1.0},  # threshold 상향
                "reason": f"FP rate {fp_rate*100:.0f}% - CPA threshold 상향",
            },
            "detection-anomaly": {
                "old_config": {"rot_threshold": 20},
                "new_config": {"rot_threshold": 30},
                "reason": f"FP rate {fp_rate*100:.0f}% - ROT threshold 상향",
            },
            "analysis-anomaly-ai": {
                "old_config": {"confidence_threshold": 0.5},
                "new_config": {"confidence_threshold": 0.7},
                "reason": f"FP rate {fp_rate*100:.0f}% - confidence threshold 상향",
            },
        }

        adjustment = adjustments.get(agent_id)
        if not adjustment:
            logger.info("No rule adjustment strategy for %s", agent_id)
            return

        logger.info(
            "Proposing rule update for %s: %s → %s",
            agent_id,
            adjustment["old_config"],
            adjustment["new_config"],
        )

        # learn.rule_update 이벤트 발행
        event = Event(
            flow_id=f"rule_update:{agent_id}",
            type=EventType.LEARN_RULE_UPDATE,
            agent_id=self.agent_id,
            payload={
                "target_agent_id": agent_id,
                "old_config": adjustment["old_config"],
                "new_config": adjustment["new_config"],
                "reason": adjustment["reason"],
                "confidence": 0.7,  # 제안의 신뢰도
            },
        )

        channel = f"learn.rule_update.{agent_id}"
        await self._redis.publish(channel, event.to_json())

    async def track_feedback(
        self,
        agent_id: str,
        feedback: str,
    ) -> None:
        """피드백 통계 업데이트"""
        try:
            key = f"agent:fp_feedback:{agent_id}"

            # 피드백 카운트 증가
            await self._redis.hincrby(key, feedback, 1)
            await self._redis.hincrby(key, "total", 1)

            # TTL 설정 (30일)
            await self._redis.expire(key, 30 * 24 * 60 * 60)

        except Exception as e:
            logger.error("Failed to track feedback for %s: %s", agent_id, e)

    async def on_respond_event(self, event: dict) -> None:
        """respond.* 이벤트 수신 (대응 완료 이벤트)

        대응이 완료된 이벤트를 분석해서 파라미터 조정 제안을 생성합니다.
        """
        try:
            flow_id = event.get("flow_id") if isinstance(event, dict) else event.payload.get("flow_id")
            alert_ids = event.get("alert_ids") if isinstance(event, dict) else event.payload.get("alert_ids", [])

            logger.info("Learning: analyzing respond event for flow %s (%d alerts)", flow_id, len(alert_ids) if alert_ids else 0)

            # 대응 이벤트 저장 (선택적)
            # 실제 파라미터 조정은 사용자 피드백 후에 수행

        except Exception as e:
            logger.exception("Error processing respond event: %s", e)

    async def on_user_event(self, event: dict) -> None:
        """user.* 이벤트 수신 (사용자 명령/피드백)

        사용자 명령이나 피드백을 처리해서 학습 데이터로 기록합니다.
        """
        try:
            event_data = event if isinstance(event, dict) else event.payload
            event_type = event_data.get("type")
            user_id = event_data.get("user_id")

            logger.info("Learning: processing user event %s from %s", event_type, user_id)

            # 사용자 피드백 저장 (선택적)
            # 예: 사용자가 "이 경보는 거짓 경보다"라고 표시한 경우

        except Exception as e:
            logger.exception("Error processing user event: %s", e)
