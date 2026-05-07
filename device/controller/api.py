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
        command = {
            "action": str(data.get("action") or data.get("command") or "hold_position"),
            "params": data.get("params") or {},
            "reason": data.get("reason") or f"A2A task {request.taskId}",
        }
        result = runtime.apply_command(command)

        # Report mission result back to the upstream endpoint when correlation ids are present.
        response_id = str(data.get("response_id") or "")
        if response_id:
            report_base = str((command.get("params") or {}).get("report_to_endpoint") or "").strip()
            if not report_base:
                report_base = str(runtime.config.get("system_agent", {}).get("url") or "http://127.0.0.1:9116").strip()
            report_endpoint = report_base if report_base.endswith("/message:send") else f"{report_base.rstrip('/')}/message:send"
            execution_status = "failed"
            if isinstance(result, dict) and str(result.get("status") or "").lower() in {"ok", "success", "completed"}:
                execution_status = "completed"

            asyncio.create_task(
                _report_mission_result_to_endpoint(
                    runtime=runtime,
                    response_id=response_id,
                    alert_id=str(data.get("alert_id") or ""),
                    step_id=str(data.get("step_id") or ""),
                    task_id=str(data.get("task_id") or request.taskId or ""),
                    command=command,
                    execution_result=result if isinstance(result, dict) else {"status": "unknown", "raw": result},
                    execution_status=execution_status,
                    endpoint=report_endpoint,
                )
            )

        # If task execution failed, report to System Agent asynchronously
        if isinstance(result, dict) and result.get('status') == 'failed':
            # config에서 system agent URL 조회
            system_agent_url = (
                runtime.config.get("system_agent", {}).get("url")
                or "http://127.0.0.1:9116"
            )
            asyncio.create_task(
                _report_task_failure_to_system_agent(
                    runtime=runtime,
                    task_id=request.taskId,
                    command=command,
                    error=result.get('error'),
                    execution_result=result,
                    system_agent_url=f"{system_agent_url.rstrip('/')}/message:send",
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
    response_id: str,
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
        payload = {
            "message_type": "mission.result",
            "response_id": response_id,
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
                "payload": {
                    "response_id": response_id,
                    "alert_id": alert_id,
                    "step_id": step_id or "default",
                    "task_id": task_id or "default",
                    "source_agent_id": source_agent_id,
                },
            },
        }

        result_message = A2AMessage(
            role="device",
            parts=[A2APart(type="data", data=payload)],
        )
        result_request = A2ASendRequest(
            message=result_message,
            taskId=task_id or response_id,
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
                "Mission result reported: response_id=%s step_id=%s task_id=%s status=%s endpoint=%s",
                response_id,
                step_id or "default",
                task_id or "default",
                normalized_status,
                endpoint,
            )
    except Exception as e:
        logger.error(
            "Failed to report mission result: response_id=%s step_id=%s task_id=%s endpoint=%s error=%s",
            response_id,
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
