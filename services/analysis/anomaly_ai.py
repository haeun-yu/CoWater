"""
Analysis - Anomaly AI Agent

Detection이 감지한 비정상 항적을 분석하고 원인을 파악.
Claude API를 사용해서 AI 기반 분석.
"""

from __future__ import annotations

import asyncio
import json
import logging
from uuid import uuid4

import httpx
import redis.asyncio as aioredis

from shared.events import Event, EventType
from config import settings
from .base import AnalysisAgent

logger = logging.getLogger(__name__)


class AnalysisAnomalyAIAgent(AnalysisAgent):
    """Analysis 단계: AI 기반 비정상 분석"""

    agent_id = "analysis-anomaly-ai"

    def __init__(self, redis: aioredis.Redis, core_api_url: str) -> None:
        super().__init__(redis, core_api_url)

        self._client = None

    async def on_detect_event(self, event: Event) -> None:
        """detect.anomaly.* 이벤트 수신 (빠른 반환, 분석은 백그라운드)"""

        if event.type != EventType.DETECT_ANOMALY:
            return

        payload = event.payload
        platform_id = payload.get("platform_id")
        anomaly_type = payload.get("anomaly_type")
        reason = payload.get("reason", "")

        logger.info(
            "Queued anomaly analysis: platform=%s, type=%s",
            platform_id,
            anomaly_type,
        )

        # AI 분석을 백그라운드 태스크로 실행 (이벤트 처리를 블로킹하지 않음)
        asyncio.create_task(
            self._analyze_and_emit(
                event=event,
                platform_id=platform_id,
                anomaly_type=anomaly_type,
                reason=reason,
            )
        )

    async def _analyze_and_emit(
        self,
        event: Event,
        platform_id: str,
        anomaly_type: str,
        reason: str,
    ) -> None:
        """백그라운드에서 AI 분석 후 이벤트 발행"""

        try:
            # AI 분석 (시간이 걸릴 수 있음)
            analysis_result = await self._analyze_with_ai(
                platform_id=platform_id,
                anomaly_type=anomaly_type,
                reason=reason,
            )
        except Exception as e:
            logger.error("AI analysis failed: %s", e)
            return

        # 분석 결과 Event 발행
        alert_id = str(uuid4())

        analysis_payload = {
            "alert_id": alert_id,
            "platform_id": platform_id,
            "original_anomaly_type": anomaly_type,
            "analysis_result": analysis_result.get("result", "분석 불가"),
            "recommendation": analysis_result.get("recommendation"),
            "confidence": analysis_result.get("confidence", 0.5),
            "timestamp": event.timestamp.isoformat(),
            "ai_model": settings.claude_model,
            "execution_time_ms": analysis_result.get("execution_time_ms", 0),
        }

        await self.emit_analysis_event(
            event_type=EventType.ANALYZE_ANOMALY,
            payload=analysis_payload,
            flow_id=event.flow_id,
            causation_id=event.event_id,
        )

    async def _analyze_with_ai(
        self,
        platform_id: str,
        anomaly_type: str,
        reason: str,
    ) -> dict:
        """Claude API를 사용해서 비정상 분석"""

        prompt = f"""
해양 선박의 비정상 항적이 감지되었습니다.

선박 ID: {platform_id}
비정상 타입: {anomaly_type}
상세: {reason}

다음을 분석해주세요:
1. 가능한 원인 (기술적 문제, 환경, 의도된 행동 등)
2. 위험도 평가
3. 권고사항

JSON 형식으로 응답해주세요:
{{
    "possible_causes": ["원인1", "원인2", ...],
    "risk_level": "low|medium|high",
    "recommendation": "권고사항",
    "confidence": 0.0-1.0
}}
"""

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{settings.anthropic_api_url}/messages",
                    headers={
                        "x-api-key": settings.anthropic_api_key,
                        "anthropic-version": "2023-06-01",
                    },
                    json={
                        "model": settings.claude_model,
                        "max_tokens": 500,
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

            # Claude 응답 파싱
            content = data.get("content", [{}])[0].get("text", "{}")
            analysis = json.loads(content)

            return {
                "result": f"원인: {', '.join(analysis.get('possible_causes', []))}",
                "recommendation": analysis.get("recommendation"),
                "confidence": analysis.get("confidence", 0.5),
                "execution_time_ms": 0,  # 실제로는 측정 필요
            }

        except Exception as e:
            logger.error("Claude API call failed: %s", e)

            # Fallback: 규칙 기반 분석
            return self._fallback_analysis(anomaly_type)

    @staticmethod
    def _fallback_analysis(anomaly_type: str) -> dict:
        """AI 실패 시 규칙 기반 분석"""

        rules = {
            "rot": {
                "result": "선회율 이상 - 선박 조종 오류 또는 흐름 영향",
                "recommendation": "선박의 자세 확인 및 해류/바람 영향 검토",
                "confidence": 0.6,
            },
            "heading_jump": {
                "result": "방향 급변 - 의도된 항로 변경 또는 기술적 오류",
                "recommendation": "선박 운항 계획과 실제 항로 비교",
                "confidence": 0.5,
            },
            "speed_spike": {
                "result": "속도 급변 - 엔진 출력 변화 또는 측정 오류",
                "recommendation": "선박 운항 상태 모니터링",
                "confidence": 0.6,
            },
            "position_jump": {
                "result": "위치 점프 - GPS 신호 오류 또는 데이터 왜곡",
                "recommendation": "GPS 신호 강도 확인",
                "confidence": 0.5,
            },
        }

        return rules.get(
            anomaly_type,
            {
                "result": "알 수 없는 비정상",
                "recommendation": "추가 정보 필요",
                "confidence": 0.3,
            },
        )
