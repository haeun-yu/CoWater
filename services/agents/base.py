"""
Agent 기본 클래스.

모든 Rule Agent / AI Agent가 이 클래스를 상속한다.
- on_platform_report(): 위치 보고 이벤트 처리
- on_alert(): 다른 Agent가 생성한 Alert 처리 (연계 로직)
- emit_alert(): Alert를 Redis에 퍼블리시
- L1/L2/L3 자율성 레벨 적용
"""

from __future__ import annotations

import json
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

AgentLevel = Literal["L1", "L2", "L3"]
AgentType = Literal["rule", "ai"]


@dataclass
class PlatformReport:
    platform_id: str
    timestamp: datetime
    lat: float
    lon: float
    depth_m: float | None
    altitude_m: float | None
    sog: float | None
    cog: float | None
    heading: float | None
    rot: float | None
    nav_status: str | None
    source_protocol: str

    @classmethod
    def from_dict(cls, d: dict) -> "PlatformReport":
        return cls(
            platform_id=d["platform_id"],
            timestamp=datetime.fromisoformat(d["timestamp"]),
            lat=d["lat"],
            lon=d["lon"],
            depth_m=d.get("depth_m"),
            altitude_m=d.get("altitude_m"),
            sog=d.get("sog"),
            cog=d.get("cog"),
            heading=d.get("heading"),
            rot=d.get("rot"),
            nav_status=d.get("nav_status"),
            source_protocol=d.get("source_protocol", "custom"),
        )


@dataclass
class AlertPayload:
    alert_type: str
    severity: Literal["info", "warning", "critical"]
    message: str
    platform_ids: list[str] = field(default_factory=list)
    zone_id: str | None = None
    recommendation: str | None = None
    metadata: dict = field(default_factory=dict)

    alert_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    generated_by: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(tz=timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "alert_id": self.alert_id,
            "alert_type": self.alert_type,
            "severity": self.severity,
            "status": "new",
            "platform_ids": self.platform_ids,
            "zone_id": self.zone_id,
            "generated_by": self.generated_by,
            "message": self.message,
            "recommendation": self.recommendation,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }


class Agent(ABC):
    agent_id: str
    name: str
    description: str
    agent_type: AgentType

    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis
        self.level: AgentLevel = "L1"
        self.enabled: bool = True
        self.config: dict = {}
        self._log = logging.getLogger(f"agent.{self.agent_id}")

    # ── 서브클래스 구현 ────────────────────────────────────────────────────

    @abstractmethod
    async def on_platform_report(self, report: PlatformReport) -> None: ...

    async def on_alert(self, alert: dict) -> None:
        """다른 Agent Alert에 반응 — 필요 시 오버라이드."""

    # ── 공통 헬퍼 ─────────────────────────────────────────────────────────

    async def emit_alert(self, payload: AlertPayload) -> None:
        payload.generated_by = self.agent_id
        channel = f"alert.created.{payload.severity}"
        await self._redis.publish(channel, json.dumps(payload.to_dict()))
        self._log.info("Alert emitted: type=%s severity=%s", payload.alert_type, payload.severity)

    def set_level(self, level: AgentLevel) -> None:
        self.level = level
        self._log.info("Level set to %s", level)

    def health(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "type": self.agent_type,
            "level": self.level,
            "enabled": self.enabled,
        }
