from __future__ import annotations

import logging
from typing import Any

from agent.base_runtime import BaseAgentRuntime
from agent.state import utc_now

logger = logging.getLogger(__name__)


class InsightReporterRuntime(BaseAgentRuntime):
    """InsightReporter 역할: Registry 데이터를 바탕으로 한국어 리포트/인사이트 생성"""

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

    def _unwrap_a2a_envelope(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        if isinstance(payload.get("payload"), dict):
            inner = payload["payload"]
            if isinstance(inner.get("result"), dict):
                return inner["result"]
            if isinstance(inner.get("data"), dict):
                return inner["data"]
        if isinstance(payload.get("result"), dict):
            return payload["result"]
        if isinstance(payload.get("data"), dict):
            return payload["data"]
        return payload

    def _build_korean_report(self, devices: list[dict[str, Any]], missions: list[dict[str, Any]], insights: list[dict[str, Any]]) -> dict[str, Any]:
        connected = [item for item in devices if bool(item.get("connected")) or str(item.get("connectivity_status") or "").lower() == "online"]
        in_progress = [item for item in missions if str(item.get("status") or "").upper() == "IN_PROGRESS"]
        failed = [item for item in missions if str(item.get("status") or "").upper() == "FAILED"]
        critical_insights = [item for item in insights if str(item.get("severity") or "").upper() == "CRITICAL"]
        summary = (
            f"장치 {len(devices)}개 중 {len(connected)}개가 연결되어 있고, "
            f"진행 중 미션 {len(in_progress)}개, 실패 미션 {len(failed)}개, "
            f"인사이트 {len(insights)}개(중요 {len(critical_insights)}개)입니다."
        )
        highlights = [
            f"연결 장치 수: {len(connected)}개",
            f"진행 중 미션 수: {len(in_progress)}개",
            f"실패 미션 수: {len(failed)}개",
        ]
        recommendations: list[str] = []
        if failed:
            recommendations.append("실패한 미션의 최신 timeline과 task result를 우선 점검하세요.")
        if len(connected) < max(1, len(devices)):
            recommendations.append("연결이 끊긴 장치의 healthcheck와 복구 상태를 확인하세요.")
        if not recommendations:
            recommendations.append("현재 특별한 이상은 보이지 않지만, 주기적인 상태 점검을 유지하세요.")
        return {
            "language": "ko",
            "summary": summary,
            "highlights": highlights,
            "recommendations": recommendations,
        }

    async def _generate_insight_from_event(self, event: dict[str, Any]) -> None:
        """이벤트 수신 시 fleet 리포트 생성 및 Insight 저장"""
        event_id = str(event.get("event_id") or "")
        event_type = str(event.get("type") or event.get("event_type") or "")
        logger.info(f"[InsightReporter] 이벤트 처리: {event_id} ({event_type})")
        try:
            devices = self.registry_client.list_devices()
            missions = self.registry_client.list_missions()
            insights = self.registry_client.list_insights()
            report = self._build_korean_report(devices, missions, insights)
            if report.get("summary"):
                self.registry_client.create_insight({
                    "title": f"{event_type} 분석 리포트",
                    "summary": report.get("summary", ""),
                    "highlights": report.get("highlights", []),
                    "recommendations": report.get("recommendations", []),
                    "source": "event_triggered_report",
                    "related_event_id": event_id,
                    "created_at": utc_now(),
                })
                logger.info(f"[InsightReporter] Insight 생성 완료 (event: {event_id})")
        except Exception as e:
            logger.error(f"[InsightReporter] Insight 생성 오류: {e}")

    async def _execute_insight_reporter(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """Fleet 전체 현황 한국어 리포트 생성"""
        envelope = self._unwrap_a2a_envelope(parameters.get("a2a_envelope"))
        request = parameters.get("report_request") or envelope.get("report_request") or {}
        try:
            devices = self.registry_client.list_devices()
            missions = self.registry_client.list_missions()
            insights = self.registry_client.list_insights()
        except Exception as exc:
            return self._response_envelope(
                status="error",
                error={"code": "registry_lookup_failed", "message": str(exc), "details": {}},
            )
        if not devices and not missions and not insights:
            return self._response_envelope(
                status="needs_clarification",
                response={
                    "report": {
                        "language": "ko",
                        "summary": "리포트를 생성할 데이터가 부족합니다.",
                        "highlights": [],
                        "recommendations": ["Registry 데이터가 쌓인 뒤 다시 요청해 주세요."],
                    }
                },
            )
        report = self._build_korean_report(devices, missions, insights)
        if not report.get("summary"):
            return self._response_envelope(
                status="error",
                error={"code": "empty_report", "message": "빈 리포트를 생성할 수 없습니다.", "details": {"request": request}},
            )
        return self._response_envelope(
            status="ok",
            response={
                "report": report,
                "data": {"devices": devices, "missions": missions, "insights": insights, "request": request},
                "report_source": "rule_based",
            },
        )

    def classify_event_severity(self, event: dict[str, Any]) -> str:
        return super().classify_event_severity(event)

    def recommended_action_for_event(self, event_type: str, severity: str) -> str | None:
        return super().recommended_action_for_event(event_type, severity)
