from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from agent.decision import DecisionEngine, TOOL_DEFINITIONS

REACT_MAX_STEPS = 6
from agent.event_system import (
    EventPublisher,
    create_step_evaluation_event,
    create_recovery_action_event,
    create_mission_state_change_event,
    create_device_status_change_event,
)
from agent.manifest import ManifestBuilder
from agent.policy_evaluator import PolicyEvaluator
from agent.state import AgentState, utc_now
from agent.task_dispatcher import TaskDispatcher
from controller.commands import CommandController
from simulator.device import DeviceSimulator
from skills.catalog import SkillCatalog
from storage.identity_store import IdentityStore
from storage.runtime_store import PersistentLog, PersistentMapping, RuntimeStore
from tools.command_executor import CommandExecutor
from tools.telemetry_reader import TelemetryReader
from transport.registry_client import RegistryClient


logger = logging.getLogger(__name__)


class AgentRuntime:
    def __init__(self, config_path: Path, overrides: dict[str, Any] | None = None) -> None:
        self.config_path = config_path
        self.config = json.loads(config_path.read_text(encoding="utf-8"))
        if overrides:
            self._deep_update(self.config, overrides)
        self.server = self.config.get("server", {})
        self.agent_config = self.config.get("agent", {})
        self.capabilities = self.agent_config.get("capabilities", {})
        self.event_rules = self.config.get("event_rules", {})
        self.instance_id = self._resolve_instance_id()
        self.identity_store = IdentityStore(config_path.parent / ".runtime", self.instance_id)
        self.identity = self.identity_store.read()
        self.runtime_store = RuntimeStore(config_path.parent / ".runtime" / f"{self.instance_id}.db")
        self.skills = SkillCatalog(self.capabilities)
        self.manifest_builder = ManifestBuilder(self.config, self.skills)
        self.policy_evaluator = PolicyEvaluator(self)
        configured_name = str(self.agent_config.get("name") or "CoWater Agent").strip()
        self.state = AgentState(
            agent_id=self.identity.get("agent_id") or f"{self.agent_config.get('id', 'agent')}-{self.instance_id}",
            role=str(self.agent_config.get("role") or "device_agent"),
            layer=str(self.agent_config.get("layer") or "lower"),
            device_type=self.agent_config.get("device_type"),
            instance_id=self.instance_id,
            name=self.identity.get("name") or configured_name or "CoWater Agent",
        )
        self.registry_client = RegistryClient(self.config.get("registry", {}))
        self.event_publisher = EventPublisher(self.registry_client)
        self.decision_engine = DecisionEngine(self.agent_config, self.skills)
        self.task_dispatcher = TaskDispatcher(self.registry_client, enable_logging=True)
        self.telemetry_reader = TelemetryReader()
        self.simulator = DeviceSimulator(self.config.get("simulation", {}), self.skills.list_tracks())
        self.command_controller = CommandController(CommandExecutor())
        self.state.children = PersistentMapping(self.runtime_store, "children")
        self.state.tasks = PersistentMapping(self.runtime_store, "tasks")
        self.state.inbox = PersistentLog(self.runtime_store, "inbox", keep_last_n=200)
        self.state.outbox = PersistentLog(self.runtime_store, "outbox", keep_last_n=200)
        self.state.memory = PersistentLog(self.runtime_store, "memory", keep_last_n=100)
        self._last_assignment_signature: dict[str, Any] | None = None
        self._mission_lock = asyncio.Lock()
        self._device_allocations = PersistentMapping(
            self.runtime_store,
            "device_allocations",
            key_encoder=lambda key: str(int(key)),
            key_decoder=lambda key: int(key),
        )
        self._waiting_queue: dict[str, dict[str, Any]] = {}
        self._action_aliases: dict[str, list[str]] = {
            "survey_depth": ["survey_depth", "scan_area", "sonar_scanning"],
            "remove_mine": ["remove_mine", "grab_object", "precise_manipulation"],
            "return_to_base": ["return_to_base", "surface", "hold_position"],
        }
        self._recommendation_suppressions: dict[str, str] = {}
        self._policy_action_dedupe: dict[str, float] = {}
        self._command_requests: dict[str, dict[str, Any]] = {}
        self._command_request_tasks: set[asyncio.Task[Any]] = set()

    @classmethod
    def _deep_update(cls, target: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
        for key, value in updates.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                cls._deep_update(target[key], value)
            else:
                target[key] = value
        return target

    def _resolve_instance_id(self) -> str:
        explicit = os.getenv("COWATER_INSTANCE_ID") or self.agent_config.get("instance_id")
        if explicit:
            return str(explicit)
        return f"{int(time.time())}-{os.getpid()}-{uuid4().hex[:6]}"

    def base_url(self) -> str:
        host = str(self.server.get("public_host") or self.server.get("host") or "127.0.0.1")
        port = int(os.getenv("COWATER_AGENT_PORT") or self.server.get("port") or 9010)
        return f"http://{host}:{port}"

    @staticmethod
    def _task_status(value: Any, default: str = "PENDING") -> str:
        normalized = str(value or default).strip().upper()
        aliases = {
            "SUCCESS": "COMPLETED",
            "OK": "COMPLETED",
            "DONE": "COMPLETED",
            "REJECTED": "ABORTED",
            "DISPATCHED": "ASSIGNED",
            "RUNNING": "IN_PROGRESS",
        }
        normalized = aliases.get(normalized, normalized)
        if normalized in {"PENDING", "ASSIGNED", "IN_PROGRESS", "COMPLETED", "FAILED", "CANCELLED", "ABORTED"}:
            return normalized
        return default

    @staticmethod
    def _mission_status(value: Any, default: str = "IN_PROGRESS") -> str:
        normalized = str(value or default).strip().upper()
        aliases = {
            "PENDING": "READY",
            "PLANNED": "READY",
            "RUNNING": "IN_PROGRESS",
            "ABORTED": "CANCELLED",
        }
        normalized = aliases.get(normalized, normalized)
        if normalized in {"READY", "IN_PROGRESS", "COMPLETED", "FAILED", "CANCELLED", "EXPIRED"}:
            return normalized
        return default

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
                if self.state.layer == "system":
                    self._restore_device_allocations()
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
        self.state.registry_id = int(created.get("registry_id") or created["id"])
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
        if self.state.layer == "system":
            self._restore_device_allocations()

    def _restore_device_allocations(self) -> None:
        """재시작 후 Registry의 active missions에서 device 예약 상태를 복원한다."""
        logger = logging.getLogger(__name__)
        restored = 0
        try:
            missions = self.registry_client.list_missions()
        except Exception as exc:
            logger.warning(f"_restore_device_allocations: failed to list missions: {exc}")
            missions = []
        for mission in missions:
            if not isinstance(mission, dict):
                continue
            if str(mission.get("status") or "").upper() not in {"READY", "IN_PROGRESS", "FAILED"}:
                continue
            dispatch_state = ((mission.get("metadata") or {}).get("dispatch_state") or {})
            if not isinstance(dispatch_state, dict):
                continue
            for step_state in dispatch_state.get("steps") or []:
                if not isinstance(step_state, dict):
                    continue
                if self._task_status(step_state.get("status")) in {"COMPLETED", "FAILED", "CANCELLED", "ABORTED"}:
                    continue
                for task_state in step_state.get("tasks") or []:
                    if not isinstance(task_state, dict):
                        continue
                    if self._task_status(task_state.get("execution_status")) in {"COMPLETED", "FAILED", "CANCELLED", "ABORTED"}:
                        continue
                    try:
                        device_id = int(task_state.get("target_device_id") or 0)
                    except (TypeError, ValueError):
                        continue
                    if device_id and device_id not in self._device_allocations:
                        self._device_allocations[device_id] = {
                            "device_id": device_id,
                            "mission_id": str(mission.get("mission_id") or ""),
                            "step_id": str(step_state.get("step_id") or ""),
                            "task_id": str(task_state.get("task_id") or ""),
                            "reason": "restored_from_mission_on_restart",
                            "reserved_at": str(mission.get("updated_at") or utc_now()),
                        }
                        restored += 1

        if restored:
            logger.info(f"Restored {restored} device allocation(s) from active missions")
            self.state.remember({"kind": "device_allocations_restored", "at": utc_now(), "count": restored})

    def _allocation_restore_ttl_seconds(self) -> int:
        rules = self.agent_config.get("rules") or {}
        try:
            return max(60, int(rules.get("device_allocation_restore_ttl_seconds", 900)))
        except (TypeError, ValueError):
            return 900

    def apply_assignment(self, assignment: dict[str, Any]) -> None:
        signature = {
            "parent_id": assignment.get("parent_id"),
            "parent_endpoint": assignment.get("parent_endpoint"),
            "parent_command_endpoint": assignment.get("parent_command_endpoint"),
            "gateway_agent_id": assignment.get("gateway_agent_id") or assignment.get("parent_agent_id"),
            "environment_state": assignment.get("environment_state"),
            "active_mediums": tuple(assignment.get("active_mediums") or []),
            "route_mode": str(assignment.get("route_mode") or "direct_to_system"),
            "force_parent_routing": bool(assignment.get("force_parent_routing", False)),
        }
        self.state.parent_id = assignment.get("parent_id")
        self.state.parent_endpoint = assignment.get("parent_endpoint")
        self.state.parent_command_endpoint = assignment.get("parent_command_endpoint")
        self.state.gateway_agent_id = assignment.get("gateway_agent_id") or assignment.get("parent_agent_id")
        self.state.environment_state = assignment.get("environment_state")
        self.state.active_mediums = list(assignment.get("active_mediums") or self.state.active_mediums or [])
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
            agent_id=self.state.agent_id,
            endpoint=self.base_url(),
            command_endpoint=f"{self.base_url()}/agents/{self.state.token}/command",
            role=self.state.role,
            llm_enabled=bool(self.decision_engine.llm_enabled),
            skills=self.skills.list_skills(),
            actions=self.skills.list_actions(),
            last_seen_at=self.state.last_seen_at,
            gateway_agent_id=self.state.gateway_agent_id,
            environment_state=self.state.environment_state,
            active_mediums=list(self.state.active_mediums or []),
        )

    async def simulation_loop(self) -> None:
        if self.state.layer == "system":
            tasks = [self._registry_keepalive_loop(), self._state_cleanup_loop()]
            if self.state.role == "policy_manager":
                tasks.append(self._alert_processing_loop())
            if self.state.role == "insight_reporter":
                tasks.append(self._event_based_report_loop())
            await asyncio.gather(*tasks)
        else:
            await self._telemetry_processing_loop()

    async def _state_cleanup_loop(self) -> None:
        """state.tasks, inbox, outbox의 오래된 항목을 주기적으로 정리한다."""
        max_tasks = 500
        max_inbox_outbox = 200
        cleanup_interval = 300  # 5분마다
        while True:
            await asyncio.sleep(cleanup_interval)
            try:
                # tasks: 완료/실패 상태인 오래된 것부터 제거
                if len(self.state.tasks) > max_tasks:
                    # 완료/실패 상태인 task만 제거 대상
                    removable = [
                        k for k, v in self.state.tasks.items()
                        if isinstance(v, dict) and self._task_status(v.get("status")) in {"COMPLETED", "FAILED", "CANCELLED", "ABORTED"}
                    ]
                    for k in removable[:len(self.state.tasks) - max_tasks]:
                        self.state.tasks.pop(k, None)
                # inbox/outbox: 크기 제한
                if len(self.state.inbox) > max_inbox_outbox:
                    self.state.inbox.trim(max_inbox_outbox)
                if len(self.state.outbox) > max_inbox_outbox:
                    self.state.outbox.trim(max_inbox_outbox)
            except Exception as e:
                logging.getLogger(__name__).debug(f"State cleanup error: {e}")

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
        poll_interval = 2
        all_devices: list[dict[str, Any]] = []

        while True:
            try:
                await asyncio.sleep(poll_interval)
                self.state.last_seen_at = utc_now()

                try:
                    all_devices = self.registry_client.list_devices()
                    # P3 (보고 기반): Agent가 보고한 위치/배터리 정보를 device dict에 반영
                    all_devices = [self._normalize_device_from_registry(d) for d in all_devices]
                except Exception as e:
                    logger.debug(f"Failed to fetch device list: {e}")

                # Fetch all alerts from registry
                try:
                    alerts = self.registry_client.list_alerts()
                except Exception as e:
                    logger.debug(f"Failed to fetch alerts: {e}")
                    continue

                # handle_event_report에서 처리 못 한 registered 상태 alert만 폴백 처리
                now_ts = time.time()
                stale_cutoff = now_ts - 30 * 60
                waiting_alerts = [
                    alert for alert in alerts
                    if alert.get("status") == "registered"
                    and self._parse_iso_ts(str(alert.get("created_at") or "")) > stale_cutoff
                ]
                waiting_alerts.sort(
                    key=lambda alert: (
                        self._severity_rank(str(alert.get("severity") or "INFORMATION")),
                        -self._parse_iso_ts(str(alert.get("created_at") or "")),
                    ),
                    reverse=False,
                )
                # 루프당 최대 3개 처리 (백로그가 많아도 신규 alert가 빠르게 처리되도록)
                for alert in waiting_alerts[:3]:
                    alert_id = alert.get("alert_id")

                    logger.info(f"Processing alert {alert_id}: {alert.get('alert_type')}")
                    try:
                        self.registry_client.acknowledge_alert(
                            str(alert_id),
                            approved=True,
                            notes="system-agent claimed alert for processing",
                        )
                    except Exception as exc:
                        logger.debug(f"Failed to claim alert {alert_id}: {exc}")
                    await self._process_alert(alert, all_devices, logger)

                await self._process_waiting_queue(all_devices, logger)

                # ✅ Policy 평가 및 자동 대응 (Ch.17.1)
                await self._evaluate_and_apply_policies(all_devices, logger)

            except Exception as e:
                logger.error(f"Alert processing loop error: {e}")
                await asyncio.sleep(1)

    async def _event_based_report_loop(self) -> None:
        """InsightReporter: MEB 이벤트 기반 한국어 리포트 생성 (Registry 폴링)"""
        logger = logging.getLogger(__name__)
        poll_interval = 2
        processed_event_ids = getattr(self.state, 'processed_event_ids', set())

        while True:
            try:
                await asyncio.sleep(poll_interval)
                self.state.last_seen_at = utc_now()

                try:
                    events = self.registry_client.list_events()
                except Exception as e:
                    logger.debug(f"Failed to fetch events: {e}")
                    continue

                # SYS_MISSION_COMPLETED, SYS_ANOMALY_DETECTED 이벤트만 필터링
                new_events = [
                    event for event in events
                    if event.get('type') in ['SYS_MISSION_COMPLETED', 'SYS_ANOMALY_DETECTED']
                    and str(event.get('event_id') or '') not in processed_event_ids
                ]

                # 최신 이벤트부터 처리 (역순)
                for event in reversed(new_events[-10:]):
                    event_id = str(event.get('event_id') or '')
                    event_type = str(event.get('type') or '')
                    if not event_id:
                        continue

                    try:
                        logger.info(f"Processing event {event_id}: {event_type}")
                        devices = self.registry_client.list_devices()
                        missions = self.registry_client.list_missions()
                        insights = self.registry_client.list_insights()

                        # 한국어 리포트 생성
                        report, error = await self.decision_engine.generate_fleet_report(
                            devices, missions, insights, self.state
                        )

                        if report:
                            # 리포트를 새 Insight로 저장
                            insight_record = self.registry_client.create_insight({
                                "title": f"{event_type} 분석 리포트",
                                "summary": report.get("report", ""),
                                "highlights": report.get("highlights", []),
                                "recommendations": report.get("recommendations", []),
                                "source": "event_triggered_report",
                                "related_event_id": event_id,
                                "created_at": utc_now(),
                            })
                            logger.info(f"✅ Insight created from event {event_id}")
                            self.state.remember({
                                "kind": "event_report_generated",
                                "at": utc_now(),
                                "event_id": event_id,
                                "event_type": event_type,
                                "insight_id": insight_record.get("id"),
                            })
                        elif error:
                            logger.warning(f"Report generation failed for event {event_id}: {error}")
                            self.state.remember({
                                "kind": "event_report_failed",
                                "at": utc_now(),
                                "event_id": event_id,
                                "error": str(error),
                            })

                        # 처리 완료 표시
                        processed_event_ids.add(event_id)
                        if len(processed_event_ids) > 1000:
                            processed_event_ids = set(list(processed_event_ids)[-500:])
                        self.state.processed_event_ids = processed_event_ids

                    except Exception as e:
                        logger.error(f"Failed to process event {event_id}: {e}")

            except Exception as e:
                logger.error(f"Event-based report loop error: {e}")
                await asyncio.sleep(1)

    async def _evaluate_and_apply_policies(self, devices: list[dict[str, Any]], logger: Any) -> None:
        """Policy를 평가하고 Critical 상황 시 자동 대응 (Ch.17.1)"""
        try:
            # Critical 상황 감지 (예: device offline)
            for device in devices:
                connectivity_status = device.get("connectivity_status", "offline")
                device_layer = str(device.get("layer") or "").lower()
                device_id = str(device.get("id") or device.get("registry_id") or "")

                # Device OFFLINE 상황
                if connectivity_status == "offline" and device_layer != "system" and device_id:
                    # auto_rtb_on_offline 정책 검사
                    policy = self.registry_client.get_policy("auto_rtb_on_offline")
                    if policy and policy.get("enabled"):
                        dedupe_key = f"auto_rtb_on_offline:{device_id}"
                        now = time.time()
                        if self._policy_action_dedupe.get(dedupe_key, 0) > now - 600:
                            continue
                        self._policy_action_dedupe[dedupe_key] = now
                        logger.info(f"🚨 Policy triggered: {policy.get('policy_name')} for device {device.get('id')}")
                        # 자동 Mission 생성: Return to Base
                        mission = {
                            "mission_id": str(uuid4()),
                            "title": f"Auto Recovery: {device.get('name')} - Return to Base",
                            "trigger_type": "policy",
                            "trigger_policy_id": "auto_rtb_on_offline",
                            "target_device_id": device.get("id"),
                            "steps": [
                                {
                                    "step_id": "recovery_1",
                                    "step_type": "return_to_base",
                                    "action": "return_to_base",
                                    "params": {},
                                }
                            ],
                            "status": "READY",
                            "created_at": utc_now(),
                        }
                        try:
                            self.registry_client.create_mission(mission)
                            logger.info(f"✅ Auto Mission created: {mission['mission_id']}")
                        except Exception as e:
                            logger.error(f"Failed to create auto mission: {e}")
        except Exception as e:
            logger.debug(f"Policy evaluation error: {e}")

    async def _process_waiting_queue(self, devices: list[dict[str, Any]], logger: Any) -> None:
        return

    async def _process_alert(self, alert: dict[str, Any], devices: list[dict[str, Any]], logger: Any) -> dict[str, Any]:
        """단일 alert를 insight/proposal/approval 흐름으로 처리한다."""
        # Critical 긴급 상황 — LLM 없이 즉각 에스컬레이션
        if self.decision_engine.is_critical_urgent(alert):
            critical = self.decision_engine.critical_response(alert)
            self.state.remember({"kind": "alert_critical_urgent", "at": utc_now(), "alert": alert.get("alert_type"), "decision": critical})
            logger.warning(f"CRITICAL URGENT alert: {alert.get('alert_type')} — 즉각 에스컬레이션")
            try:
                self.registry_client.acknowledge_alert(str(alert.get("alert_id")), approved=True, notes="Critical urgent — auto escalated")
            except Exception:
                pass
            proposal_bundle = await self.generate_mission_proposal(
                {
                    "title": f"{str(alert.get('alert_type') or 'Critical').replace('_', ' ').title()} Critical Response",
                    "goal": str(alert.get("message") or alert.get("alert_type") or "Critical mission"),
                    "alert_id": str(alert.get("alert_id") or ""),
                    "event_id": str(alert.get("event_id") or ""),
                    "severity": str(alert.get("severity") or "CRITICAL"),
                    "source": "critical_policy",
                    "summary": "Policy-based critical response was generated automatically.",
                    "reason_summary": critical.get("reasoning") or "Critical policy auto response.",
                    "insight_summary": f"Critical policy response for {alert.get('alert_type') or 'alert'}",
                }
            )
            auto_decision = None
            approval_id = (proposal_bundle.get("approval") or {}).get("approval_id")
            if approval_id:
                auto_decision = await self.decide_approval_flow(
                    str(approval_id),
                    True,
                    decided_by="system_policy",
                    notes="Critical policy auto approval",
                )
            return {
                **critical,
                "proposal_id": (proposal_bundle.get("proposal") or {}).get("proposal_id"),
                "approval_id": approval_id,
                "mission_id": ((auto_decision or {}).get("mission") or {}).get("mission_id"),
            }

        # LLM 분석을 Lock 외부에서 먼저 수행 (최대 120초 블로킹이 Lock 밖에서 일어남)
        decision = self.decision_engine.decide(self.state, alert)
        llm_result, llm_error = await self.decision_engine.analyze_alert(alert, devices, self.state)
        
        # LLM 결과 처리
        if llm_result:
            decision["llm_analysis"] = llm_result
        if llm_error:
            # LLM 오류 발생 - Event 기록
            self.event_publisher.publish(
                create_device_status_change_event(
                    source_agent_id=self.state.agent_id,
                    device_id=0,  # System-level event
                    device_name="system",
                    old_status="OPERATIONAL",
                    new_status="DEGRADED",
                    reason=f"LLM error: {llm_error.get('error_type')} - {llm_error.get('message')[:50]}"
                )
            )
            decision["llm_error"] = llm_error
            logger.warning(f"Alert {alert.get('alert_id')} processing with LLM error: {llm_error}")

        async with self._mission_lock:
            alert_id = alert.get("alert_id")

            self.state.remember({"kind": "alert_processed", "at": utc_now(), "alert_id": alert_id, "decision": decision})
            logger.info(f"Alert {alert_id} decision: {decision.get('mode')} | llm={'success' if llm_result else ('error' if llm_error else 'disabled')}")
            proposal_bundle = await self.generate_mission_proposal(
                {
                    "title": f"{str(alert.get('alert_type') or 'Alert').replace('_', ' ').title()} Proposal",
                    "goal": str(alert.get("message") or alert.get("alert_type") or "Mission proposal"),
                    "alert_id": str(alert_id or ""),
                    "event_id": alert.get("event_id") or (alert.get("metadata") or {}).get("event_id"),
                    "severity": alert.get("severity") or "INFORMATION",
                    "source": "alert_processing_loop",
                    "summary": f"Proposal generated from alert {alert_id}.",
                }
            )
            return {
                "alert_id": alert_id,
                "decision": decision,
                **proposal_bundle,
            }

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
            requested_action = self._canonical_action(str(alert.get("recommended_action") or "survey_depth"))
            target = self._select_best_device(devices, requested_action, location, preferred_id=preferred_survey or None)
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
                            requested_action,
                            target,
                            location,
                            extra_params=task_param_overrides.get(requested_action),
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
                    "status": "PENDING",
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
                            "dispatch_status": "PENDING",
                            "execution_status": "PENDING",
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
        missions = self.registry_client.list_missions()
        items: list[dict[str, Any]] = []
        for mission in missions:
            if not isinstance(mission, dict):
                continue
            mission_status = str(mission.get("status") or "").upper()
            if mission_status != "FAILED":
                continue
            dispatch_result = ((mission.get("metadata") or {}).get("dispatch_state") or {})
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
                    "mission_id": mission.get("mission_id"),
                    "alert_id": mission.get("alert_id"),
                    "status": mission_status,
                    "reason": (mission.get("final_result") or {}).get("reason"),
                    "notes": mission.get("summary"),
                    "manual_intervention": intervention,
                }
            )
        items.sort(key=lambda item: str((item.get("manual_intervention") or {}).get("at") or ""), reverse=True)
        return items

    async def execute_role_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        role = self.state.role
        parameters = payload.get("parameters") if isinstance(payload.get("parameters"), dict) else payload
        if role == "request_handler":
            return await self._execute_request_handler(parameters)
        if role == "mission_planner":
            return await self.generate_mission_proposal(parameters, allow_suppression=False)
        if role == "policy_manager":
            return self._execute_policy_manager(parameters)
        if role == "device_bridge":
            command = {
                "action": parameters.get("action") or parameters.get("command") or "hold_position",
                "params": parameters.get("params") or {},
                "reason": parameters.get("reason") or "DeviceBridge execute request",
            }
            result = await self.handle_command_with_llm(command)
            return {"type": "COMMAND", "status": "SUCCESS", "result": result}
        if role == "system_sentinel":
            return {
                "type": "STATE",
                "status": "SUCCESS",
                "devices": self.registry_client.list_devices(),
                "alerts": self.registry_client.list_alerts(),
            }
        if role == "insight_reporter":
            return await self._execute_insight_reporter(parameters)
        return {"type": "RESPONSE", "status": "ERROR", "message": f"unsupported role: {role}"}

    def _summarize_tool_result(self, tool_name: str, raw: Any) -> Any:
        """LLM 히스토리에 넣을 도구 결과를 핵심 필드만 추려 간결하게 정리"""
        if tool_name == "get_devices" and isinstance(raw, list):
            return [
                {
                    "id": d.get("id"),
                    "name": d.get("name"),
                    "type": d.get("device_type"),
                    "status": d.get("connectivity_status"),
                    "battery": d.get("last_battery_percent"),
                    "lat": d.get("latitude"),
                    "lon": d.get("longitude"),
                    "layer": d.get("layer"),
                    "actions": (d.get("actions") or [])[:5],
                    "submerged": d.get("is_submerged"),
                }
                for d in raw
                if d.get("layer") != "system"  # 내부 시스템 에이전트 제외
            ]
        if tool_name == "get_missions" and isinstance(raw, list):
            return [
                {
                    "id": m.get("mission_id"),
                    "title": m.get("title"),
                    "status": m.get("status"),
                    "type": m.get("type"),
                    "priority": m.get("priority"),
                }
                for m in raw
            ]
        if tool_name == "get_alerts" and isinstance(raw, list):
            return [
                {
                    "id": a.get("id") or a.get("alert_id"),
                    "type": a.get("alert_type") or a.get("type"),
                    "severity": a.get("severity"),
                    "status": a.get("status"),
                    "created_at": a.get("created_at"),
                }
                for a in raw
            ]
        return raw

    async def _execute_tool(self, tool_name: str, tool_input: dict[str, Any]) -> Any:
        if tool_name == "get_devices":
            return self._summarize_tool_result("get_devices", self.registry_client.list_devices())
        if tool_name == "get_missions":
            return self._summarize_tool_result("get_missions", self.registry_client.list_missions())
        if tool_name == "get_alerts":
            return self._summarize_tool_result("get_alerts", self.registry_client.list_alerts())
        if tool_name == "get_insights":
            return self.registry_client.list_insights()
        if tool_name == "plan_mission":
            goal = str(tool_input.get("goal") or "")
            return await self.generate_mission_proposal({"goal": goal}, allow_suppression=False)
        return {"error": f"알 수 없는 도구: {tool_name}"}

    async def _execute_request_handler(self, parameters: dict[str, Any]) -> dict[str, Any]:
        user_input = str(
            parameters.get("user_input") or parameters.get("goal") or parameters.get("message") or ""
        ).strip()

        if not user_input:
            return {"type": "RESPONSE", "status": "ERROR", "message": "사용자 명령이 비어 있습니다."}

        tools = list(TOOL_DEFINITIONS)
        history: list[dict[str, Any]] = []
        timeout = self.decision_engine.agent_config.get("llm", {}).get("timeout_seconds", 30)

        for step_num in range(1, REACT_MAX_STEPS + 1):
            step_result, error = await self.decision_engine.react_step(
                user_input, tools, history, timeout
            )

            if error:
                error_msg = f"{error.get('error_type', 'unknown')}: {error.get('message', 'LLM 호출 실패')}"
                return {"type": "RESPONSE", "status": "ERROR", "message": f"처리 실패 (단계 {step_num}): {error_msg}"}

            if not step_result or not step_result.get("action"):
                return {"type": "RESPONSE", "status": "ERROR", "message": f"LLM이 다음 행동을 결정하지 못했습니다. (단계 {step_num})"}

            action = str(step_result["action"])
            action_input = step_result.get("action_input") or {}
            thought = step_result.get("thought", "")
            logger.info(f"[ReAct {step_num}/{REACT_MAX_STEPS}] {action} | {thought[:80]}")

            if action == "final_answer":
                response_text = (
                    action_input.get("response", "")
                    if isinstance(action_input, dict)
                    else str(action_input)
                )
                self.registry_client.ingest_event({
                    "event_type": "SYS_REQUEST_PROCESSED",
                    "source_system": "system_agent",
                    "source_agent_id": self.state.agent_id,
                    "source_role": self.state.role,
                    "severity": "INFORMATION",
                    "message": user_input,
                    "target_type": "SYSTEM",
                    "title": "Request processed",
                    "description": f"RequestHandler completed in {step_num} step(s).",
                    "data": {"steps": step_num, "tools_used": [h["action"] for h in history]},
                })
                return {
                    "type": "RESPONSE",
                    "status": "SUCCESS",
                    "message": response_text,
                    "steps": step_num,
                }

            tool_result = await self._execute_tool(
                action, action_input if isinstance(action_input, dict) else {}
            )
            history.append({"action": action, "input": action_input, "result": tool_result})

        return {
            "type": "RESPONSE",
            "status": "ERROR",
            "message": f"최대 처리 단계({REACT_MAX_STEPS})를 초과했습니다.",
        }

    def _execute_policy_manager(self, parameters: dict[str, Any]) -> dict[str, Any]:
        policy_id = str(parameters.get("policy_id") or parameters.get("id") or "").strip()
        if policy_id:
            policy = self.registry_client.update_policy(policy_id, parameters)
        else:
            policy = self.registry_client.create_policy(parameters)
        return {"type": "RESPONSE", "status": "SUCCESS", "policy": policy}

    async def generate_mission_proposal(
        self,
        payload: dict[str, Any],
        *,
        allow_suppression: bool = True,
        _preset_mission_type: str | None = None,
        _preset_location: dict | None = None,
    ) -> dict[str, Any]:
        devices = self.registry_client.list_devices()
        goal = str(payload.get("goal") or "").strip()
        alert = None
        alert_id = payload.get("alert_id")
        if alert_id:
            try:
                alert = self.registry_client.get_alert(str(alert_id))
            except Exception:
                alert = None

        # Mission type 결정: preset이 있으면 사용, 없으면 LLM 필수
        if _preset_mission_type:
            mission_type = _preset_mission_type
            location = _preset_location or payload.get("location") or ((alert or {}).get("metadata") or {}).get("location") or {}
        else:
            # LLM으로 mission_type 분석 (필수, fallback 없음)
            llm_intent, llm_error = await self.decision_engine.analyze_intent(goal, devices, self.state)

            if llm_error or not llm_intent or not llm_intent.get("mission_type"):
                # LLM 호출 실패 → ERROR 반환 (규칙 기반 fallback 없음)
                error_msg = llm_error.get("message", "LLM 호출 실패") if llm_error else "LLM 응답 형식 오류"
                raise RuntimeError(f"Mission type 분석 실패: {error_msg}")

            mission_type = llm_intent.get("mission_type")
            location = llm_intent.get("location") or payload.get("location") or ((alert or {}).get("metadata") or {}).get("location") or {}
        suppression_fingerprint = f"{mission_type}:{goal}:{(alert or {}).get('alert_id') or ''}"
        suppressed_until = self._recommendation_suppressions.get(suppression_fingerprint)
        if allow_suppression and suppressed_until and self._parse_iso_ts(suppressed_until) > time.time():
            return {
                "suppressed": True,
                "fingerprint": suppression_fingerprint,
                "suppressed_until": suppressed_until,
            }
        synthetic_alert = {
            "alert_type": "mine_detection" if mission_type == "mine_clearance" else "operator_request",
            "recommended_action": "survey_depth" if mission_type in {"survey", "mine_clearance"} else "hold_position",
            "metadata": {"location": location},
        }
        steps = self._build_mission_steps(synthetic_alert, devices)
        if not steps:
            fallback_step = self._build_generic_steps_for_goal(goal or mission_type, devices, location)
            steps = fallback_step

        # Phase 4: LLM으로 한국어 insight 요약 생성
        insight_texts, insight_err = await self.decision_engine.generate_insight_summary(
            goal, mission_type, devices, {"location": location}, self.state
        )

        insight = self.registry_client.create_insight(
            {
                "summary": payload.get("insight_summary") or insight_texts.get("summary") or f"'{mission_type.replace('_', ' ').title()}' 미션이 준비되었습니다.",
                "reason_summary": payload.get("reason_summary") or insight_texts.get("reason_summary") or "현재 디바이스 가용성 및 라우팅을 고려하여 실행 가능합니다.",
                "severity": str(payload.get("severity") or ((alert or {}).get("severity") or "INFORMATION")).upper(),
                "recommended_action": "review_and_approve_mission",
                "confidence_level": "medium",
                "related_event_id": payload.get("event_id") or (alert or {}).get("event_id"),
                "related_alert_id": (alert or {}).get("alert_id"),
                "metadata": {"goal": goal, "location": location},
            }
        )
        proposal = self.registry_client.create_mission_proposal(
            {
                "title": payload.get("title") or f"{mission_type.replace('_', ' ').title()} Proposal",
                "mission_type": mission_type,
                "goal": goal or mission_type,
                "summary": payload.get("summary") or f"Proposal with {len(steps)} step(s) for operator review.",
                "source": payload.get("source") or "system_agent",
                "alert_id": (alert or {}).get("alert_id"),
                "event_id": payload.get("event_id") or (alert or {}).get("event_id"),
                "insight_id": insight.get("insight_id"),
                "steps": steps,
                "metadata": {"location": location, "fingerprint": suppression_fingerprint},
            }
        )
        approval = self.registry_client.create_approval(
            {
                "target_type": "mission_proposal",
                "target_id": proposal.get("proposal_id"),
                "summary": f"Approve mission proposal '{proposal.get('title')}'",
                "requested_action": "approve_mission_proposal",
                "related_insight_id": insight.get("insight_id"),
                "metadata": {
                    "mission_type": mission_type,
                    "goal": proposal.get("goal"),
                    "location": location,
                },
            }
        )
        proposal["approval_id"] = approval.get("approval_id")
        proposal = self.registry_client.create_mission_proposal(proposal)
        return {
            "insight": insight,
            "proposal": proposal,
            "approval": approval,
        }

    async def generate_multiple_mission_proposals(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        사용자 대화 전용: 3개의 mission proposal을 생성하여 반환
        각 proposal은 서로 다른 전략(표준/신속/정밀)을 기반으로 함

        최적화: analyze_intent는 한 번만 호출하고 결과를 재사용

        Returns: {
            "proposals": [proposal1, proposal2, proposal3],
            "approvals": [approval1, approval2, approval3],
            "insights": [insight1, insight2, insight3],
            "strategy_source": "llm" | "rule_based"
        }
        """
        devices = self.registry_client.list_devices()
        goal = str(payload.get("goal") or "").strip()

        # Step 1: LLM으로 mission_type 분류 (한 번만!)
        llm_intent, _ = await self.decision_engine.analyze_intent(goal, devices, self.state)
        if llm_intent and llm_intent.get("mission_type"):
            mission_type = llm_intent["mission_type"]
            location = llm_intent.get("location") or payload.get("location") or {}
        else:
            mission_type = self._infer_mission_type(goal, None)
            location = payload.get("location") or {}

        # Step 2: LLM으로 3가지 전략 생성
        strategies, strategy_error = await self.decision_engine.generate_proposal_strategies(
            goal, mission_type, location, devices, self.state
        )

        # Step 3: 각 전략으로 proposal/approval/insight 생성 (이미 분석된 mission_type 재사용)
        results = []
        for strategy in strategies:
            bundle = await self.generate_mission_proposal(
                {
                    **payload,
                    "title": strategy.get("title") or f"{mission_type} Proposal",
                    "summary": strategy.get("summary") or f"{strategy.get('approach', 'strategy')} approach",
                    "_approach": strategy.get("approach"),  # 메타데이터용
                },
                allow_suppression=False,
                _preset_mission_type=mission_type,  # 분석 결과 재사용
                _preset_location=location,
            )
            if not bundle.get("suppressed"):
                results.append(bundle)

        return {
            "proposals": [r["proposal"] for r in results],
            "approvals": [r["approval"] for r in results],
            "insights": [r["insight"] for r in results],
            "strategy_source": "llm" if not strategy_error else "rule_based",
        }

    def _command_proposal_title(self, goal: str, mission_type: str) -> str:
        goal_text = str(goal or "").strip()
        if goal_text:
            if any(keyword in goal_text for keyword in ["기뢰", "mine"]):
                return "기뢰 탐지 및 제거 미션 제안"
            if any(keyword in goal_text for keyword in ["수색", "survey", "탐사"]):
                return "기뢰 수색 미션 제안"
            if any(keyword in goal_text for keyword in ["복귀", "return to base", "rtb"]):
                return "안전 복귀 미션 제안"
        normalized = str(mission_type or "mission").replace("_", " ").strip().title()
        return f"{normalized} Mission Proposal"

    async def decide_approval_flow(self, approval_id: str, approved: bool, *, decided_by: str, notes: str | None = None) -> dict[str, Any]:
        approval = self.registry_client.decide_approval(
            approval_id,
            approved=approved,
            decided_by=decided_by,
            notes=notes,
        )
        if str(approval.get("target_type") or "") == "mission_reapproval":
            mission_id = str(approval.get("target_id") or "")
            mission = self.registry_client.get_mission(mission_id)
            mission.setdefault("timeline", []).append(
                {
                    "timestamp": utc_now(),
                    "type": "USER_REAPPROVAL",
                    "message": "User reapproval recorded.",
                    "data": {"approval_id": approval_id, "approved": approved},
                }
            )
            # ✅ Record mission reapproval decision timeline event (Ch.18-20)
            event_type = "MISSION_APPROVED" if approved else "MISSION_REJECTED"
            try:
                self.registry_client.append_mission_timeline_event(
                    mission_id=mission_id,
                    event_type=event_type,
                    actor=f"user_{decided_by}",
                    details={
                        "approval_id": str(approval.get("approval_id") or approval_id),
                        "step_id": str((approval.get("metadata") or {}).get("step_id") or ""),
                        "recovery_mode": str((approval.get("metadata") or {}).get("recovery_mode") or ""),
                        "notes": notes or "",
                    },
                )
            except Exception as e:
                logger.debug(f"Failed to record reapproval timeline: {e}")
            if not approved:
                mission["status"] = "FAILED"
                mission["completed_at"] = utc_now()
                mission["final_result"] = {"status": "FAILED", "reason": "user rejected mission reapproval"}
                self.registry_client.replace_mission(mission_id, mission)
                return {"approval": approval, "mission": mission}
            dispatch_state = dict((mission.get("metadata") or {}).get("dispatch_state") or self._build_dispatch_result_from_steps(mission.get("steps") or []))
            step_id = str((approval.get("metadata") or {}).get("step_id") or "")
            recovery_mode = str((approval.get("metadata") or {}).get("recovery_mode") or "retry_same_step")
            devices = self.registry_client.list_devices()
            current_step_def = next(
                (item for item in (mission.get("steps") or []) if isinstance(item, dict) and str(item.get("step_id") or "") == step_id),
                None,
            )
            current_step_state = next(
                (item for item in (dispatch_state.get("steps") or []) if isinstance(item, dict) and str(item.get("step_id") or "") == step_id),
                None,
            )
            if isinstance(current_step_def, dict) and isinstance(current_step_state, dict):
                self._prepare_step_recovery(current_step_def, current_step_state, devices, mode=recovery_mode)
            mission["status"] = "IN_PROGRESS"
            mission["completed_at"] = None
            mission["final_result"] = {}
            mission = self._sync_mission_from_dispatch_state(mission, dispatch_state)
            self.registry_client.replace_mission(mission_id, mission)
            mission = await self._start_mission_execution(mission)
            return {"approval": approval, "mission": mission}
        if str(approval.get("target_type") or "") != "mission_proposal":
            return {"approval": approval, "mission": None}
        proposal = self.registry_client.get_mission_proposal(str(approval.get("target_id")))
        proposal["status"] = "APPROVED" if approved else "CANCELLED"
        proposal = self.registry_client.create_mission_proposal(proposal)
        if not approved:
            fingerprint = str((proposal.get("metadata") or {}).get("fingerprint") or "")
            if fingerprint:
                self._recommendation_suppressions[fingerprint] = datetime.fromtimestamp(time.time() + 3600, tz=timezone.utc).isoformat()
            return {"approval": approval, "proposal": proposal, "mission": None}
        mission = self._mission_from_proposal(proposal, approval_id=str(approval.get("approval_id") or approval_id))
        mission = self.registry_client.create_mission(mission)
        # ✅ Record mission approval timeline event (Ch.18-20)
        try:
            self.registry_client.append_mission_timeline_event(
                mission_id=mission.get("mission_id", ""),
                event_type="MISSION_APPROVED",
                actor=f"user_{decided_by}",
                details={
                    "approval_id": str(approval.get("approval_id") or approval_id),
                    "notes": notes or "",
                },
            )
        except Exception as e:
            logger.debug(f"Failed to record mission approval timeline: {e}")
        mission = await self._start_mission_execution(mission)
        return {"approval": approval, "proposal": proposal, "mission": mission}

    def _current_hhmm(self) -> str:
        now = datetime.now()
        return now.strftime("%H:%M")

    def _condition_snapshot(self) -> dict[str, Any]:
        try:
            devices = self.registry_client.list_devices()
        except Exception:
            devices = []
        try:
            alerts = self.registry_client.list_alerts()
        except Exception:
            alerts = []
        try:
            missions = self.registry_client.list_missions()
        except Exception:
            missions = []
        return {
            "devices": devices,
            "alerts": alerts,
            "missions": missions,
            "devices.connected_count": len([device for device in devices if bool(device.get("connected"))]),
            "alerts.waiting_count": len([alert for alert in alerts if str(alert.get("status") or "") in {"waiting", "registered", "processing"}]),
            "missions.in_progress_count": len([mission for mission in missions if str(mission.get("status") or "").upper() == "IN_PROGRESS"]),
            "missions.failed_count": len([mission for mission in missions if str(mission.get("status") or "").upper() == "FAILED"]),
        }

    def _value_at_path(self, source: dict[str, Any], field_name: str) -> Any:
        if field_name in source:
            return source.get(field_name)
        current: Any = source
        for key in field_name.split("."):
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    def _condition_clause_matches(self, clause: dict[str, Any], source: dict[str, Any]) -> bool:
        field_name = str(clause.get("field") or "").strip()
        if not field_name:
            return False
        actual = self._value_at_path(source, field_name)
        if "exists" in clause:
            exists = bool(actual is not None)
            if exists != bool(clause.get("exists")):
                return False
        if "equals" in clause and actual != clause.get("equals"):
            return False
        if "not_equals" in clause and actual == clause.get("not_equals"):
            return False
        if "in" in clause:
            values = clause.get("in") or []
            if actual not in values:
                return False
        if "gte" in clause:
            try:
                if float(actual) < float(clause.get("gte")):
                    return False
            except (TypeError, ValueError):
                return False
        if "lte" in clause:
            try:
                if float(actual) > float(clause.get("lte")):
                    return False
            except (TypeError, ValueError):
                return False
        return True

    def _trigger_matches(
        self,
        trigger: dict[str, Any],
        *,
        event: dict[str, Any] | None = None,
        snapshot: dict[str, Any] | None = None,
    ) -> bool:
        trigger_type = str(trigger.get("type") or trigger.get("trigger_type") or "").upper()
        if trigger_type == "MANUAL":
            return False
        if trigger_type == "EVENT":
            if event is None:
                return False
            return str(trigger.get("event_type") or "").strip().lower() == str(event.get("event_type") or event.get("type") or "").strip().lower()
        if trigger_type == "TIME":
            hhmm = str(trigger.get("time") or trigger.get("at") or "").strip()
            return bool(hhmm) and hhmm == self._current_hhmm()
        if trigger_type == "CONDITION":
            source = snapshot or event or {}
            if isinstance(trigger.get("all"), list):
                return all(
                    isinstance(clause, dict) and self._condition_clause_matches(clause, source)
                    for clause in trigger.get("all") or []
                )
            if isinstance(trigger.get("any"), list):
                return any(
                    isinstance(clause, dict) and self._condition_clause_matches(clause, source)
                    for clause in trigger.get("any") or []
                )
            return self._condition_clause_matches(trigger, source)
        return False

    def _infer_mission_type(self, goal: str, alert_type: Any) -> str:
        goal_text = str(goal or "").lower()
        alert_text = str(alert_type or "").lower()
        if "mine" in goal_text or "기뢰" in goal_text or alert_text == "mine_detection":
            return "mine_clearance"
        if "survey" in goal_text or "scan" in goal_text or "탐지" in goal_text:
            return "survey"
        if "inspect" in goal_text or "intervention" in goal_text:
            return "inspection"
        return "generic_mission"

    def _build_generic_steps_for_goal(self, goal: str, devices: list[dict[str, Any]], location: dict[str, Any]) -> list[dict[str, Any]]:
        action = "survey_depth" if any("survey" in goal.lower() for _ in [0]) else "hold_position"
        target = self._select_best_device(devices, "survey_depth", location) if action == "survey_depth" else None
        if target is None:
            for device in devices:
                if self._device_is_connected(device) and str(device.get("layer") or "") in {"lower", "middle"}:
                    target = device
                    break
        if target is None:
            return []
        return [
            self._build_step(
                "step-1",
                step_type="generic_action",
                evaluation_policy="all_tasks_success_v1",
                tasks=[self._build_task("task-1", action, target, location)],
            )
        ]

    def _mission_from_proposal(self, proposal: dict[str, Any], *, approval_id: str) -> dict[str, Any]:
        mission_id = f"mission-{uuid4()}"
        timeline = [
            {
                "timestamp": utc_now(),
                "type": "MISSION_CREATED",
                "message": "Mission created from approved proposal.",
                "data": {"proposal_id": proposal.get("proposal_id"), "approval_id": approval_id},
            },
            {
                "timestamp": utc_now(),
                "type": "USER_APPROVAL",
                "message": "User approval recorded.",
                "data": {"approval_id": approval_id},
            },
        ]
        return {
            "mission_id": mission_id,
            "title": proposal.get("title") or "Mission",
            "mission_type": proposal.get("mission_type") or "generic_mission",
            "goal": proposal.get("goal") or "",
            "status": "READY",
            "summary": proposal.get("summary") or "",
            "source": proposal.get("source") or "system_agent",
            "alert_id": proposal.get("alert_id"),
            "event_id": proposal.get("event_id"),
            "proposal_id": proposal.get("proposal_id"),
            "approval_id": approval_id,
            "insight_id": proposal.get("insight_id"),
            "steps": proposal.get("steps") or [],
            "timeline": timeline,
            "logs": list(timeline),
            "device_execution_results": [],
            "final_result": {},
            "metadata": {
                **dict(proposal.get("metadata") or {}),
                "dispatch_state": self._build_dispatch_result_from_steps(proposal.get("steps") or []),
            },
            "approved_at": utc_now(),
        }

    def _sync_mission_from_dispatch_state(self, mission: dict[str, Any], dispatch_state: dict[str, Any]) -> dict[str, Any]:
        step_states = dispatch_state.get("steps") or []
        mission_steps = mission.get("steps") or []
        for mission_step in mission_steps:
            step_id = str(mission_step.get("step_id") or "")
            step_state = next((item for item in step_states if isinstance(item, dict) and str(item.get("step_id") or "") == step_id), None)
            if not isinstance(step_state, dict):
                continue
            mission_step["status"] = self._task_status(step_state.get("status") or mission_step.get("status"))
            task_states = step_state.get("tasks") or []
            for mission_task in mission_step.get("tasks") or []:
                state = next((item for item in task_states if isinstance(item, dict) and str(item.get("logical_task_id") or item.get("task_id") or "") == str(mission_task.get("logical_task_id") or mission_task.get("task_id") or "")), None)
                if not isinstance(state, dict):
                    continue
                mission_task["dispatch_status"] = self._task_status(state.get("dispatch_status"))
                mission_task["execution_status"] = self._task_status(state.get("execution_status"))
                mission_task["attempt"] = state.get("attempt", mission_task.get("attempt", 0))
                mission_task["attempted_device_ids"] = state.get("attempted_device_ids") or mission_task.get("attempted_device_ids") or []
                mission_task["completed_at"] = state.get("completed_at")
        mission.setdefault("metadata", {})["dispatch_state"] = dispatch_state
        mission["device_execution_results"] = list(dispatch_state.get("execution_results") or [])
        return mission

    def _append_dispatch_timeline_entries(self, mission: dict[str, Any], dispatch: dict[str, Any], mission_steps: list[dict[str, Any]]) -> None:
        step_id = str(dispatch.get("step_id") or "")
        if not step_id:
            return
        step_def = next(
            (item for item in mission_steps if isinstance(item, dict) and str(item.get("step_id") or "") == step_id),
            None,
        )
        mission.setdefault("timeline", []).append(
            {
                "timestamp": utc_now(),
                "type": "STEP_STARTED",
                "message": f"Step {step_id} started.",
                "data": {
                    "step_id": step_id,
                    "step_type": (step_def or {}).get("step_type"),
                },
            }
        )
        for task_result in dispatch.get("task_results") or []:
            if not isinstance(task_result, dict):
                continue
            task_id = str(task_result.get("task_id") or "")
            mission.setdefault("timeline", []).append(
                {
                    "timestamp": utc_now(),
                    "type": "TASK_STARTED",
                    "message": f"Task {task_id} dispatched for execution.",
                    "data": {
                        "step_id": step_id,
                        "task_id": task_id,
                        "target_device_id": task_result.get("target_device_id"),
                        "route_agent_id": task_result.get("route_agent_id"),
                        "dispatch": task_result.get("dispatch"),
                    },
                }
            )

    def _normalize_device_execution_entry(
        self,
        *,
        mission_id: str,
        reporter: str,
        step_id: str,
        task_id: str,
        normalized_status: str,
        execution_log: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        raw_result = execution_log.get("result") if isinstance(execution_log.get("result"), dict) else {}
        forwarded_payload = execution_log.get("payload") if isinstance(execution_log.get("payload"), dict) else {}
        raw_refs = raw_result.get("output_refs") or raw_result.get("raw_data_ref") or raw_result.get("artifacts") or []
        if isinstance(raw_refs, dict):
            raw_refs = [raw_refs]
        if not isinstance(raw_refs, list):
            raw_refs = [raw_refs]
        return {
            "mission_id": mission_id,
            "device_id": str(
                execution_log.get("source_device_id")
                or forwarded_payload.get("source_device_id")
                or payload.get("source_device_id")
                or ""
            ),
            "reporter": reporter,
            "step_id": step_id,
            "task_id": task_id,
            "task_status": normalized_status,
            "status": normalized_status,
            "acceptance_status": raw_result.get("acceptance_status"),
            "started_at": raw_result.get("started_at") or raw_result.get("accepted_at"),
            "finished_at": raw_result.get("finished_at") or raw_result.get("reported_at"),
            "success": normalized_status == "COMPLETED",
            "failure_reason": raw_result.get("reason") or raw_result.get("error") or raw_result.get("failure_message"),
            "failure_category": self._standardize_failure_category(
                raw_result.get("failure_category") or execution_log.get("failure_category") or ("unknown" if normalized_status != "COMPLETED" else None)
            ),
            "location": (
                raw_result.get("location")
                or execution_log.get("location")
                or execution_log.get("command", {}).get("params", {}).get("location")
                or forwarded_payload.get("location")
            ),
            "data_summary": raw_result.get("summary") or raw_result.get("output_summary") or execution_log.get("result_summary"),
            "raw_data_ref": raw_refs,
            "device_state_changes": raw_result.get("device_state_changes") or execution_log.get("device_state_changes") or {},
            "device_agent_judgement": raw_result.get("agent_judgement") or execution_log.get("agent_judgement") or execution_log.get("action"),
            "payload": execution_log,
            "received_at": utc_now(),
        }

    async def _start_mission_execution(self, mission: dict[str, Any]) -> dict[str, Any]:
        devices = self.registry_client.list_devices()
        steps = mission.get("steps") or []
        if not steps:
            mission["status"] = "FAILED"
            mission["completed_at"] = utc_now()
            mission["final_result"] = {"status": "FAILED", "reason": "no_steps_generated"}
            mission.setdefault("timeline", []).append({
                "timestamp": utc_now(),
                "type": "DISPATCH_FAILED",
                "message": "Mission has no steps — no capable device found.",
                "data": {"mission_id": mission.get("mission_id")},
            })
            self.registry_client.replace_mission(str(mission.get("mission_id")), mission)
            return mission
        mission["status"] = "IN_PROGRESS"
        mission["started_at"] = utc_now()
        mission.setdefault("timeline", []).append(
            {
                "timestamp": utc_now(),
                "type": "MISSION_STARTED",
                "message": "Mission execution started.",
                "data": {"mission_id": mission.get("mission_id")},
            }
        )
        dispatch_state = dict((mission.get("metadata") or {}).get("dispatch_state") or self._build_dispatch_result_from_steps(steps))
        response_like = {
            "mission_id": mission.get("mission_id"),
            "response_id": mission.get("mission_id"),
            "alert_id": mission.get("alert_id"),
            "reason": mission.get("title"),
            "dispatch_result": dispatch_state,
            "params": {"steps": steps},
        }
        dispatch = await self._dispatch_next_step(response_like, steps, devices, logging.getLogger(__name__))
        mission = self._sync_mission_from_dispatch_state(mission, dispatch)
        self._append_dispatch_timeline_entries(mission, dispatch, steps)
        mission.setdefault("timeline", []).append(
            {
                "timestamp": utc_now(),
                "type": "TASK_DISPATCHED" if dispatch.get("delivered") else "DISPATCH_FAILED",
                "message": "Initial mission step dispatched." if dispatch.get("delivered") else "Initial mission dispatch failed.",
                "data": dispatch,
            }
        )
        if not dispatch.get("delivered"):
            mission["status"] = "FAILED"
            mission["completed_at"] = utc_now()
            mission["final_result"] = {"status": "FAILED", "reason": dispatch.get("error") or "dispatch_failed"}
        self.registry_client.replace_mission(str(mission.get("mission_id")), mission)
        return mission

    def _build_task(
        self,
        task_id: str,
        action: str,
        target_device: dict[str, Any],
        location: dict[str, Any],
        *,
        extra_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        requested_action = self._canonical_action(action)
        dispatch_action = self._resolve_device_action(target_device, requested_action)
        route_hop = self._resolve_route_hop(target_device)
        merged_params = {
            "action": dispatch_action,
            "requested_action": requested_action,
            "location": location,
            "mission_type": "mine_clearance",
            "target_device_id": self._device_id(target_device),
        }
        if isinstance(extra_params, dict):
            merged_params.update(extra_params)
        return {
            "task_id": task_id,
            "logical_task_id": task_id,
            "attempt": 0,
            "attempted_device_ids": [self._device_id(target_device)],
            "action": dispatch_action,
            "requested_action": requested_action,
            "target_device_id": self._device_id(target_device),
            "target_device_name": target_device.get("name"),
            "target_device_type": target_device.get("device_type"),
            "route_agent_id": self._device_id(route_hop),
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

    def _parse_iso_ts(self, value: str | None) -> float:
        if not value:
            return 0.0
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0.0

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
            if str(device.get("layer") or "") not in {"lower", "middle"}:
                continue
            device_id = self._device_id(device)
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

        requested_action = self._canonical_action(str(alert.get("recommended_action") or "survey_depth"))
        available = self._has_capable_device(devices, requested_action, location, include_reserved=False)
        exists = self._has_capable_device(devices, requested_action, location, include_reserved=True)
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
        """
        다중 요소 기반 device 선택 (Phase 2, Step 3 최적화)
        
        Scoring Factors:
        - Distance (25%): 목표까지의 거리
        - Battery (30% 경고 / 10% 자동 복귀): 배터리 수준
        - Capability (20%): action 수행 능력
        - Reliability (15%): 역사적 성공률
        - Workload (15%): 현재 작업 부하
        - Availability (5%): 유휴 시간
        """
        try:
            # TaskDispatcher 활용
            selected = self.task_dispatcher.select_best_device(
                devices=devices,
                action=action,
                location=location,
                exclude_ids=exclude_ids,
                preferred_id=preferred_id,
            )
            if selected is not None:
                return selected
        except Exception as e:
            logger.error(f"TaskDispatcher error, falling back to distance-based selection: {e}")

        # Fallback: alias-aware 기존 거리 기반 선택
        excluded = exclude_ids or set()
        candidates = [
            device
            for device in devices
            if self._device_is_connected(device)
            and str(device.get("layer") or "") in {"lower", "middle"}
            and self._device_can_execute(device, action)
            and self._device_id(device) not in excluded
            and not self._is_device_reserved(self._device_id(device))
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
                self._device_id(device),
            )

        return min(candidates, key=rank)

    def _resolve_route_hop(self, target_device: dict[str, Any]) -> dict[str, Any]:
        parent_id = target_device.get("parent_id")
        if not parent_id:
            return target_device
        try:
            parent = self.registry_client.get_device(str(parent_id))
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

    def _canonical_action(self, action: str | None) -> str:
        raw = str(action or "").strip().lower()
        if not raw:
            return ""
        for canonical, aliases in self._action_aliases.items():
            if raw == canonical or raw in aliases:
                return canonical
        return raw

    def _device_supported_actions(self, device: dict[str, Any]) -> set[str]:
        actions_payload = device.get("actions") or []
        if isinstance(actions_payload, dict):
            action_values = list(actions_payload.get("custom", []) or []) + list(actions_payload.get("core", []) or [])
        else:
            action_values = list(actions_payload or [])
        actions = set(str(v).lower() for v in action_values)
        agent = device.get("agent") or {}
        if isinstance(agent, dict):
            actions.update(str(v).lower() for v in agent.get("available_actions") or [])
            actions.update(str(v).lower() for v in agent.get("skills") or [])
        return actions

    def _resolve_device_action(self, device: dict[str, Any], action: str) -> str:
        canonical = self._canonical_action(action)
        supported = self._device_supported_actions(device)
        for candidate in self._action_aliases.get(canonical, [canonical]):
            if candidate in supported:
                return candidate

        device_type = str(device.get("device_type") or "").upper()
        if canonical == "survey_depth" and device_type == "AUV":
            return "scan_area" if "scan_area" in supported else canonical
        if canonical == "remove_mine" and device_type == "ROV":
            return "grab_object" if "grab_object" in supported else canonical
        return canonical

    def _device_can_execute(self, device: dict[str, Any], action: str) -> bool:
        canonical = self._canonical_action(action)
        device_type = str(device.get("device_type") or "").upper()
        actions = self._device_supported_actions(device)

        if canonical == "survey_depth":
            return device_type == "AUV" or any(keyword in actions for keyword in self._action_aliases["survey_depth"])
        if canonical == "remove_mine":
            return device_type == "ROV" or any(keyword in actions for keyword in self._action_aliases["remove_mine"])
        return canonical in actions

    def _device_id(self, device: dict[str, Any]) -> int:
        """registry_id(내부 numeric id) 우선, 없으면 id 변환 시도."""
        rid = device.get("registry_id")
        if rid is not None:
            return int(rid)
        try:
            return int(device.get("id", 0))
        except (TypeError, ValueError):
            return 0

    def _distance_to_location(self, device: dict[str, Any], location: dict[str, Any]) -> float:
        try:
            lat = float(location.get("lat") if location.get("lat") is not None else location.get("latitude"))
            lon = float(location.get("lon") if location.get("lon") is not None else location.get("longitude"))
            device_lat = float(device.get("latitude") if device.get("latitude") is not None else device.get("lat"))
            device_lon = float(device.get("longitude") if device.get("longitude") is not None else device.get("lon"))
        except (TypeError, ValueError):
            return float("inf")
        lat_delta = device_lat - lat
        lon_delta = device_lon - lon
        return lat_delta * lat_delta + lon_delta * lon_delta

    def _normalize_device_from_registry(self, device: dict[str, Any]) -> dict[str, Any]:
        """
        P3 (보고 기반): Registry로부터 받은 device dict를 정규화
        
        Agent가 주기적으로 보고한 위치와 배터리 정보를 최상위 수준에 반영하여,
        Task 분배 시 최신 정보를 사용하도록 함
        """
        # Agent가 보고한 위치가 더 최신이면 device 최상위 수준에 반영
        agent = device.get("agent") or {}
        if isinstance(agent, dict):
            if agent.get("latitude") is not None:
                device["latitude"] = agent["latitude"]
            if agent.get("longitude") is not None:
                device["longitude"] = agent["longitude"]
            # Agent가 보고한 배터리 정보도 함께 반영
            if agent.get("battery_percent") is not None:
                device["battery_percent"] = agent["battery_percent"]
        return device

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

    def _standardize_failure_category(self, category: Any) -> str | None:
        """Normalize failure category to lowercase and validate against allowed values."""
        if not category:
            return None
        normalized = str(category).lower().strip()
        valid_categories = {"device", "communication", "sensor", "mission", "policy", "user", "unknown"}
        if normalized in valid_categories:
            return normalized
        return "unknown"

    async def handle_device_recovery_report(self, device_id: str, report: dict[str, Any]) -> None:
        """Device Agent 복구 후 로컬 상태 보고 처리 (Ch.16)"""
        try:
            logger.info(f"📡 Device {device_id} recovery report received")

            # Device 상태를 "online"으로 복원
            device = self.registry_client.get_device(device_id)
            if device and device.get("connectivity_status") == "offline":
                # Connectivity status를 online으로 변경
                self.registry_client.update_device_connectivity(device_id, "online")
                logger.info(f"✅ Device {device_id} marked as online")

            # Task 결과 동기화
            missions_to_update: list[dict[str, Any]] = []
            for task_result in report.get("local_task_results", []):
                task_id = task_result.get("task_id")
                if task_id:
                    # 해당 mission과 task를 찾아 상태 업데이트
                    try:
                        missions = self.registry_client.list_missions()
                        for mission in missions:
                            # Mission의 step들 중 해당 task를 찾음
                            for step in mission.get("steps", []):
                                for task in step.get("tasks", []):
                                    if task.get("task_id") == task_id:
                                        # Task 상태 업데이트
                                        task["execution_status"] = self._task_status(task_result.get("status"), "COMPLETED")
                                        task["result"] = task_result
                                        if mission not in missions_to_update:
                                            missions_to_update.append(mission)
                                        logger.info(f"✅ Task {task_id} result synced: {task_result.get('status')}")
                    except Exception as e:
                        logger.debug(f"Failed to sync task {task_id}: {e}")

            for mission in missions_to_update:
                try:
                    self.registry_client.replace_mission(str(mission.get("mission_id") or ""), mission)
                except Exception as exc:
                    logger.debug(f"Failed to persist synced mission {mission.get('mission_id')}: {exc}")

            # Event 동기화
            for event in report.get("local_events", []):
                try:
                    self.registry_client.ingest_event(event)
                    logger.debug(f"✅ Event {event.get('event_id')} synced")
                except Exception as e:
                    logger.debug(f"Failed to sync event: {e}")

            logger.info(f"✅ Device {device_id} recovery sync completed")

        except Exception as e:
            logger.error(f"❌ Failed to handle recovery report for device {device_id}: {e}")

    def _is_step_terminal(self, step_state: dict[str, Any]) -> bool:
        task_states = [task for task in (step_state.get("tasks") or []) if isinstance(task, dict)]
        if not task_states:
            return False
        terminal_statuses = {"COMPLETED", "FAILED", "CANCELLED", "ABORTED"}
        return all(self._task_status(task.get("execution_status")) in terminal_statuses for task in task_states)

    def _evaluate_step(
        self,
        response: dict[str, Any],
        step: dict[str, Any],
        step_state: dict[str, Any],
        step_execution_results: list[dict[str, Any]],
        devices: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Step 평가: PolicyEvaluator를 사용하여 의사결정 (P3 보고 기반, P9 기록)
        
        이 메서드는 PolicyEvaluator로 위임하여 정책 관리를 중앙화합니다.
        새로운 정책 추가 시 PolicyEvaluator에만 추가하면 됩니다.
        
        평가 결과를 Event로 기록하여 P9 (기록 가능성) 원칙을 준수합니다.
        
        Args:
            response: Mission response 정보
            step: Step 정의
            step_state: Step 실행 상태
            step_execution_results: Task 실행 결과 목록
            devices: 사용 가능한 device 목록
        
        Returns:
            평가 결과 (decision, sufficient, reason 등 포함)
        """
        # P3 (보고 기반): PolicyEvaluator가 정책에 따라 의사결정
        evaluation = self.policy_evaluator.evaluate(
            response, step, step_state, step_execution_results, devices
        )
        
        # P9 (기록 가능성): 평가 결과를 Event로 기록
        try:
            event = create_step_evaluation_event(
                source_agent_id=self.state.agent_id,
                response_id=response.get("response_id", ""),
                step_id=step.get("step_id", ""),
                policy=evaluation.get("policy", ""),
                decision=evaluation.get("decision", ""),
                sufficient=evaluation.get("sufficient", False),
                metrics={
                    "task_total": evaluation.get("task_total", 0),
                    "completed_task_count": evaluation.get("completed_task_count", 0),
                    "failed_task_count": evaluation.get("failed_task_count", 0),
                    "usable_task_count": evaluation.get("usable_task_count", 0),
                },
                reason=evaluation.get("reason", ""),
            )
            self.event_publisher.publish(event)
        except Exception as e:
            logger.debug(f"Failed to publish step evaluation event: {e}")
        
        return evaluation

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
            if self._task_status(task_state.get("execution_status")) != "FAILED":
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
            if self._task_status(task_state.get("execution_status")) != "FAILED":
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
            if self._task_status(task_state.get("execution_status")) != "FAILED":
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
                attempted_device_ids = [*list(task_state.get("attempted_device_ids") or []), self._device_id(replacement)]
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
                    "dispatch_status": "PENDING",
                    "execution_status": "PENDING",
                    "dispatch": None,
                    "execution_result": None,
                    "completed_at": None,
                    "recovery_history": current_history,
                }
            )
            recovered_any = True

        if recovered_any:
            step_state["status"] = "PENDING"
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
        mission_id = str(response.get("mission_id") or response.get("response_id") or "")
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
            if step_state and self._task_status(step_state.get("status")) in {"ASSIGNED", "IN_PROGRESS", "COMPLETED"}:
                continue
            depends_on = [str(dep) for dep in (step.get("depends_on") or [])]
            if any(
                not any(
                    isinstance(state, dict)
                    and str(state.get("step_id")) == dep_step_id
                    and self._task_status(state.get("status")) == "COMPLETED"
                    for state in step_states
                )
                for dep_step_id in depends_on
            ):
                continue
            # ✅ Record step_started timeline event (Ch.18-20)
            try:
                self.registry_client.append_mission_timeline_event(
                    mission_id=mission_id,
                    event_type="STEP_STARTED",
                    actor="system",
                    details={
                        "step_type": step.get("step_type", "unknown"),
                        "num_tasks": len(step.get("tasks") or []),
                    },
                    step_index=str(step["step_id"]),
                )
            except Exception as e:
                logger.debug(f"Failed to record step_started timeline: {e}")
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
                                # ✅ Record task_assigned timeline event (Ch.18-20)
                                try:
                                    self.registry_client.append_mission_timeline_event(
                                        mission_id=mission_id,
                                        event_type="TASK_ASSIGNED",
                                        actor="system",
                                        details={
                                            "action": task["action"],
                                            "target_device_id": str(task["target_device_id"]),
                                            "route_agent_id": str(task["route_agent_id"]),
                                        },
                                        task_id=str(task["task_id"]),
                                        step_index=str(step["step_id"]),
                                    )
                                except Exception as e:
                                    logger.debug(f"Failed to record task_assigned timeline: {e}")
                                try:
                                    self.registry_client.ingest_event(
                                        {
                                            "source_system": "system_agent",
                                            "source_agent_id": str(self.state.agent_id),
                                            "source_role": str(self.state.role or "mission_planner"),
                                            "event_type": "SYS_TASK_DISPATCHED",
                                            "severity": "INFO",
                                            "title": f"Task {task['task_id']} dispatched",
                                            "description": f"Task {task['task_id']} dispatched to device {task['target_device_id']}.",
                                            "target_type": "TASK",
                                            "target_id": str(task["task_id"]),
                                            "data": {
                                                "mission_id": mission_id,
                                                "step_id": str(step["step_id"]),
                                                "task_id": str(task["task_id"]),
                                                "action": task["action"],
                                                "target_device_id": str(task["target_device_id"]),
                                                "route_agent_id": str(task["route_agent_id"]),
                                            },
                                            "target_agents": ["SystemSentinel", "InsightReporter"],
                                        }
                                    )
                                except Exception as e:
                                    logger.debug(f"Failed to record task dispatched event: {e}")
                            task_state["dispatch"] = dispatch
                            task_state["dispatch_status"] = "ASSIGNED" if dispatch.get("delivered") else "FAILED"
                            task_state["acceptance_status"] = dispatch.get("acceptance_status")
                            task_state["failure_message"] = dispatch.get("reason")
                            task_state["dispatched_task_id"] = (
                                f"{response['response_id']}:{step['step_id']}:{task['task_id']}"
                            )
                            break
            if isinstance(step_state, dict):
                step_state["status"] = "FAILED" if delivery_failed else "ASSIGNED"
            dispatch_result["steps"] = step_states
            if delivery_failed:
                # ✅ Record failed task dispatch as task_failed timeline event (Ch.18-20)
                for (task, _task_response), dispatch in zip(task_requests, dispatches):
                    if not dispatch.get("delivered"):
                        try:
                                self.registry_client.append_mission_timeline_event(
                                    mission_id=mission_id,
                                    event_type="TASK_FAILED",
                                    actor="system",
                                    details={
                                        "dispatch_error": dispatch.get("error", "unknown"),
                                    "failure_category": "communication",
                                    "failure_message": f"Task dispatch failed: {dispatch.get('error', 'unknown')}",
                                },
                                task_id=str(task["task_id"]),
                                step_index=str(step["step_id"]),
                            )
                        except Exception as e:
                            logger.debug(f"Failed to record dispatch failure timeline: {e}")
                return {
                    "delivered": False,
                    "error": "step_dispatch_failed",
                    "step_id": step["step_id"],
                    "task_results": task_results,
                    "steps": step_states,
                    "execution_results": dispatch_result.get("execution_results") or [],
                    "execution_result": dispatch_result.get("execution_result"),
                    "execution_aggregate_status": dispatch_result.get("execution_aggregate_status"),
                    "step_evaluations": dispatch_result.get("step_evaluations") or {},
                    "replan_history": dispatch_result.get("replan_history") or [],
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
                "step_evaluations": dispatch_result.get("step_evaluations") or {},
                "replan_history": dispatch_result.get("replan_history") or [],
            }

        return {
            "delivered": True,
            "task_id": response["response_id"],
            "step_id": None,
            "steps": step_states,
            "execution_results": dispatch_result.get("execution_results") or [],
            "execution_result": dispatch_result.get("execution_result"),
            "execution_aggregate_status": dispatch_result.get("execution_aggregate_status"),
            "step_evaluations": dispatch_result.get("step_evaluations") or {},
            "replan_history": dispatch_result.get("replan_history") or [],
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
                registry_id = str(agent.get("registry_id") or "")

                if (
                    str(agent_id_from_info) == str(target_agent_id)
                    or device_id == str(target_agent_id)
                    or registry_id == str(target_agent_id)
                ):
                    target_agent = agent
                    break
            except Exception as e:
                logger.debug(f"Error checking agent {agent.get('id')}: {e}")
                continue

        if not target_agent:
            logger.debug(f"Target agent {target_agent_id} not found in cache, skipping A2A")
            return {"delivered": False, "error": "target_not_found"}

        # Check device connectivity status before dispatching
        connectivity_status = target_agent.get("connectivity_status", "offline")
        if connectivity_status != "online":
            logger.warning(f"Target device {target_agent_id} connectivity_status is '{connectivity_status}', skipping dispatch")
            return {"delivered": False, "error": f"device_{connectivity_status}"}

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
                                    "mission_id": response.get("mission_id") or response.get("response_id"),
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
                    "metadata": {
                        "sender_id": self.state.agent_id,
                        "sender_device_id": "system",
                    }
                }
            }

            # Send POST request to target agent using JSON-RPC
            data = json.dumps(a2a_message).encode("utf-8")
            # Device agent handles JSON-RPC at root endpoint
            rpc_endpoint = endpoint if endpoint else None
            if not rpc_endpoint:
                logger.warning(f"Target agent {target_agent_id} has no endpoint")
                return {"delivered": False, "error": "target_endpoint_missing"}
            
            def _do_urlopen(url: str, body: bytes, timeout: int) -> dict:
                req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return json.loads(resp.read() or b"{}")

            result = await asyncio.to_thread(_do_urlopen, rpc_endpoint, data, 15)
            artifact_data = {}
            try:
                artifact_data = (((result.get("result") or {}).get("artifacts") or [])[0].get("parts") or [])[0].get("data") or {}
            except Exception:
                artifact_data = {}
            acceptance = str(artifact_data.get("acceptance_status") or artifact_data.get("status") or "").upper()
            accepted = acceptance != "REJECTED"
            logger.info(f"A2A task sent to {target_agent_id}: accepted={accepted} status={acceptance or 'unknown'}")

            # ✅ Record task acceptance/rejection timeline event (Ch.18-20)
            mission_id = str(response.get("mission_id") or response.get("response_id") or "")
            task_id = str(response.get("task_id") or "")
            step_id = str(response.get("step_id") or "")
            if mission_id:
                try:
                    event_type = "task_accepted" if accepted else "task_rejected"
                    self.registry_client.append_mission_timeline_event(
                        mission_id=mission_id,
                        event_type=event_type,
                        actor=f"device_{target_agent_id}",
                        details={
                            "acceptance_status": acceptance,
                            "reason": artifact_data.get("reason") or "",
                        },
                        task_id=task_id if task_id else None,
                        step_index=step_id if step_id else None,
                    )
                except Exception as e:
                    logger.debug(f"Failed to record task acceptance timeline: {e}")

            # ✅ Log A2A message to Registry Server (archi Ch.14.1)
            try:
                task_id = str(response.get("task_id") or "")
                mission_id = str(response.get("mission_id") or response.get("response_id") or "")
                self.registry_client.log_a2a_message(
                    direction="outbound",
                    from_agent_id=self.state.agent_id,
                    to_agent_id=target_agent_id,
                    message_type="task.assign",
                    task_id=task_id if task_id else None,
                    mission_id=mission_id if mission_id else None,
                    payload=a2a_message.get("params", {}).get("message", {}),
                )
            except Exception as e:
                logger.debug(f"A2A logging failed (non-critical): {e}")

            return {
                "delivered": accepted,
                "endpoint": endpoint,
                "task_id": response.get("response_id"),
                "a2a_result": result,
                "acceptance_status": acceptance or "ACCEPTED",
                "reason": artifact_data.get("reason"),
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

    def start_async_command(self, command: dict[str, Any], *, requested_by: str = "user") -> dict[str, Any]:
        request_id = f"cmd-{uuid4()}"
        now = utc_now()
        request_record = {
            "request_id": request_id,
            "status": "queued",
            "requested_by": requested_by,
            "command": command,
            "result": None,
            "error": None,
            "created_at": now,
            "updated_at": now,
            "started_at": None,
            "finished_at": None,
        }
        self._command_requests[request_id] = request_record

        task = asyncio.create_task(self._run_async_command(request_id, command))
        self._command_request_tasks.add(task)
        task.add_done_callback(self._command_request_tasks.discard)

        self.state.remember(
            {
                "kind": "command_async_queued",
                "at": now,
                "request_id": request_id,
                "command": command,
            }
        )

        return {
            "accepted": True,
            "request_id": request_id,
            "status": "queued",
            "created_at": now,
        }

    def get_async_command(self, request_id: str) -> dict[str, Any] | None:
        item = self._command_requests.get(request_id)
        if item is None:
            return None
        return dict(item)

    async def _run_async_command(self, request_id: str, command: dict[str, Any]) -> None:
        request = self._command_requests.get(request_id)
        if request is None:
            return

        started_at = utc_now()
        request["status"] = "IN_PROGRESS"
        request["started_at"] = started_at
        request["updated_at"] = started_at

        try:
            result = await self.handle_command_with_llm(command)
            finished_at = utc_now()
            request["status"] = "COMPLETED"
            request["result"] = result
            request["updated_at"] = finished_at
            request["finished_at"] = finished_at
            self.state.remember(
                {
                    "kind": "command_async_completed",
                    "at": finished_at,
                    "request_id": request_id,
                }
            )
        except Exception as exc:
            finished_at = utc_now()
            request["status"] = "FAILED"
            request["error"] = str(exc)
            request["updated_at"] = finished_at
            request["finished_at"] = finished_at
            self.state.remember(
                {
                    "kind": "command_async_failed",
                    "at": finished_at,
                    "request_id": request_id,
                    "error": str(exc),
                }
            )
            logger.exception("Async command failed: request_id=%s", request_id)

    async def handle_command_with_llm(self, command: dict[str, Any]) -> dict[str, Any]:
        """사용자 명령을 LLM으로 해석한 뒤 실행. LLM 불가 시 직접 실행."""
        logger = logging.getLogger(__name__)
        try:
            devices = self.registry_client.list_devices()
        except Exception:
            devices = []

        llm_result, llm_error = await self.decision_engine.analyze_command(command, devices, self.state)

        if llm_error:
            # LLM 오류 발생 - Event 기록 후 fallback 정규화 경로 진행
            self.event_publisher.publish(
                create_device_status_change_event(
                    source_agent_id=self.state.agent_id,
                    device_id=0,  # System-level event
                    device_name="system",
                    old_status="OPERATIONAL",
                    new_status="DEGRADED",
                    reason=f"LLM error during command: {llm_error.get('error_type')} - {llm_error.get('message')[:50]}"
                )
            )
            logger.warning(f"명령 LLM 해석 실패: {llm_error}")
            llm_result = None

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

        command_goal_text = " ".join(
            str(part or "")
            for part in [
                command.get("goal"),
                command.get("reason"),
                llm_result.get("reasoning") if llm_result else "",
                json.dumps(command.get("params") or {}, ensure_ascii=False),
            ]
        ).strip().lower()
        command_action = str(resolved.get("action") or "").strip()
        if any(keyword in command_goal_text for keyword in ["기뢰", "mine", "mine_clearance", "mine_survey"]):
            command_action = "mission.assign"
            resolved["action"] = "mission.assign"
            resolved.setdefault("params", {})
            resolved["params"]["mission_type"] = "mine_clearance"
            resolved["params"]["requested_mission_type"] = "mine_clearance"
            if "desired_outcome" not in resolved["params"]:
                resolved["params"]["desired_outcome"] = "mine_clearance"
        command_result = self.command_controller.apply(self.state, resolved)
        if isinstance(command_result, dict):
            command_result["command"] = resolved
            command_result["resolved_command"] = resolved
            if "action" in resolved:
                command_result["action"] = resolved.get("action")
        if llm_result is not None:
            self.state.remember(
                {
                    "kind": "command_llm_interpreted_normalized",
                    "at": utc_now(),
                    "original": command,
                    "llm": {
                        **dict(llm_result),
                        "normalized_action": command_action,
                        "normalized_goal": command.get("goal") or command.get("reason") or llm_result.get("reasoning"),
                    },
                    "resolved_command": resolved,
                }
            )
        proposal_bundle: dict[str, Any] | None = None
        if command_action in {"mission.assign", "task.assign", "approve_response"}:
            base_goal = command.get("goal") or command.get("reason") or (llm_result or {}).get("reasoning") or ""
            goal = str(base_goal).strip() if base_goal else str(command.get("action") or "operator command").strip()
            params_mission_type = str((command.get("params") or {}).get("mission_type") or (command.get("params") or {}).get("desired_outcome") or "").strip()
            mission_type = self._infer_mission_type(goal, None)
            if mission_type == "generic_mission" and params_mission_type:
                mission_type = self._infer_mission_type(params_mission_type, None)
            proposal_bundle = await self.generate_mission_proposal(
                {
                    "title": command.get("title") or self._command_proposal_title(goal, mission_type),
                    "goal": goal,
                    "summary": f"LLM interpreted operator command as {command_action}.",
                    "reason_summary": llm_result.get("reasoning") if llm_result else "Operator command interpreted by system agent.",
                    "source": "user_command",
                    "location": (command.get("params") or {}).get("location") or {},
                    "insight_summary": f"Command-driven response for {command_action}",
                    "severity": "INFORMATION",
                },
                allow_suppression=False,
            )
            self.state.remember(
                {
                    "kind": "command_mission_proposal_created",
                    "at": utc_now(),
                    "command": command,
                    "resolved": resolved,
                    "proposal": proposal_bundle,
                }
            )
            proposal = proposal_bundle.get("proposal") if isinstance(proposal_bundle, dict) else {}
            approval = proposal_bundle.get("approval") if isinstance(proposal_bundle, dict) else {}
            self.state.remember(
                {
                    "kind": "command_mission_bundle_created",
                    "at": utc_now(),
                    "command": command,
                    "resolved": resolved,
                    "bundle": {
                        "proposal_id": str((proposal or {}).get("proposal_id") or ""),
                        "approval_id": str((approval or {}).get("approval_id") or ""),
                        "mission_type": str((proposal or {}).get("mission_type") or ""),
                        "goal": str((proposal or {}).get("goal") or goal),
                    },
                }
            )

        return {
            **command_result,
            "resolved_command": resolved,
            "llm_analysis": llm_result,
            "mission_bundle": proposal_bundle,
        }

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
            return self._canonical_action(action.strip())
        if severity == "CRITICAL":
            return "escalate_alert"
        return None

    async def handle_event_report(self, event: dict[str, Any]) -> dict[str, Any]:
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
        alert_id = stored_alert.get("alert_id")
        try:
            self.registry_client.acknowledge_alert(str(alert_id), approved=True, notes="System Agent processing")
        except Exception:
            pass
        proposal_bundle = await self.generate_mission_proposal(
            {
                "title": f"{event_type.replace('_', ' ').title()} Mission Proposal",
                "goal": message,
                "alert_id": stored_alert.get("alert_id"),
                "event_id": stored_event.get("event_id"),
                "severity": severity,
                "source": "event_report",
                "summary": f"Proposal generated from alert {stored_alert.get('alert_id')}.",
            }
        )
        self.state.remember(
            {
                "kind": "event_report_processed",
                "at": utc_now(),
                "event_id": event_id,
                "alert_id": stored_alert.get("alert_id"),
                "proposal_id": (proposal_bundle.get("proposal") or {}).get("proposal_id"),
                "event_type": event_type,
                "severity": severity,
            }
        )
        return {
            "received": True,
            "message_type": "event.report",
            "event_id": stored_event.get("event_id"),
            "alert_id": stored_alert.get("alert_id"),
            "proposal_id": (proposal_bundle.get("proposal") or {}).get("proposal_id"),
            "approval_id": (proposal_bundle.get("approval") or {}).get("approval_id"),
            "severity": severity,
        }

    async def handle_task_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Device가 Task 실패/거절을 보고할 때 mission 상태에 반영한다."""
        task_id = str(payload.get("task_id") or "")
        mission_id = str(payload.get("mission_id") or payload.get("response_id") or "")
        device_id = str(payload.get("device_id") or "")
        agent_id = str(payload.get("agent_id") or "")
        status = self._task_status(payload.get("status"), "FAILED")
        error = str(payload.get("error") or "Unknown error")
        command = payload.get("command") or {}
        execution_result = payload.get("execution_result") or {}
        
        logger.info(f"Task failure reported: task_id={task_id}, device={device_id}, error={error}")
        
        # Record task failure
        self.state.remember({
            "kind": "task_failed",
            "at": utc_now(),
            "task_id": task_id,
            "device_id": device_id,
            "agent_id": agent_id,
            "error": error,
            "command": command,
        })
        
        current_mission = None
        if mission_id:
            try:
                current_mission = self.registry_client.get_mission(mission_id)
            except Exception:
                current_mission = None
        if current_mission is None:
            for mission in self.registry_client.list_missions():
                dispatch_state = ((mission.get("metadata") or {}).get("dispatch_state") or {})
                for step_state in dispatch_state.get("steps") or []:
                    for task_state in step_state.get("tasks") or []:
                        if str(task_state.get("task_id") or "") == task_id:
                            current_mission = mission
                            mission_id = str(mission.get("mission_id") or "")
                            break
                    if current_mission is not None:
                        break
                if current_mission is not None:
                    break

        if not current_mission:
            return {
                "received": True,
                "message_type": "task.result",
                "task_id": task_id,
                "status": "acknowledged",
                "note": "No related mission found - failure logged"
            }

        if status == "COMPLETED":
            mission_result_payload = {
                "mission_id": mission_id,
                "response_id": mission_id,
                "alert_id": current_mission.get("alert_id"),
                "step_id": str(payload.get("step_id") or "default"),
                "task_id": task_id,
                "source_agent_id": agent_id or device_id or "unknown",
                "execution_status": "COMPLETED",
                "execution_log": {
                    "source_agent_id": agent_id or device_id or "unknown",
                    "source_device_id": device_id,
                    "step_id": str(payload.get("step_id") or "default"),
                    "task_id": task_id,
                    "action": command.get("action"),
                    "command": command,
                    "result": execution_result,
                    "reported_at": utc_now(),
                    "result_summary": execution_result.get("summary") or execution_result.get("output_summary") or execution_result.get("message") or "task completed",
                    "output_refs": execution_result.get("output_refs") or execution_result.get("raw_data_ref") or execution_result.get("artifacts") or [],
                    "failure_category": None,
                    "failure_message": None,
                    "location": execution_result.get("location") or execution_result.get("position") or {},
                    "device_state_changes": execution_result.get("device_state_changes") or {},
                    "agent_judgement": execution_result.get("agent_judgement") or command.get("action"),
                    "payload": {
                        "response_id": mission_id,
                        "mission_id": mission_id,
                        "alert_id": current_mission.get("alert_id"),
                        "step_id": str(payload.get("step_id") or "default"),
                        "task_id": task_id,
                        "source_agent_id": agent_id or device_id or "unknown",
                        "source_device_id": device_id,
                        "location": execution_result.get("location") or execution_result.get("position") or {},
                    },
                },
            }
            return await self.handle_mission_result(mission_result_payload)

        dispatch_state = dict((current_mission.get("metadata") or {}).get("dispatch_state") or {})
        execution_results = list(dispatch_state.get("execution_results") or [])
        failure_entry = {
            "mission_id": mission_id,
            "reporter": agent_id or device_id or "unknown",
            "step_id": str(payload.get("step_id") or "default"),
            "task_id": task_id,
            "status": "ABORTED" if status == "ABORTED" else "FAILED",
            "payload": execution_result,
            "received_at": utc_now(),
            "error": error,
        }
        execution_results.append(failure_entry)
        retry_count = len([e for e in execution_results if str(e.get("task_id") or "") in {task_id} and str(e.get("status") or "") in {"FAILED", "ABORTED"}])
        decision = "abort_mission" if retry_count >= 2 or status == "ABORTED" else "retry_step"
        dispatch_state["execution_results"] = execution_results
        dispatch_state["last_failure"] = {
            "task_id": task_id,
            "error": error,
            "at": utc_now(),
            "decision": decision
        }
        for step_state in dispatch_state.get("steps") or []:
            if not isinstance(step_state, dict):
                continue
            for task_state in step_state.get("tasks") or []:
                if not isinstance(task_state, dict):
                    continue
                if str(task_state.get("task_id") or "") == task_id:
                    task_state["execution_status"] = "ABORTED" if status == "ABORTED" else "FAILED"
                    task_state["failure_message"] = error
                    task_state["completed_at"] = utc_now()
                    step_state["status"] = "FAILED"
        current_mission["metadata"] = {**dict(current_mission.get("metadata") or {}), "dispatch_state": dispatch_state}
        current_mission.setdefault("timeline", []).append(
            {
                "timestamp": utc_now(),
                "type": "WARNING",
                "message": f"Warning raised for task {task_id}.",
                "data": {"task_id": task_id, "error": error, "decision": decision},
            }
        )
        current_mission.setdefault("timeline", []).append(
            {
                "timestamp": utc_now(),
                "type": "TASK_FAILURE",
                "message": f"Task {task_id} reported {status}.",
                "data": {"task_id": task_id, "error": error, "decision": decision},
            }
        )
        try:
            self.registry_client.ingest_event(
                {
                    "source_system": "system_agent",
                    "source_agent_id": str(self.state.agent_id),
                    "source_role": str(self.state.role or "mission_planner"),
                    "event_type": "SYS_TASK_FAILED",
                    "severity": "WARNING",
                    "title": f"Task {task_id} failed",
                    "description": f"Task {task_id} reported {status}.",
                    "target_type": "TASK",
                    "target_id": task_id,
                    "data": {
                        "mission_id": mission_id,
                        "step_id": str(payload.get("step_id") or "default"),
                        "task_id": task_id,
                        "status": status,
                        "error": error,
                        "decision": decision,
                    },
                    "target_agents": ["MissionPlanner", "SystemSentinel", "InsightReporter"],
                }
            )
        except Exception as exc:
            logger.debug(f"Failed to record task failed event: {exc}")
        current_mission["status"] = "FAILED" if decision == "abort_mission" else "IN_PROGRESS"
        if decision == "abort_mission":
            current_mission["completed_at"] = utc_now()
            current_mission["final_result"] = {"status": "FAILED", "reason": error}
        current_mission = self._sync_mission_from_dispatch_state(current_mission, dispatch_state)
        self.registry_client.replace_mission(mission_id, current_mission)
        
        self.state.remember({
            "kind": "task_failure_handled",
            "at": utc_now(),
            "mission_id": mission_id,
            "task_id": task_id,
            "decision": decision,
            "retry_count": retry_count,
        })
        
        return {
            "received": True,
            "message_type": "task.result",
            "task_id": task_id,
            "status": "processed",
            "decision": decision,
            "retry_count": retry_count
        }

    async def handle_mission_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        """중간/하위 에이전트의 임무 수행 결과를 수신해 mission 원장에 최종 반영한다."""
        mission_id = str(payload.get("mission_id") or payload.get("response_id") or "")
        reporter = str(payload.get("source_agent_id") or payload.get("reporter") or "unknown")
        step_id = str(payload.get("step_id") or "")
        execution_status = self._task_status(payload.get("execution_status"), "COMPLETED")
        execution_log = payload.get("execution_log") or {}

        if not mission_id:
            return {"received": False, "message_type": "mission.result", "error": "mission_id required"}

        normalized_status = "COMPLETED" if execution_status == "COMPLETED" else "FAILED"
        async with self._mission_lock:
            devices = self.registry_client.list_devices()
            try:
                mission = self.registry_client.get_mission(mission_id)
                dispatch_state = dict((mission.get("metadata") or {}).get("dispatch_state") or self._build_dispatch_result_from_steps(mission.get("steps") or []))
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
                existing_results = dispatch_state.get("execution_results") or []
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
                            "mission_id": mission_id,
                            "alert_id": mission.get("alert_id"),
                            "reporter": reporter,
                            "step_id": step_id,
                            "task_id": task_id,
                        }
                    )
                    return {
                        "received": True,
                        "message_type": "mission.result",
                        "mission_id": mission_id,
                        "status": mission.get("status") or normalized_status,
                        "duplicate": True,
                        "dedup_key": {
                            "mission_id": mission_id,
                            "step_id": step_id,
                            "task_id": task_id,
                            "reporter": reporter,
                        },
                    }

                execution_entry = self._normalize_device_execution_entry(
                    mission_id=mission_id,
                    reporter=reporter,
                    step_id=step_id,
                    task_id=task_id,
                    normalized_status=normalized_status,
                    execution_log=execution_log if isinstance(execution_log, dict) else {},
                    payload=payload,
                )
                execution_results = [*existing_results, execution_entry]
                dispatch_state["execution_results"] = execution_results
                dispatch_state["execution_result"] = execution_entry

                mission_steps = mission.get("steps") or []
                step_states = dispatch_state.get("steps") or []
                if not isinstance(step_states, list):
                    step_states = []
                step_evaluations = dispatch_state.get("step_evaluations") or {}
                if not isinstance(step_evaluations, dict):
                    step_evaluations = {}
                replan_history = dispatch_state.get("replan_history") or []
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
                                # ✅ Record task completion/failure timeline event (Ch.18-20)
                                try:
                                    event_type = "TASK_COMPLETED" if normalized_status == "COMPLETED" else "TASK_FAILED"
                                    self.registry_client.append_mission_timeline_event(
                                        mission_id=mission_id,
                                        event_type=event_type,
                                        actor=f"device_{reporter}",
                                        details={
                                            "execution_status": normalized_status,
                                            "result_summary": execution_entry.get("result_summary", ""),
                                            "failure_category": execution_entry.get("failure_category"),
                                            "failure_message": execution_entry.get("failure_message"),
                                        },
                                        task_id=task_id if task_id else None,
                                        step_index=step_id if step_id else None,
                                    )
                                except Exception as e:
                                    logging.getLogger(__name__).debug(f"Failed to record task completion timeline: {e}")
                        task_statuses = [
                            self._task_status(task_state.get("execution_status"))
                            for task_state in item.get("tasks") or []
                            if isinstance(task_state, dict)
                        ]
                        if any(status in {"FAILED", "ABORTED", "CANCELLED"} for status in task_statuses):
                            item["status"] = "FAILED"
                        elif task_statuses and all(status == "COMPLETED" for status in task_statuses):
                            item["status"] = "COMPLETED"
                            item["completed_at"] = utc_now()
                        else:
                            item["status"] = "IN_PROGRESS"
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
                        {"response_id": mission_id, "alert_id": mission.get("alert_id")},
                        current_step_def,
                        current_step_state,
                        current_step_results,
                        devices,
                    )
                    step_evaluations[step_id] = step_evaluation
                    dispatch_state["step_evaluations"] = step_evaluations
                    self.state.remember({"kind": "step_evaluation", "at": utc_now(), "evaluation": step_evaluation})
                    if step_evaluation.get("decision") != "proceed_next_step":
                        replan_history.append(
                            {
                                "at": utc_now(),
                                "mission_id": mission_id,
                                "step_id": step_id,
                                "decision": step_evaluation.get("decision"),
                                "reason": step_evaluation.get("reason"),
                            }
                        )
                        dispatch_state["replan_history"] = replan_history
                        mission.setdefault("timeline", []).append(
                            {
                                "timestamp": utc_now(),
                                "type": "PLAN_CHANGED",
                                "message": f"Mission plan changed after step {step_id}.",
                                "data": {
                                    "step_id": step_id,
                                    "decision": step_evaluation.get("decision"),
                                    "reason": step_evaluation.get("reason"),
                                },
                            }
                        )
                    if step_evaluation.get("decision") == "manual_intervention_required":
                        dispatch_state["manual_intervention"] = self._build_manual_intervention_record(
                            response_id=mission_id,
                            alert_id=str(mission.get("alert_id") or ""),
                            step_evaluation=step_evaluation,
                            step_execution_results=current_step_results,
                        )
                        reapproval = self.registry_client.create_approval(
                            {
                                "target_type": "mission_reapproval",
                                "target_id": mission_id,
                                "summary": f"Mission {mission_id} requires user reapproval",
                                "requested_action": "review_and_resume_mission",
                                "related_insight_id": mission.get("insight_id"),
                                "metadata": {
                                    "mission_id": mission_id,
                                    "step_id": step_id,
                                    "recovery_mode": "retry_same_step",
                                    "reason": step_evaluation.get("reason"),
                                },
                            }
                        )
                        try:
                            self.registry_client.ingest_event(
                                {
                                    "source_system": "system_agent",
                                    "source_agent_id": str(self.state.agent_id),
                                    "source_role": str(self.state.role or "mission_planner"),
                                    "event_type": "SYS_MISSION_REPLAN_REQUESTED",
                                    "severity": "INFO",
                                    "title": "Mission replan requested",
                                    "description": f"Mission {mission_id} requires replan or reapproval.",
                                    "target_type": "MISSION",
                                    "target_id": mission_id,
                                    "data": {
                                        "approval_id": reapproval.get("approval_id"),
                                        "step_id": step_id,
                                        "reason": step_evaluation.get("reason"),
                                    },
                                    "target_agents": ["MissionPlanner", "InsightReporter"],
                                }
                            )
                        except Exception as exc:
                            logger.debug(f"Failed to record SYS_MISSION_REPLAN_REQUESTED event: {exc}")
                        mission.setdefault("timeline", []).append(
                            {
                                "timestamp": utc_now(),
                                "type": "USER_REAPPROVAL_REQUESTED",
                                "message": "Mission reapproval requested.",
                                "data": {
                                    "approval_id": reapproval.get("approval_id"),
                                    "step_id": step_id,
                                    "reason": step_evaluation.get("reason"),
                                },
                            }
                        )
                        self.state.remember(
                            {
                                "kind": "manual_intervention_required",
                                "at": utc_now(),
                                "mission_id": mission_id,
                                "alert_id": mission.get("alert_id"),
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
                        if step_state and self._task_status(step_state.get("status")) in {"ASSIGNED", "IN_PROGRESS", "COMPLETED"}:
                            continue
                        next_step = candidate
                        break

                if next_step is not None:
                    mission.setdefault("metadata", {})["dispatch_state"] = dispatch_state
                    next_dispatch = await self._dispatch_next_step(
                        {"response_id": mission_id, "alert_id": mission.get("alert_id"), "reason": mission.get("title"), "dispatch_result": dispatch_state, "params": {"steps": mission_steps}},
                        mission_steps,
                        devices,
                        logging.getLogger(__name__),
                        previous_step_results=[
                            {
                                "response_id": mission_id,
                                "alert_id": mission.get("alert_id"),
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
                    dispatch_state = next_dispatch
                    self._append_dispatch_timeline_entries(mission, next_dispatch, mission_steps)
                elif should_retry_same_step or should_reassign_failed_tasks:
                    recovery_mode = "reassign_failed_tasks" if should_reassign_failed_tasks else "retry_same_step"
                    prepared = self._prepare_step_recovery(
                        current_step_def,
                        current_step_state,
                        devices,
                        mode=recovery_mode,
                    ) if isinstance(current_step_def, dict) and isinstance(current_step_state, dict) else False
                    if prepared and isinstance(current_step_def, dict):
                        mission.setdefault("metadata", {})["dispatch_state"] = dispatch_state
                        retry_dispatch = await self._dispatch_next_step(
                            {"response_id": mission_id, "alert_id": mission.get("alert_id"), "reason": mission.get("title"), "dispatch_result": dispatch_state, "params": {"steps": mission_steps}},
                            mission_steps,
                            devices,
                            logging.getLogger(__name__),
                            previous_step_results=self._collect_previous_step_results(current_step_def, execution_results),
                        )
                        dispatch_state = retry_dispatch
                        self._append_dispatch_timeline_entries(mission, retry_dispatch, mission_steps)

                all_step_states_completed = bool(step_states) and all(
                    isinstance(item, dict) and self._task_status(item.get("status")) == "COMPLETED"
                    for item in step_states
                )
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
                aggregate_status = "IN_PROGRESS"
                manual_intervention_required = bool(
                    step_evaluation and step_evaluation.get("decision") == "manual_intervention_required"
                )
                if manual_intervention_required:
                    aggregate_status = "FAILED"
                elif step_evaluation and step_evaluation.get("decision") == "abort_mission":
                    aggregate_status = "FAILED"
                elif all_step_states_completed:
                    aggregate_status = "COMPLETED"
                elif planned_step_ids and all(step in proceed_step_ids for step in planned_step_ids):
                    aggregate_status = "COMPLETED"

                if aggregate_status == "FAILED":
                    self._release_response_devices(dispatch_state, reason=aggregate_status)
                elif aggregate_status == "COMPLETED":
                    self._release_response_devices(dispatch_state, reason="mission_completed")

                mission.setdefault("timeline", []).append(
                    {
                        "timestamp": utc_now(),
                        "type": "DEVICE_RESULT_REPORTED",
                        "message": f"Task result reported by {reporter}.",
                        "data": {
                            "step_id": step_id,
                            "task_id": task_id,
                            "status": normalized_status,
                            "device_id": execution_entry.get("device_id"),
                            "failure_reason": execution_entry.get("failure_reason"),
                        },
                    }
                )
                mission.setdefault("timeline", []).append(
                    {
                        "timestamp": utc_now(),
                        "type": "TASK_COMPLETED" if normalized_status == "COMPLETED" else "WARNING",
                        "message": (
                            f"Task {task_id} completed."
                            if normalized_status == "COMPLETED"
                            else f"Task {task_id} reported non-success status."
                        ),
                        "data": {
                            "step_id": step_id,
                            "task_id": task_id,
                            "status": normalized_status,
                            "device_id": execution_entry.get("device_id"),
                            "failure_reason": execution_entry.get("failure_reason"),
                        },
                    }
                )
                try:
                    self.registry_client.ingest_event(
                        {
                            "source_system": "system_agent",
                            "source_agent_id": str(self.state.agent_id),
                            "source_role": str(self.state.role or "mission_planner"),
                            "event_type": "SYS_TASK_COMPLETED" if normalized_status == "COMPLETED" else "SYS_TASK_FAILED",
                            "severity": "INFO" if normalized_status == "COMPLETED" else "WARNING",
                            "title": f"Task {task_id} {normalized_status.lower()}",
                            "description": f"Task {task_id} reported {normalized_status}.",
                            "target_type": "TASK",
                            "target_id": task_id,
                            "data": {
                                "mission_id": mission_id,
                                "step_id": step_id,
                                "task_id": task_id,
                                "status": normalized_status,
                                "device_id": execution_entry.get("device_id"),
                                "failure_reason": execution_entry.get("failure_reason"),
                            },
                            "target_agents": ["MissionPlanner", "SystemSentinel", "InsightReporter"],
                        }
                    )
                except Exception as exc:
                    logger.debug(f"Failed to record task event: {exc}")
                mission.setdefault("timeline", []).append(
                    {
                        "timestamp": utc_now(),
                        "type": "AGENT_JUDGEMENT",
                        "message": "System Agent updated mission evaluation.",
                        "data": step_evaluation or {"status": aggregate_status},
                    }
                )
                mission["status"] = aggregate_status
                if aggregate_status == "COMPLETED":
                    mission["completed_at"] = utc_now()
                    mission["final_result"] = {
                        "status": "COMPLETED",
                        "summary": f"Mission completed after step {step_id}.",
                    }
                    mission.setdefault("timeline", []).append(
                        {
                            "timestamp": utc_now(),
                            "type": "MISSION_COMPLETED",
                            "message": "Mission completed.",
                            "data": {"mission_id": mission_id},
                        }
                    )
                    alert_id = str(mission.get("alert_id") or "")
                    if alert_id:
                        try:
                            self.registry_client.complete_alert(alert_id, notes="Mission completed")
                        except Exception as exc:
                            logger.debug(f"Failed to complete alert {alert_id}: {exc}")
                    try:
                        self.registry_client.ingest_event(
                            {
                                "source_system": "system_agent",
                                "source_agent_id": str(self.state.agent_id),
                                "source_role": str(self.state.role or "mission_planner"),
                                "event_type": "SYS_MISSION_COMPLETED",
                                "severity": "INFO",
                                "title": "Mission completed",
                                "description": f"Mission {mission_id} completed.",
                                "target_type": "MISSION",
                                "target_id": mission_id,
                                "data": {
                                    "mission_id": mission_id,
                                    "step_id": step_id,
                                    "status": "COMPLETED",
                                },
                                "target_agents": ["InsightReporter", "SystemSentinel"],
                            }
                        )
                    except Exception as exc:
                        logger.debug(f"Failed to record mission completed event: {exc}")
                elif aggregate_status == "FAILED":
                    mission["completed_at"] = utc_now()
                    mission["final_result"] = {
                        "status": "FAILED",
                        "reason": (step_evaluation or {}).get("reason") or "task execution failure",
                    }
                    mission.setdefault("timeline", []).append(
                        {
                            "timestamp": utc_now(),
                            "type": "MISSION_FAILED",
                            "message": "Mission failed.",
                            "data": {
                                "mission_id": mission_id,
                                "reason": mission["final_result"].get("reason"),
                            },
                        }
                    )
                    alert_id = str(mission.get("alert_id") or "")
                    if alert_id:
                        try:
                            self.registry_client.acknowledge_alert(alert_id, approved=False, notes="Mission failed")
                        except Exception as exc:
                            logger.debug(f"Failed to mark alert {alert_id} as failed: {exc}")
                    try:
                        self.registry_client.ingest_event(
                            {
                                "source_system": "system_agent",
                                "source_agent_id": str(self.state.agent_id),
                                "source_role": str(self.state.role or "mission_planner"),
                                "event_type": "SYS_MISSION_UPDATED",
                                "severity": "WARNING",
                                "title": "Mission failed",
                                "description": f"Mission {mission_id} failed.",
                                "target_type": "MISSION",
                                "target_id": mission_id,
                                "data": {
                                    "mission_id": mission_id,
                                    "step_id": step_id,
                                    "status": "FAILED",
                                    "reason": mission["final_result"].get("reason"),
                                },
                                "target_agents": ["InsightReporter", "SystemSentinel"],
                            }
                        )
                    except Exception as exc:
                        logger.debug(f"Failed to record mission failed event: {exc}")
                if manual_intervention_required:
                    mission.setdefault("timeline", []).append(
                        {
                            "timestamp": utc_now(),
                            "type": "WARNING",
                            "message": "Mission requires manual review.",
                            "data": {
                                "mission_id": mission_id,
                                "step_id": step_id,
                                "reason": (step_evaluation or {}).get("reason"),
                            },
                        }
                    )
                mission = self._sync_mission_from_dispatch_state(mission, dispatch_state)
                self.registry_client.replace_mission(mission_id, mission)
            except Exception as exc:
                self.state.remember(
                    {
                        "kind": "mission_result_update_failed",
                        "at": utc_now(),
                        "mission_id": mission_id,
                        "error": str(exc),
                    }
                )
                return {"received": False, "message_type": "mission.result", "error": str(exc)}

        self.state.remember(
            {
                "kind": "mission_result_received",
                "at": utc_now(),
                "mission_id": mission_id,
                "alert_id": mission.get("alert_id"),
                "reporter": reporter,
                "step_id": step_id,
                "task_id": task_id,
                "status": mission.get("status"),
            }
        )
        return {
            "received": True,
            "message_type": "mission.result",
            "mission_id": mission_id,
            "status": mission.get("status"),
            "duplicate": False,
            "dedup_key": {
                "mission_id": mission_id,
                "step_id": step_id,
                "task_id": task_id,
                "reporter": reporter,
            },
        }

    # ──────────────────────────────────────────────
    # Phase 4: InsightReporter
    # ──────────────────────────────────────────────

    async def _execute_insight_reporter(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """Fleet 전체 현황 한국어 리포트 생성"""
        devices = self.registry_client.list_devices()
        missions = self.registry_client.list_missions()
        insights = self.registry_client.list_insights()

        report, error = await self.decision_engine.generate_fleet_report(
            devices, missions, insights, self.state
        )

        return {
            "type": "RESPONSE",
            "status": "SUCCESS",
            "data": {"devices": devices, "missions": missions, "insights": insights},
            "report": report,
            "report_source": "llm" if not error else "rule_based",
        }
