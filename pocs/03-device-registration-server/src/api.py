from __future__ import annotations

import argparse
from typing import Any, List

from fastapi import FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from src.core.config import APP_SETTINGS
from src.core.models import (
    AlertAckRequest,
    AlertIngestRequest,
    CORE_ACTIONS,
    DeviceAgentRegistrationRequest,
    DeviceRegistrationRequest,
    DeviceRenameRequest,
    MainVideoTrackRequest,
    ResponseIngestRequest,
    TRACK_TYPES,
)
from src.registry.alert_registry import AlertRegistry
from src.registry.device_registry import DeviceRegistry


registry = DeviceRegistry(
    secret_key=APP_SETTINGS["secret_key"],
    host=APP_SETTINGS["server"]["host"],
    port=APP_SETTINGS["server"]["port"],
    ping_endpoint=APP_SETTINGS["server"]["ping_endpoint"],
    agent_scheme=APP_SETTINGS["agent"]["scheme"],
    agent_host=APP_SETTINGS["agent"]["host"],
    agent_port=APP_SETTINGS["agent"]["port"],
    agent_path_prefix=APP_SETTINGS["agent"]["path_prefix"],
    agent_command_scheme=APP_SETTINGS["agent"]["command_scheme"],
    agent_command_path_prefix=APP_SETTINGS["agent"]["command_path_prefix"],
)
alert_registry = AlertRegistry()

app = FastAPI(title="CoWater Device Registration Server", version="1.0.0")
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
        "server": registry.server_dict(),
        "agent": registry.agent_dict(),
        "track_types": list(TRACK_TYPES.__args__),
        "core_actions": list(CORE_ACTIONS.__args__),
        "alerts": {
            "ingest": "/alerts/ingest",
            "list": "/alerts",
            "ack": "/alerts/{alert_id}/ack",
            "responses": "/responses",
        },
        "config_path": APP_SETTINGS["config_path"],
        "cors": APP_SETTINGS["cors"],
    }


@app.post("/devices", status_code=status.HTTP_201_CREATED)
def register_device(request: DeviceRegistrationRequest) -> dict[str, Any]:
    try:
        device = registry.register(request)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return device.to_dict()


@app.get("/devices")
def list_devices() -> List[dict[str, Any]]:
    return [device.to_dict() for device in registry.list_devices()]


@app.get("/devices/{device_id}")
def get_device(device_id: int) -> dict[str, Any]:
    try:
        return registry.get_device(device_id).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="device not found") from exc


@app.patch("/devices/{device_id}")
def rename_device(device_id: int, request: DeviceRenameRequest) -> Response:
    try:
        registry.rename(device_id, request.name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="device not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.patch("/devices/{device_id}/main-video-track")
def update_main_video_track(device_id: int, request: MainVideoTrackRequest) -> Response:
    try:
        registry.update_main_video_track(device_id, request.name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="device not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.delete("/devices/{device_id}")
def delete_device(device_id: int) -> Response:
    try:
        registry.delete(device_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="device not found") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.put("/devices/{device_id}/agent")
def upsert_device_agent(device_id: int, request: DeviceAgentRegistrationRequest) -> dict[str, Any]:
    try:
        device = registry.attach_agent(device_id, request)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="device not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return device.to_dict()


@app.delete("/devices/{device_id}/agent")
def detach_device_agent(device_id: int, secretKey: str) -> dict[str, Any]:
    try:
        device = registry.detach_agent(device_id, secretKey)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="device not found") from exc
    return device.to_dict()


@app.post("/alerts/ingest", status_code=status.HTTP_201_CREATED)
def ingest_alert(request: AlertIngestRequest) -> dict[str, Any]:
    alert = alert_registry.ingest_alert(request)
    return alert.to_dict()


@app.get("/alerts")
def list_alerts() -> list[dict[str, Any]]:
    return [alert.to_dict() for alert in alert_registry.list_alerts()]


@app.get("/alerts/{alert_id}")
def get_alert(alert_id: str) -> dict[str, Any]:
    try:
        return alert_registry.get_alert(alert_id).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="alert not found") from exc


@app.post("/alerts/{alert_id}/ack")
def acknowledge_alert(alert_id: str, request: AlertAckRequest) -> dict[str, Any]:
    try:
        return alert_registry.acknowledge_alert(alert_id, approved=request.approved, notes=request.notes).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="alert not found") from exc


@app.post("/responses/ingest", status_code=status.HTTP_201_CREATED)
def ingest_response(request: ResponseIngestRequest) -> dict[str, Any]:
    response = alert_registry.ingest_response(request)
    return response.to_dict()


@app.get("/responses")
def list_responses() -> list[dict[str, Any]]:
    return [response.to_dict() for response in alert_registry.list_responses()]


@app.get("/responses/{response_id}")
def get_response(response_id: str) -> dict[str, Any]:
    try:
        return alert_registry.get_response(response_id).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="response not found") from exc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", help="Override bind host from config/env")
    parser.add_argument("--port", type=int, help="Override bind port from config/env")
    args = parser.parse_args()
    bind_host = args.host or APP_SETTINGS["server"]["host"]
    bind_port = args.port or APP_SETTINGS["server"]["port"]
    uvicorn.run(app, host=bind_host, port=bind_port, reload=False, log_level="info")


if __name__ == "__main__":
    main()

