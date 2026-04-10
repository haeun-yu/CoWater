"""
Report Agent — Claude 기반 운항 사건 보고서 자동 생성.

Core API에서 Incident 데이터를 가져와 구조화된 보고서를 생성하고
다시 Core API에 저장한다.
"""

from __future__ import annotations

import logging

import httpx
import redis.asyncio as aioredis

from ai.llm_client import make_llm_client
from base import Agent, AlertPayload, PlatformReport
from config import settings

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = """당신은 해양 운항 사고 분석 전문가입니다.
제공된 사건 데이터를 기반으로 공식 보고서를 작성하십시오.

**중요: 한글 응답시 반드시 정확한 띄어쓰기와 문법을 사용하세요. 모든 단어 사이에 띄어쓰기를 포함하세요.**

보고서 형식:
# 해양 사건 보고서

## 1. 사건 개요
## 2. 관련 선박 정보
## 3. 사건 경위 (시간 순)
## 4. 원인 분석
## 5. 조치 사항
## 6. 재발 방지 권고
## 7. 결론"""


class ReportAgent(Agent):
    agent_id = "report-agent"
    name = "Report Agent"
    description = "사건 종료 후 Claude 기반 운항 보고서 자동 생성"
    agent_type = "ai"

    def __init__(self, redis: aioredis.Redis) -> None:
        super().__init__(redis)
        self._llm = make_llm_client(settings)

    async def on_platform_report(self, report: PlatformReport) -> None:
        pass

    async def on_alert(self, alert: dict) -> None:
        """Critical 경보 수신 시 상황 보고서 자동 생성."""
        if alert.get("generated_by") == self.agent_id:
            return
        if self.level == "L1":
            return
        if alert.get("severity") != "critical":
            return
        if alert.get("alert_type") not in ("distress", "cpa", "zone_intrusion"):
            return

        context = self._build_alert_context(alert)
        llm_fallback = False
        try:
            report_text = await self._llm.chat(
                system=_SYSTEM_PROMPT,
                user=context,
                max_tokens=settings.report_alert_max_tokens,
            )
        except Exception:
            logger.exception("Auto report generation failed for alert %s", alert.get("alert_id"))
            llm_fallback = True
            report_text = (
                "# 해양 사건 보고서 (Fallback)\n\n"
                "## 1. 사건 개요\n"
                f"- 유형: {alert.get('alert_type')}\n"
                f"- 심각도: {alert.get('severity')}\n"
                f"- 시각: {alert.get('created_at')}\n\n"
                "## 2. 관련 선박 정보\n"
                f"- {', '.join(alert.get('platform_ids', []))}\n\n"
                "## 3. 사건 경위\n"
                f"- 경보 메시지: {alert.get('message')}\n\n"
                "## 4. 원인 분석\n"
                "- LLM 분석 실패로 Rule 기반 요약만 제공됨\n\n"
                "## 5. 조치 사항\n"
                "- 운영자가 수동 검토 후 후속 조치 필요\n"
            )

        await self.emit_alert(AlertPayload(
            alert_type="compliance",
            severity="info",
            message=f"[상황 보고서] {alert.get('message', '')[:80]}",
            platform_ids=alert.get("platform_ids", []),
            recommendation=report_text,
            metadata={
                "source_alert_type": alert.get("alert_type"),
                "source_alert_id": alert.get("alert_id"),
                "auto_report": True,
                "llm_fallback": llm_fallback,
                "fallback_reason": "llm_call_failed" if llm_fallback else None,
            },
        ))

    def _build_alert_context(self, alert: dict) -> str:
        return (
            f"경보 유형: {alert.get('alert_type')}\n"
            f"심각도: {alert.get('severity')}\n"
            f"발생 시각: {alert.get('created_at', '미상')}\n"
            f"관련 선박: {', '.join(alert.get('platform_ids', []))}\n"
            f"경보 내용: {alert.get('message')}\n"
            f"발생 에이전트: {alert.get('generated_by')}\n"
            "\n위 해양 사건에 대한 운항 보고서를 작성하십시오."
        )

    async def generate_report(self, incident_id: str) -> str | None:
        """
        incident_id에 해당하는 사건 데이터를 Core API에서 조회하여 보고서 생성.
        외부에서 직접 호출하거나 API 엔드포인트를 통해 트리거.
        """
        incident = await self._fetch_incident(incident_id)
        if not incident:
            return None

        context = _build_incident_context(incident)
        try:
            report_text = await self._llm.chat(
                system=_SYSTEM_PROMPT,
                user=context,
                max_tokens=settings.report_incident_max_tokens,
            )
        except Exception:
            logger.exception("Report generation failed for incident %s", incident_id)
            return None

        await self._save_report(incident_id, report_text)
        return report_text

    async def _fetch_incident(self, incident_id: str) -> dict | None:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{settings.core_api_url}/incidents/{incident_id}", timeout=5
                )
                resp.raise_for_status()
                return resp.json()
        except Exception:
            logger.exception("Failed to fetch incident %s", incident_id)
            return None

    async def _save_report(self, incident_id: str, report: str) -> None:
        try:
            async with httpx.AsyncClient() as client:
                await client.patch(
                    f"{settings.core_api_url}/incidents/{incident_id}",
                    json={"report": report},
                    timeout=5,
                )
        except Exception:
            logger.exception("Failed to save report for incident %s", incident_id)


def _build_incident_context(incident: dict) -> str:
    timeline = "\n".join(
        f"  - {e.get('timestamp', '')}: {e.get('description', '')}"
        for e in incident.get("timeline", [])
    )
    return (
        f"사건 ID: {incident.get('incident_id')}\n"
        f"사건 유형: {incident.get('incident_type')}\n"
        f"관련 선박: {', '.join(incident.get('platform_ids', []))}\n"
        f"해결 여부: {'해결됨' if incident.get('resolved') else '미해결'}\n\n"
        f"사건 타임라인:\n{timeline}\n\n"
        f"위 정보를 바탕으로 공식 해양 사건 보고서를 작성하십시오."
    )
