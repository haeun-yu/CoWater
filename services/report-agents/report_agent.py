"""Report Agent - 대응 완료 후 AI 기반 보고서 생성"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from uuid import uuid4

import httpx
import redis.asyncio as aioredis
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from base import ReportAgent
from config import settings
from db import AsyncSessionLocal
from models import ReportModel

logger = logging.getLogger(__name__)


class AIReportAgent(ReportAgent):
    """AI 기반 보고서 생성 Agent"""

    agent_id = "ai-report-agent"

    def __init__(self, redis: aioredis.Redis) -> None:
        super().__init__(redis)
        self._llm = None

    async def on_respond_event(self, event: dict) -> None:
        """respond.* 이벤트를 받아 보고서 생성"""
        try:
            flow_id = event.get("flow_id")
            alert_ids = event.get("alert_ids", [])
            report_type = "summary"  # 기본값

            if not flow_id or not alert_ids:
                logger.warning("Invalid respond event: missing flow_id or alert_ids")
                return

            # 백그라운드에서 보고서 생성
            asyncio.create_task(
                self._generate_and_save(
                    flow_id=flow_id,
                    alert_ids=alert_ids,
                    report_type=report_type,
                )
            )
        except Exception as e:
            logger.exception("Error processing respond event: %s", e)

    async def _generate_and_save(
        self,
        flow_id: str,
        alert_ids: list[str],
        report_type: str,
    ) -> None:
        """보고서 생성 후 DB에 저장"""
        try:
            logger.info("Generating report for flow %s (%d alerts)", flow_id, len(alert_ids))

            # 1. Alert 정보 조회
            alerts = await self._fetch_alerts(alert_ids)
            if not alerts:
                logger.warning("No alerts found for report generation")
                return

            # 2. AI로 보고서 생성
            content = await self._generate_with_ai(alerts, report_type)
            if not content:
                logger.warning("Failed to generate report content")
                return

            # 3. DB에 저장
            report_id = str(uuid4())
            await self._save_to_db(
                report_id=report_id,
                flow_id=flow_id,
                alert_ids=alert_ids,
                report_type=report_type,
                content=content,
            )

            logger.info("Report %s saved for flow %s", report_id, flow_id)

            # 4. report.* 이벤트 발행
            await self.emit_report_event(
                report_id=report_id,
                flow_id=flow_id,
                report_type=report_type,
                content=content[:500],  # 요약본
            )

        except Exception as e:
            logger.exception("Error generating report: %s", e)

    async def _fetch_alerts(self, alert_ids: list[str]) -> list[dict]:
        """Core API에서 alert 정보 조회"""
        alerts = []
        for alert_id in alert_ids:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(
                        f"{settings.core_api_url}/alerts/{alert_id}",
                    )
                    if resp.status_code == 200:
                        alerts.append(resp.json())
            except Exception as e:
                logger.warning("Failed to fetch alert %s: %s", alert_id, e)

        return alerts

    async def _generate_with_ai(
        self,
        alerts: list[dict],
        report_type: str,
    ) -> str:
        """AI로 보고서 생성"""
        alerts_text = json.dumps(alerts, indent=2, ensure_ascii=False)

        if report_type == "summary":
            prompt = f"""다음 해양 경보들을 종합하여 요약 보고서를 작성하세요.

경보들:
{alerts_text}

요약 보고서 (2-3문장):"""
        elif report_type == "detailed":
            prompt = f"""다음 해양 경보들의 상세 분석 보고서를 작성하세요.

경보들:
{alerts_text}

보고서 (개요, 상황분석, 영향평가, 권고사항 포함):"""
        else:  # incident
            prompt = f"""다음 경보들에 대한 해양 사건 조사보고서를 작성하세요.

경보들:
{alerts_text}

보고서 (사건개요, 시간순서, 원인분석, 권고조치 포함):"""

        try:
            # LLM 클라이언트 초기화 (lazy init)
            if self._llm is None:
                from shared.llm_client import make_llm_client
                self._llm = make_llm_client(settings)

            # AI API 호출
            content = await self._llm.generate(prompt)
            return content if content else self._fallback_report(alerts, report_type)

        except Exception as e:
            logger.exception("AI generation failed: %s", e)
            return self._fallback_report(alerts, report_type)

    async def _save_to_db(
        self,
        report_id: str,
        flow_id: str,
        alert_ids: list[str],
        report_type: str,
        content: str,
    ) -> None:
        """DB에 보고서 저장"""
        try:
            async with AsyncSessionLocal() as session:
                stmt = insert(ReportModel).values(
                    report_id=report_id,
                    flow_id=flow_id,
                    alert_ids=alert_ids,
                    report_type=report_type,
                    content=content,
                    ai_model=self._llm.model_name if self._llm else "unknown",
                    created_at=datetime.utcnow(),
                )
                await session.execute(stmt)
                await session.commit()
        except Exception as e:
            logger.exception("Failed to save report to DB: %s", e)

    @staticmethod
    def _fallback_report(alerts: list[dict], report_type: str) -> str:
        """AI 실패 시 기본 보고서"""
        if not alerts:
            return "보고서를 작성할 경보가 없습니다."

        alert_count = len(alerts)
        severity_counts = {}
        alert_types = set()

        for alert in alerts:
            severity = alert.get("severity", "unknown")
            alert_type = alert.get("alert_type", "unknown")
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
            alert_types.add(alert_type)

        severity_text = ", ".join([f"{k}:{v}" for k, v in severity_counts.items()])
        types_text = ", ".join(alert_types)

        return f"해양 경보 보고서: 총 {alert_count}건의 경보 기록 ({types_text}). 심각도 분포: {severity_text}"
