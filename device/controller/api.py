from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from application.bootstrap import build_device_runtime
from agent.runtime import AgentRuntime
from agent.message_router import handle_a2a
from agent.state import utc_now
from controller.a2a import A2ASendRequest
from controller.commands import CommandRequest

logger = logging.getLogger(__name__)


def create_app(runtime: AgentRuntime) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            runtime.register()
        except Exception as exc:
            runtime.state.remember({"kind": "registration_error", "at": utc_now(), "error": str(exc)})
            if runtime.registry_client.required:
                raise
        app.state.simulation_task = asyncio.create_task(_run_simulation_loop_with_logging(runtime))
        try:
            yield
        finally:
            task = getattr(app.state, "simulation_task", None)
            if task is not None:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await runtime.stop()

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
    async def command(token: str, request: CommandRequest) -> dict[str, Any]:
        if runtime.state.token and token != runtime.state.token:
            raise HTTPException(status_code=403, detail="token mismatch")
        # P5 원칙: Device Agent가 최종 판단 (입력 검증)
        command_dict = request.model_dump()
        action = command_dict.get("action", "")
        available_actions = runtime.skills.list_actions()
        if action and action not in available_actions:
            raise HTTPException(status_code=400, detail=f"Unknown action: {action}. Available: {available_actions}")
        return runtime.apply_command(command_dict)

    @app.post("/children/register")
    async def register_child(child: dict[str, Any]) -> dict[str, Any]:
        if runtime.state.layer != "middle":
            raise HTTPException(status_code=404, detail="child management unavailable")
        record = runtime.register_child(child)
        return {"registered": True, "child": record}

    @app.get("/children")
    def children() -> dict[str, Any]:
        if runtime.state.layer != "middle":
            raise HTTPException(status_code=404, detail="child management unavailable")
        return {"children": runtime.list_children()}

    @app.post("/children/healthcheck")
    async def relay_child_healthcheck(payload: dict[str, Any]) -> dict[str, Any]:
        if runtime.state.layer != "middle":
            raise HTTPException(status_code=404, detail="child management unavailable")
        child_state = runtime.relay_child_healthcheck(payload)
        publisher = getattr(runtime, "moth_publisher", None)
        if publisher is not None:
            await publisher.publish_healthcheck_payload(dict(payload, relayed_by=runtime.state.registry_id))
        return {"relayed": True, "child": child_state.get("agent_id")}

    @app.get("/tasks")
    def tasks() -> dict[str, Any]:
        return {"tasks": runtime.list_tasks(), "nextPageToken": ""}

    return app


async def _run_simulation_loop_with_logging(runtime: AgentRuntime) -> None:
    """Wrapper to catch and log simulation_loop exceptions"""
    try:
        logger.info("Starting simulation loop...")
        await runtime.simulation_loop()
    except Exception as e:
        logger.error(f"Simulation loop failed: {e}", exc_info=True)
        raise


def run(config_path: Path, host_override: str | None = None, port_override: int | None = None) -> None:
    import os

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    runtime = build_device_runtime(config_path)
    host = host_override or runtime.server.get("host") or "127.0.0.1"
    port = port_override or int(os.getenv("COWATER_AGENT_PORT") or runtime.server.get("port") or 9010)
    runtime.server["host"] = host
    runtime.server["port"] = port
    runtime.config.setdefault("server", {})["host"] = host
    runtime.config.setdefault("server", {})["port"] = port
    app = create_app(runtime)
    uvicorn.run(app, host=host, port=port, reload=False, log_level="info")
