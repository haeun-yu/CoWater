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
import asyncio
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

import redis.asyncio as aioredis

from shared.events import alert_created_channel, build_event

# shared 패키지에서 canonical PlatformReport 임포트
from shared.schemas.report import PlatformReport  # noqa: F401 (re-exported for sub-modules)

ALERT_SCHEMA_VERSION = 1

logger = logging.getLogger(__name__)

AgentLevel = Literal["L1", "L2", "L3"]
AgentType = Literal["rule", "ai"]


@dataclass
class AlertPayload:
    alert_type: str
    severity: Literal["info", "warning", "critical"]
    message: str
    platform_ids: list[str] = field(default_factory=list)
    zone_id: str | None = None
    recommendation: str | None = None
    metadata: dict = field(default_factory=dict)
    # 중복 방지 키 — 같은 문제면 동일값, 없으면 매번 새 경보
    dedup_key: str | None = None

    alert_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    generated_by: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(tz=timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        meta = dict(self.metadata)
        meta.setdefault("schema_version", ALERT_SCHEMA_VERSION)
        meta.setdefault("source", "agent-runtime")
        meta.setdefault("produced_at", self.created_at)
        meta.setdefault("generated_by", self.generated_by)
        meta.setdefault("created_at", self.created_at)
        if self.dedup_key:
            meta["dedup_key"] = self.dedup_key
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
            "metadata": meta,
            "created_at": self.created_at,
            "dedup_key": self.dedup_key,
            "schema_version": ALERT_SCHEMA_VERSION,
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
        self._failure_count: int = 0
        self._last_error: str | None = None

    # ── 서브클래스 구현 ────────────────────────────────────────────────────

    @abstractmethod
    async def on_platform_report(self, report: PlatformReport) -> None: ...

    async def on_alert(self, alert: dict) -> None:
        """다른 Agent Alert에 반응 — 필요 시 오버라이드."""

    # ── 공통 헬퍼 ─────────────────────────────────────────────────────────

    async def emit_alert(self, payload: AlertPayload) -> None:
        payload.generated_by = self.agent_id
        channel = alert_created_channel(payload.severity)
        body_dict = payload.to_dict()
        body_dict["event"] = build_event(
            "alert_created",
            "agents",
            channel=channel,
            produced_at=payload.created_at,
        )
        body = json.dumps(body_dict)
        last_error: Exception | None = None

        for attempt in range(1, 4):
            try:
                await self._redis.publish(channel, body)
                self._log.info(
                    "Alert emitted: type=%s severity=%s attempt=%s",
                    payload.alert_type,
                    payload.severity,
                    attempt,
                )
                return
            except Exception as exc:
                last_error = exc
                self._record_error(f"emit_alert failed: {exc}")
                self._log.warning(
                    "Alert publish failed: type=%s severity=%s attempt=%s",
                    payload.alert_type,
                    payload.severity,
                    attempt,
                    exc_info=exc,
                )
                if attempt < 3:
                    await asyncio.sleep(0.25 * attempt)

        assert last_error is not None
        raise last_error

    def set_level(self, level: AgentLevel) -> None:
        self.level = level
        self._log.info("Level set to %s", level)

    def _record_error(self, message: str) -> None:
        """오류 발생 시 카운터 증가 및 마지막 오류 메시지 기록."""
        self._failure_count += 1
        self._last_error = message

    def health(self) -> dict:
        result: dict = {
            "agent_id": self.agent_id,
            "name": self.name,
            "type": self.agent_type,
            "level": self.level,
            "enabled": self.enabled,
            "failure_count": self._failure_count,
            "last_error": self._last_error,
        }
        # AI 에이전트는 현재 LLM 모델명 포함
        if hasattr(self, "_llm"):
            result["model_name"] = self._llm.model_name  # type: ignore[attr-defined]
        return result
