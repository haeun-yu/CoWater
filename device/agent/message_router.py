from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from uuid import uuid4
import urllib.request

from controller.a2a import A2APart, A2AMessage, A2ASendRequest, build_task, extract_message_data
from agent.state import utc_now

logger = logging.getLogger(__name__)


async def _execute_and_report_task(
    runtime: Any,
    task_id: str,
    command: dict[str, Any],
    message_data: dict[str, Any],
    request: A2ASendRequest,
) -> None:
    try:
        execution_result = await asyncio.to_thread(runtime.apply_command, command)
        normalized_status = "COMPLETED" if str(execution_result.get("status") or "").lower() in {"ok", "success", "completed"} else "FAILED"

        mission_id = str(message_data.get("mission_id") or message_data.get("response_id") or "")
        report_base = str((command.get("params") or {}).get("report_to_endpoint") or "").strip()
        if not report_base:
            report_base = str(runtime.config.get("system_agent", {}).get("url") or "http://127.0.0.1:9116").strip()
        report_endpoint = report_base if report_base.endswith("/message:send") else f"{report_base.rstrip('/')}/message:send"

        await _report_task_result_to_system_agent(
            runtime=runtime,
            task_id=task_id,
            command=command,
            execution_result=execution_result if isinstance(execution_result, dict) else {"status": "unknown", "raw": execution_result},
            execution_status=normalized_status,
            system_agent_url=report_endpoint,
            mission_id=mission_id or None,
            step_id=str(message_data.get("step_id") or ""),
            response_id=str(message_data.get("response_id") or mission_id or ""),
        )

        if normalized_status == "FAILED":
            category = execution_result.get("failure_category", "").lower().strip()
            if not category or category not in {"device", "communication", "sensor", "mission", "policy", "user", "unknown"}:
                category = "device"
            execution_result["failure_category"] = category
            if "failure_message" not in execution_result:
                execution_result["failure_message"] = (
                    execution_result.get("failure_message")
                    or execution_result.get("error")
                    or "Task execution failed"
                )

        if task_id:
            result_to_store = {
                "task_id": task_id,
                "status": normalized_status,
                "execution_result": execution_result if isinstance(execution_result, dict) else {"status": "unknown", "raw": execution_result},
            }
            runtime.task_id_store.record(task_id, result_to_store)

        logger.info(f"Task {task_id} executed and reported: {normalized_status}")
    except Exception as e:
        logger.error(f"Error executing and reporting task {task_id}: {e}", exc_info=True)


async def _relay_task_to_child(runtime: Any, request: A2ASendRequest, data: dict[str, Any]) -> dict[str, Any]:
    target_device_id = str(data.get("target_device_id") or (data.get("params") or {}).get("target_device_id") or "")
    try:
        child_device = runtime.registry_client.get_device(target_device_id)
    except Exception as exc:
        return {
            "status": "REJECTED",
            "task_status": "REJECTED",
            "reason": f"child_lookup_failed:{exc}",
            "task_id": str(data.get("task_id") or request.taskId or ""),
        }

    agent = child_device.get("agent") or {}
    endpoint = str(agent.get("endpoint") or "").strip()
    if not endpoint or not child_device.get("connected"):
        return {
            "status": "REJECTED",
            "task_status": "REJECTED",
            "reason": "child_unreachable",
            "task_id": str(data.get("task_id") or request.taskId or ""),
        }

    relay_payload = {
        **data,
        "message_type": "task.assign",
        "relayed_by_agent_id": runtime.state.agent_id,
        "relayed_by_device_id": runtime.state.registry_id,
    }

    def _send_to_child() -> dict[str, Any]:
        rpc = {
            "jsonrpc": "2.0",
            "method": "message/send",
            "id": str(request.taskId or data.get("task_id") or ""),
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"type": "data", "data": relay_payload}],
                },
                "taskId": request.taskId,
                "metadata": {
                    "sender_id": runtime.state.agent_id,
                    "sender_device_id": str(runtime.state.registry_id or ""),
                },
            },
        }
        raw = json.dumps(rpc).encode("utf-8")
        req = urllib.request.Request(endpoint, data=raw, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read() or b"{}")

    try:
        child_response = await asyncio.to_thread(_send_to_child)
    except Exception as exc:
        return {
            "status": "REJECTED",
            "task_status": "REJECTED",
            "reason": f"relay_failed:{exc}",
            "task_id": str(data.get("task_id") or request.taskId or ""),
        }

    artifact_data: dict[str, Any] = {}
    try:
        artifact_data = (((child_response.get("result") or {}).get("artifacts") or [])[0].get("parts") or [])[0].get("data") or {}
    except Exception:
        artifact_data = {}
    return {
        **artifact_data,
        "relayed": True,
        "relayed_to_device_id": target_device_id,
        "relayed_to_endpoint": endpoint,
    }


