from __future__ import annotations

# ────────────────────────────────────────────────────────────────────────────
# 02 디바이스 에이전트 허브
# FastAPI 앱, WebSocket 텔레메트리 스트림, A2A 메시지 엔드포인트를 통합한다.
#
# A2A 구조:
#   - POST /message:send   : 05(control_ship) 또는 06(control_center)로부터 task.assign 수신
#   - GET  /.well-known/agent-card.json : A2A Discovery
#   - task.assign 수신 → 디바이스에 명령 전달 → reply_endpoint로 task.complete 보고
#   - reply_endpoint는 메시지 payload에 포함; 발신자가 05든 06이든 무관하게 처리
# ────────────────────────────────────────────────────────────────────────────

import asyncio
import argparse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from .core.models import DeviceCommandRequest
from .profiles import CONFIG_PATH, load_runtime_config
from .transport.registry import AgentHub
from .transport.registry_client import RegistryClient


# ────────────────────────────────────────────────────────────────────────────
# 설정 로딩
# ────────────────────────────────────────────────────────────────────────────

APP_SETTINGS = load_runtime_config(CONFIG_PATH)
_KEEPALIVE_INTERVAL = 25.0
_KEEPALIVE_PAYLOAD = b"ping"

_agent_cfg = APP_SETTINGS.get("agent") or {}
_AGENT_ID   = str(_agent_cfg.get("id")   or "device-hub-01")
_AGENT_ROLE = str(_agent_cfg.get("role") or "device_hub")


# ────────────────────────────────────────────────────────────────────────────
# 디바이스 허브 초기화
# ────────────────────────────────────────────────────────────────────────────

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


# ────────────────────────────────────────────────────────────────────────────
# A2A 인메모리 상태
# 수신 inbox, 발신 outbox, task 추적 딕셔너리를 인메모리로 관리한다 (PoC 수준).
# ────────────────────────────────────────────────────────────────────────────

