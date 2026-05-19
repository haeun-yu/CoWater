from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from agent.base_runtime import BaseAgentRuntime
from agent.state import utc_now
from controller.a2a import A2ASendRequest, build_task, extract_message_data
from controller.commands import CommandRequest


def create_app(runtime: BaseAgentRuntime) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            runtime.register()
        except Exception as exc:
            runtime.state.remember({"kind": "registration_error", "at": utc_now(), "error": str(exc)})
            if runtime.registry_client.required:
                raise
        app.state.simulation_task = asyncio.create_task(runtime.simulation_loop())
        try:
            yield
        finally:
            task = getattr(app.state, "simulation_task", None)
            if task is not None:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            runtime.runtime_store.close()

    app = FastAPI(title=f"CoWater {runtime.state.role}", version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=runtime.config.get("cors", {}).get("allow_origins", ["*"]),
        allow_methods=["*"],
        allow_headers=["*"],
    )

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
    async def command(
        token: str,
        request: CommandRequest,
        async_mode: bool = Query(default=False),
    ) -> dict[str, Any]:
        if runtime.state.token and token != runtime.state.token:
            raise HTTPException(status_code=403, detail="token mismatch")
        if async_mode:
            return runtime.start_async_command(request.model_dump(), requested_by="user")
        return await runtime.handle_command_with_llm(request.model_dump())

    @app.get("/commands/{request_id}")
    def get_command_status(request_id: str) -> dict[str, Any]:
        status = runtime.get_async_command(request_id)
        if status is None:
            raise HTTPException(status_code=404, detail="command request not found")
        return status

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
        device_id = str(payload.get("device_id") or child_id)
        now = utc_now()
        child_state = runtime.state.children.get(child_id, {})
        child_state["last_healthcheck_at"] = now
        child_state["healthcheck"] = payload
        runtime.state.children[child_id] = child_state
        try:
            device_updates = {
                "id": device_id,
                "connectivity_status": payload.get("status", "offline").lower(),
                "last_seen_at": now,
            }
            if "battery_percent" in payload:
                device_updates["battery_percent"] = payload.get("battery_percent")
            if "location" in payload:
                location = payload.get("location")
                if isinstance(location, dict):
                    device_updates["latitude"] = location.get("lat")
                    device_updates["longitude"] = location.get("lon")
            runtime.registry_client.update_device(device_id, device_updates)
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug(f"Failed to update device {device_id}: {e}")
        return {"relayed": True, "child": child_id}

    @app.post("/device-recovery")
    async def handle_device_recovery(payload: dict[str, Any], request: Request) -> dict[str, Any]:
        internal_token = request.headers.get("x_cowater_internal", "")
        if not internal_token or internal_token != runtime.config.get("internal_auth_token"):
            raise HTTPException(status_code=401, detail="Missing or invalid x_cowater_internal header")
        device_id = str(payload.get("device_id") or "")
        if not device_id:
            raise HTTPException(status_code=400, detail="device_id required")
        await runtime.handle_device_recovery_report(device_id, payload)
        return {"processed": True, "device_id": device_id}

    @app.get("/tasks")
    def tasks() -> dict[str, Any]:
        return {"tasks": list(runtime.state.tasks.values()), "nextPageToken": ""}

    @app.get("/manual-interventions")
    def manual_interventions() -> dict[str, Any]:
        items = runtime.list_manual_interventions()
        return {"items": items, "count": len(items)}

    @app.get("/manual-interventions/{mission_id}")
    def manual_intervention(mission_id: str) -> dict[str, Any]:
        for item in runtime.list_manual_interventions():
            if str(item.get("mission_id") or "") == mission_id:
                return item
        raise HTTPException(status_code=404, detail="manual intervention not found")

    @app.post("/execute")
    async def execute(body: dict[str, Any] | None = Body(None)) -> dict[str, Any]:
        return await runtime.execute_role_request(body or {})

    @app.post("/mission-proposals/generate")
    async def generate_mission_proposal(body: dict[str, Any] | None = Body(None)) -> dict[str, Any]:
        import traceback
        body = body or {}
        try:
            return await runtime.generate_multiple_mission_proposals(body)
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(
                status_code=500,
                detail=f"Error in generate_multiple_mission_proposals: {type(e).__name__}: {str(e)}"
            )

    @app.post("/approvals/{approval_id}/decision")
    async def approval_decision(approval_id: str, body: dict[str, Any] | None = Body(None)) -> dict[str, Any]:
        body = body or {}
        approved = bool(body.get("approved"))
        decided_by = str(body.get("decided_by") or "user")
        notes = body.get("notes")
        return await runtime.decide_approval_flow(approval_id, approved, decided_by=decided_by, notes=notes)

    @app.post("/agent-connections")
    def create_agent_connection(body: dict[str, Any] | None = Body(None)) -> dict[str, Any]:
        return runtime.registry_client.create_agent_connection(body or {})

    @app.get("/agent-connections")
    def list_agent_connections(
        limit: int = Query(default=100, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
    ) -> list[dict[str, Any]]:
        return runtime.registry_client.list_agent_connections(limit=limit, offset=offset)

    @app.get("/agent-connections/{connection_id}")
    def get_agent_connection(connection_id: str) -> dict[str, Any]:
        return runtime.registry_client.get_agent_connection(connection_id)

    @app.put("/agent-connections/{connection_id}")
    def update_agent_connection(connection_id: str, body: dict[str, Any] | None = Body(None)) -> dict[str, Any]:
        return runtime.registry_client.update_agent_connection(connection_id, body or {})

    @app.delete("/agent-connections/{connection_id}")
    def delete_agent_connection(connection_id: str) -> dict[str, Any]:
        return runtime.registry_client.delete_agent_connection(connection_id)

    return app


async def handle_a2a(runtime: BaseAgentRuntime, request: A2ASendRequest) -> dict[str, Any]:
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
    elif msg_type == "task.result":
        result = await runtime.handle_task_result(data)
    elif msg_type == "task.assign":
        command = {
            "action": str(data.get("action") or data.get("command") or "hold_position"),
            "params": data.get("params") or {},
            "reason": data.get("reason") or f"A2A task {request.taskId}",
        }
        result = runtime.apply_command(command)
    else:
        result = {"received": True, "message_type": msg_type}
    task = build_task(request.taskId, request.message, result)
    runtime.state.tasks[task["id"]] = task
    runtime.state.outbox.append({"task_id": task["id"], "at": utc_now(), "result": result})
    return task


def run(default_config_path: Path, runtime: BaseAgentRuntime | None = None, argv: list[str] | None = None) -> None:
    import argparse
    import os

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args(argv)
    config_path = (args.config or default_config_path).resolve()
    host = args.host or runtime.server.get("host") or "127.0.0.1"
    port = args.port or int(os.getenv("COWATER_AGENT_PORT") or runtime.server.get("port") or 9010)
    runtime.server["host"] = host
    runtime.server["port"] = port
    runtime.config.setdefault("server", {})["host"] = host
    runtime.config.setdefault("server", {})["port"] = port
    app = create_app(runtime)
    uvicorn.run(app, host=host, port=port, reload=False, log_level="info")
