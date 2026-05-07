from __future__ import annotations

import argparse
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, List
from uuid import uuid4

from fastapi import Body, FastAPI, Header, HTTPException, Query, Response, status, WebSocket, WebSocketDisconnect
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
    TRACK_TYPES,
)
from src.core.pubsub import get_pubsub_manager
from src.application.bootstrap import build_registry_components
from src.registry.domain_registry import utc_now_iso
from src.db.connection import close_db
from src.transport.moth_publisher import get_publisher as get_moth_publisher


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


def require_internal_caller(x_cowater_internal: str | None) -> None:
    if str(x_cowater_internal or "").strip() != INTERNAL_CALLER_HEADER:
        raise HTTPException(status_code=403, detail="system agent only")


components = build_registry_components()
registry = components.registry
alert_registry = components.alert_registry
event_registry = components.event_registry
a2a_log_registry = components.a2a_log_registry
policy_registry = components.policy_registry
domain_registry = components.domain_registry
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
        "alert_severities": list(ALERT_SEVERITIES.__args__),
        "alerts": {
            "ingest": "/alerts/ingest",
            "list": "/alerts",
            "ack": "/alerts/{alert_id}/ack",
        },
        "device_roles": "/device-roles",
        "operation_plans": "/operation-plans",
        "insights": "/insights",
        "approvals": "/approvals",
        "mission_proposals": "/mission-proposals",
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


@app.post("/alerts/ingest", status_code=status.HTTP_201_CREATED)
def ingest_alert(request: AlertIngestRequest) -> dict[str, Any]:
    alert = alert_registry.ingest_alert(request)
    result = alert.to_dict()
    _schedule_background_task(get_moth_publisher().publish("alerts", [a.to_dict() for a in alert_registry.list_alerts()]))
    return result


@app.post("/events/ingest", status_code=status.HTTP_201_CREATED)
def ingest_event(request: EventIngestRequest) -> dict[str, Any]:
    event = event_registry.ingest_event(request)
    result = event.to_dict()
    _schedule_background_task(get_moth_publisher().publish("events", [e.to_dict() for e in event_registry.list_events()]))
    return result


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


@app.get("/alerts")
def list_alerts(
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    return [alert.to_dict() for alert in alert_registry.list_alerts(limit=limit, offset=offset)]


@app.get("/alerts/{alert_id}")
def get_alert(alert_id: str) -> dict[str, Any]:
    try:
        return alert_registry.get_alert(alert_id).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="alert not found") from exc


@app.post("/alerts/{alert_id}/ack")
def acknowledge_alert(alert_id: str, request: AlertAckRequest) -> dict[str, Any]:
    try:
        result = alert_registry.acknowledge_alert(alert_id, approved=request.approved, notes=request.notes).to_dict()
        _schedule_background_task(get_moth_publisher().publish("alerts", [a.to_dict() for a in alert_registry.list_alerts()]))
        return result
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="alert not found") from exc


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
def create_policy(body: dict[str, Any], x_cowater_internal: str | None = Header(default=None)) -> dict[str, Any]:
    """정책 생성 (Ch.17.1)"""
    require_internal_caller(x_cowater_internal)
    result = policy_registry.create_policy(body)
    _schedule_background_task(get_moth_publisher().publish("policies", policy_registry.get_policies()))
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
def update_policy(policy_id: str, body: dict[str, Any], x_cowater_internal: str | None = Header(default=None)) -> dict[str, Any]:
    """정책 업데이트"""
    require_internal_caller(x_cowater_internal)
    result = policy_registry.update_policy(policy_id, body)
    _schedule_background_task(get_moth_publisher().publish("policies", policy_registry.get_policies()))
    return result


