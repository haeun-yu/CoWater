from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, List
from uuid import uuid4

from fastapi import Body, FastAPI, Header, HTTPException, Query, Response, status, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

# 서버 루트 디렉토리를 Python path에 추가하여 shared 모듈 import 가능
_server_root = Path(__file__).resolve().parent.parent.parent
if str(_server_root) not in sys.path:
    sys.path.insert(0, str(_server_root))

from src.core.config import APP_SETTINGS
from src.core.models import (
    AUVSubmersionRequest,
    CORE_ACTIONS,
    DEVICE_TYPES,
    DeviceAgentRegistrationRequest,
    DeviceConnectivityStateRequest,
    DeviceRegistrationRequest,
    DeviceRenameRequest,
    LocationUpdate,
    MainVideoTrackRequest,
    TRACK_TYPES,
    normalize_mission_status,
)
from src.core.pubsub import get_pubsub_manager
from src.application.bootstrap import build_registry_components
from src.db.connection import close_db
from src.transport.moth_publisher import get_publisher as get_moth_publisher
from shared.storage.coverse_store import get_coverse_store


logger = logging.getLogger(__name__)

INTERNAL_CALLER_HEADER = "system-agent"


def _schedule_background_task(coro: Any) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        close = getattr(coro, "close", None)
        if callable(close):
            close()
        return
    loop.create_task(coro)


def _publish_registry_snapshot(channel: str, payload: Any) -> None:
    async def publish() -> None:
        await get_moth_publisher().publish(channel, payload)

    _schedule_background_task(publish())


def require_internal_caller(x_cowater_internal: str | None) -> None:
    if str(x_cowater_internal or "").strip() != INTERNAL_CALLER_HEADER:
        raise HTTPException(status_code=403, detail="system agent only")


components = build_registry_components()
registry = components.registry
event_registry = components.event_registry
a2a_log_registry = components.a2a_log_registry
policy_registry = components.policy_registry
user_registry = components.user_registry
agent_registry = components.agent_registry
proposal_task_registry = components.proposal_task_registry
task_registry = components.task_registry
report_registry = components.report_registry
rule_registry = components.rule_registry
config_registry = components.config_registry
sensor_registry = components.sensor_registry
mission_registry = components.mission_registry
insight_registry = components.insight_registry
approval_registry = components.approval_registry
mission_proposal_registry = components.mission_proposal_registry
agent_connection_registry = components.agent_connection_registry
moth_subscriber = components.moth_subscriber

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Server lifecycle management."""
    try:
        await moth_subscriber.start()
    except Exception as exc:
        logger.warning("Moth 구독 시작 실패 - healthcheck monitor만으로 계속 기동합니다: %s", exc)
    _schedule_background_task(registry.healthcheck_monitor.start())
    try:
        yield
    finally:
        await registry.healthcheck_monitor.stop()
        await moth_subscriber.stop()
        close_db()


app = FastAPI(title="CoWater Device Registration Server", version="1.0.0", lifespan=lifespan)
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
        "device_types": list(DEVICE_TYPES.__args__),
        "core_actions": list(CORE_ACTIONS.__args__),
        "device_register": "/devices/register",
        "agent_register": "/agents/register",
        "insights": "/insights",
        "approvals": "/approvals",
        "mission_proposals": "/mission-proposals",
        "agent_connections": "/agent-connections",
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


@app.post("/devices/register", status_code=status.HTTP_201_CREATED)
def register_device_alias(request: DeviceRegistrationRequest) -> dict[str, Any]:
    return register_device(request)


@app.get("/devices/{device_id}/assignment")
def get_device_assignment(device_id: str) -> dict[str, Any]:
    try:
        return registry.assignment_for(device_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="device not found") from exc


@app.get("/devices")
def list_devices(
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> List[dict[str, Any]]:
    return [device.to_dict() for device in registry.list_devices(limit=limit, offset=offset)]


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


@app.post("/agents/register")
def register_agent(request: DeviceAgentRegistrationRequest) -> dict[str, Any]:
    if request.device_id is None:
        raise HTTPException(status_code=400, detail="device_id is required")
    return upsert_device_agent(str(request.device_id), request)


@app.delete("/devices/{device_id}/agent")
def detach_device_agent(device_id: str, secretKey: str) -> dict[str, Any]:
    try:
        device = registry.detach_agent(device_id, secretKey)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="device not found") from exc
    return device.to_dict()


@app.put("/devices/{device_id}/connectivity")
def update_device_connectivity(
    device_id: str,
    body: dict[str, Any],
    x_cowater_internal: str | None = Header(default=None),
) -> dict[str, Any]:
    """Device 연결 상태 업데이트 (Ch.16 - 통신 복구 동기화)"""
    require_internal_caller(x_cowater_internal)
    try:
        device = registry.get_device(device_id)
        device.connectivity_status = body.get("connectivity_status", "offline")
        registry.upsert_device(device)
        logger.info(f"Device {device_id} connectivity updated to {device.connectivity_status}")
        return device.to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="device not found") from exc


@app.post("/events/ingest", status_code=status.HTTP_201_CREATED)
def ingest_event(body: dict[str, Any]) -> dict[str, Any]:
    """Event 생성 (Registry 저장 전용 — 에이전트 간 통신은 Moth MEB 직접 사용)"""
    event_type = body.get("type", body.get("event_type", "UNKNOWN"))
    payload = dict(body.get("data", {}) or {})
    metadata = body.get("metadata") or {}
    if isinstance(metadata, dict):
        for key, value in metadata.items():
            payload.setdefault(key, value)
    if "source_role" in body and "source_role" not in payload:
        payload["source_role"] = body.get("source_role")
    if "source_agent_id" in body and "source_agent_id" not in payload:
        payload["source_agent_id"] = body.get("source_agent_id")
    actor_type = body.get("actor_type")
    if not actor_type:
        source_system = str(body.get("source_system") or "").lower()
        if source_system.startswith("device"):
            actor_type = "DEVICE"
        elif source_system.startswith("user"):
            actor_type = "USER"
        else:
            actor_type = "SYSTEM"
    actor_id = body.get("actor_id") or body.get("source_agent_id") or body.get("source_device_id") or body.get("source_user_id") or "system"
    event = event_registry.create_event(
        actor_type=actor_type,
        actor_id=actor_id,
        type=event_type,
        severity=body.get("severity", "INFO"),
        title=body.get("title", ""),
        description=body.get("description") or body.get("message", ""),
        target_type=body.get("target_type"),
        target_id=body.get("target_id"),
        data=payload,
        status=body.get("status", "OPEN"),
    )
    return event.to_dict()


@app.get("/events")
def list_events(
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    return [event.to_dict() for event in event_registry.list_events(limit=limit, offset=offset)]


@app.get("/events/{event_id}")
def get_event(event_id: str) -> dict[str, Any]:
    try:
        return event_registry.get_event(event_id).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="event not found") from exc


@app.patch("/events/{event_id}/status")
def update_event_status(event_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Event 상태 전환 (OPEN → HANDLED → RESOLVED)"""
    new_status = str(body.get("status") or "").upper()
    if new_status not in ("OPEN", "HANDLED", "RESOLVED"):
        raise HTTPException(status_code=400, detail="status must be OPEN | HANDLED | RESOLVED")
    try:
        return event_registry.update_event_status(event_id, new_status).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="event not found") from exc


