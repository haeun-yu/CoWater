from __future__ import annotations

from typing import Any

from agent.base_runtime import BaseAgentRuntime
from agent.state import utc_now


class SystemSentinelRuntime(BaseAgentRuntime):
    """SystemSentinel 역할: 시스템/장치/연결 상태를 관찰하고 이상을 탐지"""

    async def handle_moth_message(self, event_type: str, payload: dict[str, Any], raw_event: dict[str, Any]) -> bool:
        if event_type in {
            "DEVICE_HEALTHCHECK",
            "ENV_STATE_CHANGED",
            "SYS_TASK_DISPATCHED",
            "SYS_TASK_COMPLETED",
            "SYS_TASK_FAILED",
        }:
            self.state.remember({"kind": "system_sentinel_event_seen", "at": utc_now(), "event_type": event_type, "payload": payload})
            return True
        return False

    async def _execute_role(self, parameters: dict[str, Any]) -> dict[str, Any]:
        from uuid import uuid4
        import time

        request_id = str(parameters.get("request_id") or "")
        context_id = str(parameters.get("context_id") or f"ctx-{uuid4()}")
        start_time = time.time()

        # Event: SYS_REQUEST_RECEIVED (A2A 요청 수신)
        if request_id:
            self.registry_client.ingest_event({
                "event_type": "SYS_REQUEST_RECEIVED",
                "context_id": context_id,
                "actor_type": "SYSTEM",
                "actor_id": self.state.agent_id,
                "target_type": "AGENT_COMMUNICATION",
                "target_id": request_id,
                "severity": "INFO",
                "data": {
                    "request_id": request_id,
                    "from_agent": "RequestHandler",
                    "to_agent": "SystemSentinel",
                    "timestamp": utc_now()
                }
            })

        try:
            devices = self.registry_client.list_devices()
        except Exception as exc:
            duration_ms = int((time.time() - start_time) * 1000)
            self.registry_client.ingest_agent_log({
                "context_id": context_id,
                "agent_id": self.state.agent_id,
                "agent_role": "SYSTEM_SENTINEL",
                "action": "detect_anomalies",
                "input": {},
                "output": {},
                "status": "FAILED",
                "duration_ms": duration_ms,
            })
            if request_id:
                self.registry_client.ingest_event({
                    "event_type": "SYS_RESPONSE_SENT",
                    "context_id": context_id,
                    "actor_type": "SYSTEM",
                    "actor_id": self.state.agent_id,
                    "target_type": "AGENT_COMMUNICATION",
                    "target_id": request_id,
                    "severity": "ERROR",
                    "data": {
                        "request_id": request_id,
                        "from_agent": "SystemSentinel",
                        "to_agent": "RequestHandler",
                        "response_status": "error",
                        "error_type": type(exc).__name__,
                        "timestamp": utc_now()
                    }
                })
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
            duration_ms = int((time.time() - start_time) * 1000)
            self.registry_client.ingest_agent_log({
                "context_id": context_id,
                "agent_id": self.state.agent_id,
                "agent_role": "SYSTEM_SENTINEL",
                "action": "detect_anomalies",
                "input": {"device_count": len(devices), "mission_count": len(missions)},
                "output": {"findings_count": 0, "anomalies_detected": False},
                "status": "SUCCESS",
                "duration_ms": duration_ms,
            })
            if request_id:
                self.registry_client.ingest_event({
                    "event_type": "SYS_RESPONSE_SENT",
                    "context_id": context_id,
                    "actor_type": "SYSTEM",
                    "actor_id": self.state.agent_id,
                    "target_type": "AGENT_COMMUNICATION",
                    "target_id": request_id,
                    "severity": "INFO",
                    "data": {
                        "request_id": request_id,
                        "from_agent": "SystemSentinel",
                        "to_agent": "RequestHandler",
                        "response_status": "ok",
                        "timestamp": utc_now()
                    }
                })
            return self._response_envelope(
                status="ok",
                response={
                    "findings": [],
                    "events": [],
                    "summary": "특이 이상 징후가 감지되지 않았습니다.",
                },
            )

        duration_ms = int((time.time() - start_time) * 1000)
        self.registry_client.ingest_agent_log({
            "context_id": context_id,
            "agent_id": self.state.agent_id,
            "agent_role": "SYSTEM_SENTINEL",
            "action": "detect_anomalies",
            "input": {"device_count": len(devices), "mission_count": len(missions)},
            "output": {"findings_count": len(findings), "anomalies_detected": True},
            "reasoning": {
                "anomaly_types": [f.get("type") for f in findings],
                "severity_levels": [f.get("severity") for f in findings],
            },
            "status": "SUCCESS",
            "duration_ms": duration_ms,
        })
        if request_id:
            self.registry_client.ingest_event({
                "event_type": "SYS_RESPONSE_SENT",
                "context_id": context_id,
                "actor_type": "SYSTEM",
                "actor_id": self.state.agent_id,
                "target_type": "AGENT_COMMUNICATION",
                "target_id": request_id,
                "severity": "WARNING",
                "data": {
                    "request_id": request_id,
                    "from_agent": "SystemSentinel",
                    "to_agent": "RequestHandler",
                    "response_status": "ok",
                    "finding_count": len(findings),
                    "timestamp": utc_now()
                }
            })
        return self._response_envelope(
            status="ok",
            response={
                "findings": findings,
                "events": events,
                "summary": "이상 징후를 감지했습니다.",
            },
        )
