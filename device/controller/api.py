from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from agent.runtime import AgentRuntime
from agent.state import utc_now
from controller.a2a import A2APart, A2AMessage, A2ASendRequest, build_task, extract_message_data
from controller.commands import CommandRequest

logger = logging.getLogger(__name__)


def create_app(runtime: AgentRuntime) -> FastAPI:
    app = FastAPI(title=f"CoWater {runtime.state.role}", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=runtime.config.get("cors", {}).get("allow_origins", ["*"]),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    async def _run_simulation_loop_with_logging() -> None:
        """Wrapper to catch and log simulation_loop exceptions"""
        try:
            logger.info("Starting simulation loop...")
            await runtime.simulation_loop()
        except Exception as e:
            logger.error(f"Simulation loop failed: {e}", exc_info=True)
            raise

    @app.on_event("startup")
    async def startup() -> None:
        try:
            runtime.register()
        except Exception as exc:
            runtime.state.remember({"kind": "registration_error", "at": utc_now(), "error": str(exc)})
            if runtime.registry_client.required:
                raise
        app.state.simulation_task = asyncio.create_task(_run_simulation_loop_with_logging())

    @app.on_event("shutdown")
    async def shutdown() -> None:
        task = getattr(app.state, "simulation_task", None)
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await runtime.stop()

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "agent_id": runtime.state.agent_id}

    @app.get("/meta")
    def meta() -> dict[str, Any]:
        return {"config_path": str(runtime.config_path), "manifest": runtime.manifest_builder.manifest(runtime.state)}

    @app.get("/state")
    def state() -> dict[str, Any]:
        return runtime.state.to_dict()

    @app.get("/manifest")
    def manifest() -> dict[str, Any]:
        return runtime.manifest_builder.manifest(runtime.state)

    @app.get("/.well-known/agent-card.json")
    def agent_card() -> dict[str, Any]:
        return runtime.manifest_builder.agent_card(runtime.state)

    @app.get("/.well-known/agent.json")
    def agent_card_legacy() -> dict[str, Any]:
        return runtime.manifest_builder.agent_card(runtime.state)

    @app.post("/")
    async def json_rpc(request: dict[str, Any]) -> dict[str, Any]:
        if request.get("method") != "message/send":
            return {"jsonrpc": "2.0", "id": request.get("id"), "error": {"code": -32601, "message": "method not found"}}
        task = await handle_a2a(runtime, A2ASendRequest(**(request.get("params") or {})))
        return {"jsonrpc": "2.0", "id": request.get("id"), "result": task}

    @app.post("/message:send")
    async def message_send(request: A2ASendRequest) -> dict[str, Any]:
        return await handle_a2a(runtime, request)

    @app.post("/agents/{token}/command")
    async def command(token: str, request: CommandRequest) -> dict[str, Any]:
        if runtime.state.token and token != runtime.state.token:
            raise HTTPException(status_code=403, detail="token mismatch")
        return runtime.apply_command(request.model_dump())

    @app.post("/children/register")
    async def register_child(child: dict[str, Any]) -> dict[str, Any]:
        child_id = str(child.get("agent_id") or child.get("id"))
        record = dict(child, agent_id=child_id, registered_at=utc_now())
        runtime.state.children[child_id] = record
        runtime.state.remember({"kind": "child_registered", "at": utc_now(), "child": child_id})
        return {"registered": True, "child": record}

    @app.get("/children")
    def children() -> dict[str, Any]:
        return {"children": list(runtime.state.children.values())}

    @app.post("/children/healthcheck")
    async def relay_child_healthcheck(payload: dict[str, Any]) -> dict[str, Any]:
        child_id = str(payload.get("agent_id") or payload.get("device_id"))
        now = utc_now()
        child_state = runtime.state.children.setdefault(child_id, {})
        child_state["last_healthcheck_at"] = now
        child_state["healthcheck"] = payload
        publisher = getattr(runtime, "moth_publisher", None)
        if publisher is not None:
            await publisher.publish_healthcheck_payload(dict(payload, relayed_by=runtime.state.registry_id))
        return {"relayed": True, "child": child_id}

    @app.get("/tasks")
    def tasks() -> dict[str, Any]:
        return {"tasks": list(runtime.state.tasks.values()), "nextPageToken": ""}

    return app