_a2a_inbox: List[dict] = []
_a2a_outbox: List[dict] = []
_a2a_tasks: Dict[str, dict] = {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_task(task_id: str, state: str = "submitted") -> dict:
    """새 Task 레코드를 생성하고 _a2a_tasks에 등록한다."""
    task = {
        "id": task_id,
        "status": {"state": state},
        "createdAt": _utc_now(),
        "updatedAt": _utc_now(),
        "artifacts": [],
        "history": [],
    }
    _a2a_tasks[task_id] = task
    return task


def _touch_task(task_id: str, state: str, artifact: Optional[dict] = None) -> None:
    """Task 상태를 갱신하고 선택적으로 아티팩트를 추가한다."""
    task = _a2a_tasks.get(task_id)
    if not task:
        return
    task["status"]["state"] = state
    task["updatedAt"] = _utc_now()
    if artifact:
        task["artifacts"].append({"name": "result", "parts": [{"type": "data", "data": artifact}]})


# ────────────────────────────────────────────────────────────────────────────
# A2A Pydantic 입력 모델
# ────────────────────────────────────────────────────────────────────────────

class A2APartInput(BaseModel):
    """A2A 메시지의 part 한 요소. type은 'text' 또는 'data'."""
    type: str
    text: Optional[str] = None
    data: Optional[dict] = None
    mime_type: Optional[str] = Field(default=None, alias="mimeType")


class A2AMessageEnvelopeInput(BaseModel):
    """POST /message:send 의 message 필드. role과 parts 배열로 구성된다."""
    role: str
    parts: List[A2APartInput]


class SendMessageRequest(BaseModel):
    """
    POST /message:send 요청 바디.
    A2A 표준 send message 바인딩에 대응하며, taskId/contextId는 camelCase alias를 허용한다.
    """
    model_config = ConfigDict(populate_by_name=True)
    message: A2AMessageEnvelopeInput
    task_id: Optional[str] = Field(default=None, alias="taskId")
    context_id: Optional[str] = Field(default=None, alias="contextId")


# ────────────────────────────────────────────────────────────────────────────
# 비동기 HTTP 헬퍼
# ────────────────────────────────────────────────────────────────────────────

async def _post_json(url: str, payload: dict, timeout: float = 5.0) -> dict:
    """JSON POST 요청을 보내고 응답을 dict로 반환한다. 실패 시 빈 dict."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json() if resp.content else {}
    except Exception:
        return {}


async def _send_a2a_message(endpoint: str, data: dict) -> dict:
    """
    지정된 endpoint의 /message:send 로 A2A 메시지를 발송한다.
    endpoint는 base URL이며, /message:send 경로를 자동 추가한다.
    """
    url = endpoint.rstrip("/") + "/message:send"
    envelope = {
        "message": {
            "role": "agent",
            "parts": [{"type": "data", "data": data}],
        }
    }
    return await _post_json(url, envelope)


# ────────────────────────────────────────────────────────────────────────────
# Agent Card / Manifest 빌더
# ────────────────────────────────────────────────────────────────────────────

def _build_agent_card() -> dict:
    """
    A2A Discovery 표준 Agent Card를 반환한다.
    /.well-known/agent-card.json 에서 노출된다.
    """
    base_url = f"http://{APP_SETTINGS['server']['host']}:{APP_SETTINGS['server']['port']}"
    return {
        "name": _AGENT_ID,
        "displayName": "CoWater Device Agent Hub",
        "description": (
            "Per-device Agent hub for USV, AUV, and ROV telemetry sessions. "
            "Accepts A2A task.assign from any parent agent (control_ship or control_center) "
            "and relays commands to connected devices via WebSocket."
        ),
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
                "description": (
                    "Accept A2A task.assign (from control_ship or control_center) and relay "
                    "the command to the target device session identified by token."
                ),
            },
        ],
    }


def _build_agent_manifest() -> dict:
    """
    상위 에이전트에 자신을 등록할 때 사용하는 내부 능력 명세를 반환한다.
    /agents/register 엔드포인트가 이 형식을 반환한다.
    """
    base_url = f"http://{APP_SETTINGS['server']['host']}:{APP_SETTINGS['server']['port']}"
    profiles = APP_SETTINGS.get("profiles", {})
    return {
        "agent_id": _AGENT_ID,
        "role": _AGENT_ROLE,
        "mode": "dynamic",
        "endpoint": base_url,
        "command_endpoint": f"{base_url}/message:send",
        "skills": ["stream_ingest", "rule_recommendation", "command_relay"],
        "tools": ["websocket_relay", "device_registry", "rule_engine"],
        "constraints": ["requires_registered_token", "device_types: usv, auv, rov"],
        "available_actions": ["task.assign", "task.accept", "task.complete", "status.report"],
        "supported_inputs": ["application/json"],
        "supported_outputs": ["application/json"],
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
            "device_types": list(profiles.keys()),
        },
        "updated_at": _utc_now(),
    }


# ────────────────────────────────────────────────────────────────────────────
# A2A 메시지 처리 — task.assign 핵심 로직
# ────────────────────────────────────────────────────────────────────────────

def _extract_data(parts: List[A2APartInput]) -> dict:
    """parts 배열에서 실제 데이터를 추출한다. type='data' 우선, 없으면 type='text'."""
    for part in parts:
        if part.type == "data" and isinstance(part.data, dict):
            return part.data
    for part in parts:
        if part.type == "text" and part.text:
            return {"text": part.text}
    return {}


async def _handle_task_assign(data: dict, task_id: str, context_id: str) -> dict:
    """
    task.assign 수신 시 처리 흐름:
      1. payload에서 token(디바이스)·action·params 추출
      2. hub.send_command()로 해당 디바이스에 명령 전달
      3. reply_endpoint(payload 또는 route_hint에 포함)로 task.complete / status.report 비동기 보고

    reply_endpoint 결정 우선순위:
      payload["reply_endpoint"] > route_hint["reply_to"] > (없으면 보고 생략)

    이 설계 덕분에 발신자가 PoC 05(control_ship)든 PoC 06(control_center)든
    동일한 방식으로 처리할 수 있다.
    """
    token          = str(data.get("token") or "")
    action         = str(data.get("action") or data.get("command") or "")
    params: dict   = data.get("params") or {}
    from_agent_id  = str(data.get("from_agent_id") or data.get("sender_id") or "unknown")
    # 발신자가 응답을 받을 HTTP 엔드포인트 (메시지에 포함; 05/06 어느 쪽이든 동작)
    reply_endpoint = (
        data.get("reply_endpoint")
        or (data.get("route_hint") or {}).get("reply_to")
        or ""
    )

    # task.accept ACK 구성 — /message:send 응답에 포함
    ack = {
        "message_type": "task.accept",
        "message_id": str(uuid4()),
        "task_id": task_id,
        "conversation_id": context_id,
        "from_agent_id": _AGENT_ID,
        "to_agent_id": from_agent_id,
        "payload": {"accepted": True, "token": token, "action": action},
    }
    _a2a_outbox.append(ack)
    _touch_task(task_id, "working")

    # 디바이스 명령 전달 및 결과 보고를 비동기로 수행 (LLM 미사용, 규칙 기반 즉시 처리)
    async def _deliver_and_report() -> None:
        delivered = False
        error_msg = ""

        if token and action:
            command = {
                "action": action,
                "params": params,
                "reason": f"A2A task.assign from {from_agent_id}",
            }
            try:
                delivered = await hub.send_command(token, command)
            except Exception as exc:
                error_msg = str(exc)

        final_state = "completed" if delivered else "failed"
        report_type = "task.complete" if delivered else "status.report"
        _touch_task(task_id, final_state, {"delivered": delivered, "token": token, "action": action})

        if reply_endpoint:
            report = {
                "message_type": report_type,
                "message_id": str(uuid4()),
                "task_id": task_id,
                "conversation_id": context_id,
                "from_agent_id": _AGENT_ID,
                "to_agent_id": from_agent_id,
                "payload": {
                    "delivered": delivered,
                    "token": token,
                    "action": action,
                    "error": error_msg or None,
                },
            }
            _a2a_outbox.append(report)
            await _send_a2a_message(reply_endpoint, report)

    asyncio.create_task(_deliver_and_report())
    return ack


# ────────────────────────────────────────────────────────────────────────────
# 기본 엔드포인트
# ────────────────────────────────────────────────────────────────────────────

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
        "runtime_note": (
            "Each device type has its own Agent class; "
            "a profile with LLM configuration uses hybrid decision logic, "
            "otherwise it falls back to rule-based planning."
        ),
    }


# ────────────────────────────────────────────────────────────────────────────
# A2A Discovery 엔드포인트
# ────────────────────────────────────────────────────────────────────────────

@app.get("/.well-known/agent-card.json")
def agent_card() -> dict[str, Any]:
    """A2A 표준 Agent Card. 외부 에이전트가 이 허브의 능력을 discovery할 때 사용한다."""
    return _build_agent_card()


@app.get("/.well-known/agent.json")
def agent_card_legacy() -> dict[str, Any]:
    """agent-card.json 의 legacy alias."""
    return _build_agent_card()


@app.get("/agents/register")
def agent_manifest() -> dict[str, Any]:
    """
    상위 에이전트(05/06)가 이 허브를 child로 등록할 때 참조하는 manifest를 반환한다.
    상위 에이전트는 이 응답을 POST /children/register 에 전달하거나 직접 사용한다.
    """
    return _build_agent_manifest()


# ────────────────────────────────────────────────────────────────────────────
# A2A 메시지 엔드포인트
# ────────────────────────────────────────────────────────────────────────────

@app.post("/message:send")
async def message_send(request: SendMessageRequest) -> dict[str, Any]:
    """
    A2A 표준 메시지 수신 엔드포인트.

    발신자가 PoC 05(control_ship)이든 PoC 06(control_center)이든 동일하게 처리한다.
    메시지 payload의 reply_endpoint로 처리 결과를 돌려보낸다.

    지원 message_type:
      - task.assign  : 디바이스 명령 실행 후 task.complete / status.report 보고
      - status.report: 수신 기록만 남김
      - 기타         : inbox에 기록
    """
    task_id    = request.task_id    or str(uuid4())
    context_id = request.context_id or task_id

    task = _new_task(task_id, "submitted")
    task["message"] = request.message.model_dump(by_alias=True)

    data = _extract_data(request.message.parts)
    _a2a_inbox.append({
        "task_id": task_id,
        "context_id": context_id,
        "received_at": _utc_now(),
        "role": request.message.role,
        "data": data,
    })

    msg_type = str(data.get("message_type") or data.get("type") or "task.assign")

    if msg_type == "task.assign":
        result = await _handle_task_assign(data, task_id, context_id)
        _touch_task(task_id, "working", result)
    elif msg_type == "status.report":
        _touch_task(task_id, "completed", {"status": "acknowledged"})
        result = {"message_type": "status.report", "acknowledged": True}
    else:
        _touch_task(task_id, "completed", {"status": "received", "type": msg_type})
        result = {"message_type": msg_type, "received": True}

    return {"task": _a2a_tasks[task_id]}


@app.get("/tasks")
async def list_tasks(status: Optional[str] = None) -> dict[str, Any]:
    """
    수신된 A2A Task 목록을 반환한다.
    status 쿼리 파라미터로 submitted / working / completed / failed 필터링 가능.
    """
    tasks = list(_a2a_tasks.values())
    if status:
        tasks = [t for t in tasks if t.get("status", {}).get("state") == status]
    return {"tasks": tasks, "nextPageToken": ""}


@app.get("/tasks/{task_id}")
async def get_task(task_id: str) -> dict[str, Any]:
    """Task를 ID로 조회한다."""
    task = _a2a_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    return {"task": task}


@app.get("/a2a/inbox")
async def a2a_inbox() -> dict[str, Any]:
    """수신된 A2A 메시지 inbox를 반환한다 (최근 50건)."""
    return {"inbox": _a2a_inbox[-50:], "count": len(_a2a_inbox)}


@app.get("/a2a/outbox")
async def a2a_outbox() -> dict[str, Any]:
    """발신된 A2A 메시지 outbox를 반환한다 (최근 50건)."""
    return {"outbox": _a2a_outbox[-50:], "count": len(_a2a_outbox)}


# ────────────────────────────────────────────────────────────────────────────
# 디바이스 세션 REST 엔드포인트 (기존)
# ────────────────────────────────────────────────────────────────────────────

@app.get("/agents")
async def list_agents() -> list[dict[str, Any]]:
    """현재 허브에 연결된 디바이스 세션 목록을 반환한다."""
    return [session.to_dict() for session in hub.list_sessions()]


@app.get("/agents/{token}")
async def get_agent(token: str) -> dict[str, Any]:
    """토큰으로 특정 디바이스 세션을 조회한다."""
    try:
        return hub.get_session(token).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="agent not found") from exc


@app.post("/agents/{token}/command")
async def send_agent_command(token: str, request: DeviceCommandRequest) -> dict[str, Any]:
    """
    REST 방식으로 디바이스에 직접 명령을 전달한다.
    A2A /message:send 를 사용할 수 없는 레거시 클라이언트용.
    """
    command = request.model_dump()
    delivered = await hub.send_command(token, command)
    if not delivered:
        raise HTTPException(status_code=409, detail="agent is not connected")
    return {"status": "sent", "token": token, "command": command}


# ────────────────────────────────────────────────────────────────────────────
# WebSocket 디바이스 스트림 엔드포인트
# ────────────────────────────────────────────────────────────────────────────

@app.websocket("/agents/{token}")
async def device_agent_socket(token: str, websocket: WebSocket) -> None:
    """
    디바이스(USV/AUV/ROV)와의 WebSocket 세션을 관리한다.

    연결 시 hello 메시지를 전송하고, 수신된 텔레메트리를 AgentHub로 넘긴다.
    _KEEPALIVE_INTERVAL 마다 ping 바이트를 전송해 연결을 유지한다.
    종료 시 레지스트리에서 등록 해제하고 WebSocket을 분리한다.
    """
    await websocket.accept()
    session = hub.attach_websocket(token, websocket)
    await websocket.send_json(
        {
            "kind": "hello",
            "agent": "cowater-device-agent-hub",
            "token": token,
            "profiles": list(APP_SETTINGS["profiles"].keys()),
            "a2a_endpoint": f"http://{APP_SETTINGS['server']['host']}:{APP_SETTINGS['server']['port']}/message:send",
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
            await hub.ingest_message(token, message)
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


# ────────────────────────────────────────────────────────────────────────────
# 서버 진입점
# ────────────────────────────────────────────────────────────────────────────

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
