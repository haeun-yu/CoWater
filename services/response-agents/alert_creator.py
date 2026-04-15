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

    async def on_detect_event(self, event: Event) -> None:
        if event.type == EventType.DETECT_CPA:
            await self._handle_cpa_detect(event)
        elif event.type == EventType.DETECT_ZONE:
            await self._handle_zone_detect(event)

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
            dedup_key=(
                f"anomaly:{payload.get('platform_id')}:{payload.get('original_anomaly_type')}"
                if payload.get("platform_id") and payload.get("original_anomaly_type")
                else None
            ),
        )

        if alert_id:
            # Alert 생성 Event 발행
            await self.emit_response_event(
                event_type=EventType.RESPOND_ALERT,
                payload={
                    "alert_id": alert_id,
                    "alert_ids": [alert_id],
                    "platform_id": platform_id,
                    "alert_type": alert_type,
                    "severity": severity,
                    "message": message,
                },
                flow_id=event.flow_id,
                causation_id=event.event_id,
            )

    async def _handle_cpa_detect(self, event: Event) -> None:
        payload = event.payload
        platform_ids = [
            pid for pid in [payload.get("platform_id"), payload.get("target_platform_id")] if pid
        ]
        if len(platform_ids) != 2:
            return

        dedup_key = f"cpa:{min(platform_ids)}:{max(platform_ids)}"
        if payload.get("event_state") == "cleared":
            await self.create_alert(
                alert_type="cpa_cleared",
                severity="info",
                platform_ids=platform_ids,
                message=f"CPA 위험 해소: {platform_ids[0]} ↔ {platform_ids[1]}",
                metadata={"resolve_only": True, "reason": payload.get("reason")},
                resolve_dedup_key=dedup_key,
                resolve_only=True,
            )
            return

        message = (
            f"충돌 위험 {payload.get('severity', 'warning').upper()}: "
            f"{platform_ids[0]} ↔ {platform_ids[1]} "
            f"CPA={payload.get('cpa_nm'):.2f}NM TCPA={payload.get('tcpa_minutes'):.1f}분"
        )
        alert_id = await self.create_alert(
            alert_type="cpa",
            severity=payload.get("severity", "warning"),
            platform_ids=platform_ids,
            message=message,
            metadata={
                "cpa_nm": payload.get("cpa_nm"),
                "tcpa_min": payload.get("tcpa_minutes"),
                "event_state": payload.get("event_state"),
                "reason": payload.get("reason"),
            },
            dedup_key=dedup_key,
        )
        if alert_id:
            await self.emit_response_event(
                event_type=EventType.RESPOND_ALERT,
                payload={
                    "alert_id": alert_id,
                    "alert_ids": [alert_id],
                    "platform_id": payload.get("platform_id"),
                    "alert_type": "cpa",
                    "severity": payload.get("severity", "warning"),
                    "message": message,
                },
                flow_id=event.flow_id,
                causation_id=event.event_id,
            )

    async def _handle_zone_detect(self, event: Event) -> None:
        payload = event.payload
        platform_id = payload.get("platform_id")
        zone_id = payload.get("zone_id")
        if not platform_id or not zone_id:
            return

        dedup_key = f"zone:{platform_id}:{zone_id}"
        zone_name = payload.get("zone_name", zone_id)
        event_type = payload.get("event_type")

        if event_type == "exit":
            await self.create_alert(
                alert_type="zone_exit",
                severity="info",
                platform_ids=[platform_id],
                zone_id=zone_id,
                message=f"{platform_id}가 구역 '{zone_name}'에서 이탈",
                metadata={"resolve_only": True, "event_type": event_type},
                resolve_dedup_key=dedup_key,
                resolve_only=True,
            )
            return

        message = f"{platform_id}가 {payload.get('zone_type')} 구역 '{zone_name}'에 진입"
        alert_id = await self.create_alert(
            alert_type="zone_intrusion",
            severity=payload.get("severity", "warning"),
            platform_ids=[platform_id],
            zone_id=zone_id,
            message=message,
            metadata={
                "zone_name": zone_name,
                "zone_type": payload.get("zone_type"),
                "event_type": event_type,
            },
            dedup_key=dedup_key,
        )
        if alert_id:
            await self.emit_response_event(
                event_type=EventType.RESPOND_ALERT,
                payload={
                    "alert_id": alert_id,
                    "alert_ids": [alert_id],
                    "platform_id": platform_id,
                    "alert_type": "zone_intrusion",
                    "severity": payload.get("severity", "warning"),
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
