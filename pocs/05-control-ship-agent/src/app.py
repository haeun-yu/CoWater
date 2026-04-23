from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import uvicorn
from fastapi import FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.json"
CONFIG_PATH = Path(os.getenv("COWATER_CONTROL_SHIP_CONFIG_PATH", str(DEFAULT_CONFIG_PATH)))
DEFAULT_SERVER_HOST = "127.0.0.1"
DEFAULT_SERVER_PORT = 9011
DEFAULT_AGENT_ID = "control_ship-01"
DEFAULT_AGENT_ROLE = "control_ship"
DEFAULT_PARENT_ID = "control_center-01"
DEFAULT_PARENT_ENDPOINT = "http://127.0.0.1:9012"
DEFAULT_CORS_ORIGINS = ["*"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_runtime_config(config_path: Path) -> dict[str, Any]:
    raw = _load_json_file(config_path)
    server_cfg = raw.get("server") or {}
    agent_cfg = raw.get("agent") or {}
    cors_cfg = raw.get("cors") or {}

    host = str(server_cfg.get("host") or DEFAULT_SERVER_HOST)
    port = int(server_cfg.get("port") or DEFAULT_SERVER_PORT)
    cors_origins = cors_cfg.get("allow_origins") or DEFAULT_CORS_ORIGINS
    if isinstance(cors_origins, str):
        cors_origins = [origin.strip() for origin in cors_origins.split(",") if origin.strip()]
    if not isinstance(cors_origins, list) or not cors_origins:
        cors_origins = list(DEFAULT_CORS_ORIGINS)

    return {
        "config_path": str(config_path),
        "server": {"host": host, "port": port},
        "cors": {"allow_origins": cors_origins},
        "agent": {
            "id": str(agent_cfg.get("id") or DEFAULT_AGENT_ID),
            "role": str(agent_cfg.get("role") or DEFAULT_AGENT_ROLE),
            "parent_id": str(agent_cfg.get("parent_id") or DEFAULT_PARENT_ID),
            "parent_endpoint": str(agent_cfg.get("parent_endpoint") or DEFAULT_PARENT_ENDPOINT).rstrip("/"),
            "direct_route_allowed": bool(agent_cfg.get("direct_route_allowed", True)),
        },
    }


@dataclass
class ChildAgentRecord:
    agent_id: str
    role: str
    endpoint: Optional[str] = None
    capabilities: List[str] = field(default_factory=list)
    status: str = "unknown"
    last_seen_at: Optional[str] = None
    notes: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MessageRecord:
    message_id: str
    message_type: str
    from_agent_id: str
    to_agent_id: str
    task_id: Optional[str] = None
    conversation_id: Optional[str] = None
    role: Optional[str] = None
    scope: Optional[str] = None
    priority: str = "normal"
    ttl: int = 60
    payload: dict[str, Any] = field(default_factory=dict)
    route_hint: Optional[dict[str, Any]] = None
    received_at: Optional[str] = None
    routed_via: Optional[str] = None
    status: str = "received"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ControlShipState:
    agent_id: str
    role: str
    parent_id: str
    parent_endpoint: str
    direct_route_allowed: bool
    connected: bool = True
    connected_at: str = field(default_factory=utc_now_iso)
    last_seen_at: str = field(default_factory=utc_now_iso)
    children: List[ChildAgentRecord] = field(default_factory=list)
    inbox: List[MessageRecord] = field(default_factory=list)
    outbox: List[MessageRecord] = field(default_factory=list)
    dispatches: List[dict[str, Any]] = field(default_factory=list)
    memory: List[dict[str, Any]] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)

    def remember(self, item: dict[str, Any]) -> None:
        self.memory.append(item)
        self.memory = self.memory[-100:]

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "role": self.role,
            "parent_id": self.parent_id,
            "parent_endpoint": self.parent_endpoint,
            "direct_route_allowed": self.direct_route_allowed,
            "connected": self.connected,
            "connected_at": self.connected_at,
            "last_seen_at": self.last_seen_at,
            "children": [item.to_dict() for item in self.children],
            "inbox": [item.to_dict() for item in self.inbox[-50:]],
            "outbox": [item.to_dict() for item in self.outbox[-50:]],
            "dispatches": list(self.dispatches[-50:]),
            "memory": list(self.memory[-25:]),
            "context": self.context,
        }


class ChildAgentInput(BaseModel):
    agent_id: str
    role: str
    endpoint: Optional[str] = None
    capabilities: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class A2AMessageInput(BaseModel):
    message_type: str
    message_id: Optional[str] = None
    conversation_id: Optional[str] = None
    task_id: Optional[str] = None
    from_agent_id: str
    to_agent_id: str
    role: Optional[str] = None
    scope: Optional[str] = None
    priority: str = "normal"
    ttl: int = 60
    payload: Dict[str, Any] = Field(default_factory=dict)
    route_hint: Optional[dict[str, Any]] = None


