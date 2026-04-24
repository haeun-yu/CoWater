from __future__ import annotations

# 02 디바이스 에이전트 허브의 FastAPI 애플리케이션과 웹소켓 흐름을 정의한다.

import asyncio
import argparse
from typing import Any, Optional
from datetime import datetime, timezone

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .models import DeviceCommandRequest
from .profiles import CONFIG_PATH, load_runtime_config
from .registry import AgentHub
from .registry_client import RegistryClient


APP_SETTINGS = load_runtime_config(CONFIG_PATH)
_KEEPALIVE_INTERVAL = 25.0
_KEEPALIVE_PAYLOAD = b"ping"
registry_client = RegistryClient(
    APP_SETTINGS["registry"]["url"],
    APP_SETTINGS["registry"]["secret_key"],
)
hub = AgentHub(
    APP_SETTINGS["profiles"],
    registry_client=registry_client,
    public_host=APP_SETTINGS["server"]["host"],
    public_port=APP_SETTINGS["server"]["port"],
)

app = FastAPI(title="CoWater Device Agent Hub", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=APP_SETTINGS["cors"]["allow_origins"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/meta")
def meta() -> dict[str, Any]:
    return {
        "server": APP_SETTINGS["server"],
        "profiles": APP_SETTINGS["profiles"],
        "config_path": APP_SETTINGS["config_path"],
        "cors": APP_SETTINGS["cors"],
        "registry": APP_SETTINGS["registry"],
        "agent_types": ["usv", "auv", "rov"],
        "agent_modes": ["static", "dynamic"],
        "llm_optional": True,
        "runtime_note": "Each device type has its own Agent class; Agents can be static rule-based or dynamic reasoning-based; LLM is optional, not required.",
    }


def _build_agent_card() -> dict[str, Any]:
    base_url = f"http://{APP_SETTINGS['server']['host']}:{APP_SETTINGS['server']['port']}"
    return {
        "name": "cowater-device-agent-hub",
        "displayName": "CoWater Device Agent Hub",
        "description": "Per-device Agent hub for USV, AUV, and ROV telemetry sessions. Accepts WebSocket streams and issues rule-based recommendations.",
        "url": base_url,
        "version": "2.0.0",
        "protocolVersion": "1.0.0",
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
            "extendedAgentCard": False,
        },
        "defaultInputModes": ["application/json"],
        "defaultOutputModes": ["application/json"],
        "skills": [
            {
                "id": "stream_ingest",
                "name": "Stream Ingest",
                "description": "Accept device telemetry over WebSocket and extract position, motion, and sensor data.",
            },
            {
                "id": "rule_recommendation",
                "name": "Rule Recommendation",
                "description": "Produce scoped action recommendations from device state without requiring an LLM.",
            },
            {
                "id": "command_relay",
                "name": "Command Relay",
                "description": "Accept operator commands and forward them to the connected device session.",
            },
        ],
    }


@app.get("/.well-known/agent-card.json")
def agent_card() -> dict[str, Any]:
    return _build_agent_card()


@app.get("/.well-known/agent.json")
def agent_card_legacy() -> dict[str, Any]:
    return _build_agent_card()


@app.get("/agents")
async def list_agents() -> list[dict[str, Any]]:
    return [session.to_dict() for session in hub.list_sessions()]


@app.get("/agents/{token}")
async def get_agent(token: str) -> dict[str, Any]:
    try:
        return hub.get_session(token).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="agent not found") from exc


@app.post("/agents/{token}/command")
async def send_agent_command(token: str, request: DeviceCommandRequest) -> dict[str, Any]:
    command = request.model_dump()
    delivered = await hub.send_command(token, command)
    if not delivered:
        raise HTTPException(status_code=409, detail="agent is not connected")
    return {"status": "sent", "token": token, "command": command}


@app.websocket("/agents/{token}")
async def device_agent_socket(token: str, websocket: WebSocket) -> None:
    await websocket.accept()
    session = hub.attach_websocket(token, websocket)
    await websocket.send_json(
        {
            "kind": "hello",
            "agent": "cowater-device-agent-hub",
            "token": token,
            "agent_modes": ["static", "dynamic"],
            "llm_optional": True,
            "profiles": list(APP_SETTINGS["profiles"].keys()),
        }
    )

    async def keepalive_loop() -> None:
        try:
            while True:
                await asyncio.sleep(_KEEPALIVE_INTERVAL)
                if session.websocket is None:
                    return
                await websocket.send_bytes(_KEEPALIVE_PAYLOAD)
        except asyncio.CancelledError:
            return
        except Exception:
            return

    keepalive_task = asyncio.create_task(keepalive_loop())
    try:
        while True:
            message = await websocket.receive_json()
            recommendations = await hub.ingest_message(token, message)
            if recommendations:
                await websocket.send_json(
                    {
                        "kind": "recommendation",
                        "token": token,
                        "recommendations": recommendations,
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
    except WebSocketDisconnect:
        pass
    finally:
        keepalive_task.cancel()
        try:
            await keepalive_task
        except BaseException:
            pass
        await hub.detach_registry(token)
        hub.detach_websocket(token)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", help="Override bind host from config/env")
    parser.add_argument("--port", type=int, help="Override bind port from config/env")
    args = parser.parse_args()
    bind_host = args.host or APP_SETTINGS["server"]["host"]
    bind_port = args.port or APP_SETTINGS["server"]["port"]
    uvicorn.run(
        "src.app:app",
        host=bind_host,
        port=bind_port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
