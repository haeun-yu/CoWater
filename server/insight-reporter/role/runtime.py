from __future__ import annotations

import logging
from typing import Any

from agent.base_runtime import BaseAgentRuntime
from agent.state import utc_now

logger = logging.getLogger(__name__)


class InsightReporterRuntime(BaseAgentRuntime):
    """InsightReporter 역할: 이벤트 기반 Fleet 리포트 및 Insight 생성"""

    async def handle_moth_message(self, event_type: str, payload: dict[str, Any], raw_event: dict[str, Any]) -> None:
        if event_type in {
            "SYS_INTENT_CLASSIFIED",
            "SYS_TASK_DISPATCHED",
            "SYS_TASK_COMPLETED",
            "SYS_TASK_FAILED",
            "SYS_ANOMALY_DETECTED",
            "SYS_POLICY_DECISION",
            "SYS_MISSION_UPDATED",
            "SYS_MISSION_COMPLETED",
            "DEVICE_HEALTHCHECK",
        }:
            await self._generate_insight_from_event(raw_event)

    async def _execute_role(self, parameters: dict[str, Any]) -> dict[str, Any]:
        return await self._execute_insight_reporter(parameters)

    async def _generate_insight_from_event(self, event: dict[str, Any]) -> None:
        """이벤트 수신 시 fleet 리포트 생성 및 Insight 저장"""
        event_id = str(event.get("event_id") or "")
        event_type = str(event.get("type") or event.get("event_type") or "")
        logger.info(f"[InsightReporter] 이벤트 처리: {event_id} ({event_type})")
        try:
            devices = self.registry_client.list_devices()
            missions = self.registry_client.list_missions()
            insights = self.registry_client.list_insights()
            report, error = await self.decision_engine.generate_fleet_report(
                devices, missions, insights, self.state
            )
            if report:
                self.registry_client.create_insight({
                    "title": f"{event_type} 분석 리포트",
                    "summary": report.get("report", ""),
                    "highlights": report.get("highlights", []),
                    "recommendations": report.get("recommendations", []),
                    "source": "event_triggered_report",
                    "related_event_id": event_id,
                    "created_at": utc_now(),
                })
                logger.info(f"[InsightReporter] Insight 생성 완료 (event: {event_id})")
            elif error:
                logger.warning(f"[InsightReporter] 리포트 생성 실패: {error}")
        except Exception as e:
            logger.error(f"[InsightReporter] Insight 생성 오류: {e}")

    async def _execute_insight_reporter(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """Fleet 전체 현황 한국어 리포트 생성"""
        devices = self.registry_client.list_devices()
        missions = self.registry_client.list_missions()
        insights = self.registry_client.list_insights()
        report, error = await self.decision_engine.generate_fleet_report(
            devices, missions, insights, self.state
        )
        return {
            "type": "RESPONSE",
            "status": "SUCCESS",
            "data": {"devices": devices, "missions": missions, "insights": insights},
            "report": report,
            "report_source": "llm" if not error else "rule_based",
        }

    def classify_event_severity(self, event: dict[str, Any]) -> str:
        return super().classify_event_severity(event)

    def recommended_action_for_event(self, event_type: str, severity: str) -> str | None:
        return super().recommended_action_for_event(event_type, severity)