async def _report_task_result_to_system_agent(
    runtime: Any,
    task_id: str | None,
    command: dict[str, Any],
    execution_result: dict[str, Any],
    execution_status: str,
    system_agent_url: str = "http://127.0.0.1:9116/message:send",
    mission_id: str | None = None,
    step_id: str | None = None,
    response_id: str | None = None,
) -> None:
    try:
        normalized_status = "COMPLETED" if str(execution_status).lower() == "completed" else "FAILED"
        result_message = A2AMessage(
            role="device",
            parts=[
                A2APart(
                    type="data",
                    data={
                        "message_type": "task.result",
                        "task_id": task_id,
                        "mission_id": mission_id,
                        "response_id": response_id or mission_id or task_id,
                        "step_id": step_id,
                        "status": normalized_status,
                        "device_id": runtime.state.registry_id,
                        "agent_id": runtime.state.agent_id,
                        "command": command,
                        "error": execution_result.get("failure_reason") or execution_result.get("error"),
                        "execution_result": execution_result,
                        "timestamp": utc_now(),
                    },
                )
            ],
        )

        result_request = A2ASendRequest(
            message=result_message,
            taskId=task_id,
            metadata={"sender_id": runtime.state.agent_id, "sender_device_id": str(runtime.state.registry_id or "")},
        )

        data = json.dumps(result_request.model_dump()).encode("utf-8")
        req = urllib.request.Request(system_agent_url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5):
            logger.info(f"Task result reported to System Agent: task_id={task_id} status={normalized_status}")
    except Exception as e:
        logger.error(f"Failed to report task result to System Agent: {e}")


