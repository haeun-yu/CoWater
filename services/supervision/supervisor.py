"""
Supervisor Agent

모든 Agent의 상태를 모니터링하고 장애 감지.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

import redis.asyncio as aioredis

from shared.events import Event, EventType

logger = logging.getLogger(__name__)

# 모니터링 대상 Agent 목록
MONITORED_AGENTS = [
    "detection-cpa",
    "detection-anomaly",
    "detection-zone",
    "detection-distress",
    "analysis-anomaly-ai",
    "analysis-report",
    "response-alert-creator",
]

# Heartbeat 타임아웃 (초)
HEARTBEAT_TIMEOUT_SEC = 300  # 5분


class Supervisor:
    """모든 Agent의 상태를 모니터링"""

    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis
        self._last_heartbeat: dict[str, datetime] = {}

    async def start_monitoring(self) -> None:
        """Agent 상태 모니터링 시작"""
        # system.heartbeat.* 이벤트 구독
        pubsub = self._redis.pubsub()
        await pubsub.psubscribe("system.heartbeat.*")

        logger.info("Supervisor: started monitoring %d agents", len(MONITORED_AGENTS))

        async for msg in pubsub.listen():
            if msg["type"] != "pmessage":
                continue

            try:
                data = json.loads(msg["data"])
                event = Event.from_json(json.dumps(data))

                agent_id = event.agent_id
                self._last_heartbeat[agent_id] = event.timestamp

                # logger.debug("Heartbeat received from %s", agent_id)

            except Exception as e:
                logger.error("Error processing heartbeat: %s", e)

    async def check_health(self) -> dict:
        """Agent 상태 확인"""
        now = datetime.utcnow()
        health_status = {}

        for agent_id in MONITORED_AGENTS:
            last_beat = self._last_heartbeat.get(agent_id)

            if last_beat is None:
                health_status[agent_id] = "unknown"
            elif (now - last_beat).total_seconds() > HEARTBEAT_TIMEOUT_SEC:
                health_status[agent_id] = "unhealthy"
                logger.error(
                    "Agent %s is unhealthy (no heartbeat for %.0fs)",
                    agent_id,
                    (now - last_beat).total_seconds(),
                )
            else:
                health_status[agent_id] = "healthy"

        return health_status

    async def emit_system_alert(
        self,
        alert_type: str,
        message: str,
        details: dict | None = None,
    ) -> None:
        """시스템 alert 발행 (Redis 채널)"""
        alert = {
            "type": alert_type,
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
            "details": details or {},
        }

        channel = "system.alert"
        await self._redis.publish(channel, json.dumps(alert))

        logger.error("System alert: %s - %s", alert_type, message)
