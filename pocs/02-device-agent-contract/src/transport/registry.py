from __future__ import annotations

# 디바이스별 에이전트 세션을 관리하고 03 등록 서버와 동기화한다.

from typing import Any, Dict, List, Optional
from urllib.parse import quote

from fastapi import WebSocket

from ..agents import DeviceAgentBase, create_agent
from ..core.decision import DecisionLayer
from ..core.execution import ExecutionLayer
from ..core.feedback import FeedbackLayer
from ..core.models import DeviceAgentStateRecord, utc_now_iso
from ..core.planner import PlannerLayer
from .registry_client import RegistryAgentRegistration, RegistryClient


class AgentHub:
    def __init__(
        self,
        profiles: dict[str, dict[str, Any]],
        *,
        registry_client: Optional[RegistryClient] = None,
        public_host: str = "127.0.0.1",
        public_port: int = 9010,
    ) -> None:
        self._profiles = profiles
        self._sessions: Dict[str, DeviceAgentStateRecord] = {}
        self._agents: Dict[str, DeviceAgentBase] = {}
        self._planner = PlannerLayer()
        self._decision_layer = DecisionLayer()
        self._execution_layer = ExecutionLayer()
        self._feedback_layer = FeedbackLayer()
        self._registry_client = registry_client
        self._public_host = public_host
        self._public_port = public_port

    def ensure_session(self, token: str) -> DeviceAgentStateRecord:
        session = self._sessions.get(token)
        if session is None:
            session = DeviceAgentStateRecord(token=token)
            self._sessions[token] = session
        return session

    def ensure_agent(self, token: str, device_type: Optional[str] = None) -> DeviceAgentBase:
        agent = self._agents.get(token)
        session = self._sessions.get(token)
        normalized = (device_type or (session.device_type if session else None) or "usv").lower()
        if agent is None or agent.device_type != normalized:
            agent = create_agent(normalized, self._profiles)
            self._agents[token] = agent
        return agent

    def _agent_ws_endpoint(self, token: str) -> str:
        return f"ws://{self._public_host}:{self._public_port}/agents/{quote(token)}"

    def _agent_command_endpoint(self, token: str) -> str:
        return f"http://{self._public_host}:{self._public_port}/agents/{quote(token)}/command"

    def list_sessions(self) -> List[DeviceAgentStateRecord]:
        return [self._sessions[token] for token in sorted(self._sessions)]

    def get_session(self, token: str) -> DeviceAgentStateRecord:
        session = self._sessions.get(token)
        if session is None:
            raise KeyError(token)
        return session

    def set_identity(
        self,
        token: str,
        *,
        device_id: Optional[str] = None,
        device_name: Optional[str] = None,
        device_type: Optional[str] = None,
        registry_id: Optional[int] = None,
    ) -> DeviceAgentStateRecord:
        session = self.ensure_session(token)
        if device_id:
            session.device_id = device_id
        if device_name:
            session.device_name = device_name
        if device_type:
            session.device_type = device_type.lower()
        if registry_id is not None:
            session.registry_id = registry_id
        agent = self.ensure_agent(token, session.device_type)
        agent.apply_profile(session)
        session.context["agent"] = {
            "type": session.device_type,
            "llm_enabled": session.llm_enabled,
        }
        return session

    def attach_websocket(self, token: str, websocket: WebSocket) -> DeviceAgentStateRecord:
        session = self.ensure_session(token)
        session.websocket = websocket
        session.connected = True
        session.connected_at = session.connected_at or utc_now_iso()
        session.last_seen_at = utc_now_iso()
        return session

    def detach_websocket(self, token: str) -> None:
        session = self._sessions.get(token)
        if session is None:
            return
        session.websocket = None
        session.connected = False
        session.last_seen_at = utc_now_iso()

    async def sync_registry(self, token: str) -> None:
        if self._registry_client is None:
            return
        session = self._sessions.get(token)
        if session is None or session.registry_id is None:
            return
        try:
            device = await self._registry_client.fetch_device(session.registry_id)
            session.context["registry_device"] = device
            if not session.device_name and device.get("name"):
                session.device_name = device["name"]
        except Exception:
            device = None
        registration = RegistryAgentRegistration(
            secret_key=self._registry_client.secret_key,
            endpoint=self._agent_ws_endpoint(token),
            command_endpoint=self._agent_command_endpoint(token),
            role=session.device_type or "device",
            llm_enabled=session.llm_enabled,
            skills=list(session.skills),
            available_actions=list(session.available_actions),
            connected=session.connected,
            last_seen_at=session.last_seen_at,
            device_name=session.device_name,
            device_type=session.device_type,
        )
        try:
            updated = await self._registry_client.upsert_agent(session.registry_id, registration)
            session.registry_endpoint = updated.get("agent", {}).get("endpoint", registration.endpoint)
            session.registry_command_endpoint = updated.get("agent", {}).get("command_endpoint", registration.command_endpoint)
            session.registry_token = updated.get("token")
            if updated.get("name"):
                session.device_name = updated["name"]
            if device is None:
                session.context["registry_device"] = updated
        except Exception:
            pass

    async def detach_registry(self, token: str) -> None:
        if self._registry_client is None:
            return
        session = self._sessions.get(token)
        if session is None or session.registry_id is None:
            return
        try:
            await self._registry_client.detach_agent(session.registry_id)
        except Exception:
            pass

    async def ingest_message(self, token: str, message: dict[str, Any]) -> List[dict[str, Any]]:
        session = self.ensure_session(token)
        session.last_seen_at = utc_now_iso()
        session.remember({"kind": "inbound", "at": session.last_seen_at, "message": message})

        envelope = message.get("envelope") if isinstance(message, dict) else None
        payload = message.get("payload") if isinstance(message, dict) else None
        if isinstance(envelope, dict) and isinstance(payload, dict):
            session.last_stream = envelope.get("stream")
            session.last_payload = payload
            session.context["last_envelope"] = envelope
            if not session.device_type:
                session.device_type = str(envelope.get("device_type") or "usv").lower()
            agent = self.ensure_agent(token, session.device_type)
            agent.apply_profile(session)
            recommendations = agent.recommend(session, envelope, payload)
            plan = self._planner.plan(session, envelope, payload, recommendations)
            decision = self._decision_layer.decide(session, plan)
            self._feedback_layer.record(
                session,
                source="telemetry",
                plan=plan.to_dict(),
                decision=decision.to_dict() if decision else None,
            )
            session.recommendations.extend(recommendations)
            session.remember({"kind": "recommendation", "at": utc_now_iso(), "count": len(recommendations)})
            await self.sync_registry(token)
            return [item.to_dict() for item in recommendations]

        kind = message.get("kind") if isinstance(message, dict) else None
        if kind == "hello":
            self.set_identity(
                token,
                device_id=message.get("device_id"),
                device_name=message.get("device_name"),
                device_type=message.get("device_type"),
                registry_id=message.get("registry_id"),
            )
            await self.sync_registry(token)
        elif kind == "command":
            session.pending_commands.append(message)
        return []

    async def send_command(self, token: str, command: dict[str, Any]) -> bool:
        session = self._sessions.get(token)
        if session is None:
            return False
        execution = await self._execution_layer.execute(session, command, source="external")
        self._feedback_layer.record(
            session,
            source="command",
            decision=dict(command),
            execution=execution.to_dict(),
            note="manual command request",
        )
        if not execution.delivered:
            return False
        return True
