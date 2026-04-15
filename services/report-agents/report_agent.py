"""Report Agent - 경보 기반 보고서 생성 및 저장"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from uuid import uuid4

import httpx
import redis.asyncio as aioredis
from sqlalchemy import insert

from base import ReportAgent
from config import settings
from db import AsyncSessionLocal
from models import ReportModel
from shared.events import Event
from shared.llm_client import make_llm_client

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


class AIReportAgent(ReportAgent):
    """AI 기반 보고서 생성 Agent"""

    agent_id = "report-agent"

    def __init__(self, redis: aioredis.Redis) -> None:
        super().__init__(redis)
        self._llm = make_llm_client(settings)

    async def on_respond_event(self, event: Event) -> None:
        """respond.* 이벤트를 받아 필요 시 보고서 생성"""
        try:
            payload = event.payload
            alert_ids = payload.get("alert_ids") or (
                [payload["alert_id"]] if payload.get("alert_id") else []
            )
            if not alert_ids:
                logger.warning("Invalid respond event: missing alert_ids")
                return

            report_type = "incident" if payload.get("severity") == "critical" else "summary"
            asyncio.create_task(
                self._generate_and_save(
                    flow_id=event.flow_id,
                    alert_ids=alert_ids,
                    report_type=report_type,
                )
            )
        except Exception as exc:
            logger.exception("Error processing respond event: %s", exc)

    async def generate_report(self, alert_id: str) -> str | None:
        alerts = await self._fetch_alerts([alert_id])
        if not alerts:
            return None

        content = await self._generate_with_ai(alerts, "incident")
        await self._save_to_db(
            report_id=str(uuid4()),
            flow_id=f"report:{alert_id}",
            alert_ids=[alert_id],
            report_type="incident",
            content=content,
        )
        return content

    async def _generate_and_save(
        self,
        flow_id: str,
        alert_ids: list[str],
        report_type: str,
    ) -> None:
        alerts = await self._fetch_alerts(alert_ids)
        if not alerts:
            logger.warning("No alerts found for report generation")
            return

        content = await self._generate_with_ai(alerts, report_type)
        report_id = str(uuid4())
        await self._save_to_db(
            report_id=report_id,
            flow_id=flow_id,
            alert_ids=alert_ids,
            report_type=report_type,
            content=content,
        )
        await self.emit_report_event(
            report_id=report_id,
            flow_id=flow_id,
            report_type=report_type,
            content=content[:500],
        )

    async def _fetch_alerts(self, alert_ids: list[str]) -> list[dict]:
        alerts: list[dict] = []
        async with httpx.AsyncClient(timeout=5.0) as client:
            for alert_id in alert_ids:
                try:
                    response = await client.get(f"{settings.core_api_url}/alerts/{alert_id}")
                    response.raise_for_status()
                    alerts.append(response.json())
                except Exception as exc:
                    logger.warning("Failed to fetch alert %s: %s", alert_id, exc)
        return alerts

    async def _generate_with_ai(self, alerts: list[dict], report_type: str) -> str:
        context = _build_alerts_context(alerts)
        max_tokens = (
            settings.report_incident_max_tokens
            if report_type == "incident"
            else settings.report_alert_max_tokens
        )
        timeout = (
            settings.claude_timeout_sec
            if "claude" in (settings.llm_backend or "")
            else settings.local_llm_timeout_sec
        )

        try:
            return await asyncio.wait_for(
                self._llm.chat(
                    system=_SYSTEM_PROMPT,
                    user=context,
                    max_tokens=max_tokens,
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("Report generation timed out after %ss", timeout)
            return self._fallback_report(alerts, report_type)
        except Exception:
            logger.exception("Report generation failed, using fallback")
            return self._fallback_report(alerts, report_type)

    async def _save_to_db(
        self,
        report_id: str,
        flow_id: str,
        alert_ids: list[str],
        report_type: str,
        content: str,
    ) -> None:
        try:
            async with AsyncSessionLocal() as session:
                stmt = insert(ReportModel).values(
                    report_id=report_id,
                    flow_id=flow_id,
                    alert_ids=alert_ids,
                    report_type=report_type,
                    content=content,
                    ai_model=self._llm.model_name,
                    created_at=datetime.now(timezone.utc),
                )
                await session.execute(stmt)
                await session.commit()
        except Exception as exc:
            logger.exception("Failed to save report to DB: %s", exc)
            try:
                await self.redis.hset(
                    f"report:{report_id}",
                    mapping={
                        "content": content,
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
            except Exception:
                logger.exception("Failed to save fallback report copy for %s", report_id)

    @staticmethod
    def _fallback_report(alerts: list[dict], report_type: str) -> str:
        if not alerts:
            return "보고서를 작성할 경보가 없습니다."

        if len(alerts) == 1:
            alert = alerts[0]
            return (
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
                "- LLM 분석 실패로 기본 요약만 제공됨\n\n"
                "## 5. 조치 사항\n"
                "- 운영자가 수동 검토 후 후속 조치 필요\n"
            )

        severity_counts: dict[str, int] = {}
        for alert in alerts:
            severity = alert.get("severity", "unknown")
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
        severity_text = ", ".join(f"{key}:{value}" for key, value in severity_counts.items())
        return f"해양 경보 보고서: 총 {len(alerts)}건. 보고서 유형={report_type}, 심각도 분포={severity_text}"


def _build_alerts_context(alerts: list[dict]) -> str:
    if len(alerts) == 1:
        alert = alerts[0]
        return (
            f"경보 유형: {alert.get('alert_type')}\n"
            f"심각도: {alert.get('severity')}\n"
            f"발생 시각: {alert.get('created_at', '미상')}\n"
            f"관련 선박: {', '.join(alert.get('platform_ids', []))}\n"
            f"경보 내용: {alert.get('message')}\n"
            f"발생 에이전트: {alert.get('generated_by')}\n"
            "\n위 해양 사건에 대한 운항 보고서를 작성하십시오."
        )
    return f"다음 경보 목록을 기반으로 종합 보고서를 작성하십시오.\n{json.dumps(alerts, ensure_ascii=False, indent=2)}"
