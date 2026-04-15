"""
Response - Distress Agent

조난 탐지 이벤트를 받아 경보와 대응 지침을 생성한다.
"""

from __future__ import annotations

import logging
import time

import redis.asyncio as aioredis

from shared.events import Event, EventType
from shared.llm_client import make_llm_client

from config import settings
from .base import ResponseAgent

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """당신은 해양 수색구조(SAR) 전문 운항 조정관입니다.
조난 상황을 평가하고 즉각적인 대응 지침을 작성하십시오.

응답 형식:
- 상황 요약: (조난 상황 간략 기술)
- 즉각 조치:
  1. (첫 번째 조치)
  2. (두 번째 조치)
- 통보 기관: (해경, SAR 등 연락해야 할 기관 목록)
- 예상 위험도: (low/medium/high/critical)"""


class ResponseDistressAgent(ResponseAgent):
    agent_id = "response-distress-agent"

    def __init__(self, redis: aioredis.Redis, core_api_url: str) -> None:
        super().__init__(redis, core_api_url)
        self._llm = make_llm_client(settings)
        self._last_handled_at: dict[str, float] = {}

    async def on_analyze_event(self, event: Event) -> None:
        return

    async def on_detect_event(self, event: Event) -> None:
        if event.type == EventType.DETECT_DISTRESS:
            await self._handle_detect_distress(event)
            return

        if event.type != EventType.DETECT_ANOMALY:
            return

        payload = event.payload
        if payload.get("anomaly_type") != "ais_off":
            return

        platform_id = payload.get("platform_id")
        cooldown_key = f"ais_off:{platform_id}"
        if not platform_id or self._is_in_cooldown(cooldown_key):
            return

        self._mark_handled(cooldown_key)
        alert_id = await self.create_alert(
            alert_type="distress",
            severity="warning",
            platform_ids=[platform_id],
            message=f"{platform_id} AIS 소실 — 조난 가능성 검토 필요",
            recommendation="AIS 소실 선박의 마지막 위치 확인 후 해경 통보를 검토하십시오.",
            metadata={
                "source_event_type": event.type.value,
                "source_anomaly_type": payload.get("anomaly_type"),
            },
            dedup_key=f"distress-ais-off:{platform_id}",
        )
        if alert_id:
            await self.emit_response_event(
                event_type=EventType.RESPOND_ALERT,
                payload={
                    "alert_id": alert_id,
                    "alert_ids": [alert_id],
                    "platform_id": platform_id,
                    "alert_type": "distress",
                    "severity": "warning",
                    "message": f"{platform_id} AIS 소실 — 조난 가능성 검토 필요",
                },
                flow_id=event.flow_id,
                causation_id=event.event_id,
            )

    async def _handle_detect_distress(self, event: Event) -> None:
        payload = event.payload
        platform_id = payload.get("platform_id")
        cooldown_key = f"distress:{platform_id}"
        if not platform_id or self._is_in_cooldown(cooldown_key):
            return
        self._mark_handled(cooldown_key)

        recommendation = (
            f"{platform_id} 위치 ({payload.get('latitude')}, {payload.get('longitude')}) "
            "기준으로 VHF Ch.16 교신 시도 및 해양경찰청(122) 통보를 검토하십시오."
        )
        llm_fallback = False

        try:
            recommendation = await self._llm.chat(
                system=_SYSTEM_PROMPT,
                user=_build_context(payload),
                max_tokens=settings.distress_agent_max_tokens,
            )
        except Exception:
            logger.exception("LLM call failed for distress response")
            llm_fallback = True

        alert_id = await self.create_alert(
            alert_type="distress",
            severity="critical",
            platform_ids=[platform_id],
            message=(
                f"조난 신호 감지: {platform_id} "
                f"위치 ({payload.get('latitude')}, {payload.get('longitude')}) "
                f"타입: {payload.get('distress_type')}"
            ),
            recommendation=recommendation,
            metadata={
                "source_event_type": event.type.value,
                "distress_type": payload.get("distress_type"),
                "ai_model": self._llm.model_name,
                "llm_fallback": llm_fallback,
            },
            dedup_key=f"distress:{platform_id}",
        )
        if alert_id:
            await self.emit_response_event(
                event_type=EventType.RESPOND_ALERT,
                payload={
                    "alert_id": alert_id,
                    "alert_ids": [alert_id],
                    "platform_id": platform_id,
                    "alert_type": "distress",
                    "severity": "critical",
                    "message": f"조난 신호 감지: {platform_id}",
                },
                flow_id=event.flow_id,
                causation_id=event.event_id,
            )

    def _is_in_cooldown(self, key: str) -> bool:
        last_ts = self._last_handled_at.get(key)
        return (
            last_ts is not None
            and (time.time() - last_ts) < settings.distress_alert_cooldown_sec
        )

    def _mark_handled(self, key: str) -> None:
        self._last_handled_at[key] = time.time()


def _build_context(payload: dict) -> str:
    return (
        f"조난 선박: {payload.get('platform_id')}\n"
        f"위치: 위도 {payload.get('latitude')}, 경도 {payload.get('longitude')}\n"
        f"조난 유형: {payload.get('distress_type')}\n"
        "조난 상황에 대한 즉각적인 SAR 대응 지침을 작성하십시오."
    )
