"""
Analysis Agent 기본 클래스.

Detection 이벤트를 받아서 분석하고 analyze.* 이벤트 발행.
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


class AnalysisAgent(ABC):
    """Analysis 계층 Agent 기본 클래스"""

    agent_id: str = "analysis-base"

    def __init__(self, redis: aioredis.Redis, core_api_url: str) -> None:
        self._redis = redis
        self._core_api_url = core_api_url

    @abstractmethod
    async def on_detect_event(self, event: Event) -> None:
        """Detection 이벤트 수신 및 분석"""
        pass

    # ─────────────────────────────────────────────────────────────────────────
    # Event 발행
    # ─────────────────────────────────────────────────────────────────────────

    async def emit_analysis_event(
        self,
        event_type: EventType,
        payload: dict,
        flow_id: Optional[str] = None,
        causation_id: Optional[str] = None,
    ) -> None:
        """분석 결과 Event 발행"""

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
            "Analysis event emitted: %s → %s (flow=%s, caused_by=%s)",
            event_type.value,
            channel,
            event.flow_id[:8],
            causation_id[:8] if causation_id else "None",
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
