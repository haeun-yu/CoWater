from __future__ import annotations

import argparse
import asyncio
import logging
import os
from typing import Any, List
from uuid import uuid4

from fastapi import Body, FastAPI, HTTPException, Query, Response, status, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from src.core.config import APP_SETTINGS
from src.core.models import (
    AlertAckRequest,
    AlertIngestRequest,
    ALERT_SEVERITIES,
    AUVSubmersionRequest,
    CORE_ACTIONS,
    DEVICE_TYPES,
    DeviceAgentRegistrationRequest,
    DeviceConnectivityStateRequest,
    DeviceRegistrationRequest,
    DeviceRenameRequest,
    EventIngestRequest,
    LocationUpdate,
    MainVideoTrackRequest,
    ResponseIngestRequest,
    TRACK_TYPES,
)
from src.core.pubsub import get_pubsub_manager
from src.registry.alert_registry import AlertRegistry
from src.registry.device_registry import DeviceRegistry
from src.registry.event_registry import EventRegistry
from src.registry.mission_registry import MissionRegistry
from src.transport.moth_subscriber import MothHealthcheckSubscriber


logger = logging.getLogger(__name__)

# Determine storage backend: 'sqlite' or 'memory'
STORAGE_TYPE = os.getenv("COWATER_STORAGE", "memory").lower()
USE_SQLITE = STORAGE_TYPE == "sqlite"

logger.info(f"🔧 Storage backend: {STORAGE_TYPE}")


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
    healthcheck_interval_seconds=APP_SETTINGS["healthcheck"]["interval_seconds"],
    healthcheck_timeout_seconds=APP_SETTINGS["healthcheck"]["timeout_seconds"],
    healthcheck_topic_template=APP_SETTINGS["moth"]["healthcheck_topic_template"],
    telemetry_topic_template=APP_SETTINGS["moth"]["telemetry_topic_template"],
)
alert_registry = AlertRegistry()
event_registry = EventRegistry()
mission_registry = MissionRegistry(use_db=USE_SQLITE)

moth_subscriber = MothHealthcheckSubscriber(
    registry=registry,
    moth_server_url=APP_SETTINGS["moth"]["server_url"],
)

