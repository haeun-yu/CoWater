"""
Report Agent — Claude 기반 운항 사건 보고서 자동 생성.

Core API에서 Incident 데이터를 가져와 구조화된 보고서를 생성하고
다시 Core API에 저장한다.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
import redis.asyncio as aioredis

from ai.llm_client import make_llm_client
from base import Agent, AlertPayload, PlatformReport
from config import settings

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = """You are a maritime incident analysis expert.
Write a formal incident report based on the provided alert information.

Report format:
# Maritime Incident Report

## 1. Alert Overview
## 2. Affected Vessels
## 3. Incident Timeline
## 4. Root Cause Analysis
## 5. Actions Taken
## 6. Preventive Measures
## 7. Conclusions"""


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

    async def generate_report(self, alert_id: str) -> str | None:
        """
        alert_id에 해당하는 경보 데이터를 Core API에서 조회하여 보고서 생성.
        Alert의 정보(메시지, 관련 선박, 생성 시간)를 기반으로 보고서 작성.
        """
        alert = await self._fetch_alert(alert_id)
        if not alert:
            return None

        context = self._build_alert_context(alert)
        try:
            report_text = await self._llm.chat(
                system=_SYSTEM_PROMPT,
                user=context,
                max_tokens=settings.report_incident_max_tokens,
            )
        except Exception:
            logger.exception("Report generation failed for alert %s", alert_id)
            return None

        await self._save_report(alert_id, report_text)
        return report_text

    async def _fetch_alert(self, alert_id: str) -> dict | None:
        """Core API에서 alert 조회"""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{settings.core_api_url}/alerts/{alert_id}", timeout=5
                )
                resp.raise_for_status()
                return resp.json()
        except Exception:
            logger.exception("Failed to fetch alert %s", alert_id)
            return None

    async def _save_report(self, alert_id: str, report: str) -> None:
        """Core API를 통해 alert.metadata.report에 보고서 저장"""
        try:
            await self._redis.hset(
                f"alert:{alert_id}:report",
                mapping={
                    "content": report,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception:
            logger.exception("Failed to save report for alert %s", alert_id)