async def _execute_and_report_task(
    runtime: AgentRuntime,
    task_id: str,
    command: dict[str, Any],
    message_data: dict[str, Any],
    request: A2ASendRequest,
) -> None:
    """Execute task asynchronously and report result back to System Agent."""
    try:
        # Execute command in thread pool to avoid blocking
        execution_result = await asyncio.to_thread(runtime.apply_command, command)

        # Determine execution status
        normalized_status = "completed" if str(execution_result.get("status") or "").lower() in {"ok", "success", "completed"} else "failed"

        # Get report endpoint
        mission_id = str(message_data.get("mission_id") or message_data.get("response_id") or "")
        report_base = str((command.get("params") or {}).get("report_to_endpoint") or "").strip()
        if not report_base:
            report_base = str(runtime.config.get("system_agent", {}).get("url") or "http://127.0.0.1:9116").strip()
        report_endpoint = report_base if report_base.endswith("/message:send") else f"{report_base.rstrip('/')}/message:send"

        # Report based on whether it's a mission task or standalone task
        if mission_id:
            # Mission task: use mission.result endpoint
            await _report_mission_result_to_endpoint(
                runtime=runtime,
                mission_id=mission_id,
                alert_id=str(message_data.get("alert_id") or ""),
                step_id=str(message_data.get("step_id") or ""),
                task_id=task_id,
                command=command,
                execution_result=execution_result if isinstance(execution_result, dict) else {"status": "unknown", "raw": execution_result},
                execution_status=normalized_status,
                endpoint=report_endpoint,
            )
        else:
            # Standalone task: send task.result to System Agent
            await _report_task_failure_to_system_agent(
                runtime=runtime,
                task_id=task_id,
                command=command,
                error=None,
                execution_result=execution_result if isinstance(execution_result, dict) else {"status": "unknown", "raw": execution_result},
                system_agent_url=report_endpoint,
            )

        # ✅ Standardize failure_category and failure_message (archi Ch.10)
        if normalized_status == "failed":
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

        # ✅ Record task execution in task_id_store to prevent future duplicates
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