app = FastAPI(title="CoWater Device Registration Server", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=APP_SETTINGS["cors"]["allow_origins"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event() -> None:
    """서버 시작 시 Moth 구독 시작"""
    try:
        await moth_subscriber.start()
    except Exception as exc:
        logger.warning("Moth 구독 시작 실패 - healthcheck monitor만으로 계속 기동합니다: %s", exc)
    asyncio.create_task(registry.healthcheck_monitor.start())


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """서버 종료 시 Moth 구독 중지"""
    await registry.healthcheck_monitor.stop()
    await moth_subscriber.stop()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/meta")
def meta() -> dict[str, Any]:
    return {
        "server": registry.server_dict(),
        "agent": registry.agent_dict(),
        "track_types": list(TRACK_TYPES.__args__),
        "device_types": list(DEVICE_TYPES.__args__),
        "core_actions": list(CORE_ACTIONS.__args__),
        "alert_severities": list(ALERT_SEVERITIES.__args__),
        "alerts": {
            "ingest": "/alerts/ingest",
            "list": "/alerts",
            "ack": "/alerts/{alert_id}/ack",
            "responses": "/responses",
        },
        "events": {
            "ingest": "/events/ingest",
            "list": "/events",
            "detail": "/events/{event_id}",
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
    return device.to_device_registration_dict()


@app.get("/devices/{device_id}/assignment")
def get_device_assignment(device_id: str) -> dict[str, Any]:
    try:
        return registry.assignment_for(device_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="device not found") from exc


@app.get("/devices")
def list_devices() -> List[dict[str, Any]]:
    return [device.to_dict() for device in registry.list_devices()]


@app.get("/devices/{device_id}")
def get_device(device_id: str) -> dict[str, Any]:
    try:
        return registry.get_device(device_id).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="device not found") from exc


@app.patch("/devices/{device_id}")
def rename_device(device_id: str, request: DeviceRenameRequest) -> Response:
    try:
        registry.rename(device_id, request.name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="device not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.patch("/devices/{device_id}/main-video-track")
def update_main_video_track(device_id: str, request: MainVideoTrackRequest) -> Response:
    try:
        registry.update_main_video_track(device_id, request.name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="device not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.delete("/devices/{device_id}")
def delete_device(device_id: str) -> Response:
    try:
        registry.delete(device_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="device not found") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.put("/devices/{device_id}/agent")
def upsert_device_agent(device_id: str, request: DeviceAgentRegistrationRequest) -> dict[str, Any]:
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
def detach_device_agent(device_id: str, secretKey: str) -> dict[str, Any]:
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


@app.post("/events/ingest", status_code=status.HTTP_201_CREATED)
def ingest_event(request: EventIngestRequest) -> dict[str, Any]:
    event = event_registry.ingest_event(request)
    return event.to_dict()


@app.get("/events")
def list_events() -> list[dict[str, Any]]:
    return [event.to_dict() for event in event_registry.list_events()]


@app.get("/events/{event_id}")
def get_event(event_id: str) -> dict[str, Any]:
    try:
        return event_registry.get_event(event_id).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="event not found") from exc


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


@app.post("/devices/{device_id}/location")
def update_device_location(device_id: int, request: LocationUpdate) -> dict[str, Any]:
    """POC 01-05 에이전트의 텔레메트리 기반 위치 업데이트"""
    try:
        device = registry.update_device_location(
            device_id,
            latitude=request.latitude,
            longitude=request.longitude
        )
        return device.to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="device not found") from exc


@app.patch("/devices/{device_id}/metadata")
def update_device_metadata(device_id: int, request: dict[str, Any]) -> Response:
    """디바이스 메타데이터 업데이트 (device_type, layer, connectivity)"""
    try:
        registry.update_device_metadata(
            device_id,
            device_type=request.get("device_type"),
            layer=request.get("layer"),
            connectivity=request.get("connectivity")
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="device not found") from exc


@app.patch("/devices/{device_id}/auv-submersion")
def update_auv_submersion(device_id: int, request: AUVSubmersionRequest) -> dict[str, Any]:
    """AUV 수중/수면 상태 업데이트 (수중음향통신 라우팅 활성화)"""
    try:
        device = registry.update_auv_submersion(device_id, request.is_submerged)
        registry.notify_assignment(registry.assignment_for(device_id))
        return device.to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="device not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/devices/{device_id}/connectivity-state")
def update_device_connectivity_state(device_id: int, request: DeviceConnectivityStateRequest) -> dict[str, Any]:
    """
    디바이스 연결 상태 업데이트

    - ROV: parent_id를 통한 유선 연결 강제 (항상 중간 계층을 통해야 함)
    - AUV: 수중 시에만 parent_id를 통한 음향통신 (수면 시 직접 연결)
    """
    try:
        device = registry.update_device_connectivity_state(
            device_id,
            parent_id=request.parent_id,
            force_parent_routing=request.force_parent_routing
        )
        registry.notify_assignment(registry.assignment_for(device_id))
        return device.to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="device not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class MissionCreateRequest(BaseModel):
    response_id: str
    alert_id: str
    event_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


@app.post("/missions", status_code=status.HTTP_201_CREATED)
def create_mission(
    body: MissionCreateRequest = Body(...),
    response_id: str = Query(None),
    alert_id: str = Query(None),
    event_id: str = Query(None),
) -> dict[str, Any]:
    """새 Mission 생성 (Response 기반) - JSON body 우선"""
    r_id = body.response_id or response_id
    a_id = body.alert_id or alert_id
    e_id = body.event_id or event_id
    meta = body.metadata

    if not r_id or not a_id or not e_id:
        raise HTTPException(
            status_code=400,
            detail="response_id, alert_id, event_id are required"
        )

    mission = mission_registry.create_mission(
        response_id=r_id,
        alert_id=a_id,
        event_id=e_id,
        metadata=meta,
    )
    return mission.to_dict()


@app.get("/missions")
def list_missions() -> list[dict[str, Any]]:
    """모든 Mission 목록"""
    return [m.to_dict() for m in mission_registry.list_missions()]


@app.get("/missions/status/{status}")
def list_missions_by_status(status: str) -> list[dict[str, Any]]:
    """특정 상태의 Mission 목록"""
    return [m.to_dict() for m in mission_registry.list_missions_by_status(status)]


@app.get("/missions/{mission_id}")
def get_mission(mission_id: str) -> dict[str, Any]:
    """특정 Mission 조회"""
    try:
        mission = mission_registry.get_mission(mission_id)
        return mission.to_dict()
    except KeyError:
        raise HTTPException(status_code=404, detail="mission not found")


@app.post("/missions/{mission_id}/step-execution")
def record_step_execution(
    mission_id: str,
    step_id: str,
    execution_result: dict[str, Any] = None,
) -> dict[str, Any]:
    """Step 실행 결과 기록"""
    if not step_id:
        raise HTTPException(status_code=400, detail="step_id is required")
    
    try:
        mission = mission_registry.record_step_execution(
            mission_id=mission_id,
            step_id=step_id,
            execution_result=execution_result or {},
        )
        return mission.to_dict()
    except KeyError:
        raise HTTPException(status_code=404, detail="mission not found")


@app.post("/missions/{mission_id}/complete")
def complete_mission(
    mission_id: str,
    completion_report: dict[str, Any] = None,
) -> dict[str, Any]:
    """Mission 완료 및 보고서 저장"""
    try:
        mission = mission_registry.complete_mission(
            mission_id=mission_id,
            completion_report=completion_report or {},
        )
        return mission.to_dict()
    except KeyError:
        raise HTTPException(status_code=404, detail="mission not found")


@app.post("/missions/{mission_id}/abort")
def abort_mission(mission_id: str, reason: str = "Unknown error") -> dict[str, Any]:
    """Mission 실패 처리"""
    try:
        mission = mission_registry.abort_mission(mission_id=mission_id, reason=reason)
        return mission.to_dict()
    except KeyError:
        raise HTTPException(status_code=404, detail="mission not found")


@app.post("/missions/{mission_id}/update-status")
def update_mission_status_endpoint(mission_id: str, status: str) -> dict[str, Any]:
    """Manual Intervention: Mission 상태 업데이트 (재시도용)"""
    if status not in ["pending", "in_progress", "completed", "failed"]:
        raise HTTPException(status_code=400, detail="Invalid status value")
    
    try:
        mission = mission_registry.update_mission_status(mission_id=mission_id, status=status)
        
        # Publish mission update via WebSocket
        asyncio.create_task(publish_mission_update(mission_id, "status_update"))
        
        return mission.to_dict()
    except KeyError:
        raise HTTPException(status_code=404, detail="mission not found")


@app.get("/missions/stats")
def get_mission_stats() -> dict[str, Any]:
    """Mission 통계"""
    return mission_registry.get_mission_stats()


@app.post("/admin/reset", status_code=status.HTTP_204_NO_CONTENT)
def reset_all_data() -> Response:
    """
    모든 Registry 데이터 초기화 (테스트 용도)
    
    - 모든 디바이스 삭제
    - 모든 alert/response 초기화
    - 모든 event 초기화
    """
    logger.warning("Registry 데이터 초기화 시작")
    device_count = len(registry.list_devices())
    alert_count = len(alert_registry.list_alerts())
    response_count = len(alert_registry.list_responses())
    event_count = len(event_registry.list_events())
    mission_count = len(mission_registry.list_missions())
    
    registry.reset()
    alert_registry.reset()
    event_registry.reset()
    mission_registry.reset()
    
    logger.info(
        f"Registry 초기화 완료: "
        f"devices={device_count}, alerts={alert_count}, responses={response_count}, "
        f"events={event_count}, missions={mission_count}"
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ======================== WebSocket Endpoints ========================

@app.websocket("/ws/missions")
async def websocket_missions(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time mission updates"""
    connection_id = str(uuid4())
    channel = "missions"
    
    await websocket.accept()
    pubsub = get_pubsub_manager()
    await pubsub.connect(channel, connection_id, websocket)
    
    logger.info(f"✅ WebSocket client connected: {connection_id}")
    
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        await pubsub.disconnect(channel, connection_id)
        logger.info(f"✅ WebSocket client disconnected: {connection_id}")
    except Exception as e:
        logger.error(f"❌ WebSocket error: {e}")
        await pubsub.disconnect(channel, connection_id)


@app.websocket("/ws/dashboard")
async def websocket_dashboard(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time dashboard updates (all data)"""
    connection_id = str(uuid4())
    channel = "dashboard"
    
    await websocket.accept()
    pubsub = get_pubsub_manager()
    await pubsub.connect(channel, connection_id, websocket)
    
    logger.info(f"✅ Dashboard WebSocket connected: {connection_id}")
    
    try:
        # Send initial data
        initial_data = {
            "type": "initial",
            "events": [e.to_dict() for e in event_registry.list_events()],
            "alerts": [a.to_dict() for a in alert_registry.list_alerts()],
            "missions": [m.to_dict() for m in mission_registry.list_missions()],
            "stats": mission_registry.get_mission_stats(),
        }
        await websocket.send_json(initial_data)
        
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        await pubsub.disconnect(channel, connection_id)
        logger.info(f"✅ Dashboard WebSocket disconnected: {connection_id}")
    except Exception as e:
        logger.error(f"❌ Dashboard WebSocket error: {e}")
        await pubsub.disconnect(channel, connection_id)


# Helper function to publish mission updates
async def publish_mission_update(mission_id: str, update_type: str) -> None:
    """Publish mission update to WebSocket subscribers"""
    try:
        pubsub = get_pubsub_manager()
        mission = mission_registry.get_mission(mission_id)
        
        message = {
            "type": update_type,
            "mission_id": mission_id,
            "mission": mission.to_dict(),
            "timestamp": asyncio.get_event_loop().time(),
        }
        
        await pubsub.publish("missions", message)
        await pubsub.publish("dashboard", {
            "type": "mission_update",
            "data": message,
        })
    except Exception as e:
        logger.warning(f"⚠️ Failed to publish mission update: {e}")





def main() -> None:
    # Python logging 설정 (stdout으로 로그 출력)
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", help="Override bind host from config/env")
    parser.add_argument("--port", type=int, help="Override bind port from config/env")
    args = parser.parse_args()
    bind_host = args.host or APP_SETTINGS["server"]["host"]
    bind_port = args.port or APP_SETTINGS["server"]["port"]
    uvicorn.run(app, host=bind_host, port=bind_port, reload=False, log_level="info")


if __name__ == "__main__":
    main()
