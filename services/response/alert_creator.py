"""
Response - Alert Creator Agent

분석 결과를 받아서 Alert 객체를 생성하고 Core API에 저장.
"""

from __future__ import annotations

import logging
from uuid import uuid4

import redis.asyncio as aioredis

from shared.events import Event, EventType
from .base import ResponseAgent

logger = logging.getLogger(__name__)


class ResponseAlertCreatorAgent(ResponseAgent):
    """Response 단계: Alert 생성"""

    agent_id = "response-alert-creator"

    def __init__(self, redis: aioredis.Redis, core_api_url: str) -> None:
        super().__init__(redis, core_api_url)

    async def on_analyze_event(self, event: Event) -> None:
        """분석 이벤트 수신 및 Alert 생성"""

        if event.type == EventType.ANALYZE_ANOMALY:
            await self._handle_anomaly_analysis(event)

    async def _handle_anomaly_analysis(self, event: Event) -> None:
        """비정상 분석 결과 → Alert 생성"""

        payload = event.payload
        platform_id = payload.get("platform_id")
        alert_type = "anomaly"
        severity = self._get_severity(payload)
        message = payload.get("analysis_result", "비정상 감지됨")
        recommendation = payload.get("recommendation")

        # Alert 생성
        alert_id = await self.create_alert(
            alert_type=alert_type,
            severity=severity,
            platform_ids=[platform_id] if platform_id else [],
            message=message,
            recommendation=recommendation,
            metadata={
                "original_anomaly_type": payload.get("original_anomaly_type"),
                "confidence": payload.get("confidence"),
                "ai_model": payload.get("ai_model"),
            },
        )

        if alert_id:
            # Alert 생성 Event 발행
            await self.emit_response_event(
                event_type=EventType.RESPOND_ALERT,
                payload={
                    "alert_id": alert_id,
                    "platform_id": platform_id,
                    "alert_type": alert_type,
                    "severity": severity,
                    "message": message,
                },
                flow_id=event.flow_id,
                causation_id=event.event_id,
            )

    @staticmethod
    def _get_severity(payload: dict) -> str:
        """분석 결과에서 심각도 결정"""
        confidence = payload.get("confidence", 0.5)

        # confidence > 0.8 → critical
        # confidence > 0.5 → warning
        # else → info

        if confidence > 0.8:
            return "critical"
        elif confidence > 0.5:
            return "warning"
        else:
            return "info"