@app.delete("/policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_policy(policy_id: str, x_cowater_internal: str | None = Header(default=None)) -> Response:
    """정책 삭제"""
    require_internal_caller(x_cowater_internal)
    policy_registry.delete_policy(policy_id)
    _schedule_background_task(get_moth_publisher().publish("policies", policy_registry.get_policies()))
    return Response(status_code=204)


@app.get("/device-roles")
def list_device_roles(
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    return [item.to_dict() for item in domain_registry.list_device_roles(limit=limit, offset=offset)]


@app.get("/device-roles/{device_id}")
def get_device_role(device_id: str) -> dict[str, Any]:
    try:
        return domain_registry.get_device_role(device_id).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="device role not found") from exc


@app.put("/devices/{device_id}/role")
def upsert_device_role(
    device_id: str,
    body: dict[str, Any],
    x_cowater_internal: str | None = Header(default=None),
) -> dict[str, Any]:
    require_internal_caller(x_cowater_internal)
    return domain_registry.upsert_device_role(device_id, body).to_dict()


@app.post("/operation-plans", status_code=status.HTTP_201_CREATED)
def create_operation_plan(body: dict[str, Any]) -> dict[str, Any]:
    return domain_registry.create_operation_plan(body).to_dict()


@app.get("/operation-plans")
def list_operation_plans(
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    return [item.to_dict() for item in domain_registry.list_operation_plans(limit=limit, offset=offset)]


@app.get("/operation-plans/{operation_plan_id}")
def get_operation_plan(operation_plan_id: str) -> dict[str, Any]:
    try:
        return domain_registry.get_operation_plan(operation_plan_id).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="operation plan not found") from exc


@app.post("/operation-plans/{operation_plan_id}/activate")
def activate_operation_plan(
    operation_plan_id: str,
    x_cowater_internal: str | None = Header(default=None),
) -> dict[str, Any]:
    require_internal_caller(x_cowater_internal)
    try:
        plan = domain_registry.get_operation_plan(operation_plan_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="operation plan not found") from exc
    updated = domain_registry.create_operation_plan({**plan.to_dict(), "status": "active"})
    return updated.to_dict()


@app.post("/insights", status_code=status.HTTP_201_CREATED)
def create_insight(body: dict[str, Any]) -> dict[str, Any]:
    return domain_registry.create_insight(body).to_dict()


@app.get("/insights")
def list_insights(
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    return [item.to_dict() for item in domain_registry.list_insights(limit=limit, offset=offset)]


@app.get("/insights/{insight_id}")
def get_insight(insight_id: str) -> dict[str, Any]:
    try:
        return domain_registry.get_insight(insight_id).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="insight not found") from exc


@app.post("/approvals", status_code=status.HTTP_201_CREATED)
def create_approval(body: dict[str, Any]) -> dict[str, Any]:
    result = domain_registry.create_approval(body).to_dict()
    _schedule_background_task(get_moth_publisher().publish("approvals", [item.to_dict() for item in domain_registry.list_approvals()]))
    return result


@app.get("/approvals")
def list_approvals(
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    return [item.to_dict() for item in domain_registry.list_approvals(limit=limit, offset=offset)]


@app.get("/approvals/{approval_id}")
def get_approval(approval_id: str) -> dict[str, Any]:
    try:
        return domain_registry.get_approval(approval_id).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="approval not found") from exc


@app.post("/approvals/{approval_id}/decision")
def decide_approval(approval_id: str, body: dict[str, Any]) -> dict[str, Any]:
    approved = bool(body.get("approved"))
    decided_by = str(body.get("decided_by") or "user")
    notes = body.get("notes")
    try:
        approval = domain_registry.decide_approval(
            approval_id,
            approved,
            decided_by=decided_by,
            notes=notes,
        )
        result = approval.to_dict()
        _schedule_background_task(get_moth_publisher().publish("approvals", [item.to_dict() for item in domain_registry.list_approvals()]))
        return result
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="approval not found") from exc


@app.post("/mission-proposals", status_code=status.HTTP_201_CREATED)
def create_mission_proposal(body: dict[str, Any]) -> dict[str, Any]:
    result = domain_registry.create_mission_proposal(body).to_dict()
    _schedule_background_task(get_moth_publisher().publish("mission_proposals", [item.to_dict() for item in domain_registry.list_mission_proposals()]))
    return result


@app.get("/mission-proposals")
def list_mission_proposals(
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    return [item.to_dict() for item in domain_registry.list_mission_proposals(limit=limit, offset=offset)]


@app.get("/mission-proposals/{proposal_id}")
def get_mission_proposal(proposal_id: str) -> dict[str, Any]:
    try:
        return domain_registry.get_mission_proposal(proposal_id).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="mission proposal not found") from exc


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
    mission_id: str | None = None
    title: str | None = None
    mission_type: str | None = None
    goal: str | None = None
    summary: str | None = None
    source: str | None = None
    alert_id: str | None = None
    event_id: str | None = None
    operation_plan_id: str | None = None
    proposal_id: str | None = None
    approval_id: str | None = None
    insight_id: str | None = None
    status: str | None = None
    steps: list[dict[str, Any]] = Field(default_factory=list)
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    logs: list[dict[str, Any]] = Field(default_factory=list)
    device_execution_results: list[dict[str, Any]] = Field(default_factory=list)
    final_result: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    approved_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


@app.post("/missions", status_code=status.HTTP_201_CREATED)
def create_mission(
    body: MissionCreateRequest | None = Body(None),
    alert_id: str = Query(None),
    event_id: str = Query(None),
) -> dict[str, Any]:
    """새 Mission 생성 또는 전체 상태 upsert"""
    body = body or MissionCreateRequest()
    mission_payload = body.model_dump()
    mission_payload["alert_id"] = mission_payload.get("alert_id") or alert_id
    mission_payload["event_id"] = mission_payload.get("event_id") or event_id
    if not mission_payload.get("title"):
        mission_payload["title"] = "Mission"
    if not mission_payload.get("mission_type"):
        mission_payload["mission_type"] = "generic_mission"
    if not mission_payload.get("status"):
        mission_payload["status"] = "pending_approval"
    mission = domain_registry.create_mission(mission_payload)
    result = mission.to_dict()
    async def publish_mission():
        await get_moth_publisher().publish("missions", [m.to_dict() for m in domain_registry.list_missions()])
        await get_moth_publisher().publish(f"mission.{mission.mission_id}", result)
    _schedule_background_task(publish_mission())
    return result


