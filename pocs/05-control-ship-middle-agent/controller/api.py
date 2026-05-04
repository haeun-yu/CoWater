from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from agent.runtime import AgentRuntime
from agent.state import utc_now
from controller.a2a import A2ASendRequest, build_task, extract_message_data
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
        asyncio.create_task(_run_simulation_loop_with_logging())

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

    @app.post("/children/heartbeat")
    async def relay_child_heartbeat(payload: dict[str, Any]) -> dict[str, Any]:
        child_id = str(payload.get("agent_id") or payload.get("device_id"))
        runtime.state.children.setdefault(child_id, {})["last_heartbeat_at"] = utc_now()
        runtime.state.children[child_id]["heartbeat"] = payload
        publisher = getattr(runtime, "moth_publisher", None)
        if publisher is not None:
            await publisher.publish_heartbeat_payload(dict(payload, relayed_by=runtime.state.registry_id))
        return {"relayed": True, "child": child_id}

    @app.get("/tasks")
    def tasks() -> dict[str, Any]:
        return {"tasks": list(runtime.state.tasks.values()), "nextPageToken": ""}

    return app


async def handle_a2a(runtime: AgentRuntime, request: A2ASendRequest) -> dict[str, Any]:
    data = extract_message_data(request.message)
    runtime.state.inbox.append({"task_id": request.taskId, "at": utc_now(), "data": data})
    msg_type = str(data.get("message_type") or data.get("type") or "task.assign")
    if msg_type == "child.register":
        child = data.get("child") or data
        child_id = str(child.get("agent_id"))
        runtime.state.children[child_id] = dict(child, agent_id=child_id, registered_at=utc_now())
        result = {"registered": True, "child_id": child_id}
    elif msg_type == "layer.assignment":
        runtime.apply_assignment(data)
        result = {"assigned": True, "route_mode": runtime.state.route_mode, "parent_id": runtime.state.parent_id}
    elif msg_type == "task.assign":
        action = str(data.get("action") or data.get("command") or "hold_position")
        params = data.get("params") or {}
        reason = data.get("reason") or f"A2A task {request.taskId}"
        response_id = str(data.get("response_id") or request.taskId or str(uuid4()))
        alert_id = str(data.get("alert_id") or "")

        runtime.state.remember(
            {
                "kind": "incident_decision",
                "at": utc_now(),
                "source": "control_ship",
                "response_id": response_id,
                "alert_id": alert_id,
                "action": action,
                "reason": reason,
                "params": params,
            }
        )

        # For mine-clearing missions, route to lower agents
        if action == "survey_depth" and params.get("mission_type") == "mine_clearance":
            route_result = await _route_to_lower_agent(
                runtime,
                "survey_depth",
                params,
                f"Mine survey command: {reason}",
                response_id=response_id,
                alert_id=alert_id,
            )
            result = {"routed": True, "action": action, "target": "lower_agents", "route_result": route_result}
            await _report_mission_result_to_system(
                runtime,
                response_id=response_id,
                alert_id=alert_id,
                execution_status="completed" if route_result.get("overall_status") != "failed" else "failed",
                execution_log={
                    "executor": runtime.state.agent_id,
                    "route_result": route_result,
                    "note": "Control Ship routed mission to lower agents",
                },
            )
        else:
            command = {
                "action": action,
                "params": params,
                "reason": reason,
            }
            result = runtime.apply_command(command)
            await _report_mission_result_to_system(
                runtime,
                response_id=response_id,
                alert_id=alert_id,
                execution_status="completed",
                execution_log={"executor": runtime.state.agent_id, "result": result},
            )
    elif msg_type == "mission.result":
        result = {"received": True, "message_type": msg_type}
        await _report_mission_result_to_system(
            runtime,
            response_id=str(data.get("response_id") or request.taskId or str(uuid4())),
            alert_id=str(data.get("alert_id") or ""),
            execution_status=str(data.get("execution_status") or "completed"),
            execution_log={
                "forwarded_by": runtime.state.agent_id,
                "source_agent_id": data.get("source_agent_id"),
                "payload": data,
            },
        )
    else:
        result = {"received": True, "message_type": msg_type}
    task = build_task(request.taskId, request.message, result)
    runtime.state.tasks[task["id"]] = task
    runtime.state.outbox.append({"task_id": task["id"], "at": utc_now(), "result": result})
    return task


