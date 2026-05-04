from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import urllib.error
import urllib.request
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
        self.event_rules = self.config.get("event_rules", {})
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
        self._last_assignment_signature: dict[str, Any] | None = None

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
        if self.identity.get("registry_id") and self.identity.get("token"):
            self.state.registry_id = int(self.identity["registry_id"])
            self.state.token = str(self.identity["token"])
            self.state.registered_at = self.identity.get("registered_at")
            try:
                self._upsert_agent()
                self._registration_response = self.registry_client.get_device(self.state.registry_id)
                self._refresh_assignment()
                self.state.connected = True
                self.state.last_seen_at = utc_now()
                return
            except Exception:
                self.state.remember({"kind": "identity_reconnect_failed", "at": utc_now()})

        created = self.registry_client.register_device(
            self.state.name,
            self.skills.list_tracks(),
            self.skills.list_actions(),
            device_type=self.agent_config.get("device_type"),
            layer=self.agent_config.get("layer"),
            connectivity=self.agent_config.get("connectivity"),
            location=self.config.get("simulation", {}).get("start_position"),
        )
        self.state.registry_id = int(created["id"])
        self.state.token = str(created["token"])
        self.state.registered_at = utc_now()
        self.state.connected = True
        self.state.last_seen_at = utc_now()
        self._upsert_agent()
        self._refresh_assignment()
        self.identity_store.write(
            {
                "agent_id": self.state.agent_id,
                "name": self.state.name,
                "registry_id": self.state.registry_id,
                "token": self.state.token,
                "registered_at": self.state.registered_at,
            }
        )

    def apply_assignment(self, assignment: dict[str, Any]) -> None:
        signature = {
            "parent_id": assignment.get("parent_id"),
            "parent_endpoint": assignment.get("parent_endpoint"),
            "parent_command_endpoint": assignment.get("parent_command_endpoint"),
            "route_mode": str(assignment.get("route_mode") or "direct_to_system"),
            "force_parent_routing": bool(assignment.get("force_parent_routing", False)),
        }
        self.state.parent_id = assignment.get("parent_id")
        self.state.parent_endpoint = assignment.get("parent_endpoint")
        self.state.parent_command_endpoint = assignment.get("parent_command_endpoint")
        self.state.route_mode = str(signature["route_mode"])
        self.state.force_parent_routing = bool(signature["force_parent_routing"])
        if self._last_assignment_signature != signature:
            self.state.remember({"kind": "layer_assignment", "at": utc_now(), "assignment": assignment})
            self._last_assignment_signature = signature

    def _refresh_assignment(self) -> None:
        if self.state.registry_id is None:
            return
        try:
            self.apply_assignment(self.registry_client.get_assignment(self.state.registry_id))
        except Exception as exc:
            self.state.remember({"kind": "assignment_refresh_failed", "at": utc_now(), "error": str(exc)})

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
            await asyncio.gather(
                self._alert_processing_loop(),
                self._registry_keepalive_loop(),
            )
        else:
            await self._telemetry_processing_loop()

    async def _registry_keepalive_loop(self) -> None:
        """System Agent는 Registry keepalive로 last_seen_at을 갱신한다."""
        interval = max(1, int(self.config.get("registry", {}).get("heartbeat_interval_seconds", 1)))
        logger = logging.getLogger(__name__)

        while True:
            await asyncio.sleep(interval)
            if self.state.registry_id is None or not self.state.token:
                continue
            try:
                self.state.last_seen_at = utc_now()
                self._upsert_agent()
            except Exception as exc:
                logger.debug(f"System Agent keepalive failed: {exc}")

    async def _telemetry_processing_loop(self) -> None:
        while True:
            await asyncio.sleep(self.simulator.interval_seconds())
            telemetry = self.telemetry_reader.normalize(self.simulator.next_telemetry(self.state))
            self.state.last_seen_at = utc_now()
            self.state.last_telemetry = telemetry
            decision = self.decision_engine.decide(self.state, telemetry)
            self.state.remember({"kind": "telemetry", "at": utc_now(), "decision": decision})

    async def _alert_processing_loop(self) -> None:
        """System-layer agent alert processing loop"""
        logger = logging.getLogger(__name__)
        processed_alerts = set()
        poll_interval = 2  # Poll every 2 seconds
        middle_layer_agents = {}  # Cache of middle-layer agents

        while True:
            try:
                await asyncio.sleep(poll_interval)
                self.state.last_seen_at = utc_now()

                # Periodically refresh middle-layer agent cache
                try:
                    all_devices = self.registry_client.list_devices()
                    middle_layer_agents = {
                        d["id"]: d for d in all_devices
                        if d.get("layer") == "middle" and d.get("connected")
                    }
                except Exception as e:
                    logger.debug(f"Failed to fetch device list: {e}")

                # Fetch all alerts from registry
                try:
                    alerts = self.registry_client.list_alerts()
                except Exception as e:
                    logger.debug(f"Failed to fetch alerts: {e}")
                    continue

                # Process unprocessed waiting alerts
                for alert in alerts:
                    alert_id = alert.get("alert_id")
                    status = alert.get("status")

                    # Only process waiting alerts that haven't been processed yet
                    if status != "waiting" or alert_id in processed_alerts:
                        continue

                    logger.info(f"Processing alert {alert_id}: {alert.get('alert_type')}")
                    processed_alerts.add(alert_id)
                    await self._process_alert(alert, middle_layer_agents, logger)

            except Exception as e:
                logger.error(f"Alert processing loop error: {e}")
                await asyncio.sleep(1)

    async def _process_alert(self, alert: dict[str, Any], middle_layer_agents: dict[int, dict[str, Any]], logger: Any) -> dict[str, Any]:
        """단일 alert를 승인/응답/전파까지 처리한다."""
        alert_id = alert.get("alert_id")
        decision = self.decision_engine.decide(self.state, alert)
        self.state.remember({"kind": "alert_processed", "at": utc_now(), "alert_id": alert_id, "decision": decision})
        logger.info(f"Alert {alert_id} decision: {decision}")

        response = {
            "response_id": str(uuid4()),
            "alert_id": alert_id,
            "action": "mission.assign",
            "target_agent_id": None,
            "status": "planned",
            "reason": f"System Agent response to {alert.get('alert_type')}",
            "dispatch_result": {}
        }
        alert_type = alert.get("alert_type")
        metadata = alert.get("metadata", {})

        if alert_type == "mine_detection":
            control_ship = None
            for _, device in middle_layer_agents.items():
                if "control" in device.get("name", "").lower():
                    control_ship = device
                    break
            if control_ship:
                agent_info = control_ship.get("agent", {}) if isinstance(control_ship.get("agent"), dict) else {}
                target_agent_id = agent_info.get("agent_id") or str(control_ship["id"])
                response["target_agent_id"] = target_agent_id
                response["action"] = "task.assign"
                response["params"] = {
                    "action": "survey_depth",
                    "location": metadata.get("location", {}),
                    "mission_type": "mine_clearance",
                    "target_device_id": control_ship["id"]
                }
                logger.info(f"Routing mine detection to Control Ship {control_ship['id']}")

        if not response.get("target_agent_id"):
            recommended_action = str(alert.get("recommended_action") or "")
            if "survey" in recommended_action.lower() and middle_layer_agents:
                target = next(iter(middle_layer_agents.values()))
                response["target_agent_id"] = str(target.get("id"))
                response["action"] = "task.assign"
                response["params"] = {
                    "action": "survey_depth",
                    "location": metadata.get("location", {}),
                    "mission_type": "mine_survey",
                    "target_device_id": target["id"]
                }

        try:
            self.registry_client.acknowledge_alert(str(alert_id), approved=True, notes="System Agent approved")
            logger.info(f"Alert {alert_id} acknowledged")
        except Exception as e:
            logger.warning(f"Failed to acknowledge alert {alert_id}: {e}")

        try:
            self.registry_client.ingest_response(response)
            logger.info(f"Response {response['response_id']} ingested for alert {alert_id}")
        except Exception as e:
            logger.warning(f"Failed to ingest response: {e}")

        if response.get("target_agent_id"):
            dispatch = await self._send_a2a_task(response["target_agent_id"], middle_layer_agents, response, logger)
            response["dispatch_result"] = dispatch
            if dispatch.get("delivered"):
                response["status"] = "completed"
                response["task_id"] = dispatch.get("task_id")
            else:
                response["status"] = "failed"
                response["notes"] = dispatch.get("error")
            try:
                self.registry_client.ingest_response(response)
            except Exception as e:
                logger.warning(f"Failed to update response status: {e}")
        return response

    async def _send_a2a_task(
        self,
        target_agent_id: str,
        agents_cache: dict[int, dict[str, Any]],
        response: dict[str, Any],
        logger: Any,
    ) -> dict[str, Any]:
        """Send A2A message to target agent to execute the task"""
        # Find target agent in cache
        target_agent = None
        for agent in agents_cache.values():
            try:
                agent_info = agent.get("agent") or {}
                if not isinstance(agent_info, dict):
                    agent_info = {}
                agent_id_from_info = agent_info.get("agent_id") or ""
                device_id = str(agent.get("id") or "")

                if str(agent_id_from_info) == str(target_agent_id) or device_id == str(target_agent_id):
                    target_agent = agent
                    break
            except Exception as e:
                logger.debug(f"Error checking agent {agent.get('id')}: {e}")
                continue

        if not target_agent:
            logger.debug(f"Target agent {target_agent_id} not found in cache, skipping A2A")
            return {"delivered": False, "error": "target_not_found"}

        # Build A2A message with task details
        try:
            agent_info = target_agent.get("agent") or {}
            if not isinstance(agent_info, dict):
                agent_info = {}
            endpoint = agent_info.get("endpoint")
        except Exception:
            endpoint = None

        if not endpoint:
            logger.warning(f"Target agent {target_agent_id} has no endpoint")
            return {"delivered": False, "error": "target_endpoint_missing"}

        try:
            a2a_message = {
                "jsonrpc": "2.0",
                "method": "message/send",
                "id": str(uuid4()),
                "params": {
                    "message": {
                        "role": "user",
                        "parts": [
                            {
                                "type": "data",
                                "data": {
                                    "message_type": "task.assign",
                                    "action": response.get("params", {}).get("action", "survey_depth"),
                                    "params": response.get("params", {}),
                                    "reason": response.get("reason", "System Agent assignment"),
                                    "alert_id": response.get("alert_id"),
                                    "response_id": response.get("response_id")
                                }
                            }
                        ]
                    },
                    "taskId": response.get("response_id"),
                    "metadata": {}
                }
            }

            # Send POST request to target agent
            data = json.dumps(a2a_message).encode("utf-8")
            req = urllib.request.Request(
                endpoint,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read() or b"{}")
                logger.info(f"A2A task sent to {target_agent_id}: {result.get('result', {}).get('status', 'unknown')}")
                return {
                    "delivered": True,
                    "endpoint": endpoint,
                    "task_id": response.get("response_id"),
                    "a2a_result": result,
                }
        except urllib.error.HTTPError as e:
            logger.warning(f"HTTP error sending A2A to {target_agent_id}: {e.code}")
            return {"delivered": False, "error": f"http_{e.code}", "endpoint": endpoint}
        except urllib.error.URLError as e:
            logger.warning(f"Network error sending A2A to {target_agent_id}: {e.reason}")
            return {"delivered": False, "error": f"network_{e.reason}", "endpoint": endpoint}
        except Exception as e:
            logger.warning(f"Failed to send A2A task to {target_agent_id}: {e}")
            return {"delivered": False, "error": str(e), "endpoint": endpoint}

    def apply_command(self, command: dict[str, Any]) -> dict[str, Any]:
        return self.command_controller.apply(self.state, command)

    def classify_event_severity(self, event: dict[str, Any]) -> str:
        raw = str(event.get("severity") or "").strip().upper()
        aliases = {
            "CRITICAL": "CRITICAL",
            "WARNING": "WARNING",
            "WARN": "WARNING",
            "INFO": "INFORMATION",
            "INFORMATION": "INFORMATION",
        }
        if raw in aliases:
            return aliases[raw]

        event_type = str(event.get("event_type") or "").strip().lower()
        rule = self.event_rules.get(event_type, {})
        configured = str(rule.get("severity") or "").strip().upper()
        if configured in aliases:
            return aliases[configured]
        return "INFORMATION"

    def recommended_action_for_event(self, event_type: str, severity: str) -> str | None:
        event_type = str(event_type).strip().lower()
        rule = self.event_rules.get(event_type, {})
        action = rule.get("recommended_action")
        if isinstance(action, str) and action.strip():
            return action.strip()
        if severity == "CRITICAL":
            return "escalate_alert"
        return None

    def handle_event_report(self, event: dict[str, Any]) -> dict[str, Any]:
        severity = self.classify_event_severity(event)
        event_type = str(event.get("event_type") or event.get("type") or "unknown")
        event_id = str(event.get("event_id") or f"event-{uuid4()}")
        source_agent_id = event.get("source_agent_id") or event.get("detected_by") or event.get("agent_id")
        source_role = event.get("source_role") or event.get("role")
        message = str(event.get("message") or f"{event_type} reported")
        metadata = dict(event.get("metadata") or {})
        if "location" in event and "location" not in metadata:
            metadata["location"] = event["location"]
        metadata.setdefault("raw_event", dict(event))

        event_record = {
            "event_id": event_id,
            "source_system": "a2a",
            "source_agent_id": source_agent_id,
            "source_role": source_role,
            "event_type": event_type,
            "severity": severity,
            "message": message,
            "metadata": metadata,
        }
        stored_event = self.registry_client.ingest_event(event_record)

        alert_record = {
            "event_id": event_id,
            "source_system": "system_agent",
            "source_agent_id": source_agent_id,
            "source_role": source_role,
            "alert_type": event_type,
            "severity": severity,
            "message": message,
            "recommended_action": self.recommended_action_for_event(event_type, severity),
            "metadata": metadata,
        }
        stored_alert = self.registry_client.ingest_alert(alert_record)
        try:
            devices = self.registry_client.list_devices()
            middle_layer_agents = {
                d["id"]: d for d in devices
                if d.get("layer") == "middle" and d.get("connected")
            }
            loop = asyncio.get_running_loop()
            loop.create_task(self._process_alert(stored_alert, middle_layer_agents, logging.getLogger(__name__)))
        except Exception:
            # fallback: polling loop will process waiting alerts
            pass

        self.state.remember(
            {
                "kind": "event_report_processed",
                "at": utc_now(),
                "event_id": event_id,
                "alert_id": stored_alert.get("alert_id"),
                "event_type": event_type,
                "severity": severity,
            }
        )
        return {
            "received": True,
            "message_type": "event.report",
            "event_id": stored_event.get("event_id"),
            "alert_id": stored_alert.get("alert_id"),
            "severity": severity,
        }

    def handle_mission_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        """중간/하위 에이전트의 임무 수행 결과를 수신해 response 원장에 최종 반영한다."""
        response_id = str(payload.get("response_id") or "")
        alert_id = str(payload.get("alert_id") or "")
        reporter = str(payload.get("source_agent_id") or payload.get("reporter") or "unknown")
        execution_status = str(payload.get("execution_status") or "completed").lower()
        execution_log = payload.get("execution_log") or {}

        if not response_id:
            return {"received": False, "message_type": "mission.result", "error": "response_id required"}

        normalized_status = "completed" if execution_status == "completed" else "failed"
        try:
            existing = self.registry_client.get_response(response_id)
            response_record = {
                "response_id": response_id,
                "alert_id": existing.get("alert_id") or alert_id,
                "action": existing.get("action") or "task.assign",
                "target_agent_id": existing.get("target_agent_id"),
                "target_endpoint": existing.get("target_endpoint"),
                "route_mode": existing.get("route_mode") or "direct_to_system",
                "status": normalized_status,
                "reason": existing.get("reason") or f"Mission result from {reporter}",
                "task_id": existing.get("task_id") or response_id,
                "dispatch_result": dict(existing.get("dispatch_result") or {}),
                "notes": f"Mission result from {reporter}",
            }
            response_record["dispatch_result"]["execution_result"] = {
                "reporter": reporter,
                "status": normalized_status,
                "payload": execution_log,
            }
            self.registry_client.ingest_response(response_record)
        except Exception as exc:
            self.state.remember(
                {
                    "kind": "mission_result_update_failed",
                    "at": utc_now(),
                    "response_id": response_id,
                    "error": str(exc),
                }
            )
            return {"received": False, "message_type": "mission.result", "error": str(exc)}

        self.state.remember(
            {
                "kind": "mission_result_received",
                "at": utc_now(),
                "response_id": response_id,
                "alert_id": alert_id,
                "reporter": reporter,
                "status": normalized_status,
            }
        )
        return {
            "received": True,
            "message_type": "mission.result",
            "response_id": response_id,
            "status": normalized_status,
        }
