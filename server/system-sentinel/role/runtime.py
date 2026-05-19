from __future__ import annotations

import logging
from typing import Any

from agent.base_runtime import BaseAgentRuntime
from agent.state import utc_now

logger = logging.getLogger(__name__)


class SystemSentinelRuntime(BaseAgentRuntime):
    """SystemSentinel 역할: 시스템/장치/연결 상태를 관찰하고 이상을 탐지"""

    async def handle_moth_message(self, event_type: str, payload: dict[str, Any], raw_event: dict[str, Any]) -> None:
        if event_type in {
            "DEVICE_HEALTHCHECK",
            "ENV_STATE_CHANGED",
            "SYS_TASK_DISPATCHED",
            "SYS_TASK_COMPLETED",
            "SYS_TASK_FAILED",
        }:
            self.state.remember({"kind": "system_sentinel_event_seen", "at": utc_now(), "event_type": event_type, "payload": payload})

    async def _execute_role(self, parameters: dict[str, Any]) -> dict[str, Any]:
        try:
            devices = self.registry_client.list_devices()
        except Exception as exc:
            return self._response_envelope(
                status="error",
                error={"code": "device_lookup_failed", "message": str(exc), "details": {}},
            )
        try:
            missions = self.registry_client.list_missions()
        except Exception:
            missions = []
        findings: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []
        offline = [device for device in devices if str(device.get("connectivity_status") or "").lower() == "offline" or not bool(device.get("connected"))]
        if offline:
            findings.append({
                "type": "connection_loss",
                "severity": "high" if len(offline) > 1 else "medium",
                "description": f"{len(offline)}개 장치가 오프라인입니다.",
                "evidence": [{"device_id": item.get("id"), "name": item.get("name")} for item in offline[:5]],
            })
            events.append({"event_type": "SYS_ANOMALY_DETECTED", "severity": "WARNING", "count": len(offline)})
        failed_missions = [mission for mission in missions if str(mission.get("status") or "").upper() == "FAILED"]
        if failed_missions:
            findings.append({
                "type": "mission_failure",
                "severity": "medium" if len(failed_missions) == 1 else "high",
                "description": f"실패한 미션 {len(failed_missions)}개가 있습니다.",
                "evidence": [{"mission_id": item.get("mission_id"), "title": item.get("title")} for item in failed_missions[:5]],
            })
            events.append({"event_type": "SYS_ANOMALY_DETECTED", "severity": "WARNING", "count": len(failed_missions)})
        if not findings:
            return self._response_envelope(
                status="ok",
                response={
                    "findings": [],
                    "events": [],
                    "summary": "특이 이상 징후가 감지되지 않았습니다.",
                },
            )
        return self._response_envelope(
            status="ok",
            response={
                "findings": findings,
                "events": events,
                "summary": "이상 징후를 감지했습니다.",
            },
        )

    async def _process_waiting_queue(self, devices: list[dict[str, Any]], logger: Any) -> None:
        return