@app.post("/a2a-logs/ingest", status_code=status.HTTP_201_CREATED)
def ingest_a2a_log(
    direction: str = Query(..., description="inbound or outbound"),
    from_agent_id: str = Query(None, description="Source agent ID"),
    to_agent_id: str = Query(None, description="Destination agent ID"),
    message_type: str = Query(..., description="A2A message type"),
    task_id: str = Query(None, description="Related task ID"),
    mission_id: str = Query(None, description="Related mission ID"),
    payload: dict[str, Any] = Body(..., description="A2A message payload"),
    x_cowater_internal: str | None = Header(default=None),
) -> dict[str, str]:
    """A2A 메시지 로깅 (System Agent 및 Device Agent에서 호출)"""
    require_internal_caller(x_cowater_internal)
    log_id = a2a_log_registry.log_message(
        direction=direction,
        from_agent_id=from_agent_id,
        to_agent_id=to_agent_id,
        message_type=message_type,
        task_id=task_id,
        mission_id=mission_id,
        payload=payload,
    )
    return {"log_id": log_id, "message_type": message_type}


@app.get("/a2a-logs")
def get_a2a_logs(
    mission_id: str | None = Query(None, description="Filter by mission ID"),
    task_id: str | None = Query(None, description="Filter by task ID"),
    from_agent_id: str | None = Query(None, description="Filter by source agent ID"),
    to_agent_id: str | None = Query(None, description="Filter by destination agent ID"),
    message_type: str | None = Query(None, description="Filter by message type"),
    direction: str | None = Query(None, description="Filter by direction (inbound/outbound)"),
    limit: int = Query(1000, description="Max logs to return"),
    offset: int = Query(0, ge=0),
) -> list[dict[str, Any]]:
    """A2A 로그 조회 (필터링 지원)"""
    return a2a_log_registry.get_logs(
        mission_id=mission_id,
        task_id=task_id,
        from_agent_id=from_agent_id,
        to_agent_id=to_agent_id,
        message_type=message_type,
        direction=direction,
        limit=limit,
        offset=offset,
    )


@app.post("/policies", status_code=status.HTTP_201_CREATED)
async def create_policy(body: dict[str, Any], x_cowater_internal: str | None = Header(default=None)) -> dict[str, Any]:
    """정책 생성 (Ch.17.1)"""
    require_internal_caller(x_cowater_internal)
    result = policy_registry.create_policy(body)
    _publish_registry_snapshot("policies", policy_registry.get_policies())
    return result