class DispatchInput(BaseModel):
    target_agent_id: str
    target_endpoint: Optional[str] = None
    message: A2AMessageInput


class ControlShipHub:
    def __init__(self, settings: dict[str, Any]) -> None:
        agent = settings["agent"]
        self.settings = settings
        self.state = ControlShipState(
            agent_id=agent["id"],
            role=agent["role"],
            parent_id=agent["parent_id"],
            parent_endpoint=agent["parent_endpoint"],
            direct_route_allowed=agent["direct_route_allowed"],
        )
        self._child_index: Dict[str, ChildAgentRecord] = {}

    def register_child(self, payload: ChildAgentInput) -> ChildAgentRecord:
        child = ChildAgentRecord(
            agent_id=payload.agent_id,
            role=payload.role,
            endpoint=payload.endpoint,
            capabilities=list(payload.capabilities),
            status="registered",
            last_seen_at=utc_now_iso(),
            notes=payload.notes,
        )
        self._child_index[child.agent_id] = child
        self.state.children = list(self._child_index.values())
        self.state.remember({"kind": "child.registered", "at": utc_now_iso(), "child": child.to_dict()})
        return child

    def heartbeat_child(self, agent_id: str) -> ChildAgentRecord:
        child = self._child_index.get(agent_id)
        if child is None:
            raise KeyError(agent_id)
        child.status = "online"
        child.last_seen_at = utc_now_iso()
        self.state.children = list(self._child_index.values())
        self.state.remember({"kind": "child.heartbeat", "at": utc_now_iso(), "agent_id": agent_id})
        return child

    def _record_message(self, payload: A2AMessageInput, routed_via: Optional[str] = None, status_text: str = "received") -> MessageRecord:
        record = MessageRecord(
            message_id=payload.message_id or f"msg-{len(self.state.inbox) + len(self.state.outbox) + 1}",
            message_type=payload.message_type,
            from_agent_id=payload.from_agent_id,
            to_agent_id=payload.to_agent_id,
            task_id=payload.task_id,
            conversation_id=payload.conversation_id,
            role=payload.role,
            scope=payload.scope,
            priority=payload.priority,
            ttl=payload.ttl,
            payload=payload.payload,
            route_hint=payload.route_hint,
            received_at=utc_now_iso(),
            routed_via=routed_via,
            status=status_text,
        )
        return record

    def ingest_message(self, payload: A2AMessageInput, routed_via: Optional[str] = None) -> dict[str, Any]:
        record = self._record_message(payload, routed_via=routed_via)
        self.state.inbox.append(record)
        self.state.last_seen_at = utc_now_iso()
        self.state.remember({"kind": "a2a.inbox", "at": utc_now_iso(), "message": record.to_dict()})

        response_status = "accepted"
        out_messages: List[MessageRecord] = []
        if payload.message_type == "task.assign":
            dispatch_targets = list(payload.payload.get("targets") or [])
            if dispatch_targets:
                for target in dispatch_targets:
                    target_id = str(target.get("agent_id") or target.get("id") or "")
                    if not target_id:
                        continue
                    out_msg = MessageRecord(
                        message_id=f"dispatch-{len(self.state.dispatches) + 1}",
                        message_type="task.assign",
                        from_agent_id=self.state.agent_id,
                        to_agent_id=target_id,
                        task_id=payload.task_id,
                        conversation_id=payload.conversation_id,
                        role=target.get("role"),
                        scope=payload.scope,
                        priority=payload.priority,
                        ttl=payload.ttl,
                        payload={"parent_task": record.to_dict(), "command": payload.payload},
                        route_hint={"preferred_route": "direct" if self.state.direct_route_allowed else "parent"},
                        received_at=utc_now_iso(),
                        routed_via=self.state.agent_id,
                        status="planned",
                    )
                    out_messages.append(out_msg)
                    self.state.dispatches.append(out_msg.to_dict())
            ack = MessageRecord(
                message_id=f"ack-{record.message_id}",
                message_type="task.accept",
                from_agent_id=self.state.agent_id,
                to_agent_id=payload.from_agent_id,
                task_id=payload.task_id,
                conversation_id=payload.conversation_id,
                role=self.state.role,
                scope=payload.scope,
                priority=payload.priority,
                ttl=payload.ttl,
                payload={"accepted": True, "children": len(dispatch_targets)},
                received_at=utc_now_iso(),
                routed_via=self.state.agent_id,
                status="accepted",
            )
            out_messages.append(ack)
        elif payload.message_type == "status.report":
            response_status = "reported"
        elif payload.message_type == "task.complete":
            response_status = "completed"

        self.state.outbox.extend(out_messages)
        self._report_upstream(record, out_messages)
        return {
            "status": response_status,
            "agent": self.state.to_dict(),
            "accepted": record.to_dict(),
            "outbox": [msg.to_dict() for msg in out_messages],
        }

    def _report_upstream(self, record: MessageRecord, out_messages: List[MessageRecord]) -> None:
        if not self.state.parent_endpoint:
            return
        report = {
            "message_type": "status.report",
            "message_id": f"report-{record.message_id}",
            "conversation_id": record.conversation_id,
            "task_id": record.task_id,
            "from_agent_id": self.state.agent_id,
            "to_agent_id": self.state.parent_id,
            "role": self.state.role,
            "scope": record.scope,
            "priority": record.priority,
            "ttl": record.ttl,
            "payload": {
                "status": record.status,
                "accepted": record.message_type == "task.assign",
                "dispatches": [msg.to_dict() for msg in out_messages],
                "original": record.to_dict(),
            },
            "route_hint": {"preferred_route": "upstream"},
        }
        try:
            _post_json(f"{self.state.parent_endpoint.rstrip('/')}/a2a/inbox", report)
            self.state.remember({"kind": "a2a.report", "at": utc_now_iso(), "target": self.state.parent_endpoint, "payload": report})
        except Exception as exc:
            self.state.remember({"kind": "a2a.report_failed", "at": utc_now_iso(), "error": str(exc)})

    def dispatch(self, payload: DispatchInput) -> dict[str, Any]:
        record = self._record_message(payload.message, routed_via=self.state.agent_id, status_text="dispatching")
        self.state.dispatches.append(record.to_dict())
        target = payload.target_endpoint or self._child_index.get(payload.target_agent_id, ChildAgentRecord(payload.target_agent_id, "unknown")).endpoint
        if target:
            _post_json(f"{target.rstrip('/')}/a2a/inbox", payload.message.model_dump())
            record.status = "sent"
        else:
            record.status = "queued"
        self.state.outbox.append(record)
        self.state.remember({"kind": "dispatch", "at": utc_now_iso(), "target": payload.target_agent_id, "status": record.status})
        return record.to_dict()

    def reset(self) -> None:
        self.state.children = []
        self.state.inbox = []
        self.state.outbox = []
        self.state.dispatches = []
        self.state.memory = []
        self.state.context = {}
        self._child_index = {}


