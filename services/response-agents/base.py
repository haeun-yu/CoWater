"""
Response Agent 기본 클래스.

분석 결과를 받아서 경보 생성 및 사용자 대응.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional
from uuid import uuid4

import httpx
import redis.asyncio as aioredis

from shared.events import Event, EventType, get_channel_for_event

logger = logging.getLogger(__name__)


class ResponseAgent(ABC):
    """Response 계층 Agent 기본 클래스"""

    agent_id: str = "response-base"

    def __init__(self, redis: aioredis.Redis, core_api_url: str) -> None:
        self._redis = redis
        self._core_api_url = core_api_url

    @abstractmethod
    async def on_analyze_event(self, event: Event) -> None:
        """Analysis 이벤트 수신 및 대응"""
        pass

    # ─────────────────────────────────────────────────────────────────────────
    # Alert 생성 (Core API 호출)
    # ─────────────────────────────────────────────────────────────────────────

    async def create_alert(
        self,
        alert_type: str,
        severity: str,
        platform_ids: list[str],
        message: str,
        recommendation: Optional[str] = None,
        metadata: Optional[dict] = None,
        zone_id: Optional[str] = None,
        dedup_key: Optional[str] = None,
        resolve_dedup_key: Optional[str] = None,
        resolve_only: bool = False,
    ) -> Optional[str]:
        """
        Core API를 통해 Alert 생성.

        Returns: alert_id, 또는 None (실패 시)
        """

        payload = {
            "alert_type": alert_type,
            "severity": severity,
            "platform_ids": platform_ids,
            "zone_id": zone_id,
            "generated_by": self.agent_id,
            "message": message,
            "recommendation": recommendation,
            "metadata": metadata or {},
            "dedup_key": dedup_key,
            "resolve_dedup_key": resolve_dedup_key,
            "resolve_only": resolve_only,
        }

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    f"{self._core_api_url}/alerts",
                    json=payload,
                    timeout=5.0,
                )

            resp.raise_for_status()
            data = resp.json()

            alert_id = data.get("alert_id")
            logger.info("Alert created: %s (type=%s, severity=%s)", alert_id, alert_type, severity)

            return alert_id

        except Exception as e:
            logger.error("Failed to create alert: %s", e)
            return None

    async def acknowledge_alert(self, alert_id: str) -> bool:
        """Alert를 acknowledged 상태로 변경"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.patch(
                    f"{self._core_api_url}/alerts/{alert_id}/acknowledge",
                    timeout=5.0,
                )

            resp.raise_for_status()
            logger.info("Alert acknowledged: %s", alert_id)
            return True

        except Exception as e:
            logger.error("Failed to acknowledge alert: %s", e)
            return False

    async def resolve_alert(self, alert_id: str) -> bool:
        """Alert를 resolved 상태로 변경"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.patch(
                    f"{self._core_api_url}/alerts/{alert_id}/resolve",
                    timeout=5.0,
                )

            resp.raise_for_status()
            logger.info("Alert resolved: %s", alert_id)
            return True

        except Exception as e:
            logger.error("Failed to resolve alert: %s", e)
            return False

    # ─────────────────────────────────────────────────────────────────────────
    # Event 발행
    # ─────────────────────────────────────────────────────────────────────────

    async def emit_response_event(
        self,
        event_type: EventType,
        payload: dict,
        flow_id: Optional[str] = None,
        causation_id: Optional[str] = None,
    ) -> None:
        """대응 이벤트 발행"""

        event = Event(
            flow_id=flow_id or str(uuid4()),
            type=event_type,
            agent_id=self.agent_id,
            payload=payload,
            causation_id=causation_id,
            timestamp=datetime.utcnow(),
        )

        channel = get_channel_for_event(event)
        await self._redis.publish(channel, event.to_json())

        logger.info(
            "Response event emitted: %s → %s",
            event_type.value,
            channel,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Heartbeat
    # ─────────────────────────────────────────────────────────────────────────

    async def send_heartbeat(self) -> None:
        """주기적으로 agent 상태 신호 송신"""
        event = Event(
            flow_id="heartbeat",
            type=EventType.SYSTEM_HEARTBEAT,
            agent_id=self.agent_id,
            payload={
                "status": "healthy",
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

        channel = get_channel_for_event(event)
        await self._redis.publish(channel, event.to_json())
