"""
Agent Runtime: Agent 실행 엔진

Device Agent의 생명주기를 관리합니다:
1. 초기화: Config 읽기, ID 생성, Skills 등록
2. 등록: Device Registration Server에 자신을 등록
3. Simulation Loop: 센서 읽기 → Decision → Moth 발행의 반복
4. 동적 Tool 관리: importlib로 tools/ 디렉토리의 센서/제어 클래스 자동 로드
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict
import json
import logging
import os
import random
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from agent.decision import DecisionEngine
from agent.manifest import ManifestBuilder
from agent.state import AgentState, utc_now
from controller.commands import CommandController
from infrastructure.platforms import DevicePlatform, resolve_device_platform
from skills.catalog import SkillCatalog
from storage.identity_store import IdentityStore
from transport.registry_client import RegistryClient
from transport.moth_publisher import MothPublisher
from storage.runtime_store import RuntimeStore

logger = logging.getLogger(__name__)


class AgentRuntime:
    """
    Agent 실행 엔진: Device Agent의 생명주기 관리
    """

    def __init__(self, config_path: Path, platform: DevicePlatform | None = None) -> None:
        """
        Agent 초기화: Config, Identity, Skills, Simulator, Tools 설정

        Args:
            config_path: config.json 파일 경로
        """
        # Config 로드
        self.config_path = config_path
        self.config = json.loads(config_path.read_text(encoding="utf-8"))
        self.server = self.config.get("server", {})  # 서버 설정 (host, port)
        self.agent_config = self.config.get("agent", {})  # Agent 설정
        self.capabilities = self.agent_config.get("capabilities", {})  # Skills/Actions

        # Instance ID 생성 또는 로드 (환경변수 or 파일 or auto-generate)
        self.instance_id = self._resolve_instance_id()

        # device_type → platform adapter 결정
        self.platform = platform or resolve_device_platform(self.agent_config.get("device_type"))

        # Identity 저장소: agent_id, token 등을 .runtime/{instance_id}.json에 저장
        # .runtime은 device/ 루트에 저장 (configs/ 하위에 생기지 않도록)
        device_root = Path(__file__).resolve().parent.parent
        self.identity_store = IdentityStore(device_root / ".runtime", self.instance_id)
        self.identity = self.identity_store.read()

        # Skills Catalog: 이 Agent가 수행 가능한 모든 skills/actions 등록
        self.skills = SkillCatalog(self.capabilities)
        self.manifest_builder = ManifestBuilder(self.config, self.skills)

        # Agent 상태: agent_id, name, layer, device_type, 마지막 텔레메트리 등
        configured_name = str(self.agent_config.get("name") or "CoWater Agent").strip()

        self.state = AgentState(
            agent_id=self.identity.get("agent_id") or f"{self.agent_config.get('id', 'agent')}-{self.instance_id}",
            role=str(self.agent_config.get("role") or "device_agent"),
            layer=str(self.agent_config.get("layer") or "lower"),  # "lower", "middle", "system"
            device_type=self.agent_config.get("device_type"),  # "usv", "auv", "rov", etc.
            instance_id=self.instance_id,
            name=configured_name,
        )

        # Device Registration Server와의 통신
        self.registry_client = RegistryClient(self.config.get("registry", {}))

        # Task ID 처리 이력 저장소: 중복 실행 방지 (파일 스냅샷)
        from agent.task_id_store import TaskIdStore
        task_path = str(Path(__file__).resolve().parent.parent / ".runtime" / f"{self.instance_id}_tasks.json")
        self.task_id_store = TaskIdStore(path=task_path)
        self.runtime_store = RuntimeStore(device_root / ".runtime" / f"{self.instance_id}_state.json")

        # 의사결정 엔진: Rule 기반 + LLM 분석
        self.decision_engine = DecisionEngine(self.agent_config, self.skills)

        # 텔레메트리 리더 / 시뮬레이터 / 명령 제어기: 플랫폼 어댑터로 분리
        self.telemetry_reader = self.platform.build_telemetry_reader()
        self.simulator = self.platform.build_simulator(self.config.get("simulation", {}), self.skills.list_tracks())
        self.command_controller = CommandController(self.platform.build_command_executor())

        # Moth WebSocket 발행자: Healthcheck 및 Telemetry 발행
        self.moth_publisher = MothPublisher(self.config, self.state)

        # 동적 Tool 로드: tools/ 디렉토리에서 센서/제어 클래스 자동 로드
        self.tools: dict[str, Any] = {}
        self.tools = self.platform.load_tools(device_root)
        self._restore_runtime_snapshot(self.runtime_store.load_snapshot(self.instance_id))
        self._last_assignment_signature: dict[str, Any] | None = None
        self._last_parent_registration_signature: dict[str, Any] | None = None
        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._stopping = False

    def _create_background_task(self, coro: Any) -> asyncio.Task[Any]:
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    def _runtime_snapshot(self) -> dict[str, Any]:
        snapshot = asdict(self.state)
        snapshot["simulator_mission_state"] = dict(getattr(self.simulator, "mission_state", {}) or {})
        snapshot["simulator_position"] = dict(getattr(self.simulator, "position", {}) or {})
        snapshot["simulator_motion"] = dict(getattr(self.simulator, "motion", {}) or {})
        return snapshot

    def _persist_runtime_state(self) -> None:
        try:
            self.runtime_store.save_snapshot(self.instance_id, self._runtime_snapshot(), utc_now())
        except Exception as exc:
            logger.debug("Runtime snapshot persist skipped: %s", exc)

    def _restore_runtime_snapshot(self, snapshot: dict[str, Any]) -> None:
        if not snapshot:
            return
        state_fields = {
            "parent_id",
            "parent_endpoint",
            "parent_command_endpoint",
            "route_mode",
            "force_parent_routing",
            "token",
            "registry_id",
            "latitude",
            "longitude",
            "connected",
            "registered_at",
            "last_seen_at",
            "last_telemetry",
            "last_decision",
            "last_command",
            "mission_state",
            "children",
            "tasks",
            "inbox",
            "outbox",
            "memory",
        }
        for field in state_fields:
            if field in snapshot:
                setattr(self.state, field, snapshot[field])
        simulator_mission = snapshot.get("simulator_mission_state")
        if isinstance(simulator_mission, dict):
            self.simulator.mission_state = dict(simulator_mission)
            self.state.mission_state = dict(simulator_mission)
        if isinstance(snapshot.get("simulator_position"), dict):
            self.simulator.position = dict(snapshot["simulator_position"])
        elif isinstance(self.state.last_telemetry, dict):
            position = self.state.last_telemetry.get("position")
            if isinstance(position, dict):
                self.simulator.position = dict(position)
        if isinstance(snapshot.get("simulator_motion"), dict):
            self.simulator.motion = dict(snapshot["simulator_motion"])
        if self.state.mission_state and not simulator_mission:
            self.simulator.mission_state = dict(self.state.mission_state)

    async def stop(self) -> None:
        self._stopping = True
        for task in list(self._background_tasks):
            task.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        await self.moth_publisher.close()

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
            self._persist_runtime_state()
            return

        if self.identity.get("registry_id") and self.identity.get("token"):
            self.state.registry_id = str(self.identity["registry_id"])
            self.state.token = str(self.identity["token"])
            self.state.registered_at = self.identity.get("registered_at")
            try:
                self._upsert_agent()
                self._registration_response = self.registry_client.get_device(self.state.registry_id)
                self._sync_registry_name()
                self._refresh_assignment()
                self.state.connected = True
                self.state.last_seen_at = utc_now()
                logger.info(f"기존 등록 재사용: registry_id={self.state.registry_id}")
                self._persist_runtime_state()
                return
            except Exception as exc:
                # 서버가 일시적으로 내려가 있어도 로컬 캐시로 Moth 초기화 가능
                if self.identity.get("tracks") or self.identity.get("healthcheck_topic"):
                    self._registration_response = {
                        "id": self.state.registry_id,
                        "token": self.state.token,
                        "tracks": self.identity.get("tracks", []),
                        "healthcheck_topic": self.identity.get("healthcheck_topic"),
                        "telemetry_topics": self.identity.get("telemetry_topics", []),
                    }
                    self.state.connected = False
                    logger.warning(f"서버 연결 실패, 로컬 캐시로 Moth 초기화: {exc}")
                    self._persist_runtime_state()
                    return
                self.state.remember({"kind": "identity_reconnect_failed", "at": utc_now()})
                self._persist_runtime_state()

        created = self.registry_client.register_device(
            self.state.name,
            self.skills.list_tracks(),
            self.skills.list_actions(),
            device_type=self.agent_config.get("device_type"),
            layer=self.agent_config.get("layer"),
            connectivity=self.agent_config.get("connectivity"),
            location=self.config.get("simulation", {}).get("start_position"),
        )
        self.state.registry_id = str(created["id"])
        self.state.token = str(created["token"])
        self.state.registered_at = utc_now()
        self.state.connected = True
        self.state.last_seen_at = utc_now()
        # Store registration response for Moth initialization in simulation_loop
        self._registration_response = created
        self._upsert_agent()
        self._refresh_assignment()
        self.identity_store.write(
            {
                "agent_id": self.state.agent_id,
                "name": self.state.name,
                "registry_id": self.state.registry_id,
                "token": self.state.token,
                "registered_at": self.state.registered_at,
                "tracks": created.get("tracks", []),
                "healthcheck_topic": created.get("healthcheck_topic"),
                "telemetry_topics": created.get("telemetry_topics", []),
            }
        )
        self.state.connected = True
        self.state.last_seen_at = utc_now()
        self._persist_runtime_state()
        logger.info(f"등록 완료: registry_id={self.state.registry_id}")

    def _sync_registry_name(self) -> None:
        if not self.state.registry_id or not self._registration_response:
            return

        registered_name = str(self._registration_response.get("name") or "").strip()
        desired_name = str(self.state.name or "").strip()
        if not desired_name or registered_name == desired_name:
            return

        self.registry_client.rename_device(self.state.registry_id, desired_name)
        self._registration_response = self.registry_client.get_device(self.state.registry_id)
        self.identity_store.write(
            {
                **self.identity,
                "agent_id": self.state.agent_id,
                "name": desired_name,
                "registry_id": self.state.registry_id,
                "token": self.state.token,
                "registered_at": self.state.registered_at,
                "tracks": self._registration_response.get("tracks", self.identity.get("tracks", [])),
                "healthcheck_topic": self._registration_response.get("healthcheck_topic", self.identity.get("healthcheck_topic")),
                "telemetry_topics": self._registration_response.get("telemetry_topics", self.identity.get("telemetry_topics", [])),
            }
        )
        self._persist_runtime_state()

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
            self._last_parent_registration_signature = None
        self._persist_runtime_state()

    def _refresh_assignment(self) -> None:
        if self.state.registry_id is None:
            return
        try:
            self.apply_assignment(self.registry_client.get_assignment(self.state.registry_id))
        except Exception as exc:
            self.state.remember({"kind": "assignment_refresh_failed", "at": utc_now(), "error": str(exc)})
            self._persist_runtime_state()

    def _upsert_agent(self) -> None:
        if self.state.registry_id is None or not self.state.token:
            raise RuntimeError("agent identity is not registered")
        # P3 (보고 기반): 주기적으로 위치, 배터리, 상태를 Registry에 보고
        battery_percent = None
        if self.state.last_telemetry:
            battery_info = self.state.last_telemetry.get("battery", {})
            if isinstance(battery_info, dict):
                battery_percent = battery_info.get("percent")
        
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
            latitude=self.state.latitude,
            longitude=self.state.longitude,
            battery_percent=battery_percent,
            gateway_agent_id=self.state.gateway_agent_id,
            environment_state=self.state.environment_state,
            active_mediums=list(self.state.active_mediums or []),
        )

    def register_child(self, child: dict[str, Any]) -> dict[str, Any]:
        child_id = str(child.get("agent_id") or child.get("id") or "")
        if not child_id:
            raise ValueError("child agent_id required")
        record = dict(child, agent_id=child_id, registered_at=utc_now())
        self.state.children[child_id] = record
        self.state.remember({"kind": "child_registered", "at": utc_now(), "child": child_id})
        self._persist_runtime_state()
        return record

    def relay_child_healthcheck(self, payload: dict[str, Any]) -> dict[str, Any]:
        child_id = str(payload.get("agent_id") or payload.get("device_id") or "")
        if not child_id:
            raise ValueError("child agent_id/device_id required")
        now = utc_now()
        child_state = dict(self.state.children.get(child_id) or {})
        child_state["last_healthcheck_at"] = now
        child_state["healthcheck"] = payload
        child_state.setdefault("agent_id", child_id)
        self.state.children[child_id] = child_state
        self._persist_runtime_state()
        return child_state

    def list_children(self) -> list[dict[str, Any]]:
        return list(self.state.children.values())

    def list_tasks(self) -> list[dict[str, Any]]:
        return list(self.state.tasks.values())

    def record_inbox(self, request_id: str | None, data: dict[str, Any]) -> None:
        self.state.inbox.append({"task_id": request_id, "at": utc_now(), "data": data})
        self._persist_runtime_state()

    def record_task(self, task: dict[str, Any], result: dict[str, Any]) -> None:
        self.state.tasks[task["id"]] = task
        self.state.outbox.append({"task_id": task["id"], "at": utc_now(), "result": result})
        self._persist_runtime_state()

    async def _ensure_parent_registration(self) -> None:
        if self.state.layer != "lower":
            return
        if not self.state.parent_endpoint or not self.state.registry_id:
            return
        signature = {
            "parent_endpoint": self.state.parent_endpoint,
            "registry_id": self.state.registry_id,
            "agent_id": self.state.agent_id,
        }
        if self._last_parent_registration_signature == signature:
            return

        payload = {
            "agent_id": self.state.agent_id,
            "device_id": self.state.registry_id,
            "name": self.state.name,
            "layer": self.state.layer,
            "device_type": self.state.device_type,
            "endpoint": self.base_url(),
            "command_endpoint": f"{self.base_url()}/agents/{self.state.token}/command" if self.state.token else None,
            "parent_id": self.state.parent_id,
            "registered_at": self.state.registered_at,
        }

        def _register_with_parent() -> None:
            import json
            import urllib.request

            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{self.state.parent_endpoint.rstrip('/')}/children/register",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5):
                return

        try:
            await asyncio.to_thread(_register_with_parent)
            self._last_parent_registration_signature = signature
            self.state.remember(
                {
                    "kind": "parent_registration",
                    "at": utc_now(),
                    "parent_endpoint": self.state.parent_endpoint,
                    "parent_id": self.state.parent_id,
                }
            )
        except Exception as exc:
            logger.debug(f"Parent registration failed: {exc}")

    async def simulation_loop(self) -> None:
        """
        Simulation Loop: Agent의 메인 루프

        주기적으로 실행되는 메인 로직:
        1. 센서 데이터 생성 (Simulator)
        2. Tools 상태 업데이트 (Telemetry 기반 동기화) ← 새로움
        3. 의사결정 (Decision Engine)
        4. 권장사항 적용 (Tools) ← 새로움
        5. Moth로 발행 (Real-time streaming)

        이를 통해 realistic feedback loop 형성:
        Simulator → Tools ↔ Decision → Tools → Telemetry → Moth

        System Layer (POC 06)인 경우는 healthcheck만 발송
        """
        try:
            if self.state.layer == "system":
                # System layer: healthcheck만, telemetry는 발송하지 않음
                self._create_background_task(self.moth_publisher.healthcheck_loop())
                return

            # ===== Moth 연결 초기화 =====
            # 1. Registration response에서 topics 초기화
            # 2. WebSocket 연결
            # 3. 자동 재연결 loop, 주기적 healthcheck 시작
            logger.info(f"Simulation loop 시작: registry_id={self.state.registry_id}")

            if hasattr(self, '_registration_response') and self._registration_response:
                await self.moth_publisher.initialize(self._registration_response)
            else:
                logger.warning("No registration response for Moth initialization")

            await self.moth_publisher.connect()
            if self.moth_publisher.is_connected:
                logger.info("Moth connected successfully")
            else:
                logger.warning("Moth connection failed")

            self._create_background_task(self.moth_publisher._reconnect_loop())
            self._create_background_task(self.moth_publisher.healthcheck_loop())

            # ===== 메인 simulation loop =====
            _prev_connected_state = self.state.connected
            while not self._stopping:
                # 설정된 주기만큼 대기 (interval_seconds, 기본값 2초)
                await asyncio.sleep(self.simulator.interval_seconds())

                # ✅ Detect recovery from disconnection (Ch.16)
                if not _prev_connected_state and self.state.connected:
                    logger.info("🔄 Device recovered from disconnection, reporting recovery state")
                    await self._report_recovery_to_system()
                _prev_connected_state = self.state.connected

                # 1️⃣ 센서 데이터 생성 및 정규화
                telemetry = self.telemetry_reader.normalize(self.simulator.next_telemetry(self.state))
                self.state.last_seen_at = utc_now()

                # Registry keepalive: Moth 연결 여부와 무관하게 주기적으로 last_seen_at 갱신
                _keepalive_interval = int(self.config.get("registry", {}).get("healthcheck_interval_seconds", 1))
                if not hasattr(self, "_keepalive_tick"):
                    self._keepalive_tick = 0
                self._keepalive_tick += 1
                if self._keepalive_tick >= _keepalive_interval:
                    self._keepalive_tick = 0
                    try:
                        self._upsert_agent()
                    except Exception as _ka_err:
                        logger.debug(f"Registry keepalive 실패: {_ka_err}")
                    await self._ensure_parent_registration()
                self.state.last_telemetry = telemetry

                # 1-b️⃣ [SYNC GPS] Simulator 위치를 AgentState에 동기화
                if "position" in telemetry and isinstance(telemetry["position"], dict):
                    pos = telemetry["position"]
                    if "latitude" in pos:
                        self.state.latitude = float(pos["latitude"])
                    if "longitude" in pos:
                        self.state.longitude = float(pos["longitude"])

                depth_value = telemetry.get("depth")
                altitude_value = telemetry.get("altitude")
                underwater = False
                if isinstance(depth_value, (int, float)):
                    underwater = float(depth_value) > 0.0
                elif isinstance(altitude_value, (int, float)):
                    underwater = float(altitude_value) < 0.0
                self.state.environment_state = "UNDERWATER" if underwater else "SURFACE"
                self.state.active_mediums = ["ACOUSTIC"] if underwater else ["RF", "INTERNET", "ACOUSTIC"]
                # 2️⃣ [ENHANCED] Telemetry 기반으로 Tool 상태 동기화
                # GPS, Battery, IMU 등이 현재 시뮬레이션 상태를 반영하도록 업데이트
                self._update_tools_from_telemetry(telemetry)
                self.state.mission_state = dict(telemetry.get("mission") or self.simulator.mission_state or self.state.mission_state)

                # 3️⃣ 의사결정 (LLM-primary, critical rule override)
                context = self._build_decision_context(telemetry)
                decision = self.decision_engine.decide(self.state, telemetry, context)
                self.state.last_decision = decision
                self.state.remember({"kind": "telemetry", "at": utc_now(), "decision": decision})

                # 3-b️⃣ Critical rule 발동 시 SYS_ANOMALY_DETECTED 이벤트 전송
                if decision.get("mode") == "critical_rule":
                    self._post_critical_event(decision, telemetry)

                # 4️⃣ [ENHANCED] Decision 권장사항을 Tools에 적용
                # 의사결정 결과가 실제로 motor_control 등에 반영됨
                self._apply_decision_to_tools(decision)

                # 5️⃣ Moth로 Telemetry 발행
                # Real-time streaming: server에서 위치 업데이트 받고 dynamic re-binding 판단
                await self.moth_publisher.publish_telemetry(telemetry)

                # 6️⃣ ✅ Sensor health monitoring (Ch.15)
                self._check_sensor_health(telemetry)

                # 7️⃣ 실행 중 태스크 중단 감시
                await self._check_task_interrupt_conditions(telemetry)

                self._persist_runtime_state()

        except Exception as e:
            logger.error(f"Simulation loop 에러: {e}", exc_info=True)
            raise

    def _update_tools_from_telemetry(self, telemetry: dict[str, Any]) -> None:
        """
        Telemetry를 기반으로 Tool 상태를 동기화 (현실적인 시뮬레이션)

        각 Tool은 현재 시뮬레이션 상태를 반영하도록 업데이트됩니다:
        - GPS: 현재 위치를 gps_reader에 반영
        - Battery: 모터 부하를 고려하여 배터리 방전 시뮬레이션
        - IMU: 현재 heading을 IMU에 반영

        이를 통해 Tool의 read() 메서드가 항상 현실적인 값을 반환합니다.
        """
        # ===== GPS 위치 동기화 =====
        if "gps_reader" in self.tools and "position" in telemetry:
            pos = telemetry["position"]
            if isinstance(pos, dict) and "latitude" in pos and "longitude" in pos:
                # Simulator의 위치를 GPS reader에 반영
                self.tools["gps_reader"].update_position(
                    pos["latitude"],
                    pos["longitude"],
                    pos.get("altitude", 0.0),
                )

        # ===== Battery 상태 동기화 =====
        battery_state = telemetry.get("battery")
        if "battery_monitor" in self.tools and isinstance(battery_state, dict):
            try:
                self.tools["battery_monitor"].percent = float(battery_state.get("charge_percent", self.tools["battery_monitor"].percent))
            except Exception:
                pass

        # ===== IMU 방향 동기화 =====
        if "imu_reader" in self.tools and "motion" in telemetry:
            motion = telemetry["motion"]
            if isinstance(motion, dict):
                heading = motion.get("heading") or telemetry.get("navigation", {}).get("cog", 0.0)
                self.tools["imu_reader"].set_orientation(
                    roll=motion.get("roll", 0.0),
                    pitch=motion.get("pitch", 0.0),
                    yaw=float(heading),
                )

        # ===== AUV depth sensor 동기화 =====
        if "depth_sensor" in self.tools and "depth" in telemetry:
            depth_value = telemetry.get("depth")
            if isinstance(depth_value, (int, float)) and hasattr(self.tools["depth_sensor"], "set_depth"):
                self.tools["depth_sensor"].set_depth(float(depth_value))

        # ===== 장애물 시뮬레이션 (USV/표층) =====
        # 5% 확률로 10~80m 거리에 장애물 발생, 이후 서서히 소거
        if "obstacle_detector" in self.tools:
            detector = self.tools["obstacle_detector"]
            detector.clear()
            if random.random() < 0.05:
                distance = round(random.uniform(10.0, 80.0), 1)
                bearing = round(random.uniform(0.0, 360.0), 1)
                detector.add_obstacle(distance, bearing)

    def _apply_decision_to_tools(self, decision: dict[str, Any]) -> None:
        """
        Decision의 권장사항을 실제로 Tools에 적용 (피드백 루프)

        Decision Engine이 생성한 recommendations을 motor_control 등에 적용하여
        다음 iteration에서 realistic한 상태 변화가 일어나도록 합니다.

        Example:
        - "slow_down" → motor_control.set_thrust() 호출
        - "change_heading" → yaw 조정
        - "return_to_base" → full forward thrust
        """
        for rec in decision.get("recommendations", []):
            action = rec.get("action")
            params = rec.get("params", {})

            # 액션별 처리
            if action == "slow_down" and "motor_control" in self.tools:
                # 목표 속도를 thrust로 변환 (대략 속도 = thrust * 10 m/s)
                target_speed = params.get("target_speed_mps", 2.0)
                max_thrust = target_speed / 10.0
                self.tools["motor_control"].set_thrust(max(0.0, max_thrust), 0.0)

            elif action == "stop" and "motor_control" in self.tools:
                # 모터 정지
                self.tools["motor_control"].stop()

            elif action == "change_heading" and "motor_control" in self.tools:
                # 방향 변경: heading_degrees를 yaw thrust로 변환
                heading_delta = params.get("heading_degrees", 0.0)
                yaw_thrust = max(-1.0, min(1.0, heading_delta / 45.0))  # ±45도 = ±1.0 thrust
                current_status = self.tools["motor_control"].get_status()
                self.tools["motor_control"].set_thrust(current_status["forward_thrust"], yaw_thrust)

            elif action == "return_to_base" and "motor_control" in self.tools:
                # 기지 복귀: 최대 전진 thrust
                self.tools["motor_control"].set_thrust(1.0, 0.0)

    def _post_critical_event(self, decision: dict[str, Any], telemetry: dict[str, Any]) -> None:
        """Critical rule 발동 시 SYS_ANOMALY_DETECTED 이벤트를 Registry에 전송 (non-blocking)"""
        try:
            rec = (decision.get("recommendations") or [{}])[0]
            reason = rec.get("params", {}).get("reason", "critical_rule")
            self.registry_client.ingest_event({
                "event_type": "SYS_ANOMALY_DETECTED",
                "source_system": "device_agent",
                "source_agent_id": self.state.agent_id,
                "source_role": self.state.role,
                "severity": "CRITICAL",
                "title": f"[{self.state.device_type}] {self.state.name}: {reason}",
                "message": (
                    f"[{self.state.device_type}] {self.state.name}: "
                    f"{reason} — action={rec.get('action')}, "
                    f"battery={telemetry.get('battery_percent', '?')}%"
                ),
                "target_type": "DEVICE",
                "target_id": str(self.state.registry_id or self.state.agent_id),
                "data": {
                    "anomaly_type": reason,
                    "recommended_action": rec.get("action"),
                    "auto_remediated": True,
                    "device_id": self.state.registry_id,
                    "device_type": self.state.device_type,
                    "layer": self.state.layer,
                    "params": rec.get("params", {}),
                    "location": telemetry.get("position", {}),
                },
            })
        except Exception as e:
            logger.debug(f"Critical event 전송 실패: {e}")

    def _build_decision_context(self, telemetry: dict[str, Any]) -> dict[str, Any]:
        """
        Tool 읽기값을 모아 decision engine에 전달할 context 구성.
        telemetry에 없는 상세 센서 데이터(장애물, 항로 진행률, 자세, 테더 등)를 포함합니다.
        """
        ctx: dict[str, Any] = {}
        tool_reads = {
            "obstacles":      ("obstacle_detector", "detect"),
            "route":          ("route_planner",     "get_current_route"),
            "attitude":       ("imu_reader",        "read"),
            "battery_detail": ("battery_monitor",   "read"),
            "gps":            ("gps_reader",        "read"),
            "acoustic":       ("acoustic_modem",    "get_link_status"),
            "depth_detail":   ("depth_sensor",      "read"),
            "tether":         ("tether_monitor",    "read"),
        }
        for key, (tool_name, method_name) in tool_reads.items():
            tool = self.tools.get(tool_name)
            if tool and hasattr(tool, method_name):
                try:
                    ctx[key] = getattr(tool, method_name)()
                except Exception:
                    pass
        return ctx

    def apply_command(self, command: dict[str, Any]) -> dict[str, Any]:
        execution_result = self.command_controller.execute(command)
        simulation_result: dict[str, Any] = {}
        execution_status = str(execution_result.get("status") or "").upper()
        if execution_status != "FAILED" and execution_result.get("delivered", True):
            try:
                simulation_result = self.simulator.apply_command(self.state, command, self.tools)
            except Exception as exc:
                simulation_result = {
                    "status": "FAILED",
                    "delivered": False,
                    "usable_output": False,
                    "failure_reason": f"simulation_apply_failed:{exc}",
                    "artifacts": [],
                    "mission_state": dict(self.state.mission_state),
                }
        else:
            simulation_result = {
                "status": "FAILED",
                "delivered": False,
                "usable_output": False,
                "failure_reason": execution_result.get("error") or execution_result.get("failure_reason") or "command_execution_failed",
                "artifacts": [],
                "mission_state": dict(self.state.mission_state),
            }
        result = {**execution_result, **simulation_result}
        if "status" in result:
            result["status"] = "COMPLETED" if str(result.get("status") or "").upper() in {"OK", "SUCCESS", "COMPLETED"} else "FAILED"
        self.state.last_command = dict(command)
        self.state.mission_state = dict(simulation_result.get("mission_state") or self.state.mission_state)
        self.state.remember({
            "kind": "command_apply",
            "at": utc_now(),
            "command": command,
            "result": result,
        })
        self._persist_runtime_state()
        return result

    def _check_sensor_health(self, telemetry: dict[str, Any]) -> None:
        """주기적 센서 상태 확인 및 Event 생성 → Registry 보고 (Ch.15)"""
        if not hasattr(self, '_last_sensor_check'):
            self._last_sensor_check = {}

        # Battery 상태 확인
        battery = telemetry.get("battery", {})
        if isinstance(battery, dict):
            current_level = float(battery.get("charge_percent", 100.0))
        else:
            current_level = float(telemetry.get("battery_percent", 100.0))
        last_level = self._last_sensor_check.get("battery_level", current_level)

        # 배터리 상태 변화 감지 (임계값 20%)
        if current_level < self._BATTERY_THRESHOLD and last_level >= self._BATTERY_THRESHOLD:
            # ✅ Event를 Registry에 보고 (Ch.15)
            event = {
                "event_id": str(uuid4()),
                "source_system": "device_agent",
                "source_agent_id": self.state.agent_id,
                "source_role": self.state.role,
                "event_type": "SYS_ANOMALY_DETECTED",
                "severity": "WARNING",
                "message": f"Battery low: {current_level}%",
                "target_type": "DEVICE",
                "target_id": str(self.state.registry_id or self.state.agent_id),
                "title": "Low battery warning",
                "description": f"Battery dropped below warning threshold: {current_level}%",
                "data": {
                    "anomaly_type": "LOW_BATTERY",
                    "battery_percent": current_level,
                    "threshold": self._BATTERY_THRESHOLD,
                },
                "metadata": {
                    "sensor_type": "battery",
                    "sensor_id": "battery_main",
                    "status": "low",
                    "level": current_level,
                },
            }
            self.registry_client.ingest_event(event)
            logger.warning(f"⚠️ Battery low event reported: {current_level}%")

        self._last_sensor_check["battery_level"] = current_level

        # Depth sensor 상태 확인 (AUV)
        depth = telemetry.get("depth", {})
        if isinstance(depth, dict):
            depth_m = float(depth.get("depth_meters", 0.0))
        else:
            depth_m = float(depth or telemetry.get("depth_sensor", {}).get("depth_meters", 0.0))
        max_depth = 300.0
        if depth_m > max_depth:
            # ✅ Event를 Registry에 보고 (Ch.15)
            event = {
                "event_id": str(uuid4()),
                "source_system": "device_agent",
                "source_agent_id": self.state.agent_id,
                "source_role": self.state.role,
                "event_type": "SYS_ANOMALY_DETECTED",
                "severity": "CRITICAL",
                "message": f"Depth exceeded: {depth_m}m > {max_depth}m",
                "target_type": "DEVICE",
                "target_id": str(self.state.registry_id or self.state.agent_id),
                "title": "Depth limit exceeded",
                "description": f"Depth exceeded maximum limit: {depth_m}m > {max_depth}m",
                "data": {
                    "anomaly_type": "CRITICAL_HAZARD",
                    "hazard": "DEPTH_LIMIT_EXCEEDED",
                    "depth_m": depth_m,
                    "threshold_m": max_depth,
                },
                "metadata": {
                    "sensor_type": "depth",
                    "sensor_id": "depth_main",
                    "status": "max_depth_exceeded",
                    "depth": depth_m,
                },
            }
            self.registry_client.ingest_event(event)
            logger.critical(f"⚠️ Depth exceeded event reported: {depth_m}m")

    async def _check_task_interrupt_conditions(self, telemetry: dict[str, Any]) -> None:
        """실행 중 태스크의 지속 가능 여부를 확인하고, 불가하면 중단 보고 후 미션 상태를 리셋한다."""
        mission_mode = (self.state.mission_state or {}).get("mode", "idle")
        if mission_mode in {"idle", "ready", "completed", "returned", "aborted", "stopped"}:
            return  # 실행 중인 태스크 없음

        active_action = str((self.state.mission_state or {}).get("active_action") or "").lower()
        is_safe = active_action in self._SAFE_ACTIONS

        if is_safe:
            return  # 안전 복귀 명령은 중단하지 않음

        battery = telemetry.get("battery", {})
        if isinstance(battery, dict):
            current_level = float(battery.get("charge_percent", 100.0))
        else:
            current_level = float(telemetry.get("battery_percent", 100.0))

        if current_level < self._BATTERY_THRESHOLD:
            logger.warning(
                f"Task interrupted: battery {current_level:.1f}% < {self._BATTERY_THRESHOLD}% "
                f"(action={active_action}, mode={mission_mode})"
            )
            # 미션 상태를 aborted로 전환
            if hasattr(self.simulator, "mission_state"):
                self.simulator.mission_state.update({
                    "mode": "aborted",
                    "status": "aborted",
                    "active_action": None,
                    "target_position": None,
                })
                self.state.mission_state = dict(self.simulator.mission_state)

            # 현재 처리 중인 태스크 ID를 찾아 결과 보고
            last_task_id = getattr(self.state, "_executing_task_id", None)
            if last_task_id:
                from agent.message_router import _report_task_result_to_system_agent
                system_url = str(self.config.get("system_agent", {}).get("url") or "http://127.0.0.1:9116")
                report_endpoint = f"{system_url.rstrip('/')}/message:send"
                await _report_task_result_to_system_agent(
                    runtime=self,
                    task_id=last_task_id,
                    command={"action": active_action},
                    execution_result={
                        "status": "FAILED",
                        "failure_reason": f"battery_insufficient:{current_level:.1f}%",
                        "abort_type": "BATTERY_INSUFFICIENT",
                    },
                    execution_status="FAILED",
                    system_agent_url=report_endpoint,
                )
                self.state._executing_task_id = None  # type: ignore[attr-defined]

            self.state.remember({
                "kind": "task_interrupted",
                "at": utc_now(),
                "reason": f"battery_insufficient:{current_level:.1f}%",
                "action": active_action,
            })

    async def _report_recovery_to_system(self) -> None:
        """Report device recovery to System Agent (Ch.16)"""
        try:
            # Build recovery report with local device state
            recovery_report = {
                "device_id": str(self.state.registry_id),
                "agent_id": self.state.agent_id,
                "recovered_at": utc_now(),
                "local_state": {
                    "battery": self.state.last_telemetry.get("battery", {}) if self.state.last_telemetry else {},
                    "position": self.state.last_telemetry.get("position", {}) if self.state.last_telemetry else {},
                    "status": self.state.status if hasattr(self.state, 'status') else "active",
                },
                "completed_tasks": [],  # Placeholder for task results from task_id_store
                "pending_events": [],   # Placeholder for local events
            }

            # Try to get System Agent endpoint from registration response or config
            system_agent_endpoint = None
            if hasattr(self, '_registration_response') and self._registration_response:
                parents = self._registration_response.get("parents") or []
                for parent in parents:
                    if parent.get("role") == "system_agent" or parent.get("layer") == "system":
                        agent_info = parent.get("agent") or {}
                        system_agent_endpoint = agent_info.get("endpoint")
                        break

            if not system_agent_endpoint:
                # Try to get from config
                system_config = self.config.get("system_agent", {})
                system_agent_endpoint = system_config.get("endpoint")

            if not system_agent_endpoint:
                logger.warning("Could not determine System Agent endpoint for recovery report")
                return

            # POST recovery report to System Agent
            import urllib.request
            import json
            data = json.dumps(recovery_report).encode("utf-8")
            req = urllib.request.Request(
                f"{system_agent_endpoint}/device-recovery",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    result = json.loads(resp.read() or b"{}")
                    logger.info(f"✅ Recovery report sent successfully: {result}")
                    self.state.remember({"kind": "recovery_reported", "at": utc_now(), "result": result})
            except Exception as e:
                logger.warning(f"Failed to send recovery report: {e}")

        except Exception as e:
            logger.error(f"Error in recovery reporting: {e}", exc_info=True)

    # 배터리가 부족해도 반드시 허용해야 하는 안전 복귀 명령
    _SAFE_ACTIONS: frozenset[str] = frozenset({
        "return_to_base", "surface", "hold_position",
        "emergency_stop", "abort_mission", "rtb",
    })
    _BATTERY_THRESHOLD: int = 20

    def _get_battery_percent(self) -> float | None:
        telemetry = self.state.last_telemetry or {}
        battery = telemetry.get("battery")
        if isinstance(battery, dict):
            val = battery.get("charge_percent")
        else:
            val = telemetry.get("battery_percent")
        try:
            return float(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    def can_accept_command(self, command: dict[str, Any]) -> tuple[bool, str | None]:
        action = str(command.get("action") or "").strip().lower()
        if not action:
            return False, "missing_action"

        supported = {str(item).strip().lower() for item in self.skills.list_actions()}
        if action not in supported:
            return False, "unsupported_action"

        if not self.state.connected and self.registry_client.required:
            return False, "device_not_connected"

        is_safe = action in self._SAFE_ACTIONS

        # 이미 다른 태스크 실행 중 — 안전 복귀 명령은 항상 허용
        mission_mode = (self.state.mission_state or {}).get("mode", "idle")
        if not is_safe and mission_mode not in {"idle", "ready", "completed", "returned", "aborted", "stopped"}:
            return False, f"already_executing:{mission_mode}"

        # 배터리 부족 — 안전 복귀 명령은 항상 허용
        if not is_safe:
            battery = self._get_battery_percent()
            if battery is not None and battery < self._BATTERY_THRESHOLD:
                return False, f"battery_insufficient:{battery:.1f}%"

        return True, None
