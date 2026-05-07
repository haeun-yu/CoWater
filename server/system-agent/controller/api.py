from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from agent.runtime import AgentRuntime
from agent.state import utc_now
from controller.a2a import A2ASendRequest, build_task, extract_message_data
from controller.commands import CommandRequest


def create_app(runtime: AgentRuntime) -> FastAPI:
    app = FastAPI(title=f"CoWater {runtime.state.role}", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=runtime.config.get("cors", {}).get("allow_origins", ["*"]),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def startup() -> None:
        try:
            runtime.register()
        except Exception as exc:
            runtime.state.remember({"kind": "registration_error", "at": utc_now(), "error": str(exc)})
            if runtime.registry_client.required:
                raise
        app.state.simulation_task = asyncio.create_task(runtime.simulation_loop())

    @app.on_event("shutdown")
    async def shutdown() -> None:
        task = getattr(app.state, "simulation_task", None)
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

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
        return await runtime.handle_command_with_llm(request.model_dump())

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

    @app.post("/device-recovery")
    async def handle_device_recovery(payload: dict[str, Any]) -> dict[str, Any]:
        """Device Agent 복구 후 로컬 상태 보고 (Ch.16)"""
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

    @app.post("/device-roles/recommend")
    def recommend_device_roles(body: dict[str, Any] | None = Body(None)) -> dict[str, Any]:
        body = body or {}
        goal = str(body.get("goal") or "")
        return runtime.recommend_device_roles(goal)

    @app.post("/device-roles/apply")
    def apply_device_role(body: dict[str, Any] | None = Body(None)) -> dict[str, Any]:
        body = body or {}
        return runtime.assign_device_role(body, decided_by=str(body.get("decided_by") or "user"))

    @app.post("/operation-plans/recommend")
    def recommend_operation_plan(body: dict[str, Any] | None = Body(None)) -> dict[str, Any]:
        body = body or {}
        return runtime.recommend_operation_plan(body)

    @app.post("/operation-plans")
    def create_operation_plan(body: dict[str, Any] | None = Body(None)) -> dict[str, Any]:
        body = body or {}
        plan = runtime.recommend_operation_plan(body)
        merged = {**plan, **body}
        return runtime.registry_client.create_operation_plan(merged)

    @app.post("/operation-plans/{operation_plan_id}/activate")
    def activate_operation_plan(operation_plan_id: str, body: dict[str, Any] | None = Body(None)) -> dict[str, Any]:
        body = body or {}
        activated_by = str(body.get("activated_by") or body.get("decided_by") or "user")
        return runtime.activate_operation_plan(operation_plan_id, activated_by=activated_by)

    @app.post("/mission-proposals/generate")
    def generate_mission_proposal(body: dict[str, Any] | None = Body(None)) -> dict[str, Any]:
        body = body or {}
        return runtime.generate_mission_proposal(body)

    @app.post("/approvals/{approval_id}/decision")
    async def approval_decision(approval_id: str, body: dict[str, Any] | None = Body(None)) -> dict[str, Any]:
        body = body or {}
        approved = bool(body.get("approved"))
        decided_by = str(body.get("decided_by") or "user")
        notes = body.get("notes")
        return await runtime.decide_approval_flow(approval_id, approved, decided_by=decided_by, notes=notes)

    @app.get("/overview")
    def overview() -> dict[str, Any]:
        return {
            "devices": runtime.registry_client.list_devices(),
            "device_roles": runtime.registry_client.list_device_roles(),
            "operation_plans": runtime.registry_client.list_operation_plans(),
            "insights": runtime.registry_client.list_insights(),
            "approvals": runtime.registry_client.list_approvals(),
            "mission_proposals": runtime.registry_client.list_mission_proposals(),
            "missions": runtime.registry_client.list_missions(),
        }

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
    elif msg_type == "event.report":
        result = runtime.handle_event_report(data)
    elif msg_type == "mission.result":
        result = await runtime.handle_mission_result(data)
    elif msg_type == "task.result":
        # Device reports task execution result (success or failure)
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


def run(default_config_path: Path) -> None:
    import argparse
    import os

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
