"""
Distress Agent — 조난 신호 수신 및 대응.

L1: 경보 생성
L2: 경보 + Claude 기반 상황 요약 및 대응 지침
L3: 경보 + 자동 통보 (Core API를 통해 관계기관 알림 전송)
"""

from __future__ import annotations

import logging

import httpx
import redis.asyncio as aioredis

from ai.llm_client import make_llm_client
from base import Agent, AlertPayload, PlatformReport
from config import settings

logger = logging.getLogger(__name__)


_DISTRESS_NAV_STATUSES = {"not_under_command", "aground"}

_SYSTEM_PROMPT = """당신은 해양 수색구조(SAR) 전문 운항 조정관입니다.
조난 상황을 평가하고 즉각적인 대응 지침을 작성하십시오.

응답 형식:
- 상황 요약: (조난 상황 간략 기술)
- 즉각 조치:
  1. (첫 번째 조치)
  2. (두 번째 조치)
  ...
- 통보 기관: (해경, SAR 등 연락해야 할 기관 목록)
- 예상 위험도: (low/medium/high/critical)"""


class DistressAgent(Agent):
    agent_id = "distress-agent"
    name = "Distress Agent"
    description = "조난 신호 감지 및 SAR 대응 지원. L3에서 자동 통보 실행"
    agent_type = "ai"

    def __init__(self, redis: aioredis.Redis) -> None:
        super().__init__(redis)
        self._llm = make_llm_client(settings)
        self._handled: set[str] = set()     # 이미 처리된 platform_id

    async def on_platform_report(self, report: PlatformReport) -> None:
        pid = report.platform_id
        if pid in self._handled:
            return

        is_distress = report.nav_status in _DISTRESS_NAV_STATUSES
        if not is_distress:
            return

        self._handled.add(pid)
        await self._handle_distress(report)

    async def on_alert(self, alert: dict) -> None:
        """AIS 소실 경보를 조난 가능성으로 에스컬레이션."""
        if alert.get("generated_by") == self.agent_id:
            return
        if alert.get("alert_type") != "ais_off":
            return
        if alert.get("severity") != "warning":
            return
        for pid in alert.get("platform_ids", []):
            if pid not in self._handled:
                self._handled.add(pid)
                await self.emit_alert(AlertPayload(
                    alert_type="distress",
                    severity="warning",
                    message=f"{pid} AIS 소실 — 조난 가능성 검토 필요",
                    platform_ids=[pid],
                    recommendation="AIS 소실 선박의 마지막 위치 확인 후 해경 통보 검토.",
                ))

    async def _handle_distress(self, report: PlatformReport) -> None:
        # L1: 기본 권고문 / L2+: LLM 생성 권고문
        recommendation = (
            f"{report.platform_id} 위치 ({report.lat:.4f}, {report.lon:.4f}) "
            f"상태 '{report.nav_status}' 확인. "
            "VHF Ch.16 교신 시도 및 해양경찰청(122) 통보 검토."
        )
        llm_fallback = False

        if self.level in ("L2", "L3"):
            generated = await self._generate_response(report)
            if generated:
                recommendation = generated
            else:
                llm_fallback = True

        severity = "critical"
        await self.emit_alert(AlertPayload(
            alert_type="distress",
            severity=severity,
            message=(
                f"조난 신호 감지: {report.platform_id} "
                f"위치 ({report.lat:.4f}, {report.lon:.4f}) "
                f"상태: {report.nav_status}"
            ),
            platform_ids=[report.platform_id],
            recommendation=recommendation,
            metadata={
                "lat": report.lat, "lon": report.lon,
                "nav_status": report.nav_status,
                "llm_fallback": llm_fallback,
                "fallback_reason": "llm_call_failed" if llm_fallback else None,
            },
            dedup_key=f"distress:{report.platform_id}",
        ))

        # L3: 자동 통보
        if self.level == "L3":
            await self._auto_notify(report)

    async def _generate_response(self, report: PlatformReport) -> str | None:
        context = (
            f"조난 선박: {report.platform_id}\n"
            f"위치: 위도 {report.lat:.4f}, 경도 {report.lon:.4f}\n"
            f"속도: {report.sog} knots\n"
            f"항법 상태: {report.nav_status}\n"
            f"조난 상황에 대한 즉각적인 SAR 대응 지침을 작성하십시오."
        )
        try:
            return await self._llm.chat(
                system=_SYSTEM_PROMPT,
                user=context,
                max_tokens=settings.distress_agent_max_tokens,
            )
        except Exception:
            logger.exception("LLM call failed for distress response")
            return None

    async def _auto_notify(self, report: PlatformReport) -> None:
        """L3 자동 통보 — Core API를 통해 감사 로그 기록."""
        logger.warning(
            "[L3 AUTO-NOTIFY] Distress at platform=%s lat=%.4f lon=%.4f",
            report.platform_id, report.lat, report.lon,
        )
        # TODO: 실제 해경 API / 알림 채널 연동
