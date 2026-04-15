"""Report Agent 기본 클래스"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime

import redis.asyncio as aioredis

from shared.events import Event, EventType, get_channel_for_event


class ReportAgent(ABC):
    """보고서 생성 Agent 기본 클래스"""

    agent_id: str = "report-agent"

    def __init__(self, redis: aioredis.Redis) -> None:
        self.redis = redis

    @abstractmethod
    async def on_respond_event(self, event: Event) -> None:
        """respond.* 이벤트 수신"""
        pass

    async def send_heartbeat(self) -> None:
        """주기적 heartbeat 송신"""
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
        await self.redis.publish(channel, event.to_json())

    async def emit_report_event(
        self,
        report_id: str,
        flow_id: str,
        report_type: str,
        content: str,
    ) -> None:
        """report.* 이벤트 발행"""
        event = {
            "report_id": report_id,
            "flow_id": flow_id,
            "report_type": report_type,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
            "generated_by": self.agent_id,
        }
        await self.redis.publish(f"report.{report_type}", json.dumps(event))