def _post_json(url: str, payload: dict[str, Any], timeout: float = 5.0) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if not raw:
                return {}
            return json.loads(raw.decode("utf-8"))
    except HTTPError as exc:
        detail = ""
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("detail", "")
        except Exception:
            pass
        raise RuntimeError(detail or f"HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(str(exc)) from exc


APP_SETTINGS = load_runtime_config(CONFIG_PATH)
hub = ControlShipHub(APP_SETTINGS)

app = FastAPI(title="CoWater Control Ship Agent", version="0.1.0")
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
        "agent": APP_SETTINGS["agent"],
        "config_path": APP_SETTINGS["config_path"],
        "cors": APP_SETTINGS["cors"],
        "message_types": [
            "task.assign",
            "task.accept",
            "task.progress",
            "task.complete",
            "task.fail",
            "task.escalate",
            "status.report",
        ],
    }


@app.get("/state")
def state() -> dict[str, Any]:
    return hub.state.to_dict()


@app.get("/children")
def list_children() -> list[dict[str, Any]]:
    return [child.to_dict() for child in hub.state.children]


@app.post("/children/register", status_code=status.HTTP_201_CREATED)
def register_child(request: ChildAgentInput) -> dict[str, Any]:
    return hub.register_child(request).to_dict()


@app.post("/children/{agent_id}/heartbeat")
def heartbeat_child(agent_id: str) -> dict[str, Any]:
    try:
        return hub.heartbeat_child(agent_id).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="child agent not found") from exc


@app.get("/inbox")
def inbox() -> list[dict[str, Any]]:
    return [item.to_dict() for item in hub.state.inbox]


@app.get("/outbox")
def outbox() -> list[dict[str, Any]]:
    return [item.to_dict() for item in hub.state.outbox]


@app.get("/dispatches")
def dispatches() -> list[dict[str, Any]]:
    return list(hub.state.dispatches)


@app.post("/a2a/inbox")
def a2a_inbox(request: A2AMessageInput) -> dict[str, Any]:
    return hub.ingest_message(request)


@app.post("/dispatch")
def dispatch(request: DispatchInput) -> dict[str, Any]:
    try:
        return hub.dispatch(request)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/reset")
def reset() -> dict[str, str]:
    hub.reset()
    return {"status": "reset"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", help="Override bind host from config/env")
    parser.add_argument("--port", type=int, help="Override bind port from config/env")
    args = parser.parse_args()
    uvicorn.run(
        "src.app:app",
        host=args.host or APP_SETTINGS["server"]["host"],
        port=args.port or APP_SETTINGS["server"]["port"],
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
