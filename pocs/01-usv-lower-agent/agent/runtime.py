from __future__ import annotations

import asyncio
import importlib
import json
import logging
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
from transport.moth_publisher import MothPublisher

logger = logging.getLogger(__name__)


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
        # ← NEW: Moth Publisher for telemetry streaming
        self.moth_publisher = MothPublisher(self.config, self.state)
        # ← NEW: Load tools dynamically
        self.tools: dict[str, Any] = {}
        self._load_tools()

    def _load_tools(self) -> None:
        """Dynamically load tool classes from tools directory"""
        tools_dir = self.config_path.parent / "tools"
        if not tools_dir.exists():
            return

        for py_file in tools_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            module_name = py_file.stem
            # Convert snake_case to PascalCase: battery_monitor → BatteryMonitor
            class_name = "".join(word.capitalize() for word in module_name.split("_"))
            try:
                module = importlib.import_module(f"tools.{module_name}")
                cls = getattr(module, class_name, None)
                if cls:
                    self.tools[module_name] = cls()
                    logger.debug(f"Loaded tool: {module_name} ({class_name})")
            except Exception as e:
                logger.debug(f"Failed to load tool {module_name}: {e}")

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
        # ← NEW: Initialize Moth topics from registration response
        asyncio.create_task(self.moth_publisher.initialize(created))
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
            # System layer: only heartbeat, no telemetry
            asyncio.create_task(self.moth_publisher.heartbeat_loop())
            return

        # ← NEW: Start Moth connection and heartbeat loop
        await self.moth_publisher.connect()
        asyncio.create_task(self.moth_publisher._reconnect_loop())
        asyncio.create_task(self.moth_publisher.heartbeat_loop())

        while True:
            await asyncio.sleep(self.simulator.interval_seconds())
            telemetry = self.telemetry_reader.normalize(self.simulator.next_telemetry(self.state))
            self.state.last_seen_at = utc_now()
            self.state.last_telemetry = telemetry

            # ← ENHANCED: Update tools from telemetry (realistic sensor simulation)
            self._update_tools_from_telemetry(telemetry)

            decision = self.decision_engine.decide(self.state, telemetry)
            self.state.remember({"kind": "telemetry", "at": utc_now(), "decision": decision})

            # ← ENHANCED: Apply decision recommendations to tools
            self._apply_decision_to_tools(decision)

            # ← NEW: Publish telemetry to Moth
            await self.moth_publisher.publish_telemetry(telemetry)

    def _update_tools_from_telemetry(self, telemetry: dict[str, Any]) -> None:
        """Update tool states based on telemetry (enhances realism)"""
        # GPS: update position from telemetry
        if "gps_reader" in self.tools and "position" in telemetry:
            pos = telemetry["position"]
            if isinstance(pos, dict) and "latitude" in pos and "longitude" in pos:
                self.tools["gps_reader"].update_position(
                    pos["latitude"],
                    pos["longitude"],
                    pos.get("altitude", 0.0),
                )

        # Battery: simulate discharge based on power consumption
        if "battery_monitor" in self.tools:
            # Estimate consumption: 0.3% per iteration at cruising, more under heavy load
            motor_status = self.tools.get("motor_control", {}).get_status() if "motor_control" in self.tools else {}
            thrust_magnitude = abs(motor_status.get("forward_thrust", 0.0)) if motor_status else 0.0
            consumption = 0.2 + (thrust_magnitude * 0.3)  # 0.2-0.5% per iteration
            self.tools["battery_monitor"].discharge(consumption)

        # IMU: update orientation from motion
        if "imu_reader" in self.tools and "motion" in telemetry:
            motion = telemetry["motion"]
            if isinstance(motion, dict):
                # Heading from telemetry's heading or COG
                heading = motion.get("heading") or telemetry.get("navigation", {}).get("cog", 0.0)
                self.tools["imu_reader"].set_orientation(
                    roll=motion.get("roll", 0.0),
                    pitch=motion.get("pitch", 0.0),
                    yaw=float(heading),
                )

    def _apply_decision_to_tools(self, decision: dict[str, Any]) -> None:
        """Apply decision recommendations to tools for realistic feedback loop"""
        for rec in decision.get("recommendations", []):
            action = rec.get("action")
            params = rec.get("params", {})

            if action == "slow_down" and "motor_control" in self.tools:
                target_speed = params.get("target_speed_mps", 2.0)
                max_thrust = target_speed / 10.0  # Rough conversion
                self.tools["motor_control"].set_thrust(max(0.0, max_thrust), 0.0)

            elif action == "stop" and "motor_control" in self.tools:
                self.tools["motor_control"].stop()

            elif action == "change_heading" and "motor_control" in self.tools:
                # Heading change: apply yaw thrust
                heading_delta = params.get("heading_degrees", 0.0)
                yaw_thrust = max(-1.0, min(1.0, heading_delta / 45.0))
                current_status = self.tools["motor_control"].get_status()
                self.tools["motor_control"].set_thrust(current_status["forward_thrust"], yaw_thrust)

            elif action == "return_to_base" and "motor_control" in self.tools:
                # Return to base: full forward thrust
                self.tools["motor_control"].set_thrust(1.0, 0.0)

    def apply_command(self, command: dict[str, Any]) -> dict[str, Any]:
        return self.command_controller.apply(self.state, command)