@app.get("/policies")
def list_policies(
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    """정책 목록 조회"""
    return policy_registry.list_policies(limit=limit, offset=offset)


@app.get("/policies/{policy_id}")
def get_policy(policy_id: str) -> dict[str, Any]:
    """정책 조회"""
    policy = policy_registry.get_policy(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="policy not found")
    return policy


@app.put("/policies/{policy_id}")
async def update_policy(policy_id: str, body: dict[str, Any], x_cowater_internal: str | None = Header(default=None)) -> dict[str, Any]:
    """정책 업데이트"""
    require_internal_caller(x_cowater_internal)
    result = policy_registry.update_policy(policy_id, body)
    _publish_registry_snapshot("policies", policy_registry.get_policies())
    return result


@app.delete("/policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_policy(policy_id: str, x_cowater_internal: str | None = Header(default=None)) -> Response:
    """정책 삭제"""
    require_internal_caller(x_cowater_internal)
    policy_registry.delete_policy(policy_id)
    _publish_registry_snapshot("policies", policy_registry.get_policies())
    return Response(status_code=204)


@app.post("/insights", status_code=status.HTTP_201_CREATED)
def create_insight(body: dict[str, Any]) -> dict[str, Any]:
    return insight_registry.create_insight(body).to_dict()


@app.get("/insights")
def list_insights(
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    return [item.to_dict() for item in insight_registry.list_insights(limit=limit, offset=offset)]


@app.get("/insights/{insight_id}")
def get_insight(insight_id: str) -> dict[str, Any]:
    try:
        return insight_registry.get_insight(insight_id).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="insight not found") from exc


@app.post("/approvals", status_code=status.HTTP_201_CREATED)
async def create_approval(body: dict[str, Any]) -> dict[str, Any]:
    result = approval_registry.create_approval(body).to_dict()
    _publish_registry_snapshot("approvals", [item.to_dict() for item in approval_registry.list_approvals()])
    return result


@app.get("/approvals")
def list_approvals(
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    return [item.to_dict() for item in approval_registry.list_approvals(limit=limit, offset=offset)]


@app.get("/approvals/{approval_id}")
def get_approval(approval_id: str) -> dict[str, Any]:
    try:
        return approval_registry.get_approval(approval_id).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="approval not found") from exc


@app.post("/approvals/{approval_id}/decision")
async def decide_approval(approval_id: str, body: dict[str, Any]) -> dict[str, Any]:
    approved = bool(body.get("approved"))
    decided_by = str(body.get("decided_by") or "user")
    notes = body.get("notes")
    try:
        approval = approval_registry.decide_approval(
            approval_id,
            approved,
            decided_by=decided_by,
            notes=notes,
        )
        result = approval.to_dict()
        _publish_registry_snapshot("approvals", [item.to_dict() for item in approval_registry.list_approvals()])
        return result
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="approval not found") from exc


@app.post("/mission-proposals", status_code=status.HTTP_201_CREATED)
async def create_mission_proposal(body: dict[str, Any]) -> dict[str, Any]:
    result = mission_proposal_registry.create_mission_proposal(body).to_dict()
    _publish_registry_snapshot("mission_proposals", [item.to_dict() for item in mission_proposal_registry.list_mission_proposals()])
    return result


@app.get("/mission-proposals")
def list_mission_proposals(
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    return [item.to_dict() for item in mission_proposal_registry.list_mission_proposals(limit=limit, offset=offset)]


@app.get("/mission-proposals/{proposal_id}")
def get_mission_proposal(proposal_id: str) -> dict[str, Any]:
    try:
        return mission_proposal_registry.get_mission_proposal(proposal_id).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="mission proposal not found") from exc


@app.post("/agent-connections", status_code=status.HTTP_201_CREATED)
async def create_agent_connection(body: dict[str, Any]) -> dict[str, Any]:
    record = agent_connection_registry.create_agent_connection(body)
    event_registry.create_event(
        actor_type="SYSTEM",
        actor_id="system",
        type="SYS_AGENT_CONNECTION_CREATED",
        severity="INFO",
        title="Agent connection created",
        description="AgentConnection created",
        target_type="AGENT_CONNECTION",
        target_id=record.connection_id,
        data={
            "connection_id": record.connection_id,
            "agent_a_id": record.agent_a_id,
            "agent_b_id": record.agent_b_id,
            "connection_type": record.connection_type,
            "relation_level": record.relation_level,
            "parent_agent_id": record.parent_agent_id,
            "mission_id": record.mission_id,
            "reason": record.reason,
            "profile": record.profile,
            "deleted_at": record.deleted_at,
        },
    )
    _publish_registry_snapshot("events", [e.to_dict() for e in event_registry.list_events()])
    return record.to_dict()


@app.get("/agent-connections")
def list_agent_connections(
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    return [item.to_dict() for item in agent_connection_registry.list_agent_connections(limit=limit, offset=offset)]


@app.get("/agent-connections/{connection_id}")
def get_agent_connection(connection_id: str) -> dict[str, Any]:
    try:
        return agent_connection_registry.get_agent_connection(connection_id).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="agent connection not found") from exc


@app.put("/agent-connections/{connection_id}")
def update_agent_connection(connection_id: str, body: dict[str, Any]) -> dict[str, Any]:
    try:
        return agent_connection_registry.update_agent_connection(connection_id, body).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="agent connection not found") from exc