async def handle_a2a(runtime: Any, request: A2ASendRequest) -> dict[str, Any]:
    data = extract_message_data(request.message)
    runtime.record_inbox(request.taskId, data)
    msg_type = str(data.get("message_type") or data.get("type") or "task.assign")

    VALID_MESSAGE_TYPES = {
        "task.assign",
        "task.result",
        "event.report",
        "mission.result",
        "child.register",
        "layer.assignment",
    }

    if msg_type == "child.register":
        child = data.get("child") or data
        record = runtime.register_child(child)
        result = {"registered": True, "child_id": record["agent_id"]}
    elif msg_type == "layer.assignment":
        runtime.apply_assignment(data)
        result = {"assigned": True, "route_mode": runtime.state.route_mode, "parent_id": runtime.state.parent_id}
    elif msg_type == "task.assign":
        task_id = str(data.get("task_id") or request.taskId or "")
        if task_id:
            existing_result = runtime.task_id_store.is_processed(task_id)
            if existing_result:
                logger.info(f"Task {task_id} already processed, returning cached result")
                result = existing_result
                task = build_task(request.taskId, request.message, result)
                runtime.record_task(task, result)
                return task

        target_device_id = str(data.get("target_device_id") or (data.get("params") or {}).get("target_device_id") or "")
        own_device_id = str(runtime.state.registry_id or "")
        if runtime.state.layer == "middle" and target_device_id and own_device_id and target_device_id != own_device_id:
            result = await _relay_task_to_child(runtime, request, data)
            task = build_task(request.taskId, request.message, result)
            runtime.record_task(task, result)
            runtime.state.remember({
                "kind": "a2a_received",
                "at": utc_now(),
                "message_type": msg_type,
                "task_id": request.taskId,
                "result_status": result.get("status") if isinstance(result, dict) else "ok",
            })
            return task
        command = {
            "action": str(data.get("action") or data.get("command") or "hold_position"),
            "params": data.get("params") or {},
            "reason": data.get("reason") or f"A2A task {request.taskId}",
        }
        accepted, reject_reason = runtime.can_accept_command(command)
        if not accepted:
            result = {
                "status": "REJECTED",
                "reason": reject_reason or "task_rejected",
                "acceptance_status": "REJECTED",
                "task_id": str(data.get("task_id") or request.taskId or ""),
                "failure_category": "policy",
                "failure_message": f"Task rejected: {reject_reason or 'device not ready'}",
            }
        else:
            task_id = str(data.get("task_id") or request.taskId or "")
            result = {
                "acceptance_status": "ACCEPTED",
                "task_id": task_id,
            }
            asyncio.create_task(
                _execute_and_report_task(
                    runtime=runtime,
                    task_id=task_id,
                    command=command,
                    message_data=data,
                    request=request,
                )
            )
    elif msg_type == "event.report":
        event_type = str(data.get("event_type") or "UNKNOWN")
        severity = str(data.get("severity") or "INFO")
        description = str(data.get("description") or "")
        logger.warning(f"Event reported: type={event_type}, severity={severity}, description={description}")
        result = {
            "received": True,
            "event_type": event_type,
            "logged": True,
        }
    elif msg_type == "mission.result":
        mission_id = str(data.get("mission_id") or "")
        mission_status = str(data.get("status") or "UNKNOWN")
        logger.info(f"Mission result received: mission_id={mission_id}, status={mission_status}")
        runtime.state.remember({
            "kind": "mission_result",
            "mission_id": mission_id,
            "status": mission_status,
            "at": utc_now(),
        })
        result = {
            "received": True,
            "mission_id": mission_id,
            "status": mission_status,
        }
    else:
        if msg_type not in VALID_MESSAGE_TYPES:
            logger.warning(f"Unknown A2A message_type: {msg_type}, task_id: {request.taskId}, data: {data}")
        result = {"received": True, "message_type": msg_type}

    task = build_task(request.taskId, request.message, result)
    runtime.record_task(task, result)
    runtime.state.remember({
        "kind": "a2a_received",
        "at": utc_now(),
        "message_type": msg_type,
        "task_id": request.taskId,
        "result_status": result.get("status") if isinstance(result, dict) else "ok",
    })

    try:
        from_agent_id = (
            data.get("from_agent_id")
            or data.get("sender_agent_id")
            or data.get("source_agent_id")
            or data.get("agent_id")
        )
        to_agent_id = str(runtime.state.registry_id or runtime.instance_id or "")
        task_id = str(data.get("task_id") or request.taskId or "")
        mission_id = str(data.get("mission_id") or data.get("response_id") or "")

        runtime.registry_client.log_a2a_message(
            direction="inbound",
            from_agent_id=from_agent_id,
            to_agent_id=to_agent_id,
            message_type=msg_type,
            task_id=task_id if task_id else None,
            mission_id=mission_id if mission_id else None,
            payload=data,
        )
    except Exception as e:
        logger.debug(f"A2A logging failed (non-critical): {e}")

    publisher = getattr(runtime, "moth_publisher", None)
    if publisher is not None:
        metadata = request.metadata or {}
        from_device_id = (
            metadata.get("sender_device_id")
            or data.get("sender_device_id")
            or data.get("from_device_id")
            or data.get("source_device_id")
            or metadata.get("sender_id")
            or data.get("agent_id")
        )
        if from_device_id is None and msg_type in {"task.result"}:
            from_device_id = data.get("device_id")
        action = str(data.get("action") or data.get("command") or "").strip() or None
        asyncio.create_task(
            publisher.publish_a2a_event(
                from_device_id=from_device_id,
                message_type=msg_type,
                task_id=task["id"],
                action=action,
            )
        )

    return task
