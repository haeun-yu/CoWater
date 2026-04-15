"""
Analysis - Anomaly AI Agent

detect.anomaly 이벤트를 받아 이상 원인과 대응 권고를 생성한다.
"""

from __future__ import annotations

import asyncio
import logging
import time
from uuid import uuid4

import redis.asyncio as aioredis

from shared.events import Event, EventType
from shared.llm_client import make_llm_client

from config import settings
from .base import AnalysisAgent

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """당신은 해양 관제 전문가입니다.
실시간 선박 데이터를 분석하여 이상 행동의 원인을 진단하고
운항 안전을 위한 구체적인 조치를 권고합니다.

응답은 반드시 다음 형식으로 작성하십시오:
- 진단: (이상 원인 분석, 1-2문장)
- 권고: (즉각 취해야 할 조치, 번호 목록)
- 우선순위: (low/medium/high/critical 중 하나)"""


class AnalysisAnomalyAIAgent(AnalysisAgent):
    """Analysis 단계: AI 기반 비정상 분석"""

    agent_id = "analysis-anomaly-ai"

    def __init__(self, redis: aioredis.Redis, core_api_url: str) -> None:
        super().__init__(redis, core_api_url)
        self._llm = make_llm_client(settings)
        self._last_analyzed_at: dict[str, float] = {}

    async def on_detect_event(self, event: Event) -> None:
        if event.type != EventType.DETECT_ANOMALY:
            return

        payload = event.payload
        if payload.get("severity") == "info":
            return
        if (
            settings.ai_min_severity == "critical"
            and payload.get("severity") != "critical"
        ):
            return

        platform_id = payload.get("platform_id")
        anomaly_type = payload.get("anomaly_type")
        if not platform_id or not anomaly_type:
            return

        cooldown_key = f"{anomaly_type}:{platform_id}"
        now_ts = time.time()
        last_ts = self._last_analyzed_at.get(cooldown_key)
        if last_ts is not None and (now_ts - last_ts) < settings.ai_alert_cooldown_sec:
            return

        self._last_analyzed_at[cooldown_key] = now_ts
        asyncio.create_task(self._analyze_and_emit(event))

    async def _analyze_and_emit(self, event: Event) -> None:
        payload = event.payload
        llm_fallback = False
        fallback_reason = None

        try:
            analysis = await self._llm.chat(
                system=_SYSTEM_PROMPT,
                user=_build_context(payload),
                max_tokens=settings.anomaly_ai_max_tokens,
            )
        except Exception:
            logger.exception("LLM call failed for anomaly analysis")
            llm_fallback = True
            fallback_reason = "llm_call_failed"
            analysis = (
                "[LLM 호출 실패 — rule 기반 권고]\n\n"
                f"경보 유형: {payload.get('anomaly_type')} / 심각도: {payload.get('severity')}\n"
                "권고사항:\n"
                "1. 해당 선박의 현재 위치 및 상태를 즉시 확인하십시오.\n"
                "2. VHF Ch.16을 통해 교신을 시도하십시오.\n"
                "3. 필요 시 해양경찰청(122)에 상황을 통보하십시오."
            )

        await self.emit_analysis_event(
            event_type=EventType.ANALYZE_ANOMALY,
            payload={
                "alert_id": str(uuid4()),
                "platform_id": payload.get("platform_id"),
                "original_anomaly_type": payload.get("anomaly_type"),
                "analysis_result": analysis,
                "recommendation": analysis,
                "confidence": _confidence_for_severity(payload.get("severity")),
                "timestamp": event.timestamp.isoformat(),
                "ai_model": self._llm.model_name,
                "execution_time_ms": 0,
                "source_reason": payload.get("reason"),
                "source_severity": payload.get("severity"),
                "llm_fallback": llm_fallback,
                "fallback_reason": fallback_reason,
            },
            flow_id=event.flow_id,
            causation_id=event.event_id,
        )


def _build_context(payload: dict) -> str:
    lines = [
        f"이상 유형: {payload.get('anomaly_type')}",
        f"심각도: {payload.get('severity')}",
        f"사유: {payload.get('reason')}",
        f"선박 ID: {payload.get('platform_id')}",
        f"현재 위치: 위도 {payload.get('latitude')}, 경도 {payload.get('longitude')}",
    ]
    meta = payload.get("metadata") or {}
    if meta:
        lines.append(f"추가 메타데이터: {meta}")
    lines.append("위 상황을 분석하고 운항 안전 조치를 권고하십시오.")
    return "\n".join(lines)


def _confidence_for_severity(severity: str | None) -> float:
    if severity == "critical":
        return 0.9
    if severity == "warning":
        return 0.7
    return 0.5