@app.get("/missions")
def list_missions(
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    return [m.to_dict() for m in domain_registry.list_missions(limit=limit, offset=offset)]


@app.get("/missions/status/{status}")
def list_missions_by_status(status: str) -> list[dict[str, Any]]:
    return [m.to_dict() for m in domain_registry.list_missions() if str(m.status) == status]


@app.get("/missions/stats")
def get_mission_stats() -> dict[str, Any]:
    missions = domain_registry.list_missions()
    return {
        "total": len(missions),
        "pending_approval": len([m for m in missions if m.status == "pending_approval"]),
        "approved": len([m for m in missions if m.status == "approved"]),
        "running": len([m for m in missions if m.status == "running"]),
        "completed": len([m for m in missions if m.status == "completed"]),
        "failed": len([m for m in missions if m.status == "failed"]),
        "rejected": len([m for m in missions if m.status == "rejected"]),
        "canceled": len([m for m in missions if m.status == "canceled"]),
    }


@app.get("/missions/{mission_id}")
def get_mission(mission_id: str) -> dict[str, Any]:
    try:
        mission = domain_registry.get_mission(mission_id)
        return mission.to_dict()
    except KeyError:
        raise HTTPException(status_code=404, detail="mission not found")


@app.put("/missions/{mission_id}")
def replace_mission(mission_id: str, body: dict[str, Any]) -> dict[str, Any]:
    existing = None
    try:
        existing = domain_registry.get_mission(mission_id).to_dict()
    except KeyError:
        existing = {}
    mission = domain_registry.create_mission(
        {
            **existing,
            **body,
            "mission_id": mission_id,
            "updated_at": utc_now_iso(),
        }
    )
    result = mission.to_dict()
    async def publish_mission():
        await get_moth_publisher().publish("missions", [m.to_dict() for m in domain_registry.list_missions()])
        await get_moth_publisher().publish(f"mission.{mission_id}", result)
    _schedule_background_task(publish_mission())
    return result


@app.get("/missions/{mission_id}/timeline")
def get_mission_timeline(mission_id: str) -> list[dict[str, Any]]:
    """Mission Timeline 조회 (Ch.18-20)"""
    try:
        mission = domain_registry.get_mission(mission_id)
        timeline = mission.timeline if hasattr(mission, 'timeline') else []
        return [evt.to_dict() if hasattr(evt, 'to_dict') else evt for evt in timeline]
    except KeyError:
        raise HTTPException(status_code=404, detail="mission not found")


@app.post("/missions/{mission_id}/timeline/append")
def append_mission_timeline(mission_id: str, body: dict[str, Any] | None = Body(None)) -> dict[str, Any]:
    """Mission Timeline에 이벤트 추가 (Ch.18-20)"""
    body = body or {}
    try:
        event_type = str(body.get("event_type") or "unknown")
        actor = str(body.get("actor") or "system")
        details = body.get("details") or {}
        task_id = body.get("task_id")
        step_index = body.get("step_index")

        domain_registry.append_mission_timeline_event(
            mission_id=mission_id,
            event_type=event_type,
            actor=actor,
            details=details,
            task_id=str(task_id) if task_id else None,
            step_index=str(step_index) if step_index else None,
        )

        mission = domain_registry.get_mission(mission_id)
        result = {"appended": True, "mission_id": mission_id, "event_type": event_type}
        _schedule_background_task(get_moth_publisher().publish(f"mission.{mission_id}", mission.to_dict()))
        return result
    except KeyError:
        raise HTTPException(status_code=404, detail="mission not found")
    except Exception as e:
        logger.warning(f"Failed to append timeline event: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to append timeline event: {str(e)}")


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
    event_count = len(event_registry.list_events())
    mission_count = len(domain_registry.list_missions())
    
    registry.reset()
    alert_registry.reset()
    event_registry.reset()
    domain_registry.reset()
    policy_registry.reset()
    a2a_log_registry.reset()

    logger.info(
        f"Registry 초기화 완료: "
        f"devices={device_count}, alerts={alert_count}, "
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
            "device_roles": [d.to_dict() for d in domain_registry.list_device_roles()],
            "operation_plans": [p.to_dict() for p in domain_registry.list_operation_plans()],
            "insights": [i.to_dict() for i in domain_registry.list_insights()],
            "approvals": [a.to_dict() for a in domain_registry.list_approvals()],
            "mission_proposals": [p.to_dict() for p in domain_registry.list_mission_proposals()],
            "missions": [m.to_dict() for m in domain_registry.list_missions()],
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
        mission = domain_registry.get_mission(mission_id)
        
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
