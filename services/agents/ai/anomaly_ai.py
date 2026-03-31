"""
Anomaly AI Agent — Claude 기반 이상 행동 분석.

Rule Agent가 경보를 생성한 후, 이 Agent가 상황을 종합 분석하여
원인 설명과 구체적 권고사항을 생성한다. (L2/L3에서 동작)
"""

from __future__ import annotations

import logging

import redis.asyncio as aioredis

from ai.llm_client import make_llm_client
from base import Agent, AlertPayload, PlatformReport
from config import settings

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = """당신은 해양 관제 전문가입니다.
실시간 선박 데이터를 분석하여 이상 행동의 원인을 진단하고
운항 안전을 위한 구체적인 조치를 권고합니다.

응답은 반드시 다음 형식으로 작성하십시오:
- 진단: (이상 원인 분석, 1-2문장)
- 권고: (즉각 취해야 할 조치, 번호 목록)
- 우선순위: (low/medium/high/critical 중 하나)"""


class AnomalyAIAgent(Agent):
    agent_id = "anomaly-ai"
    name = "Anomaly AI Agent"
    description = "Claude 기반 이상 행동 원인 분석 및 상세 권고 생성"
    agent_type = "ai"

    def __init__(self, redis: aioredis.Redis) -> None:
        super().__init__(redis)
        self._llm = make_llm_client(settings)
        self._recent: dict[str, PlatformReport] = {}

    async def on_platform_report(self, report: PlatformReport) -> None:
        self._recent[report.platform_id] = report

    async def on_alert(self, alert: dict) -> None:
        """Rule Agent의 anomaly/ais_off 경보를 받아 AI 분석 수행."""
        if self.level == "L1":
            return
        # 자신이 생성한 경보에 반응하지 않음 — 무한 루프 방지
        if alert.get("generated_by") == self.agent_id:
            return
        if alert.get("alert_type") not in ("anomaly", "ais_off"):
            return
        if alert.get("severity") == "info":
            return

        platform_ids = alert.get("platform_ids", [])
        if not platform_ids:
            return

        pid = platform_ids[0]
        report = self._recent.get(pid)
        context = _build_context(alert, report)

        try:
            analysis = await self._llm.chat(
                system=_SYSTEM_PROMPT,
                user=context,
                max_tokens=512,
            )
        except Exception:
            logger.exception("LLM call failed for anomaly analysis")
            return

        await self.emit_alert(AlertPayload(
            alert_type="anomaly",
            severity=alert["severity"],
            message=f"[AI 분석] {alert['message']}",
            platform_ids=platform_ids,
            recommendation=analysis,
            metadata={"source_alert_id": alert.get("alert_id"), "ai_model": f"{settings.llm_backend}/{settings.ollama_model if settings.llm_backend == 'ollama' else settings.claude_model}"},
        ))


def _build_context(alert: dict, report: PlatformReport | None) -> str:
    lines = [
        f"경보 유형: {alert['alert_type']}",
        f"심각도: {alert['severity']}",
        f"메시지: {alert['message']}",
    ]
    if report:
        lines += [
            f"\n선박 ID: {report.platform_id}",
            f"현재 위치: 위도 {report.lat:.4f}, 경도 {report.lon:.4f}",
            f"속도(SOG): {report.sog} knots",
            f"침로(COG): {report.cog}°",
            f"선수방위: {report.heading}°",
            f"선회율(ROT): {report.rot}°/min",
            f"항법 상태: {report.nav_status}",
        ]
    lines.append("\n위 상황을 분석하고 운항 안전 조치를 권고하십시오.")
    return "\n".join(lines)