@app.delete("/agent-connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent_connection(connection_id: str) -> Response:
    try:
        record = agent_connection_registry.get_agent_connection(connection_id)
        agent_connection_registry.delete_agent_connection(connection_id)
        event_registry.create_event(
            actor_type="SYSTEM",
            actor_id="system",
            type="SYS_AGENT_CONNECTION_DELETED",
            severity="WARNING",
            title="Agent connection deleted",
            description="AgentConnection soft deleted",
            target_type="AGENT_CONNECTION",
            target_id=connection_id,
            data={
                "connection_id": connection_id,
                "agent_a_id": record.agent_a_id,
                "agent_b_id": record.agent_b_id,
                "reason": record.reason or "soft delete",
            },
        )
        _publish_registry_snapshot("events", [e.to_dict() for e in event_registry.list_events()])
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="agent connection not found") from exc
    return Response(status_code=204)


@app.get("/devices/{device_id}/connections")
def get_device_connections(device_id: str) -> list[dict[str, Any]]:
    connections = []
    for connection in agent_connection_registry.list_agent_connections():
        if connection.deleted_at is not None:
            continue
        if connection.agent_a_id == device_id or connection.agent_b_id == device_id:
            connections.append(connection.to_dict())
    return connections


@app.post("/devices/{device_id}/location")
def update_device_location(device_id: str, request: LocationUpdate) -> dict[str, Any]:
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
def update_device_metadata(device_id: str, request: dict[str, Any]) -> Response:
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
def update_auv_submersion(device_id: str, request: AUVSubmersionRequest) -> dict[str, Any]:
    """AUV 수중/수면 상태 업데이트 (수중음향통신 라우팅 활성화)"""
    try:
        previous = registry.get_device(device_id)
        device = registry.update_auv_submersion(device_id, request.is_submerged)
        if getattr(previous, "is_submerged", False) != device.is_submerged:
            event_registry.create_event(
                actor_type="DEVICE",
                actor_id=str(device.public_id),
                type="ENV_STATE_CHANGED",
                severity="INFO",
                title="Environment state changed",
                description=f"Device {device.name} changed environment state",
                target_type="DEVICE",
                target_id=str(device.public_id),
                data={
                    "device_id": device.public_id,
                    "registry_id": device.id,
                    "device_name": device.name,
                    "from": "UNDERWATER" if getattr(previous, "is_submerged", False) else "SURFACE",
                    "to": "UNDERWATER" if device.is_submerged else "SURFACE",
                },
            )
        registry.notify_assignment(registry.assignment_for(device_id))
        return device.to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="device not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/devices/{device_id}/connectivity-state")
def update_device_connectivity_state(device_id: str, request: DeviceConnectivityStateRequest) -> dict[str, Any]:
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
    mission_id: str | None = None
    title: str | None = None
    mission_type: str | None = None
    type: str | None = None
    source_event_id: str | None = None
    proposal_id: str | None = None
    source_proposal_id: str | None = None
    approval_id: str | None = None
    status: str | None = None
    priority: str | None = None
    target_area: str | None = None
    target_position: dict[str, Any] | None = None
    created_by: dict[str, Any] | None = None
    approved_by_user_id: str | None = None
    result_summary: str | None = None
    status_reason: str | None = None
    status_updated_at: str | None = None
    steps: list[dict[str, Any]] = Field(default_factory=list)
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    final_result: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    approved_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


