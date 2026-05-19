from __future__ import annotations

import logging
from typing import Any

from agent.base_runtime import BaseAgentRuntime
from agent.state import utc_now

logger = logging.getLogger(__name__)


class DeviceBridgeRuntime(BaseAgentRuntime):
    """DeviceBridge 역할: Device Agent와의 전달/수집/정규화만 담당"""

    async def handle_moth_message(self, event_type: str, payload: dict[str, Any], raw_event: dict[str, Any]) -> None:
        self.state.remember({"kind": "device_bridge_event_seen", "at": utc_now(), "event_type": event_type, "payload": payload})

    async def _execute_role(self, parameters: dict[str, Any]) -> dict[str, Any]:
        action = str(parameters.get("action") or parameters.get("command") or "dispatch_task").strip()
        if action == "relay_healthcheck":
            payload = dict(parameters.get("payload") or parameters.get("healthcheck") or {})
            device_id = str(parameters.get("device_id") or payload.get("device_id") or "")
            if not device_id:
                return self._response_envelope(
                    status="needs_clarification",
                    error={"code": "missing_device_id", "message": "device_id가 필요합니다.", "details": {}},
                )
            status = str(payload.get("status") or "unknown").lower()
            if status:
                try:
                    self.registry_client.update_device_connectivity(device_id, status)
                except Exception as exc:
                    return self._response_envelope(
                        status="error",
                        error={"code": "healthcheck_relay_failed", "message": str(exc), "details": {"device_id": device_id}},
                    )
            self.state.remember({"kind": "healthcheck_relayed", "at": utc_now(), "device_id": device_id, "payload": payload})
            return self._response_envelope(
                status="ok",
                response={
                    "connection": {"state": status or "unknown", "device_id": device_id},
                    "payload": {"healthcheck": payload, "normalized": {"device_id": device_id, "state": status or "unknown"}},
                },
            )

        if action == "collect_result":
            mission_id = str(parameters.get("mission_id") or "")
            task_id = str(parameters.get("task_id") or "")
            if not mission_id and not task_id:
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
            self.state.remember({"kind": "task_result_collected", "at": utc_now(), "mission_id": mission_id, "task_id": task_id})
            return self._response_envelope(
                status="ok",
                response={
                    "connection": {"state": "connected", "device_id": str(parameters.get("device_id") or "")},
                    "payload": {"task_result": {"missions": matched, "task_id": task_id}, "normalized": {"count": len(matched)}},
                },
            )

        if action == "dispatch_task":
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
                dispatch = await self._dispatch_next_step(response_like, steps, devices, logging.getLogger(__name__))
                return self._response_envelope(
                    status="ok" if dispatch.get("delivered") else "error",
                    response={
                        "connection": {"state": "connected" if dispatch.get("delivered") else "degraded", "device_id": str(parameters.get("device_id") or "")},
                        "payload": {"task_result": dispatch, "normalized": {"delivered": bool(dispatch.get("delivered")), "mission_id": mission_id}},
                    },
                    error=None if dispatch.get("delivered") else {"code": "dispatch_failed", "message": str(dispatch.get("error") or "unknown"), "details": dispatch},
                )
            command = {
                "action": parameters.get("action") or parameters.get("command") or "hold_position",
                "params": parameters.get("params") or {},
                "reason": parameters.get("reason") or "DeviceBridge execute request",
            }
            result = await self.handle_command_with_llm(command)
            return self._response_envelope(
                status="ok",
                response={
                    "connection": {"state": "connected", "device_id": str(parameters.get("device_id") or "")},
                    "payload": {"task_result": result, "normalized": result},
                },
            )

        return self._response_envelope(
            status="needs_clarification",
            error={"code": "unsupported_action", "message": f"지원하지 않는 action입니다: {action}", "details": {}},
        )
