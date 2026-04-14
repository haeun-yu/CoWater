"""
Analysis - Report Agent

경보 데이터를 종합해서 자동 보고서 생성.
Claude를 사용해서 자연어 보고서 작성.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from uuid import uuid4

import httpx
import redis.asyncio as aioredis

from shared.events import Event, EventType
from config import settings
from .base import AnalysisAgent

logger = logging.getLogger(__name__)


class AnalysisReportAgent(AnalysisAgent):
    """Analysis 단계: 자동 보고서 생성"""

    agent_id = "analysis-report"

    def __init__(self, redis: aioredis.Redis, core_api_url: str) -> None:
        super().__init__(redis, core_api_url)

    async def on_detect_event(self, event: Event) -> None:
        """Detection 이벤트를 경보로 변환"""
        # Report Agent는 주로 API 호출로 동작
        # Event 기반이 아니라 on-demand로 보고서 생성
        pass

    async def generate_report(
        self,
        alert_ids: list[str],
        report_type: str = "summary",
    ) -> str:
        """
        보고서 생성 (외부 API 호출로 사용).

        Args:
            alert_ids: 포함할 경보 ID 목록
            report_type: "summary" | "detailed" | "incident"

        Returns:
            생성된 보고서 텍스트
        """

        logger.info("Generating %s report for %d alerts", report_type, len(alert_ids))

        # 1. Core API에서 경보 정보 조회
        alerts = await self._fetch_alerts(alert_ids)
        if not alerts:
            return "경보 정보를 찾을 수 없습니다."

        # 2. Claude로 보고서 생성
        report = await self._generate_with_ai(alerts, report_type)

        # 3. 보고서 Event 발행 (선택)
        if report:
            for alert_id in alert_ids:
                await self.emit_analysis_event(
                    event_type=EventType.ANALYZE_REPORT,
                    payload={
                        "alert_id": alert_id,
                        "report_type": report_type,
                        "report_content": report[:500],  # 요약
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                    causation_id=alert_id,
                )

        return report

    async def _fetch_alerts(self, alert_ids: list[str]) -> list[dict]:
        """Core API에서 경보 정보 조회"""
        alerts = []

        for alert_id in alert_ids:
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    resp = await client.get(
                        f"{self._core_api_url}/alerts/{alert_id}",
                        timeout=2.0,
                    )
                    resp.raise_for_status()
                    alerts.append(resp.json())
            except Exception as e:
                logger.warning("Failed to fetch alert %s: %s", alert_id, e)

        return alerts

    async def _generate_with_ai(
        self,
        alerts: list[dict],
        report_type: str,
    ) -> str:
        """Claude로 보고서 생성"""

        alerts_text = json.dumps(alerts, indent=2, ensure_ascii=False)

        if report_type == "summary":
            prompt = f"""
다음 해양 경보들을 요약해주세요.

경보 정보:
{alerts_text}

요약 형식:
- 발생 시간
- 영향받은 선박
- 주요 문제
- 현재 상태

간결하게 2-3문장으로 작성해주세요.
"""
        elif report_type == "detailed":
            prompt = f"""
다음 해양 경보들에 대한 상세 보고서를 작성해주세요.

경보 정보:
{alerts_text}

보고서 구성:
1. 개요 (발생 시간, 관련 선박)
2. 상황 분석 (각 경보의 상세)
3. 영향 평가
4. 권고사항

500자 이상의 상세한 보고서를 작성해주세요.
"""
        else:  # incident
            prompt = f"""
다음 경보들이 나타내는 해양 사건의 조사 보고서를 작성해주세요.

경보 정보:
{alerts_text}

사건 보고서 구성:
1. 사건 개요
2. 시간 순서별 사건 진행
3. 관련 당사자 및 영향
4. 원인 분석
5. 권고 조치

전문적인 톤으로 작성해주세요.
"""

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{settings.anthropic_api_url}/messages",
                    headers={
                        "x-api-key": settings.anthropic_api_key,
                        "anthropic-version": "2023-06-01",
                    },
                    json={
                        "model": settings.claude_model,
                        "max_tokens": 1500,
                        "messages": [
                            {
                                "role": "user",
                                "content": prompt,
                            }
                        ],
                    },
                )

            resp.raise_for_status()
            data = resp.json()

            # Claude 응답 추출
            content = data.get("content", [{}])[0].get("text", "")
            return content

        except Exception as e:
            logger.error("Claude API call failed: %s", e)

            # Fallback: 간단한 요약
            return self._fallback_report(alerts, report_type)

    @staticmethod
    def _fallback_report(alerts: list[dict], report_type: str) -> str:
        """AI 실패 시 기본 보고서"""
        if not alerts:
            return "보고서를 작성할 경보가 없습니다."

        alert_count = len(alerts)
        severity_counts = {}
        for alert in alerts:
            severity = alert.get("severity", "unknown")
            severity_counts[severity] = severity_counts.get(severity, 0) + 1

        severity_text = ", ".join(
            [f"{k}:{v}" for k, v in severity_counts.items()]
        )

        return f"총 {alert_count}건의 해양 경보가 기록되었습니다. ({severity_text})"