@app.post("/missions", status_code=status.HTTP_201_CREATED)
def create_mission(
    body: MissionCreateRequest | None = Body(None),
) -> dict[str, Any]:
    """새 Mission 생성"""
    body = body or MissionCreateRequest()
    mission_payload = body.model_dump()
    if not mission_payload.get("title"):
        mission_payload["title"] = "Mission"
    if not mission_payload.get("mission_type"):
        mission_payload["mission_type"] = mission_payload.get("type") or "OPERATION"
    mission_payload["source_event_id"] = mission_payload.get("source_event_id")
    mission_payload["source_proposal_id"] = mission_payload.get("source_proposal_id") or mission_payload.get("proposal_id")
    if not mission_payload.get("status"):
        mission_payload["status"] = "READY"
    else:
        mission_payload["status"] = normalize_mission_status(mission_payload.get("status"))
    mission = mission_registry.create_mission(
        mission_id=mission_payload.get("mission_id"),
        title=mission_payload.get("title"),
        type=mission_payload.get("mission_type"),
        status=mission_payload.get("status"),
        priority=mission_payload.get("priority", "NORMAL"),
        source_event_id=mission_payload.get("source_event_id"),
        source_proposal_id=mission_payload.get("source_proposal_id"),
        target_area=mission_payload.get("target_area"),
        target_position=mission_payload.get("target_position"),
        created_by=mission_payload.get("created_by"),
        approved_by_user_id=mission_payload.get("approved_by_user_id"),
        approved_at=mission_payload.get("approved_at"),
        approval_id=mission_payload.get("approval_id"),
        result_summary=mission_payload.get("result_summary"),
        status_reason=mission_payload.get("status_reason"),
        steps=mission_payload.get("steps"),
        timeline=mission_payload.get("timeline"),
        final_result=mission_payload.get("final_result"),
        metadata=mission_payload.get("metadata"),
    )
    result = mission.to_dict()
    async def publish_mission():
        await get_moth_publisher().publish("missions", [m.to_dict() for m in mission_registry.list_missions()])
        await get_moth_publisher().publish(f"mission.{mission.mission_id}", result)
    _schedule_background_task(publish_mission())
    return result