async def handle_a2a(runtime: AgentRuntime, request: A2ASendRequest) -> dict[str, Any]:
    data = extract_message_data(request.message)
    runtime.state.inbox.append({"task_id": request.taskId, "at": utc_now(), "data": data})
    msg_type = str(data.get("message_type") or data.get("type") or "task.assign")

    # Valid message types for device agents
    VALID_MESSAGE_TYPES = {"child.register", "layer.assignment", "task.assign", "event.report", "mission.result"}

    if msg_type == "child.register":
        child = data.get("child") or data
        child_id = str(child.get("agent_id"))
        runtime.state.children[child_id] = dict(child, agent_id=child_id, registered_at=utc_now())
        result = {"registered": True, "child_id": child_id}
    elif msg_type == "layer.assignment":
        runtime.apply_assignment(data)
        result = {"assigned": True, "route_mode": runtime.state.route_mode, "parent_id": runtime.state.parent_id}
    elif msg_type == "task.assign":
        task_id = str(data.get("task_id") or request.taskId or "")

        # ✅ Check for duplicate task_id (prevent re-execution)
        if task_id:
            existing_result = runtime.task_id_store.is_processed(task_id)
            if existing_result:
                logger.info(f"Task {task_id} already processed, returning cached result")
                result = existing_result
                task = build_task(request.taskId, request.message, result)
                runtime.state.tasks[task["id"]] = task
                runtime.state.outbox.append({"task_id": task["id"], "at": utc_now(), "result": result})
                return task

        target_device_id = str(data.get("target_device_id") or (data.get("params") or {}).get("target_device_id") or "")
        own_device_id = str(runtime.state.registry_id or "")
        if runtime.state.layer == "middle" and target_device_id and own_device_id and target_device_id != own_device_id:
            result = await _relay_task_to_child(runtime, request, data)
            task = build_task(request.taskId, request.message, result)
            runtime.state.tasks[task["id"]] = task
            runtime.state.outbox.append({"task_id": task["id"], "at": utc_now(), "result": result})
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
            # ✅ 2-step separation: Return ACCEPTED immediately, execute asynchronously
            task_id = str(data.get("task_id") or request.taskId or "")
            result = {
                "acceptance_status": "ACCEPTED",
                "task_id": task_id,
            }

            # Spawn async execution and reporting
            asyncio.create_task(
                _execute_and_report_task(
                    runtime=runtime,
                    task_id=task_id,
                    command=command,
                    message_data=data,
                    request=request,
                )
            )
    else:
        if msg_type not in VALID_MESSAGE_TYPES:
            logger.warning(f"Unknown A2A message_type: {msg_type}, task_id: {request.taskId}, data: {data}")
        result = {"received": True, "message_type": msg_type}

    task = build_task(request.taskId, request.message, result)
    runtime.state.tasks[task["id"]] = task
    runtime.state.outbox.append({"task_id": task["id"], "at": utc_now(), "result": result})

    # Log A2A event for monitoring
    runtime.state.remember({
        "kind": "a2a_received",
        "at": utc_now(),
        "message_type": msg_type,
        "task_id": request.taskId,
        "result_status": result.get("status") if isinstance(result, dict) else "ok"
    })

    # ✅ Log A2A message to Registry Server (archi Ch.14.1)
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

    # A2A 이벤트를 수신 디바이스의 TOPIC 트랙에 발행 (system agent 개입 없음)
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
        if from_device_id is None and msg_type in {"event.report", "mission.result", "task.result"}:
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


async def _relay_task_to_child(runtime: AgentRuntime, request: A2ASendRequest, data: dict[str, Any]) -> dict[str, Any]:
    target_device_id = str(data.get("target_device_id") or (data.get("params") or {}).get("target_device_id") or "")
    try:
        child_device = runtime.registry_client.get_device(int(target_device_id))
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
        import json
        import urllib.request

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


