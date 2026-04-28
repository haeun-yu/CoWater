from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from agent.decision import DecisionEngine
from agent.manifest import ManifestBuilder
from agent.state import AgentState, utc_now
from controller.commands import CommandController
from simulator.device import DeviceSimulator
from skills.catalog import SkillCatalog
from storage.identity_store import IdentityStore
from tools.command_executor import CommandExecutor
from tools.telemetry_reader import TelemetryReader
from transport.registry_client import RegistryClient


class AgentRuntime:
    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self.config = json.loads(config_path.read_text(encoding="utf-8"))
        self.server = self.config.get("server", {})
        self.agent_config = self.config.get("agent", {})
        self.capabilities = self.agent_config.get("capabilities", {})
        self.instance_id = self._resolve_instance_id()
        self.identity_store = IdentityStore(config_path.parent / ".runtime", self.instance_id)
        self.identity = self.identity_store.read()
        self.skills = SkillCatalog(self.capabilities)
        self.manifest_builder = ManifestBuilder(self.config, self.skills)
        self.state = AgentState(
            agent_id=self.identity.get("agent_id") or f"{self.agent_config.get('id', 'agent')}-{self.instance_id}",
            role=str(self.agent_config.get("role") or "device_agent"),
            layer=str(self.agent_config.get("layer") or "lower"),
            device_type=self.agent_config.get("device_type"),
            instance_id=self.instance_id,
            name=self.identity.get("name") or f"{self.agent_config.get('name', 'CoWater Agent')} {self.instance_id}",
        )
        self.registry_client = RegistryClient(self.config.get("registry", {}))
        self.decision_engine = DecisionEngine(self.agent_config, self.skills)
        self.telemetry_reader = TelemetryReader()
        self.simulator = DeviceSimulator(self.config.get("simulation", {}), self.skills.list_tracks())
        self.command_controller = CommandController(CommandExecutor())

    def _resolve_instance_id(self) -> str:
        explicit = os.getenv("COWATER_INSTANCE_ID") or self.agent_config.get("instance_id")
        if explicit:
            return str(explicit)
        return f"{int(time.time())}-{os.getpid()}-{uuid4().hex[:6]}"

    def base_url(self) -> str:
        host = str(self.server.get("public_host") or self.server.get("host") or "127.0.0.1")
        port = int(os.getenv("COWATER_AGENT_PORT") or self.server.get("port") or 9010)
        return f"http://{host}:{port}"

    def register(self) -> None:
        if self.state.layer == "system":
            self.state.connected = True
            return

        if self.identity.get("registry_id") and self.identity.get("token"):
            self.state.registry_id = int(self.identity["registry_id"])
            self.state.token = str(self.identity["token"])
            self.state.registered_at = self.identity.get("registered_at")
            try:
                self._upsert_agent()
                self.state.connected = True
                self.state.last_seen_at = utc_now()
                return
            except Exception:
                self.state.remember({"kind": "identity_reconnect_failed", "at": utc_now()})

        created = self.registry_client.register_device(
            self.state.name,
            self.skills.list_tracks(),
            self.skills.list_actions(),
        )
        self.state.registry_id = int(created["id"])
        self.state.token = str(created["token"])
        self.state.registered_at = utc_now()
        self.state.connected = True
        self.state.last_seen_at = utc_now()
        self._upsert_agent()
        self.identity_store.write(
            {
                "agent_id": self.state.agent_id,
                "name": self.state.name,
                "registry_id": self.state.registry_id,
                "token": self.state.token,
                "registered_at": self.state.registered_at,
            }
        )

    def _upsert_agent(self) -> None:
        if self.state.registry_id is None or not self.state.token:
            raise RuntimeError("agent identity is not registered")
        self.registry_client.upsert_agent(
            self.state.registry_id,
            endpoint=self.base_url(),
            command_endpoint=f"{self.base_url()}/agents/{self.state.token}/command",
            role=self.state.role,
            llm_enabled=bool(self.agent_config.get("llm", {}).get("enabled", False)),
            skills=self.skills.list_skills(),
            actions=self.skills.list_actions(),
            last_seen_at=self.state.last_seen_at,
        )

    async def simulation_loop(self) -> None:
        if self.state.layer == "system":
            return
        while True:
            await asyncio.sleep(self.simulator.interval_seconds())
            telemetry = self.telemetry_reader.normalize(self.simulator.next_telemetry(self.state))
            self.state.last_seen_at = utc_now()
            self.state.last_telemetry = telemetry
            decision = self.decision_engine.decide(self.state, telemetry)
            self.state.remember({"kind": "telemetry", "at": utc_now(), "decision": decision})

    def apply_command(self, command: dict[str, Any]) -> dict[str, Any]:
        return self.command_controller.apply(self.state, command)