@app.get("/missions")
def list_missions(
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    return [m.to_dict() for m in mission_registry.list_missions(limit=limit, offset=offset)]


@app.get("/missions/status/{status}")
def list_missions_by_status(status: str) -> list[dict[str, Any]]:
    normalized_status = normalize_mission_status(status)
    return [m.to_dict() for m in mission_registry.list_missions_by_status(normalized_status)]


@app.get("/missions/stats")
def get_mission_stats() -> dict[str, Any]:
    return mission_registry.get_mission_stats()


@app.get("/missions/{mission_id}")
def get_mission(mission_id: str) -> dict[str, Any]:
    try:
        mission = mission_registry.get_mission(mission_id)
        return mission.to_dict()
    except KeyError:
        raise HTTPException(status_code=404, detail="mission not found")


@app.put("/missions/{mission_id}")
def replace_mission(mission_id: str, body: dict[str, Any]) -> dict[str, Any]:
    try:
        existing = mission_registry.get_mission(mission_id)
        mission = mission_registry.update_mission(mission_id, **body)
    except KeyError:
        mission = mission_registry.create_mission(
            mission_id=body.get("mission_id") or mission_id,
            title=body.get("title", "Mission"),
            type=body.get("mission_type", body.get("type", "OPERATION")),
            status=body.get("status", "READY"),
            priority=body.get("priority", "NORMAL"),
            source_event_id=body.get("source_event_id"),
            source_proposal_id=body.get("source_proposal_id"),
            target_area=body.get("target_area"),
            target_position=body.get("target_position"),
            created_by=body.get("created_by"),
            approved_by_user_id=body.get("approved_by_user_id"),
            approved_at=body.get("approved_at"),
            approval_id=body.get("approval_id"),
            result_summary=body.get("result_summary"),
            steps=body.get("steps"),
            timeline=body.get("timeline"),
            final_result=body.get("final_result"),
            metadata=body.get("metadata"),
        )
    result = mission.to_dict()
    async def publish_mission():
        await get_moth_publisher().publish("missions", [m.to_dict() for m in mission_registry.list_missions()])
        await get_moth_publisher().publish(f"mission.{mission_id}", result)
    _schedule_background_task(publish_mission())
    return result


# ======================== User Endpoints ========================

@app.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(
    name: str = Body(...),
    role: str = Body(...),
    status: str = Body(default="ACTIVE"),
) -> dict[str, Any]:
    """새 User 생성"""
    user = user_registry.create_user(name=name, role=role, status=status)
    return user.to_dict()


@app.get("/users")
def list_users(
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    """User 목록 조회"""
    return [u.to_dict() for u in user_registry.list_users(limit=limit, offset=offset)]


@app.get("/users/{user_id}")
def get_user(user_id: str) -> dict[str, Any]:
    """User 조회"""
    try:
        return user_registry.get_user(user_id).to_dict()
    except KeyError:
        raise HTTPException(status_code=404, detail="user not found")


@app.put("/users/{user_id}")
def update_user(user_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """User 업데이트"""
    try:
        user = user_registry.update_user(user_id, **body)
        return user.to_dict()
    except KeyError:
        raise HTTPException(status_code=404, detail="user not found")


@app.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: str) -> Response:
    """User 삭제"""
    try:
        user_registry.delete_user(user_id)
        return Response(status_code=204)
    except KeyError:
        raise HTTPException(status_code=404, detail="user not found")


# ======================== Agent Endpoints ========================

@app.post("/agents", status_code=status.HTTP_201_CREATED)
def create_agent(body: dict[str, Any]) -> dict[str, Any]:
    """새 Agent 생성"""
    endpoint = body.get("endpoint") or {}
    if not endpoint or not endpoint.get("host") or not endpoint.get("port"):
        raise HTTPException(status_code=400, detail="endpoint.host and endpoint.port are required (ADR-004)")
    agent = agent_registry.create_agent(
        name=body.get("name", ""),
        type=body.get("type", "SYSTEM_AGENT"),
        role=body.get("role", "SYSTEM_SENTINEL"),
        endpoint=endpoint,
        capabilities=body.get("capabilities", []),
        device_id=body.get("device_id"),
        gateway_agent_id=body.get("gateway_agent_id"),
    )
    return agent.to_dict()


@app.get("/agents")
def list_agents(
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    """Agent 목록 조회"""
    return [a.to_dict() for a in agent_registry.list_agents(limit=limit, offset=offset)]


@app.get("/agents/{agent_id}")
def get_agent(agent_id: str) -> dict[str, Any]:
    """Agent 조회"""
    try:
        return agent_registry.get_agent(agent_id).to_dict()
    except KeyError:
        raise HTTPException(status_code=404, detail="agent not found")


@app.put("/agents/{agent_id}")
def update_agent(agent_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Agent 업데이트"""
    try:
        agent = agent_registry.update_agent(agent_id, **body)
        return agent.to_dict()
    except KeyError:
        raise HTTPException(status_code=404, detail="agent not found")


@app.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(agent_id: str) -> Response:
    """Agent 삭제"""
    try:
        agent_registry.delete_agent(agent_id)
        return Response(status_code=204)
    except KeyError:
        raise HTTPException(status_code=404, detail="agent not found")


@app.patch("/agents/{agent_id}/heartbeat")
def update_agent_heartbeat(agent_id: str) -> dict[str, Any]:
    """Agent Heartbeat 업데이트"""
    try:
        agent = agent_registry.update_agent_heartbeat(agent_id)
        return agent.to_dict()
    except KeyError:
        raise HTTPException(status_code=404, detail="agent not found")


@app.patch("/agents/{agent_id}/environment-state")
def update_agent_environment_state(agent_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Agent 환경 상태 업데이트"""
    try:
        environment_state = body.get("environment_state", "SURFACE")
        active_mediums = body.get("active_mediums", [])
        agent = agent_registry.update_agent(agent_id, environment_state=environment_state, active_mediums=active_mediums)
        return agent.to_dict()
    except KeyError:
        raise HTTPException(status_code=404, detail="agent not found")


# ======================== ProposalTask Endpoints ========================

@app.post("/proposals/{proposal_id}/tasks", status_code=status.HTTP_201_CREATED)
def create_proposal_task(proposal_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """ProposalTask 생성"""
    task = proposal_task_registry.create_task(
        proposal_id=proposal_id,
        title=body.get("title", ""),
        type=body.get("type", "DEVICE_TASK"),
        required_action=body.get("required_action", ""),
        sequence=body.get("sequence", 0),
        target_area=body.get("target_area"),
        target_position=body.get("target_position"),
        recommended_device_id=body.get("recommended_device_id"),
        recommended_agent_id=body.get("recommended_agent_id"),
        alternative_device_ids=body.get("alternative_device_ids", []),
        recommendation_reason=body.get("recommendation_reason"),
        parameters=body.get("parameters", {}),
    )
    return task.to_dict()


@app.get("/proposals/{proposal_id}/tasks")
def list_proposal_tasks(proposal_id: str) -> list[dict[str, Any]]:
    """Proposal의 Task 목록 조회"""
    return [t.to_dict() for t in proposal_task_registry.list_tasks_by_proposal(proposal_id)]


@app.get("/proposals/{proposal_id}/tasks/{task_id}")
def get_proposal_task(proposal_id: str, task_id: str) -> dict[str, Any]:
    """ProposalTask 조회"""
    try:
        task = proposal_task_registry.get_task(task_id)
        if task.proposal_id != proposal_id:
            raise HTTPException(status_code=404, detail="task not found in this proposal")
        return task.to_dict()
    except KeyError:
        raise HTTPException(status_code=404, detail="task not found")


# ======================== Task Endpoints ========================

@app.post("/missions/{mission_id}/tasks", status_code=status.HTTP_201_CREATED)
def create_task(mission_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Task 생성"""
    task = task_registry.create_task(
        mission_id=mission_id,
        source_proposal_task_id=body.get("source_proposal_task_id"),
        title=body.get("title", ""),
        type=body.get("type", "DEVICE_TASK"),
        required_action=body.get("required_action", ""),
        sequence=body.get("sequence", 0),
        assigned_device_id=body.get("assigned_device_id"),
        assigned_agent_id=body.get("assigned_agent_id"),
        target_area=body.get("target_area"),
        target_position=body.get("target_position"),
        parameters=body.get("parameters", {}),
    )
    return task.to_dict()


@app.get("/missions/{mission_id}/tasks")
def list_mission_tasks(mission_id: str) -> list[dict[str, Any]]:
    """Mission의 Task 목록 조회"""
    return [t.to_dict() for t in task_registry.list_tasks_by_mission(mission_id)]


@app.get("/tasks/{task_id}")
def get_task(task_id: str) -> dict[str, Any]:
    """Task 조회"""
    try:
        return task_registry.get_task(task_id).to_dict()
    except KeyError:
        raise HTTPException(status_code=404, detail="task not found")


@app.patch("/tasks/{task_id}/status")
def update_task_status(task_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Task 상태 업데이트"""
    try:
        status_value = body.get("status", "PENDING")
        reason = body.get("reason")
        result = body.get("result")
        task = task_registry.update_task_status(task_id, status_value, reason=reason, result=result)
        return task.to_dict()
    except KeyError:
        raise HTTPException(status_code=404, detail="task not found")


# ======================== Report Endpoints ========================

@app.post("/reports", status_code=status.HTTP_201_CREATED)
def create_report(body: dict[str, Any]) -> dict[str, Any]:
    """Report 생성"""
    report = report_registry.create_report(
        type=body.get("type", "MISSION_REPORT"),
        target_type=body.get("target_type", "MISSION"),
        target_id=body.get("target_id", ""),
        title=body.get("title", ""),
        summary=body.get("summary", ""),
        details=body.get("details", {}),
        created_by=body.get("created_by"),
    )
    return report.to_dict()


@app.get("/reports")
def list_reports(
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    """Report 목록 조회"""
    return [r.to_dict() for r in report_registry.list_reports(limit=limit, offset=offset)]


@app.get("/reports/{report_id}")
def get_report(report_id: str) -> dict[str, Any]:
    """Report 조회"""
    try:
        return report_registry.get_report(report_id).to_dict()
    except KeyError:
        raise HTTPException(status_code=404, detail="report not found")


# ======================== Rule Endpoints ========================

_VALID_RULE_TYPES = {"PROBLEM_DETECTION", "AUTO_RESPONSE", "RECOMMENDATION", "APPROVAL", "AGENT_CONNECTION"}

@app.post("/rules", status_code=status.HTTP_201_CREATED)
def create_rule(body: dict[str, Any]) -> dict[str, Any]:
    """Rule 생성 (schema.md §12 기준 rule_type 검증)"""
    rule_type = str(body.get("rule_type") or "PROBLEM_DETECTION").upper()
    if rule_type not in _VALID_RULE_TYPES:
        raise HTTPException(status_code=400, detail=f"rule_type must be one of {sorted(_VALID_RULE_TYPES)}")
    rule = rule_registry.create_rule(
        rule_type=rule_type,
        name=body.get("name", ""),
        enabled=body.get("enabled", True),
        priority=body.get("priority", 0),
        conditions=body.get("conditions", []),
        action=body.get("action", {}),
        severity=body.get("severity", "INFO"),
        policy_id=body.get("policy_id"),
        created_by=body.get("created_by"),
    )
    return rule.to_dict()


@app.get("/rules")
def list_rules(
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    """Rule 목록 조회"""
    return [r.to_dict() for r in rule_registry.list_rules(limit=limit, offset=offset)]


@app.get("/rules/{rule_id}")
def get_rule(rule_id: str) -> dict[str, Any]:
    """Rule 조회"""
    try:
        return rule_registry.get_rule(rule_id).to_dict()
    except KeyError:
        raise HTTPException(status_code=404, detail="rule not found")


@app.put("/rules/{rule_id}")
def update_rule(rule_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Rule 업데이트"""
    try:
        rule = rule_registry.update_rule(rule_id, **body)
        return rule.to_dict()
    except KeyError:
        raise HTTPException(status_code=404, detail="rule not found")


@app.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: str) -> Response:
    """Rule 삭제"""
    try:
        rule_registry.delete_rule(rule_id)
        return Response(status_code=204)
    except KeyError:
        raise HTTPException(status_code=404, detail="rule not found")


# ======================== Config Endpoints ========================

@app.get("/configs")
def list_configs(scope: str | None = Query(default=None)) -> list[dict[str, Any]]:
    """Config 목록 조회"""
    return [c.to_dict() for c in config_registry.list_configs(scope=scope)]


@app.get("/configs/{key}")
def get_config(key: str) -> dict[str, Any]:
    """Config 조회"""
    try:
        return config_registry.get_config(key).to_dict()
    except KeyError:
        raise HTTPException(status_code=404, detail="config not found")


@app.put("/configs/{key}")
def set_config(key: str, body: dict[str, Any]) -> dict[str, Any]:
    """Config 저장 (upsert)"""
    config = config_registry.set_config(
        key=key,
        value=body.get("value"),
        type=body.get("type", "string"),
        scope=body.get("scope", "SYSTEM"),
        description=body.get("description"),
        updated_by=body.get("updated_by"),
    )
    return config.to_dict()


# ======================== Sensor Endpoints ========================

@app.post("/devices/{device_id}/sensors", status_code=status.HTTP_201_CREATED)
def create_sensor(device_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Device의 Sensor 생성"""
    sensor = sensor_registry.create_sensor(
        device_id=device_id,
        name=body.get("name", ""),
        type=body.get("type", "OTHER"),
        stream_endpoint=body.get("stream_endpoint", ""),
    )
    return sensor.to_dict()


@app.get("/devices/{device_id}/sensors")
def list_device_sensors(device_id: str) -> list[dict[str, Any]]:
    """Device의 Sensor 목록 조회"""
    return [s.to_dict() for s in sensor_registry.list_sensors_by_device(device_id)]


@app.get("/sensors/{sensor_id}")
def get_sensor(sensor_id: str) -> dict[str, Any]:
    """Sensor 조회"""
    try:
        return sensor_registry.get_sensor(sensor_id).to_dict()
    except KeyError:
        raise HTTPException(status_code=404, detail="sensor not found")


@app.delete("/sensors/{sensor_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sensor(sensor_id: str) -> Response:
    """Sensor 삭제"""
    try:
        sensor_registry.delete_sensor(sensor_id)
        return Response(status_code=204)
    except KeyError:
        raise HTTPException(status_code=404, detail="sensor not found")


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
    event_count = len(event_registry.list_events())
    mission_count = len(mission_registry.list_missions())
    user_count = len(user_registry.list_users(limit=10000))
    agent_count = len(agent_registry.list_agents(limit=10000))
    task_count = len(task_registry.list_tasks(limit=10000))
    report_count = len(report_registry.list_reports(limit=10000))
    rule_count = len(rule_registry.list_rules(limit=10000))
    sensor_count = len(sensor_registry.list_sensors(limit=10000))

    registry.reset()
    event_registry.reset()
    mission_registry.reset()
    insight_registry.reset()
    approval_registry.reset()
    mission_proposal_registry.reset()
    agent_connection_registry.reset()
    policy_registry.reset()
    a2a_log_registry.reset()
    user_registry.reset()
    agent_registry.reset()
    proposal_task_registry.reset()
    task_registry.reset()
    report_registry.reset()
    rule_registry.reset()
    config_registry.reset()
    sensor_registry.reset()

    logger.info(
        f"Registry 초기화 완료: "
        f"devices={device_count}, "
        f"events={event_count}, missions={mission_count}, "
        f"users={user_count}, agents={agent_count}, "
        f"tasks={task_count}, reports={report_count}, "
        f"rules={rule_count}, sensors={sensor_count}"
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
            "insights": [i.to_dict() for i in insight_registry.list_insights()],
            "approvals": [a.to_dict() for a in approval_registry.list_approvals()],
            "mission_proposals": [p.to_dict() for p in mission_proposal_registry.list_mission_proposals()],
            "missions": [m.to_dict() for m in mission_registry.list_missions()],
            "stats": get_mission_stats(),
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


# ============================================================================
# CoVerse 엔드포인트
# ============================================================================

@app.get("/coverse/snapshot")
def get_coverse_snapshot() -> dict[str, Any]:
    """CoVerse의 전체 5-레이어 스냅샷 반환"""
    try:
        coverse_store = get_coverse_store()
        return coverse_store.get_coverse_snapshot()
    except Exception as e:
        logger.error(f"CoVerse snapshot 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/coverse/entity-layer")
def get_entity_layer() -> dict[str, Any]:
    """Entity Layer 데이터 반환"""
    try:
        coverse_store = get_coverse_store()
        snapshot = coverse_store.get_coverse_snapshot()
        return snapshot.get("entityLayer", {})
    except Exception as e:
        logger.error(f"Entity Layer 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/coverse/operation-layer")
def get_operation_layer() -> dict[str, Any]:
    """Operation Layer 데이터 반환"""
    try:
        coverse_store = get_coverse_store()
        snapshot = coverse_store.get_coverse_snapshot()
        return snapshot.get("operationLayer", {})
    except Exception as e:
        logger.error(f"Operation Layer 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/coverse/system-layer")
def get_system_layer() -> dict[str, Any]:
    """System Layer 데이터 반환"""
    try:
        coverse_store = get_coverse_store()
        snapshot = coverse_store.get_coverse_snapshot()
        return snapshot.get("systemLayer", {})
    except Exception as e:
        logger.error(f"System Layer 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/coverse/temporal-layer")
def get_temporal_layer() -> dict[str, Any]:
    """Temporal Layer 데이터 반환"""
    try:
        coverse_store = get_coverse_store()
        snapshot = coverse_store.get_coverse_snapshot()
        return snapshot.get("temporalLayer", {})
    except Exception as e:
        logger.error(f"Temporal Layer 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/coverse/spatial-layer")
def get_spatial_layer() -> dict[str, Any]:
    """Spatial Layer 데이터 반환"""
    try:
        coverse_store = get_coverse_store()
        snapshot = coverse_store.get_coverse_snapshot()
        return snapshot.get("spatialLayer", {})
    except Exception as e:
        logger.error(f"Spatial Layer 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e



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