async def _report_task_failure_to_system_agent(
    runtime: AgentRuntime,
    task_id: str | None,
    command: dict[str, Any],
    error: str | None,
    execution_result: dict[str, Any],
    system_agent_url: str = "http://127.0.0.1:9116/message:send",
) -> None:
    """Report task execution failure to System Agent."""
    try:
        
        # Build task.result A2A message
        result_message = A2AMessage(
            role="device",
            parts=[
                A2APart(
                    type="data",
                    data={
                        "message_type": "task.result",
                        "task_id": task_id,
                        "status": "failed",
                        "device_id": runtime.state.registry_id,
                        "agent_id": runtime.state.agent_id,
                        "command": command,
                        "error": error,
                        "execution_result": execution_result,
                        "timestamp": utc_now(),
                    }
                )
            ]
        )

        result_request = A2ASendRequest(
            message=result_message,
            taskId=task_id,
            metadata={"sender_id": runtime.state.agent_id, "sender_device_id": str(runtime.state.registry_id or "")}
        )
        
        # POST to System Agent
        import json
        import urllib.request
        data = json.dumps(result_request.model_dump()).encode("utf-8")
        req = urllib.request.Request(
            system_agent_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            logger.info(f"Task failure reported to System Agent: task_id={task_id}")
    except Exception as e:
        logger.error(f"Failed to report task failure to System Agent: {e}")


async def _report_mission_result_to_endpoint(
    runtime: AgentRuntime,
    mission_id: str,
    alert_id: str,
    step_id: str,
    task_id: str,
    command: dict[str, Any],
    execution_result: dict[str, Any],
    execution_status: str,
    endpoint: str,
) -> None:
    """Report mission execution status to an upstream A2A endpoint."""
    try:
        normalized_status = "completed" if str(execution_status).lower() == "completed" else "failed"
        source_agent_id = str(runtime.state.agent_id or "")
        source_device_id = str(runtime.state.registry_id or "")
        result_summary = str(
            execution_result.get("summary")
            or execution_result.get("output_summary")
            or execution_result.get("message")
            or f"{command.get('action')} {normalized_status}"
        )
        location = {
            "latitude": runtime.state.latitude,
            "longitude": runtime.state.longitude,
        }
        raw_refs = execution_result.get("output_refs") or execution_result.get("raw_data_ref") or execution_result.get("artifacts") or []
        if isinstance(raw_refs, dict):
            raw_refs = [raw_refs]
        if not isinstance(raw_refs, list):
            raw_refs = [raw_refs]
        payload = {
            "message_type": "mission.result",
            "mission_id": mission_id,
            "response_id": mission_id,
            "alert_id": alert_id,
            "step_id": step_id or "default",
            "task_id": task_id or "default",
            "source_agent_id": source_agent_id,
            "execution_status": normalized_status,
            "execution_log": {
                "source_agent_id": source_agent_id,
                "source_device_id": source_device_id,
                "step_id": step_id or "default",
                "task_id": task_id or "default",
                "action": command.get("action"),
                "command": command,
                "result": execution_result,
                "reported_at": utc_now(),
                "result_summary": result_summary,
                "output_refs": raw_refs,
                "failure_category": execution_result.get("failure_category") or ("UNKNOWN" if normalized_status != "completed" else None),
                "failure_message": execution_result.get("reason") or execution_result.get("error") or execution_result.get("failure_message"),
                "location": location,
                "device_state_changes": {
                    "last_telemetry": runtime.state.last_telemetry,
                    "connected": runtime.state.connected,
                },
                "agent_judgement": execution_result.get("agent_judgement") or command.get("action"),
                "payload": {
                    "response_id": mission_id,
                    "mission_id": mission_id,
                    "alert_id": alert_id,
                    "step_id": step_id or "default",
                    "task_id": task_id or "default",
                    "source_agent_id": source_agent_id,
                    "source_device_id": source_device_id,
                    "location": location,
                },
            },
        }

        result_message = A2AMessage(
            role="device",
            parts=[A2APart(type="data", data=payload)],
        )
        result_request = A2ASendRequest(
            message=result_message,
            taskId=task_id or mission_id,
            metadata={"sender_id": source_agent_id, "sender_device_id": source_device_id},
        )

        import json
        import urllib.request

        data = json.dumps(result_request.model_dump()).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5):
            logger.info(
                "Mission result reported: mission_id=%s step_id=%s task_id=%s status=%s endpoint=%s",
                mission_id,
                step_id or "default",
                task_id or "default",
                normalized_status,
                endpoint,
            )
    except Exception as e:
        logger.error(
            "Failed to report mission result: mission_id=%s step_id=%s task_id=%s endpoint=%s error=%s",
            mission_id,
            step_id,
            task_id,
            endpoint,
            e,
        )


def run(config_path: Path, host_override: str | None = None, port_override: int | None = None) -> None:
    import os

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    runtime = AgentRuntime(config_path)
    host = host_override or runtime.server.get("host") or "127.0.0.1"
    port = port_override or int(os.getenv("COWATER_AGENT_PORT") or runtime.server.get("port") or 9010)
    runtime.server["host"] = host
    runtime.server["port"] = port
    runtime.config.setdefault("server", {})["host"] = host
    runtime.config.setdefault("server", {})["port"] = port
    app = create_app(runtime)
    uvicorn.run(app, host=host, port=port, reload=False, log_level="info")
