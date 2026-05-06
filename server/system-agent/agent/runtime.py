from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import datetime
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
        self._mission_lock = asyncio.Lock()
        self._device_allocations: dict[int, dict[str, Any]] = {}
        self._waiting_queue: dict[str, dict[str, Any]] = {}

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
        interval = max(1, int(self.config.get("registry", {}).get("healthcheck_interval_seconds",
                                       1)))
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
        poll_interval = 2
        all_devices: list[dict[str, Any]] = []

        while True:
            try:
                await asyncio.sleep(poll_interval)
                self.state.last_seen_at = utc_now()

                try:
                    all_devices = self.registry_client.list_devices()
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
                    await self._process_alert(alert, all_devices, logger)

                await self._process_waiting_queue(all_devices, logger)

            except Exception as e:
                logger.error(f"Alert processing loop error: {e}")
                await asyncio.sleep(1)

    async def _process_waiting_queue(self, devices: list[dict[str, Any]], logger: Any) -> None:
        if not self._waiting_queue:
            return
        ordered_items = sorted(
            self._waiting_queue.items(),
            key=lambda item: (
                self._severity_rank(str((item[1].get("alert") or {}).get("severity") or "INFORMATION")),
                str(item[1].get("queued_at") or ""),
            ),
        )
        for response_id, queue_item in ordered_items:
            if not isinstance(queue_item, dict):
                continue
            await self._reprocess_waiting_response(response_id, queue_item, devices, logger)

    async def _process_alert(self, alert: dict[str, Any], devices: list[dict[str, Any]], logger: Any) -> dict[str, Any]:
        """단일 alert를 승인/응답/전파까지 처리한다."""
        # Critical 긴급 상황 — LLM 없이 즉각 에스컬레이션
        if self.decision_engine.is_critical_urgent(alert):
            critical = self.decision_engine.critical_response(alert)
            self.state.remember({"kind": "alert_critical_urgent", "at": utc_now(), "alert": alert.get("alert_type"), "decision": critical})
            logger.warning(f"CRITICAL URGENT alert: {alert.get('alert_type')} — 즉각 에스컬레이션")
            # 서버 승인 후 종료 (미션 빌드 없음)
            try:
                self.registry_client.acknowledge_alert(str(alert.get("alert_id")), approved=True, notes="Critical urgent — auto escalated")
            except Exception:
                pass
            return critical

        async with self._mission_lock:
            alert_id = alert.get("alert_id")
            decision = self.decision_engine.decide(self.state, alert)

            # LLM으로 fleet 컨텍스트 기반 분석 (critical이 아닌 모든 alert)
            llm_hint = await self.decision_engine.analyze_alert(alert, devices, self.state)
            if llm_hint:
                decision["llm_analysis"] = llm_hint

            self.state.remember({"kind": "alert_processed", "at": utc_now(), "alert_id": alert_id, "decision": decision})
            logger.info(f"Alert {alert_id} decision: {decision.get('mode')} | llm={bool(llm_hint)}")

            response = {
                "response_id": str(uuid4()),
                "alert_id": str(alert_id),
                "action": "mission.assign",
                "target_agent_id": None,
                "status": "planned",
                "reason": f"System Agent response to {alert.get('alert_type')}",
                "dispatch_result": {},
            }
            alert_type = alert.get("alert_type")
            metadata = alert.get("metadata", {})
            mission_steps = self._build_mission_steps(alert, devices, llm_hint=llm_hint)
            dispatch_result = self._build_dispatch_result_from_steps(mission_steps)
            response["params"] = {
                "location": metadata.get("location", {}),
                "steps": mission_steps,
                "alert_type": alert_type,
            }
            response["dispatch_result"] = dispatch_result
            if mission_steps:
                response["action"] = "mission.assign"
                first_task = (mission_steps[0].get("tasks") or [None])[0]
                if isinstance(first_task, dict):
                    response["target_agent_id"] = str(first_task["route_agent_id"])
                    response["target_endpoint"] = first_task["route_endpoint"]
            else:
                queue_reason = self._queue_reason_for_alert(alert, devices)
                if queue_reason is not None:
                    response["status"] = "queued"
                    response["notes"] = queue_reason
                    response["dispatch_result"]["queue"] = {
                        "reason": queue_reason,
                        "queued_at": utc_now(),
                        "revalidation_required": True,
                    }
                else:
                    response["status"] = "failed"
                    response["notes"] = "no_capable_target_or_available_device"

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

            if mission_steps:
                dispatch = await self._dispatch_next_step(response, mission_steps, devices, logger)
                response["dispatch_result"] = dispatch
                if dispatch.get("delivered"):
                    response["status"] = "planned"
                    response["task_id"] = dispatch.get("task_id") or response["response_id"]
                else:
                    response["status"] = "failed"
                    response["notes"] = dispatch.get("error")
                    self._release_response_devices(dispatch, reason="initial_dispatch_failed")
                try:
                    self.registry_client.ingest_response(response)
                except Exception as e:
                    logger.warning(f"Failed to update response status: {e}")
            elif response["status"] == "queued":
                self._waiting_queue[response["response_id"]] = {
                    "response_id": response["response_id"],
                    "alert": dict(alert),
                    "queued_at": utc_now(),
                }
                self.state.remember(
                    {
                        "kind": "waiting_queue_enqueued",
                        "at": utc_now(),
                        "response_id": response["response_id"],
                        "alert_id": alert_id,
                        "reason": response.get("notes"),
                    }
                )
            return response

    async def _reprocess_waiting_response(
        self,
        response_id: str,
        queue_item: dict[str, Any],
        devices: list[dict[str, Any]],
        logger: Any,
    ) -> None:
        async with self._mission_lock:
            try:
                response = self.registry_client.get_response(response_id)
            except Exception:
                self._waiting_queue.pop(response_id, None)
                return

            if str(response.get("status") or "") != "queued":
                self._waiting_queue.pop(response_id, None)
                return

            alert = dict(queue_item.get("alert") or {})
            if not self._is_alert_still_valid(alert, queue_item):
                response["status"] = "failed"
                response["notes"] = "queue_alert_expired"
                response["dispatch_result"] = dict(response.get("dispatch_result") or {})
                response["dispatch_result"]["queue"] = {
                    **dict(response["dispatch_result"].get("queue") or {}),
                    "revalidated_at": utc_now(),
                    "still_valid": False,
                    "reason": "queue_alert_expired",
                }
                self.registry_client.ingest_response(response)
                self._waiting_queue.pop(response_id, None)
                self.state.remember(
                    {
                        "kind": "waiting_queue_expired",
                        "at": utc_now(),
                        "response_id": response_id,
                        "alert_id": alert.get("alert_id"),
                    }
                )
                return
            response["dispatch_result"] = dict(response.get("dispatch_result") or {})
            response["dispatch_result"]["queue"] = {
                **dict(response["dispatch_result"].get("queue") or {}),
                "revalidated_at": utc_now(),
            }

            mission_steps = self._build_mission_steps(alert, devices)
            queue_reason = self._queue_reason_for_alert(alert, devices)
            if not mission_steps:
                if queue_reason is not None:
                    response["notes"] = queue_reason
                    response["dispatch_result"]["queue"]["reason"] = queue_reason
                    response["dispatch_result"]["queue"]["still_valid"] = True
                    self.registry_client.ingest_response(response)
                    return
                response["status"] = "failed"
                response["notes"] = "queue_revalidation_failed"
                response["dispatch_result"]["queue"]["still_valid"] = False
                self.registry_client.ingest_response(response)
                self._waiting_queue.pop(response_id, None)
                self.state.remember(
                    {
                        "kind": "waiting_queue_invalidated",
                        "at": utc_now(),
                        "response_id": response_id,
                    }
                )
                return

            response["params"] = {
                **dict(response.get("params") or {}),
                "steps": mission_steps,
            }
            response["dispatch_result"] = self._build_dispatch_result_from_steps(mission_steps)
            response["dispatch_result"]["queue"] = {
                **dict(response["dispatch_result"].get("queue") or {}),
                "reason": "queue_revalidated_and_rescheduled",
                "still_valid": True,
            }
            first_task = (mission_steps[0].get("tasks") or [None])[0]
            if isinstance(first_task, dict):
                response["target_agent_id"] = str(first_task["route_agent_id"])
                response["target_endpoint"] = first_task["route_endpoint"]

            dispatch = await self._dispatch_next_step(response, mission_steps, devices, logger)
            response["dispatch_result"] = dispatch
            if dispatch.get("delivered"):
                response["status"] = "planned"
                response["task_id"] = dispatch.get("task_id") or response["response_id"]
                response["notes"] = "queue_rescheduled"
                self._waiting_queue.pop(response_id, None)
                self.state.remember(
                    {
                        "kind": "waiting_queue_dispatched",
                        "at": utc_now(),
                        "response_id": response_id,
                    }
                )
            else:
                response["status"] = "failed"
                response["notes"] = dispatch.get("error") or "queue_dispatch_failed"
                self._waiting_queue.pop(response_id, None)
            self.registry_client.ingest_response(response)

    def _build_mission_steps(
        self,
        alert: dict[str, Any],
        devices: list[dict[str, Any]],
        llm_hint: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        alert_type = str(alert.get("alert_type") or "")
        metadata = dict(alert.get("metadata") or {})
        location = metadata.get("location") or {}
        task_param_overrides = metadata.get("task_param_overrides") or {}
        if not isinstance(task_param_overrides, dict):
            task_param_overrides = {}

        preferred_survey = str(llm_hint.get("preferred_survey_device_id") or "") if llm_hint else ""
        preferred_remove = str(llm_hint.get("preferred_remove_device_id") or "") if llm_hint else ""

        if alert_type != "mine_detection":
            target = self._select_best_device(devices, "survey_depth", location, preferred_id=preferred_survey or None)
            if not target:
                return []
            return [
                self._build_step(
                    "step-1",
                    step_type="generic_action",
                    evaluation_policy="all_tasks_success_v1",
                    tasks=[
                        self._build_task(
                            "task-1",
                            "survey_depth",
                            target,
                            location,
                            extra_params=task_param_overrides.get("survey_depth"),
                        )
                    ],
                )
            ]

        survey_target = self._select_best_device(devices, "survey_depth", location, preferred_id=preferred_survey or None)
        remove_target = self._select_best_device(devices, "remove_mine", location, preferred_id=preferred_remove or None)
        steps: list[dict[str, Any]] = []
        if survey_target:
            steps.append(
                self._build_step(
                    "survey",
                    step_type="survey",
                    evaluation_policy="survey_sufficiency_v1",
                    tasks=[
                        self._build_task(
                            "task-1",
                            "survey_depth",
                            survey_target,
                            location,
                            extra_params=task_param_overrides.get("survey_depth"),
                        )
                    ],
                )
            )
        if remove_target:
            steps.append(
                self._build_step(
                    "remove",
                    step_type="remove",
                    evaluation_policy="all_tasks_success_v1",
                    tasks=[
                        self._build_task(
                            "task-1",
                            "remove_mine",
                            remove_target,
                            location,
                            extra_params=task_param_overrides.get("remove_mine"),
                        )
                    ],
                    depends_on=["survey"] if survey_target else [],
                )
            )
        return steps

    def _build_step(
        self,
        step_id: str,
        *,
        step_type: str,
        evaluation_policy: str,
        depends_on: list[str] | None = None,
        tasks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "step_id": step_id,
            "step_type": step_type,
            "evaluation_policy": evaluation_policy,
            "depends_on": list(depends_on or []),
            "tasks": tasks,
        }

    def _build_dispatch_result_from_steps(self, mission_steps: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "steps": [
                {
                    "step_id": step["step_id"],
                    "depends_on": list(step.get("depends_on") or []),
                    "status": "pending",
                    "tasks": [
                        {
                            "task_id": task["task_id"],
                            "logical_task_id": task["logical_task_id"],
                            "attempt": task["attempt"],
                            "attempted_device_ids": list(task.get("attempted_device_ids") or []),
                            "action": task["action"],
                            "target_device_id": task["target_device_id"],
                            "target_device_name": task["target_device_name"],
                            "route_agent_id": task["route_agent_id"],
                            "route_agent_name": task["route_agent_name"],
                            "dispatch_status": "pending",
                            "execution_status": "pending",
                        }
                        for task in step.get("tasks") or []
                    ],
                }
                for step in mission_steps
            ],
            "execution_results": [],
            "execution_result": None,
            "execution_aggregate_status": "planned",
        }

    def _build_manual_intervention_record(
        self,
        *,
        response_id: str,
        alert_id: str,
        step_evaluation: dict[str, Any],
        step_execution_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        record = {
            "required": True,
            "at": utc_now(),
            "response_id": response_id,
            "alert_id": alert_id,
            "step_id": step_evaluation.get("step_id"),
            "step_type": step_evaluation.get("step_type"),
            "policy": step_evaluation.get("policy"),
            "decision": step_evaluation.get("decision"),
            "reason": step_evaluation.get("reason"),
            "step_execution_status": step_evaluation.get("step_execution_status"),
            "usable_task_count": step_evaluation.get("usable_task_count"),
            "failed_task_count": step_evaluation.get("failed_task_count"),
            "latest_step_results": [
                {
                    "reporter": str(item.get("reporter") or ""),
                    "task_id": str(item.get("task_id") or ""),
                    "status": str(item.get("status") or ""),
                    "payload": item.get("payload") or {},
                    "received_at": item.get("received_at"),
                }
                for item in step_execution_results
                if isinstance(item, dict)
            ],
        }
        record["recommended_operator_actions"] = self._manual_intervention_actions(record)
        return record

    def _manual_intervention_actions(self, record: dict[str, Any]) -> list[dict[str, str]]:
        step_type = str(record.get("step_type") or "")
        reason = str(record.get("reason") or "")
        if step_type == "survey":
            return [
                {
                    "action": "review_latest_survey_artifacts",
                    "description": "최신 탐색 산출물과 실패 사유를 확인해 usable 위치 정보가 있는지 검토한다.",
                },
                {
                    "action": "approve_resurvey_or_retarget",
                    "description": "동일 장비 재탐색 또는 다른 capable 디바이스 재투입 여부를 결정한다.",
                },
            ]
        if "alternate capable device" in reason:
            return [
                {
                    "action": "confirm_alternate_device_policy",
                    "description": "대체 가능한 디바이스로 재할당해도 되는지 운영 정책을 확인한다.",
                }
            ]
        return [
            {
                "action": "review_step_failure",
                "description": "실패 task와 최신 실행 결과를 확인하고 수동 후속 조치를 결정한다.",
            }
        ]

    def list_manual_interventions(self) -> list[dict[str, Any]]:
        responses = self.registry_client.list_responses()
        items: list[dict[str, Any]] = []
        for response in responses:
            if not isinstance(response, dict):
                continue
            if str(response.get("status") or "") != "manual_intervention_required":
                continue
            dispatch_result = response.get("dispatch_result") or {}
            if not isinstance(dispatch_result, dict):
                dispatch_result = {}
            intervention = dispatch_result.get("manual_intervention") or {}
            if not isinstance(intervention, dict):
                intervention = {}
            if intervention and not intervention.get("recommended_operator_actions"):
                intervention = {
                    **intervention,
                    "recommended_operator_actions": self._manual_intervention_actions(intervention),
                }
            items.append(
                {
                    "response_id": response.get("response_id"),
                    "alert_id": response.get("alert_id"),
                    "status": response.get("status"),
                    "reason": response.get("reason"),
                    "notes": response.get("notes"),
                    "manual_intervention": intervention,
                }
            )
        items.sort(key=lambda item: str((item.get("manual_intervention") or {}).get("at") or ""), reverse=True)
        return items

    def _build_task(
        self,
        task_id: str,
        action: str,
        target_device: dict[str, Any],
        location: dict[str, Any],
        *,
        extra_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        route_hop = self._resolve_route_hop(target_device)
        merged_params = {
            "action": action,
            "location": location,
            "mission_type": "mine_clearance",
            "target_device_id": int(target_device["id"]),
        }
        if isinstance(extra_params, dict):
            merged_params.update(extra_params)
        return {
            "task_id": task_id,
            "logical_task_id": task_id,
            "attempt": 0,
            "attempted_device_ids": [int(target_device["id"])],
            "action": action,
            "target_device_id": int(target_device["id"]),
            "target_device_name": target_device.get("name"),
            "target_device_type": target_device.get("device_type"),
            "route_agent_id": int(route_hop["id"]),
            "route_agent_name": route_hop.get("name"),
            "route_endpoint": self._device_endpoint(route_hop),
            "params": merged_params,
        }

    def _is_device_reserved(self, device_id: int) -> bool:
        return device_id in self._device_allocations

    def _severity_rank(self, severity: str) -> int:
        normalized = str(severity or "INFORMATION").upper()
        order = {
            "CRITICAL": 0,
            "WARNING": 1,
            "INFORMATION": 2,
        }
        return order.get(normalized, 2)

    def _queue_ttl_seconds(self, alert: dict[str, Any]) -> int:
        severity = str(alert.get("severity") or "INFORMATION").upper()
        if severity == "CRITICAL":
            return 300
        if severity == "WARNING":
            return 900
        return 1800

    def _is_alert_still_valid(self, alert: dict[str, Any], queue_item: dict[str, Any]) -> bool:
        created_at = str(
            queue_item.get("queued_at")
            or alert.get("updated_at")
            or alert.get("created_at")
            or ""
        )
        if not created_at:
            return True
        try:
            created_ts = time.time() if created_at == "now" else datetime.fromisoformat(created_at.replace("Z", "+00:00")).timestamp()
        except Exception:
            return True
        age_seconds = max(0.0, time.time() - created_ts)
        return age_seconds <= float(self._queue_ttl_seconds(alert))

    def _has_capable_device(
        self,
        devices: list[dict[str, Any]],
        action: str,
        location: dict[str, Any],
        *,
        include_reserved: bool,
    ) -> bool:
        for device in devices:
            if not self._device_is_connected(device):
                continue
            if str(device.get("layer") or "") != "lower":
                continue
            device_id = int(device.get("id") or 0)
            if not include_reserved and self._is_device_reserved(device_id):
                continue
            if self._device_can_execute(device, action):
                return True
        return False

    def _queue_reason_for_alert(self, alert: dict[str, Any], devices: list[dict[str, Any]]) -> str | None:
        alert_type = str(alert.get("alert_type") or "")
        location = (alert.get("metadata") or {}).get("location") or {}
        if alert_type == "mine_detection":
            survey_available = self._has_capable_device(devices, "survey_depth", location, include_reserved=False)
            remove_available = self._has_capable_device(devices, "remove_mine", location, include_reserved=False)
            survey_exists = self._has_capable_device(devices, "survey_depth", location, include_reserved=True)
            remove_exists = self._has_capable_device(devices, "remove_mine", location, include_reserved=True)
            if not survey_available and survey_exists:
                return "waiting_for_survey_device"
            if not remove_available and remove_exists:
                return "waiting_for_remove_device"
            return None

        available = self._has_capable_device(devices, "survey_depth", location, include_reserved=False)
        exists = self._has_capable_device(devices, "survey_depth", location, include_reserved=True)
        if not available and exists:
            return "waiting_for_available_device"
        return None

    def _reserve_device(
        self,
        *,
        device_id: int,
        response_id: str,
        step_id: str,
        task_id: str,
        reason: str,
    ) -> None:
        self._device_allocations[device_id] = {
            "device_id": device_id,
            "response_id": response_id,
            "step_id": step_id,
            "task_id": task_id,
            "reason": reason,
            "reserved_at": utc_now(),
        }
        self.state.remember(
            {
                "kind": "device_reserved",
                "at": utc_now(),
                "device_id": device_id,
                "response_id": response_id,
                "step_id": step_id,
                "task_id": task_id,
                "reason": reason,
            }
        )

    def _release_device(self, device_id: int, *, reason: str) -> None:
        allocation = self._device_allocations.pop(device_id, None)
        if allocation is None:
            return
        self.state.remember(
            {
                "kind": "device_released",
                "at": utc_now(),
                "device_id": device_id,
                "response_id": allocation.get("response_id"),
                "step_id": allocation.get("step_id"),
                "task_id": allocation.get("task_id"),
                "reason": reason,
            }
        )

    def _release_step_devices(self, step_state: dict[str, Any], *, reason: str) -> None:
        for task_state in step_state.get("tasks") or []:
            if not isinstance(task_state, dict):
                continue
            device_id = int(task_state.get("target_device_id") or 0)
            if device_id:
                self._release_device(device_id, reason=reason)

    def _release_response_devices(self, dispatch_result: dict[str, Any], *, reason: str) -> None:
        for step_state in dispatch_result.get("steps") or []:
            if isinstance(step_state, dict):
                self._release_step_devices(step_state, reason=reason)

    def _select_best_device(
        self,
        devices: list[dict[str, Any]],
        action: str,
        location: dict[str, Any],
        exclude_ids: set[int] | None = None,
        preferred_id: str | None = None,
    ) -> dict[str, Any] | None:
        excluded = exclude_ids or set()
        candidates = [
            device
            for device in devices
            if self._device_is_connected(device)
            and str(device.get("layer") or "") == "lower"
            and self._device_can_execute(device, action)
            and int(device.get("id") or 0) not in excluded
            and not self._is_device_reserved(int(device.get("id") or 0))
        ]
        if not candidates:
            return None

        # LLM이 추천한 디바이스가 있으면 우선 사용
        if preferred_id:
            preferred = next(
                (d for d in candidates if str(d.get("id") or "") == preferred_id),
                None,
            )
            if preferred:
                return preferred

        def rank(device: dict[str, Any]) -> tuple[float, int]:
            return (
                self._distance_to_location(device, location),
                int(device.get("id") or 0),
            )

        return min(candidates, key=rank)

    def _resolve_route_hop(self, target_device: dict[str, Any]) -> dict[str, Any]:
        parent_id = target_device.get("parent_id")
        if not parent_id:
            return target_device
        try:
            parent = self.registry_client.get_device(int(parent_id))
        except Exception:
            return target_device
        if self._device_is_connected(parent) and self._device_endpoint(parent):
            return parent
        return target_device

    def _device_is_connected(self, device: dict[str, Any]) -> bool:
        if not device.get("connected"):
            return False
        agent = device.get("agent") or {}
        return isinstance(agent, dict) and bool(agent.get("endpoint"))

    def _device_endpoint(self, device: dict[str, Any]) -> str | None:
        agent = device.get("agent") or {}
        if not isinstance(agent, dict):
            return None
        endpoint = agent.get("endpoint")
        return str(endpoint) if endpoint else None

    def _device_can_execute(self, device: dict[str, Any], action: str) -> bool:
        device_type = str(device.get("device_type") or "").upper()
        actions = set(str(v).lower() for v in (device.get("actions") or {}).get("custom", []))
        agent = device.get("agent") or {}
        if isinstance(agent, dict):
            actions.update(str(v).lower() for v in agent.get("available_actions") or [])
            actions.update(str(v).lower() for v in agent.get("skills") or [])

        if action == "survey_depth":
            return device_type == "AUV" or any(keyword in actions for keyword in {"scan_area", "sonar_scanning"})
        if action == "remove_mine":
            return device_type == "ROV" or any(keyword in actions for keyword in {"grab_object", "precise_manipulation"})
        return bool(actions)

    def _distance_to_location(self, device: dict[str, Any], location: dict[str, Any]) -> float:
        try:
            lat = float(location.get("lat"))
            lon = float(location.get("lon"))
            device_lat = float(device.get("latitude"))
            device_lon = float(device.get("longitude"))
        except (TypeError, ValueError):
            return float("inf")
        lat_delta = device_lat - lat
        lon_delta = device_lon - lon
        return lat_delta * lat_delta + lon_delta * lon_delta

    def _extract_task_result(self, execution_entry: dict[str, Any]) -> dict[str, Any]:
        payload = execution_entry.get("payload") or {}
        if not isinstance(payload, dict):
            return {}
        if isinstance(payload.get("result"), dict):
            return payload.get("result") or {}
        inner_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
        execution_log = inner_payload.get("execution_log") if isinstance(inner_payload.get("execution_log"), dict) else {}
        if isinstance(execution_log.get("result"), dict):
            return execution_log.get("result") or {}
        return {}

    def _is_step_terminal(self, step_state: dict[str, Any]) -> bool:
        task_states = [task for task in (step_state.get("tasks") or []) if isinstance(task, dict)]
        if not task_states:
            return False
        terminal_statuses = {"completed", "failed"}
        return all(str(task.get("execution_status") or "pending") in terminal_statuses for task in task_states)

    def _evaluate_step(
        self,
        response: dict[str, Any],
        step: dict[str, Any],
        step_state: dict[str, Any],
        step_execution_results: list[dict[str, Any]],
        devices: list[dict[str, Any]],
    ) -> dict[str, Any]:
        policy = str(step.get("evaluation_policy") or "all_tasks_success_v1")
        step_type = str(step.get("step_type") or "generic_action")
        task_total = len([task for task in (step_state.get("tasks") or []) if isinstance(task, dict)])
        completed_results = [item for item in step_execution_results if str(item.get("status")) == "completed"]
        failed_results = [item for item in step_execution_results if str(item.get("status")) == "failed"]
        usable_results = [
            item for item in completed_results
            if self._extract_task_result(item).get("usable_output", True) is not False
        ]

        if policy == "survey_sufficiency_v1":
            sufficient = bool(usable_results)
            if sufficient:
                decision = "proceed_next_step"
                reason = "usable survey output available"
            elif self._can_reassign_failed_tasks(step, step_state, devices):
                decision = "reassign_failed_tasks"
                reason = "no usable survey output yet; reassign failed tasks to alternate devices"
            elif self._can_retry_failed_tasks(step_state):
                decision = "retry_same_step"
                reason = "no usable survey output yet; retry failed tasks on same devices"
            else:
                decision = "manual_intervention_required"
                reason = "no usable survey output available and no automated recovery path"
        else:
            sufficient = task_total > 0 and len(completed_results) == task_total and not failed_results
            if sufficient:
                decision = "proceed_next_step"
                reason = "all tasks completed successfully"
            elif self._can_retry_failed_tasks(step_state):
                decision = "retry_same_step"
                reason = "one or more required tasks failed; retry available"
            elif self._can_reassign_failed_tasks(step, step_state, devices):
                decision = "reassign_failed_tasks"
                reason = "one or more required tasks failed; alternate capable device available"
            else:
                decision = "abort_mission"
                reason = "one or more required tasks failed and no automated recovery path"

        return {
            "at": utc_now(),
            "response_id": response.get("response_id"),
            "step_id": step.get("step_id"),
            "step_type": step_type,
            "policy": policy,
            "task_total": task_total,
            "completed_task_count": len(completed_results),
            "failed_task_count": len(failed_results),
            "usable_task_count": len(usable_results),
            "step_execution_status": step_state.get("status"),
            "sufficient": sufficient,
            "decision": decision,
            "reason": reason,
        }

    def _max_step_retries(self) -> int:
        rules = self.agent_config.get("rules") or {}
        try:
            return int(rules.get("max_step_retries", 1))
        except (TypeError, ValueError):
            return 1

    def _can_retry_failed_tasks(self, step_state: dict[str, Any]) -> bool:
        max_retries = self._max_step_retries()
        for task_state in step_state.get("tasks") or []:
            if not isinstance(task_state, dict):
                continue
            if str(task_state.get("execution_status") or "") != "failed":
                continue
            if int(task_state.get("attempt") or 0) < max_retries:
                return True
        return False

    def _can_reassign_failed_tasks(
        self,
        step: dict[str, Any],
        step_state: dict[str, Any],
        devices: list[dict[str, Any]],
    ) -> bool:
        for task_state in step_state.get("tasks") or []:
            if not isinstance(task_state, dict):
                continue
            if str(task_state.get("execution_status") or "") != "failed":
                continue
            logical_task_id = str(task_state.get("logical_task_id") or task_state.get("task_id") or "")
            task_def = next(
                (
                    task for task in (step.get("tasks") or [])
                    if isinstance(task, dict) and str(task.get("logical_task_id") or task.get("task_id") or "") == logical_task_id
                ),
                None,
            )
            if not isinstance(task_def, dict):
                continue
            candidate = self._select_best_device(
                devices,
                str(task_def.get("action") or ""),
                dict(task_def.get("params") or {}).get("location") or {},
                exclude_ids={int(v) for v in (task_state.get("attempted_device_ids") or [])},
            )
            if candidate is not None:
                return True
        return False

    def _collect_previous_step_results(
        self,
        step: dict[str, Any],
        execution_results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        dependency_ids = {str(dep) for dep in (step.get("depends_on") or [])}
        return [
            {
                "response_id": str(item.get("response_id") or ""),
                "alert_id": str(item.get("alert_id") or ""),
                "step_id": str(item.get("step_id") or ""),
                "task_id": str(item.get("task_id") or ""),
                "reporter": str(item.get("reporter") or ""),
                "status": str(item.get("status") or ""),
                "execution_log": item.get("payload") or {},
            }
            for item in execution_results
            if isinstance(item, dict) and str(item.get("step_id") or "") in dependency_ids
        ]

    def _prepare_step_recovery(
        self,
        step: dict[str, Any],
        step_state: dict[str, Any],
        devices: list[dict[str, Any]],
        *,
        mode: str,
    ) -> bool:
        recovered_any = False
        for task_state in step_state.get("tasks") or []:
            if not isinstance(task_state, dict):
                continue
            if str(task_state.get("execution_status") or "") != "failed":
                continue
            logical_task_id = str(task_state.get("logical_task_id") or task_state.get("task_id") or "")
            task_def = next(
                (
                    task for task in (step.get("tasks") or [])
                    if isinstance(task, dict) and str(task.get("logical_task_id") or task.get("task_id") or "") == logical_task_id
                ),
                None,
            )
            if not isinstance(task_def, dict):
                continue

            next_attempt = int(task_state.get("attempt") or 0) + 1
            current_history = list(task_state.get("recovery_history") or [])
            current_history.append(
                {
                    "at": utc_now(),
                    "mode": mode,
                    "previous_task_id": task_state.get("task_id"),
                    "previous_target_device_id": task_state.get("target_device_id"),
                }
            )

            if mode == "reassign_failed_tasks":
                replacement = self._select_best_device(
                    devices,
                    str(task_def.get("action") or ""),
                    dict(task_def.get("params") or {}).get("location") or {},
                    exclude_ids={int(v) for v in (task_state.get("attempted_device_ids") or [])},
                )
                if replacement is None:
                    continue
                rebuilt = self._build_task(
                    f"{logical_task_id}-reassign-{next_attempt}",
                    str(task_def.get("action") or ""),
                    replacement,
                    dict(task_def.get("params") or {}).get("location") or {},
                )
                attempted_device_ids = [*list(task_state.get("attempted_device_ids") or []), int(replacement["id"])]
            else:
                rebuilt = dict(task_def)
                rebuilt["task_id"] = f"{logical_task_id}-retry-{next_attempt}"
                attempted_device_ids = list(task_state.get("attempted_device_ids") or [])

            rebuilt["logical_task_id"] = logical_task_id
            rebuilt["attempt"] = next_attempt
            rebuilt["attempted_device_ids"] = attempted_device_ids
            task_def.update(rebuilt)
            task_state.update(
                {
                    "task_id": rebuilt["task_id"],
                    "logical_task_id": logical_task_id,
                    "attempt": next_attempt,
                    "attempted_device_ids": attempted_device_ids,
                    "action": rebuilt["action"],
                    "target_device_id": rebuilt["target_device_id"],
                    "target_device_name": rebuilt["target_device_name"],
                    "route_agent_id": rebuilt["route_agent_id"],
                    "route_agent_name": rebuilt["route_agent_name"],
                    "dispatch_status": "pending",
                    "execution_status": "pending",
                    "dispatch": None,
                    "execution_result": None,
                    "completed_at": None,
                    "recovery_history": current_history,
                }
            )
            recovered_any = True

        if recovered_any:
            step_state["status"] = "pending"
        return recovered_any

    async def _dispatch_next_step(
        self,
        response: dict[str, Any],
        mission_steps: list[dict[str, Any]],
        devices: list[dict[str, Any]],
        logger: Any,
        *,
        previous_step_results: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        dispatch_result = dict(response.get("dispatch_result") or {})
        step_states = dispatch_result.get("steps") or []
        if not isinstance(step_states, list):
            step_states = []
        for step in mission_steps:
            step_state = next(
                (
                    item for item in step_states
                    if isinstance(item, dict) and str(item.get("step_id")) == str(step["step_id"])
                ),
                None,
            )
            if step_state and step_state.get("status") in {"dispatched", "completed"}:
                continue
            depends_on = [str(dep) for dep in (step.get("depends_on") or [])]
            if any(
                not any(
                    isinstance(state, dict)
                    and str(state.get("step_id")) == dep_step_id
                    and state.get("status") == "completed"
                    for state in step_states
                )
                for dep_step_id in depends_on
            ):
                continue
            task_results: list[dict[str, Any]] = []
            task_requests: list[tuple[dict[str, Any], dict[str, Any]]] = []
            for task in step.get("tasks") or []:
                task_params = dict(task.get("params") or {})
                if previous_step_results:
                    task_params["previous_step_results"] = previous_step_results
                task_requests.append(
                    (
                        task,
                        {
                            "response_id": response["response_id"],
                            "alert_id": response["alert_id"],
                            "reason": response["reason"],
                            "step_id": step["step_id"],
                            "task_id": task["task_id"],
                            "params": task_params,
                        },
                    )
                )
            dispatches = await asyncio.gather(
                *[
                    self._send_a2a_task(
                        str(task["route_agent_id"]),
                        devices,
                        task_response,
                        logger,
                        action=task["action"],
                    )
                    for task, task_response in task_requests
                ]
            )
            delivery_failed = False
            for (task, _task_response), dispatch in zip(task_requests, dispatches):
                task_results.append(
                    {
                        "task_id": task["task_id"],
                        "action": task["action"],
                        "target_device_id": task["target_device_id"],
                        "route_agent_id": task["route_agent_id"],
                        "dispatch": dispatch,
                    }
                )
                if not dispatch.get("delivered"):
                    delivery_failed = True
                if isinstance(step_state, dict):
                    for task_state in step_state.get("tasks") or []:
                        if isinstance(task_state, dict) and str(task_state.get("task_id")) == str(task["task_id"]):
                            if dispatch.get("delivered"):
                                self._reserve_device(
                                    device_id=int(task["target_device_id"]),
                                    response_id=str(response["response_id"]),
                                    step_id=str(step["step_id"]),
                                    task_id=str(task["task_id"]),
                                    reason="task_dispatched",
                                )
                            task_state["dispatch"] = dispatch
                            task_state["dispatch_status"] = "dispatched" if dispatch.get("delivered") else "failed"
                            task_state["dispatched_task_id"] = (
                                f"{response['response_id']}:{step['step_id']}:{task['task_id']}"
                            )
                            break
            if isinstance(step_state, dict):
                step_state["status"] = "failed" if delivery_failed else "dispatched"
            dispatch_result["steps"] = step_states
            if delivery_failed:
                return {
                    "delivered": False,
                    "error": "step_dispatch_failed",
                    "step_id": step["step_id"],
                    "task_results": task_results,
                    "steps": step_states,
                    "execution_results": dispatch_result.get("execution_results") or [],
                    "execution_result": dispatch_result.get("execution_result"),
                    "execution_aggregate_status": dispatch_result.get("execution_aggregate_status"),
                }
            return {
                "delivered": True,
                "task_id": f"{response['response_id']}:{step['step_id']}",
                "step_id": step["step_id"],
                "task_results": task_results,
                "steps": step_states,
                "execution_results": dispatch_result.get("execution_results") or [],
                "execution_result": dispatch_result.get("execution_result"),
                "execution_aggregate_status": dispatch_result.get("execution_aggregate_status"),
            }

        return {
            "delivered": True,
            "task_id": response["response_id"],
            "step_id": None,
            "steps": step_states,
            "execution_results": dispatch_result.get("execution_results") or [],
            "execution_result": dispatch_result.get("execution_result"),
            "execution_aggregate_status": dispatch_result.get("execution_aggregate_status"),
        }

    async def _send_a2a_task(
        self,
        target_agent_id: str,
        devices: list[dict[str, Any]],
        response: dict[str, Any],
        logger: Any,
        *,
        action: str | None = None,
    ) -> dict[str, Any]:
        """Send A2A message to target agent to execute the task"""
        target_agent = None
        for agent in devices:
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
                                    "action": action or response.get("params", {}).get("action", "survey_depth"),
                                    "params": response.get("params", {}),
                                    "reason": response.get("reason", "System Agent assignment"),
                                    "alert_id": response.get("alert_id"),
                                    "response_id": response.get("response_id"),
                                    "step_id": response.get("step_id"),
                                    "task_id": response.get("task_id"),
                                }
                            }
                        ]
                    },
                    "taskId": (
                        f"{response.get('response_id')}:{response.get('step_id') or 'default'}"
                        f":{response.get('task_id') or 'default'}"
                    ),
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

    async def handle_command_with_llm(self, command: dict[str, Any]) -> dict[str, Any]:
        """사용자 명령을 LLM으로 해석한 뒤 실행. LLM 불가 시 직접 실행."""
        logger = logging.getLogger(__name__)
        try:
            devices = self.registry_client.list_devices()
        except Exception:
            devices = []

        llm_result = await self.decision_engine.analyze_command(command, devices, self.state)

        if llm_result:
            self.state.remember({
                "kind": "command_llm_interpreted",
                "at": utc_now(),
                "original": command,
                "llm": llm_result,
            })
            logger.info(f"명령 LLM 해석: {llm_result.get('reasoning', '')[:80]}")
            # LLM이 해석한 action으로 command를 재구성
            resolved = {
                "action": llm_result.get("action") or command.get("action"),
                "params": {
                    **command.get("params", {}),
                    **(llm_result.get("params") or {}),
                    "target_device_id": llm_result.get("target_device_id"),
                    "llm_reasoning": llm_result.get("reasoning"),
                },
                "reason": command.get("reason") or "user command via LLM",
                "priority": command.get("priority", "normal"),
            }
        else:
            resolved = command

        return self.command_controller.apply(self.state, resolved)

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
            loop = asyncio.get_running_loop()
            loop.create_task(self._process_alert(stored_alert, devices, logging.getLogger(__name__)))
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

    async def handle_mission_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        """중간/하위 에이전트의 임무 수행 결과를 수신해 response 원장에 최종 반영한다."""
        response_id = str(payload.get("response_id") or "")
        alert_id = str(payload.get("alert_id") or "")
        reporter = str(payload.get("source_agent_id") or payload.get("reporter") or "unknown")
        step_id = str(payload.get("step_id") or "")
        execution_status = str(payload.get("execution_status") or "completed").lower()
        execution_log = payload.get("execution_log") or {}

        if not response_id:
            return {"received": False, "message_type": "mission.result", "error": "response_id required"}

        normalized_status = "completed" if execution_status == "completed" else "failed"
        aggregate_status = normalized_status
        async with self._mission_lock:
            devices = self.registry_client.list_devices()
            try:
                existing = self.registry_client.get_response(response_id)
                forwarded_payload = execution_log.get("payload") if isinstance(execution_log, dict) else None
                if not isinstance(forwarded_payload, dict):
                    forwarded_payload = {}
                reporter = str(
                    forwarded_payload.get("source_agent_id")
                    or (execution_log.get("source_agent_id") if isinstance(execution_log, dict) else None)
                    or payload.get("source_agent_id")
                    or payload.get("reporter")
                    or "unknown"
                )
                step_id = str(
                    forwarded_payload.get("step_id")
                    or (execution_log.get("step_id") if isinstance(execution_log, dict) else None)
                    or payload.get("step_id")
                    or "default"
                )
                task_id = str(
                    forwarded_payload.get("task_id")
                    or (execution_log.get("task_id") if isinstance(execution_log, dict) else None)
                    or payload.get("task_id")
                    or "default"
                )
                dispatch_result = dict(existing.get("dispatch_result") or {})
                existing_results = dispatch_result.get("execution_results") or []
                if not isinstance(existing_results, list):
                    existing_results = []
                if any(
                    str(item.get("reporter")) == reporter
                    and str(item.get("step_id") or "default") == step_id
                    and str(item.get("task_id") or "default") == task_id
                    for item in existing_results
                    if isinstance(item, dict)
                ):
                    self.state.remember(
                        {
                            "kind": "mission_result_duplicate_ignored",
                            "at": utc_now(),
                            "response_id": response_id,
                            "alert_id": existing.get("alert_id") or alert_id,
                            "reporter": reporter,
                            "step_id": step_id,
                            "task_id": task_id,
                        }
                    )
                    return {
                        "received": True,
                        "message_type": "mission.result",
                        "response_id": response_id,
                        "status": existing.get("status") or normalized_status,
                        "duplicate": True,
                        "dedup_key": {
                            "response_id": response_id,
                            "step_id": step_id,
                            "task_id": task_id,
                            "reporter": reporter,
                        },
                    }

                execution_entry = {
                    "reporter": reporter,
                    "step_id": step_id,
                    "task_id": task_id,
                    "status": normalized_status,
                    "payload": execution_log,
                    "received_at": utc_now(),
                }
                execution_results = [*existing_results, execution_entry]
                aggregate_status = "failed" if any(
                    item.get("status") == "failed" for item in execution_results if isinstance(item, dict)
                ) else "completed"
                dispatch_result["execution_results"] = execution_results
                dispatch_result["execution_result"] = execution_entry
                dispatch_result["execution_aggregate_status"] = aggregate_status

                mission_steps = []
                params = existing.get("params") or {}
                if isinstance(params, dict):
                    mission_steps = params.get("steps") or []
                if not isinstance(mission_steps, list):
                    mission_steps = []

                step_states = dispatch_result.get("steps") or []
                if not isinstance(step_states, list):
                    step_states = []
                step_evaluations = dispatch_result.get("step_evaluations") or {}
                if not isinstance(step_evaluations, dict):
                    step_evaluations = {}
                replan_history = dispatch_result.get("replan_history") or []
                if not isinstance(replan_history, list):
                    replan_history = []

                current_step_state = None
                for item in step_states:
                    if isinstance(item, dict) and str(item.get("step_id") or "default") == step_id:
                        current_step_state = item
                        for task_state in item.get("tasks") or []:
                            if isinstance(task_state, dict) and str(task_state.get("task_id") or "default") == task_id:
                                task_state["execution_status"] = normalized_status
                                task_state["execution_result"] = execution_entry
                                task_state["completed_at"] = utc_now()
                                self._release_device(int(task_state.get("target_device_id") or 0), reason="task_result_received")
                        task_statuses = [
                            str(task_state.get("execution_status") or "pending")
                            for task_state in item.get("tasks") or []
                            if isinstance(task_state, dict)
                        ]
                        if any(status == "failed" for status in task_statuses):
                            item["status"] = "failed"
                        elif task_statuses and all(status == "completed" for status in task_statuses):
                            item["status"] = "completed"
                            item["completed_at"] = utc_now()
                        else:
                            item["status"] = "dispatched"
                        break

                current_step_def = next(
                    (
                        item for item in mission_steps
                        if isinstance(item, dict) and str(item.get("step_id") or "default") == step_id
                    ),
                    None,
                )
                current_step_results = [
                    item for item in execution_results
                    if isinstance(item, dict) and str(item.get("step_id") or "default") == step_id
                ]
                step_evaluation: dict[str, Any] | None = None
                if isinstance(current_step_state, dict) and isinstance(current_step_def, dict) and self._is_step_terminal(current_step_state):
                    step_evaluation = self._evaluate_step(
                        existing,
                        current_step_def,
                        current_step_state,
                        current_step_results,
                        devices,
                    )
                    step_evaluations[step_id] = step_evaluation
                    dispatch_result["step_evaluations"] = step_evaluations
                    self.state.remember({"kind": "step_evaluation", "at": utc_now(), "evaluation": step_evaluation})
                    if step_evaluation.get("decision") != "proceed_next_step":
                        replan_history.append(
                            {
                                "at": utc_now(),
                                "response_id": response_id,
                                "step_id": step_id,
                                "decision": step_evaluation.get("decision"),
                                "reason": step_evaluation.get("reason"),
                            }
                        )
                        dispatch_result["replan_history"] = replan_history
                    if step_evaluation.get("decision") == "manual_intervention_required":
                        dispatch_result["manual_intervention"] = self._build_manual_intervention_record(
                            response_id=response_id,
                            alert_id=str(existing.get("alert_id") or alert_id),
                            step_evaluation=step_evaluation,
                            step_execution_results=current_step_results,
                        )
                        self.state.remember(
                            {
                                "kind": "manual_intervention_required",
                                "at": utc_now(),
                                "response_id": response_id,
                                "alert_id": existing.get("alert_id") or alert_id,
                                "step_id": step_id,
                                "reason": step_evaluation.get("reason"),
                            }
                        )

                should_dispatch_next = bool(step_evaluation) and step_evaluation.get("decision") == "proceed_next_step"
                should_retry_same_step = bool(step_evaluation) and step_evaluation.get("decision") == "retry_same_step"
                should_reassign_failed_tasks = bool(step_evaluation) and step_evaluation.get("decision") == "reassign_failed_tasks"
                next_step: dict[str, Any] | None = None

                if should_dispatch_next:
                    completed_step_ids = {
                        str(item.get("step_id") or "default")
                        for item in step_evaluations.values()
                        if isinstance(item, dict) and item.get("decision") == "proceed_next_step"
                    }
                    for candidate in mission_steps:
                        if not isinstance(candidate, dict):
                            continue
                        candidate_step_id = str(candidate.get("step_id") or "")
                        if candidate_step_id in completed_step_ids:
                            continue
                        depends_on = [str(dep) for dep in (candidate.get("depends_on") or [])]
                        if any(dep not in completed_step_ids for dep in depends_on):
                            continue
                        step_state = next(
                            (
                                item for item in step_states
                                if isinstance(item, dict) and str(item.get("step_id")) == candidate_step_id
                            ),
                            None,
                        )
                        if step_state and step_state.get("status") in {"dispatched", "completed"}:
                            continue
                        next_step = candidate
                        break

                if next_step is not None:
                    existing["dispatch_result"] = dispatch_result
                    next_dispatch = await self._dispatch_next_step(
                        existing,
                        mission_steps,
                        devices,
                        logging.getLogger(__name__),
                        previous_step_results=[
                            {
                                "response_id": response_id,
                                "alert_id": existing.get("alert_id") or alert_id,
                                "step_id": step_id,
                                "task_id": str(item.get("task_id") or ""),
                                "reporter": str(item.get("reporter") or ""),
                                "status": str(item.get("status") or ""),
                                "execution_log": item.get("payload") or {},
                            }
                            for item in execution_results
                            if isinstance(item, dict) and str(item.get("step_id") or "") == step_id
                        ],
                    )
                    dispatch_result = next_dispatch
                    aggregate_status = "planned" if next_dispatch.get("delivered") else "failed"
                    dispatch_result["execution_aggregate_status"] = aggregate_status
                elif should_retry_same_step or should_reassign_failed_tasks:
                    recovery_mode = "reassign_failed_tasks" if should_reassign_failed_tasks else "retry_same_step"
                    prepared = self._prepare_step_recovery(
                        current_step_def,
                        current_step_state,
                        devices,
                        mode=recovery_mode,
                    ) if isinstance(current_step_def, dict) and isinstance(current_step_state, dict) else False
                    if prepared and isinstance(current_step_def, dict):
                        existing["dispatch_result"] = dispatch_result
                        retry_dispatch = await self._dispatch_next_step(
                            existing,
                            mission_steps,
                            devices,
                            logging.getLogger(__name__),
                            previous_step_results=self._collect_previous_step_results(current_step_def, execution_results),
                        )
                        dispatch_result = retry_dispatch
                        aggregate_status = "planned" if retry_dispatch.get("delivered") else "failed"
                        dispatch_result["execution_aggregate_status"] = aggregate_status
                    else:
                        aggregate_status = "failed"
                        dispatch_result["execution_aggregate_status"] = aggregate_status
                else:
                    planned_step_ids = [
                        str(item.get("step_id") or "")
                        for item in mission_steps
                        if isinstance(item, dict)
                    ]
                    proceed_step_ids = {
                        str(step_key)
                        for step_key, evaluation in step_evaluations.items()
                        if isinstance(evaluation, dict) and evaluation.get("decision") == "proceed_next_step"
                    }
                    if step_evaluation and step_evaluation.get("decision") == "manual_intervention_required":
                        aggregate_status = "manual_intervention_required"
                    elif step_evaluation and step_evaluation.get("decision") == "abort_mission":
                        aggregate_status = "failed"
                    elif planned_step_ids and all(step in proceed_step_ids for step in planned_step_ids):
                        aggregate_status = "completed"
                    else:
                        aggregate_status = "planned"
                    dispatch_result["execution_aggregate_status"] = aggregate_status

                if step_evaluation and step_evaluation.get("decision") in {"abort_mission", "manual_intervention_required"}:
                    self._release_response_devices(dispatch_result, reason=str(step_evaluation.get("decision")))
                elif aggregate_status == "completed":
                    self._release_response_devices(dispatch_result, reason="mission_completed")

                response_record = {
                    "response_id": response_id,
                    "alert_id": existing.get("alert_id") or alert_id,
                    "action": existing.get("action") or "task.assign",
                    "target_agent_id": existing.get("target_agent_id"),
                    "target_endpoint": existing.get("target_endpoint"),
                    "route_mode": existing.get("route_mode") or "direct_to_system",
                    "status": aggregate_status,
                    "reason": existing.get("reason") or f"Mission result from {reporter}",
                    "task_id": existing.get("task_id") or response_id,
                    "params": existing.get("params") or {},
                    "dispatch_result": dispatch_result,
                    "notes": (
                        str(step_evaluation.get("reason"))
                        if step_evaluation and step_evaluation.get("decision") == "manual_intervention_required"
                        else f"Mission result from {reporter}"
                    ),
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
                "step_id": step_id,
                "task_id": task_id,
                "status": aggregate_status,
            }
        )
        return {
            "received": True,
            "message_type": "mission.result",
            "response_id": response_id,
            "status": aggregate_status,
            "duplicate": False,
            "dedup_key": {
                "response_id": response_id,
                "step_id": step_id,
                "task_id": task_id,
                "reporter": reporter,
            },
        }