async def _route_to_lower_agent(
    runtime: AgentRuntime,
    action: str,
    params: dict[str, Any],
    reason: str,
    *,
    response_id: str,
    alert_id: str,
) -> dict[str, Any]:
    """Route mission to lower agents (AUV, ROV) based on their capabilities"""
    logger = logging.getLogger(__name__)

    # Discover lower agents from registry
    try:
        registry_url = runtime.config.get("registry", {}).get("url", "http://127.0.0.1:8280").rstrip("/")
        req = urllib.request.Request(f"{registry_url}/devices", headers={"Accept": "application/json"}, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            all_devices = json.loads(resp.read() or b"[]")
    except Exception as e:
        logger.warning(f"Failed to fetch device list for routing: {e}")
        return {"overall_status": "failed", "error": str(e), "children": []}

    # Find suitable lower agents
    auv_agent = None
    rov_agent = None
    for device in all_devices:
        try:
            if device.get("layer") == "lower" and device.get("connected"):
                device_type = device.get("device_type", "").lower()
                agent_info = device.get("agent")
                if not isinstance(agent_info, dict):
                    agent_info = {}
                endpoint = agent_info.get("endpoint")

                if "auv" in device_type and endpoint and not auv_agent:
                    auv_agent = {"device_id": device["id"], "endpoint": endpoint, "name": device.get("name")}
                elif "rov" in device_type and endpoint and not rov_agent:
                    rov_agent = {"device_id": device["id"], "endpoint": endpoint, "name": device.get("name")}
        except Exception as e:
            logger.debug(f"Error processing device {device.get('id')}: {e}")
            continue

    child_results: list[dict[str, Any]] = []

    routed_params = dict(params)
    routed_params["report_to_endpoint"] = runtime.base_url()

    # Send survey_depth to AUV
    if auv_agent and action == "survey_depth":
        try:
            result = await _send_a2a_task(
                auv_agent["endpoint"],
                {
                    "message_type": "task.assign",
                    "action": "survey_depth",
                    "params": routed_params,
                    "reason": reason,
                    "alert_id": alert_id,
                    "response_id": response_id,
                },
                task_id=response_id,
            )
            logger.info(f"Routed survey_depth to AUV {auv_agent['device_id']}")
            child_results.append({"device_id": auv_agent["device_id"], "status": "completed", "result": result})
        except Exception as e:
            logger.warning(f"Failed to route to AUV: {e}")
            child_results.append({"device_id": auv_agent["device_id"], "status": "failed", "error": str(e)})

    # Send remove_mine to ROV
    if rov_agent and action == "survey_depth":  # Both operations for mine clearing
        try:
            result = await _send_a2a_task(
                rov_agent["endpoint"],
                {
                    "message_type": "task.assign",
                    "action": "remove_mine",
                    "params": routed_params,
                    "reason": reason,
                    "alert_id": alert_id,
                    "response_id": response_id,
                },
                task_id=response_id,
            )
            logger.info(f"Routed remove_mine to ROV {rov_agent['device_id']}")
            child_results.append({"device_id": rov_agent["device_id"], "status": "completed", "result": result})
        except Exception as e:
            logger.warning(f"Failed to route to ROV: {e}")
            child_results.append({"device_id": rov_agent["device_id"], "status": "failed", "error": str(e)})

    overall = "completed"
    if child_results and any(c.get("status") == "failed" for c in child_results):
        overall = "failed"
    return {"overall_status": overall, "children": child_results}


async def _send_a2a_task(endpoint: str, data_payload: dict[str, Any], task_id: str) -> dict[str, Any]:
    message = {
        "jsonrpc": "2.0",
        "method": "message/send",
        "id": str(uuid4()),
        "params": {
            "message": {"role": "user", "parts": [{"type": "data", "data": data_payload}]},
            "taskId": task_id,
            "metadata": {},
        },
    }
    data = json.dumps(message).encode("utf-8")
    req = urllib.request.Request(endpoint, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read() or b"{}")


async def _report_mission_result_to_system(
    runtime: AgentRuntime,
    *,
    response_id: str,
    alert_id: str,
    execution_status: str,
    execution_log: dict[str, Any],
) -> None:
    registry_url = runtime.config.get("registry", {}).get("url", "http://127.0.0.1:8280").rstrip("/")
    try:
        req = urllib.request.Request(f"{registry_url}/devices", headers={"Accept": "application/json"}, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            devices = json.loads(resp.read() or b"[]")
    except Exception as e:
        logger.warning(f"Failed to fetch devices for mission.result report: {e}")
        return

    system_endpoint = None
    for d in devices:
        if d.get("layer") == "system" and d.get("connected"):
            agent_info = d.get("agent") or {}
            if isinstance(agent_info, dict) and agent_info.get("endpoint"):
                system_endpoint = agent_info["endpoint"]
                break
    if not system_endpoint:
        logger.warning("No connected system endpoint for mission.result")
        return

    payload = {
        "message_type": "mission.result",
        "response_id": response_id,
        "alert_id": alert_id,
        "execution_status": execution_status,
        "source_agent_id": runtime.state.agent_id,
        "execution_log": execution_log,
    }
    try:
        await _send_a2a_task(system_endpoint, payload, response_id)
        runtime.state.remember(
            {
                "kind": "mission_result_reported",
                "at": utc_now(),
                "response_id": response_id,
                "alert_id": alert_id,
                "status": execution_status,
                "system_endpoint": system_endpoint,
            }
        )
    except Exception as e:
        logger.warning(f"Failed to report mission.result to system: {e}")


def run(default_config_path: Path) -> None:
    import argparse
    import os

    # Python logging 설정 (stdout으로 로그 출력)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()
    config_path = (args.config or default_config_path).resolve()
    runtime = AgentRuntime(config_path)
    host = args.host or runtime.server.get("host") or "127.0.0.1"
    port = args.port or int(os.getenv("COWATER_AGENT_PORT") or runtime.server.get("port") or 9010)
    runtime.server["host"] = host
    runtime.server["port"] = port
    runtime.config.setdefault("server", {})["host"] = host
    runtime.config.setdefault("server", {})["port"] = port
    app = create_app(runtime)
    uvicorn.run(app, host=host, port=port, reload=False, log_level="info")
