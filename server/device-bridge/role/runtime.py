from __future__ import annotations

from typing import Any

from agent.base_runtime import BaseAgentRuntime
from agent.state import utc_now


class DeviceBridgeRuntime(BaseAgentRuntime):
    """DeviceBridge 역할: Device Agent와의 전달/수집/정규화만 담당"""

    async def handle_moth_message(self, event_type: str, payload: dict[str, Any], raw_event: dict[str, Any]) -> bool:
        # DeviceBridge는 이벤트를 구독하지 않는다. (발행만 한다)
        return False

    async def _execute_role(self, parameters: dict[str, Any]) -> dict[str, Any]:
        from uuid import uuid4
        import time

        request_id = str(parameters.get("request_id") or "")
        context_id = str(parameters.get("context_id") or f"ctx-{uuid4()}")

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
                    "to_agent": "DeviceBridge",
                    "timestamp": utc_now()
                }
            })

        action = str(parameters.get("action") or parameters.get("command") or "dispatch_task").strip()
        if action == "relay_healthcheck":
            start_time = time.time()
            payload = dict(parameters.get("payload") or parameters.get("healthcheck") or {})
            device_id = str(parameters.get("device_id") or payload.get("device_id") or "")
            if not device_id:
                duration_ms = int((time.time() - start_time) * 1000)
                self.registry_client.ingest_agent_log({
                    "context_id": context_id,
                    "agent_id": self.state.agent_id,
                    "agent_role": "DEVICE_BRIDGE",
                    "action": "relay_healthcheck",
                    "input": {"payload": payload, "device_id": device_id},
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
                        "severity": "WARNING",
                        "data": {
                            "request_id": request_id,
                            "from_agent": "DeviceBridge",
                            "to_agent": "RequestHandler",
                            "response_status": "error",
                            "error_code": "missing_device_id",
                            "timestamp": utc_now()
                        }
                    })
                return self._response_envelope(
                    status="needs_clarification",
                    error={"code": "missing_device_id", "message": "device_id가 필요합니다.", "details": {}},
                )
            status = str(payload.get("status") or "unknown").lower()
            if status:
                try:
                    self.registry_client.update_device_connectivity(device_id, status)
                except Exception as exc:
                    duration_ms = int((time.time() - start_time) * 1000)
                    self.registry_client.ingest_agent_log({
                        "context_id": context_id,
                        "agent_id": self.state.agent_id,
                        "agent_role": "DEVICE_BRIDGE",
                        "action": "relay_healthcheck",
                        "input": {"device_id": device_id, "status": status},
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
                                "from_agent": "DeviceBridge",
                                "to_agent": "RequestHandler",
                                "response_status": "error",
                                "error_type": type(exc).__name__,
                                "timestamp": utc_now()
                            }
                        })
                    return self._response_envelope(
                        status="error",
                        error={"code": "healthcheck_relay_failed", "message": str(exc), "details": {"device_id": device_id}},
                    )
            duration_ms = int((time.time() - start_time) * 1000)
            self.registry_client.ingest_agent_log({
                "context_id": context_id,
                "agent_id": self.state.agent_id,
                "agent_role": "DEVICE_BRIDGE",
                "action": "relay_healthcheck",
                "input": {"device_id": device_id, "status": status},
                "output": {"device_id": device_id, "state": status or "unknown"},
                "status": "SUCCESS",
                "duration_ms": duration_ms,
            })
            self.state.remember({"kind": "healthcheck_relayed", "at": utc_now(), "device_id": device_id, "payload": payload})
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
                        "from_agent": "DeviceBridge",
                        "to_agent": "RequestHandler",
                        "response_status": "ok",
                        "action": "relay_healthcheck",
                        "timestamp": utc_now()
                    }
                })
            return self._response_envelope(
                status="ok",
                response={
                    "connection": {"state": status or "unknown", "device_id": device_id},
                    "payload": {"healthcheck": payload, "normalized": {"device_id": device_id, "state": status or "unknown"}},
                },
            )

        if action == "collect_result":
            start_time = time.time()
            mission_id = str(parameters.get("mission_id") or "")
            task_id = str(parameters.get("task_id") or "")
            if not mission_id and not task_id:
                duration_ms = int((time.time() - start_time) * 1000)
                self.registry_client.ingest_agent_log({
                    "context_id": context_id,
                    "agent_id": self.state.agent_id,
                    "agent_role": "DEVICE_BRIDGE",
                    "action": "collect_result",
                    "input": {"mission_id": mission_id, "task_id": task_id},
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
                        "severity": "WARNING",
                        "data": {
                            "request_id": request_id,
                            "from_agent": "DeviceBridge",
                            "to_agent": "RequestHandler",
                            "response_status": "error",
                            "error_code": "missing_reference",
                            "timestamp": utc_now()
                        }
                    })
                return self._response_envelope(
                    status="needs_clarification",
                    error={"code": "missing_reference", "message": "mission_id 또는 task_id가 필요합니다.", "details": {}},
                )
            missions = self.registry_client.list_missions()
            matched: list[dict[str, Any]] = []
            for mission in missions:
                if not isinstance(mission, dict):
                    continue
                if mission_id and str(mission.get("mission_id") or "") != mission_id:
                    continue
                matched.append(mission)
            duration_ms = int((time.time() - start_time) * 1000)
            self.registry_client.ingest_agent_log({
                "context_id": context_id,
                "agent_id": self.state.agent_id,
                "agent_role": "DEVICE_BRIDGE",
                "action": "collect_result",
                "input": {"mission_id": mission_id, "task_id": task_id},
                "output": {"missions_count": len(matched), "task_id": task_id},
                "status": "SUCCESS",
                "duration_ms": duration_ms,
            })
            self.state.remember({"kind": "task_result_collected", "at": utc_now(), "mission_id": mission_id, "task_id": task_id})
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
                        "from_agent": "DeviceBridge",
                        "to_agent": "RequestHandler",
                        "response_status": "ok",
                        "action": "collect_result",
                        "timestamp": utc_now()
                    }
                })
            return self._response_envelope(
                status="ok",
                response={
                    "connection": {"state": "connected", "device_id": str(parameters.get("device_id") or "")},
                    "payload": {"task_result": {"missions": matched, "task_id": task_id}, "normalized": {"count": len(matched)}},
                },
            )

        if action == "dispatch_task":
            start_time = time.time()
            steps = list(parameters.get("steps") or [])
            mission_id = str(parameters.get("mission_id") or "")
            if steps and mission_id:
                devices = self.registry_client.list_devices()
                response_like = {
                    "response_id": mission_id,
                    "mission_id": mission_id,
                    "alert_id": parameters.get("alert_id"),
                    "reason": parameters.get("reason") or "DeviceBridge task dispatch",
                    "dispatch_result": {"steps": []},
                }
                dispatch = await self._dispatch_next_step(response_like, steps, devices)
                duration_ms = int((time.time() - start_time) * 1000)
                self.registry_client.ingest_agent_log({
                    "context_id": context_id,
                    "agent_id": self.state.agent_id,
                    "agent_role": "DEVICE_BRIDGE",
                    "action": "dispatch_task",
                    "input": {"mission_id": mission_id, "steps_count": len(steps)},
                    "output": {"delivered": bool(dispatch.get("delivered")), "mission_id": mission_id},
                    "status": "SUCCESS" if dispatch.get("delivered") else "FAILED",
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
                        "severity": "INFO" if dispatch.get("delivered") else "WARNING",
                        "data": {
                            "request_id": request_id,
                            "from_agent": "DeviceBridge",
                            "to_agent": "RequestHandler",
                            "response_status": "ok" if dispatch.get("delivered") else "error",
                            "action": "dispatch_task",
                            "timestamp": utc_now()
                        }
                    })
                return self._response_envelope(
                    status="ok" if dispatch.get("delivered") else "error",
                    response={
                        "connection": {"state": "connected" if dispatch.get("delivered") else "degraded", "device_id": str(parameters.get("device_id") or "")},
                        "payload": {"task_result": dispatch, "normalized": {"delivered": bool(dispatch.get("delivered")), "mission_id": mission_id}},
                    },
                    error=None if dispatch.get("delivered") else {"code": "dispatch_failed", "message": str(dispatch.get("error") or "unknown"), "details": dispatch},
                )
            start_time = time.time()
            command = {
                "action": parameters.get("action") or parameters.get("command") or "hold_position",
                "params": parameters.get("params") or {},
                "reason": parameters.get("reason") or "DeviceBridge execute request",
            }
            result = await self.handle_command_with_llm(command)
            duration_ms = int((time.time() - start_time) * 1000)
            self.registry_client.ingest_agent_log({
                "context_id": context_id,
                "agent_id": self.state.agent_id,
                "agent_role": "DEVICE_BRIDGE",
                "action": "dispatch_task",
                "input": {"command": command.get("action")},
                "output": result,
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
                        "from_agent": "DeviceBridge",
                        "to_agent": "RequestHandler",
                        "response_status": "ok",
                        "action": "dispatch_task",
                        "timestamp": utc_now()
                    }
                })
            return self._response_envelope(
                status="ok",
                response={
                    "connection": {"state": "connected", "device_id": str(parameters.get("device_id") or "")},
                    "payload": {"task_result": result, "normalized": result},
                },
            )

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
                    "from_agent": "DeviceBridge",
                    "to_agent": "RequestHandler",
                    "response_status": "error",
                    "error_code": "unsupported_action",
                    "timestamp": utc_now()
                }
            })
        return self._response_envelope(
            status="needs_clarification",
            error={"code": "unsupported_action", "message": f"지원하지 않는 action입니다: {action}", "details": {}},
        )
