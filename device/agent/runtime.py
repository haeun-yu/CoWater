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
import importlib
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
from skills.catalog import SkillCatalog
from storage.identity_store import IdentityStore
from transport.registry_client import RegistryClient
from transport.moth_publisher import MothPublisher

logger = logging.getLogger(__name__)


class AgentRuntime:
    """
    Agent 실행 엔진: Device Agent의 생명주기 관리
    """

    def __init__(self, config_path: Path) -> None:
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

        # device_type → tools/simulator 디렉토리명 결정
        raw_device_type = str(self.agent_config.get("device_type") or "").upper()
        _type_map = {"USV": "usv", "AUV": "auv", "ROV": "rov", "CONTROL_SHIP": "ship"}
        self._device_dir = _type_map.get(raw_device_type, raw_device_type.lower() or "usv")

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

        # Task ID 처리 이력 저장소: 중복 실행 방지
        from agent.task_id_store import TaskIdStore
        db_path = str(Path(__file__).resolve().parent.parent / ".runtime" / f"{self.instance_id}_tasks.db")
        self.task_id_store = TaskIdStore(db_path=db_path)

        # 의사결정 엔진: Rule 기반 + LLM 분석
        self.decision_engine = DecisionEngine(self.agent_config, self.skills)

        # 텔레메트리 리더: 센서 데이터 정규화 (공통)
        _telemetry_mod = importlib.import_module("tools.common.telemetry_reader")
        TelemetryReader = getattr(_telemetry_mod, "TelemetryReader")
        self.telemetry_reader = TelemetryReader()

        # Device 시뮬레이터: device type별 동적 로드
        _sim_mod = importlib.import_module(f"simulator.{self._device_dir}")
        DeviceSimulator = getattr(_sim_mod, "DeviceSimulator")
        self.simulator = DeviceSimulator(self.config.get("simulation", {}), self.skills.list_tracks())

        # 명령 제어기: device type별 CommandExecutor 동적 로드
        _cmd_mod = importlib.import_module(f"tools.{self._device_dir}.command_executor")
        CommandExecutor = getattr(_cmd_mod, "CommandExecutor")
        self.command_controller = CommandController(CommandExecutor())

        # Moth WebSocket 발행자: Healthcheck 및 Telemetry 발행
        self.moth_publisher = MothPublisher(self.config, self.state)

        # 동적 Tool 로드: tools/ 디렉토리에서 센서/제어 클래스 자동 로드
        self.tools: dict[str, Any] = {}
        self._load_tools()
        self._last_assignment_signature: dict[str, Any] | None = None
        self._last_parent_registration_signature: dict[str, Any] | None = None
        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._stopping = False

    def _create_background_task(self, coro: Any) -> asyncio.Task[Any]:
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    async def stop(self) -> None:
        self._stopping = True
        for task in list(self._background_tasks):
            task.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        await self.moth_publisher.close()

    def _load_tools(self) -> None:
        """
        tools/{device_type}/ 및 tools/common/ 에서 센서/제어 클래스를 동적으로 로드.

        device type별 tools만 로드하므로 USV Agent가 AUV sonar 등을 로드하지 않는다.
        """
        device_module_prefix = f"tools.{self._device_dir}"
        scan_targets = [
            (device_module_prefix, f"tools/{self._device_dir}"),
            ("tools.common", "tools/common"),
        ]

        # runtime.py는 device/agent/ 안에 있으므로 device/ 루트를 기준으로 경로 탐색
        device_root = Path(__file__).resolve().parent.parent

        for module_prefix, rel_dir in scan_targets:
            tools_dir = device_root / rel_dir
            if not tools_dir.exists():
                continue
            for py_file in tools_dir.glob("*.py"):
                if py_file.name.startswith("_"):
                    continue
                module_name = py_file.stem
                class_name = "".join(word.capitalize() for word in module_name.split("_"))
                try:
                    module = importlib.import_module(f"{module_prefix}.{module_name}")
                    cls = getattr(module, class_name, None)
                    if cls:
                        self.tools[module_name] = cls()
                        logger.debug(f"Tool 로드됨: {module_name} ({class_name})")
                except Exception as e:
                    logger.debug(f"Tool 로드 실패 {module_name}: {e}")

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
                    return
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
            self._last_parent_registration_signature = None

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
            llm_enabled=bool(self.decision_engine.llm_enabled),
            skills=self.skills.list_skills(),
            actions=self.skills.list_actions(),
            last_seen_at=self.state.last_seen_at,
        )

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
            while not self._stopping:
                # 설정된 주기만큼 대기 (interval_seconds, 기본값 2초)
                await asyncio.sleep(self.simulator.interval_seconds())

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

                # 2️⃣ [ENHANCED] Telemetry 기반으로 Tool 상태 동기화
                # GPS, Battery, IMU 등이 현재 시뮬레이션 상태를 반영하도록 업데이트
                self._update_tools_from_telemetry(telemetry)

                # 3️⃣ 의사결정 (LLM-primary, critical rule override)
                context = self._build_decision_context(telemetry)
                decision = self.decision_engine.decide(self.state, telemetry, context)
                self.state.remember({"kind": "telemetry", "at": utc_now(), "decision": decision})

                # 3-b️⃣ Critical rule 발동 시 서버 alert registry에 전송
                if decision.get("mode") == "critical_rule":
                    self._post_critical_alert(decision, telemetry)

                # 4️⃣ [ENHANCED] Decision 권장사항을 Tools에 적용
                # 의사결정 결과가 실제로 motor_control 등에 반영됨
                self._apply_decision_to_tools(decision)

                # 5️⃣ Moth로 Telemetry 발행
                # Real-time streaming: server에서 위치 업데이트 받고 dynamic re-binding 판단
                await self.moth_publisher.publish_telemetry(telemetry)

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

        # ===== Battery 방전 시뮬레이션 =====
        if "battery_monitor" in self.tools:
            # 전력 소비 추정: 기본 0.2% + 모터 부하에 따른 추가 소비
            motor_status = self.tools.get("motor_control", {}).get_status() if "motor_control" in self.tools else {}
            thrust_magnitude = abs(motor_status.get("forward_thrust", 0.0)) if motor_status else 0.0
            # 0.2% (idle) ~ 0.5% (full thrust) per iteration
            consumption = 0.2 + (thrust_magnitude * 0.3)
            self.tools["battery_monitor"].discharge(consumption)

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

    def _post_critical_alert(self, decision: dict[str, Any], telemetry: dict[str, Any]) -> None:
        """Critical rule 발동 시 서버 alert registry에 비동기 전송 (non-blocking)"""
        try:
            rec = (decision.get("recommendations") or [{}])[0]
            reason = rec.get("params", {}).get("reason", "critical_rule")
            self.registry_client.ingest_alert({
                "source_system": "device_agent",
                "event_id": f"critical-{uuid4().hex[:8]}",
                "source_agent_id": self.state.agent_id,
                "source_role": self.state.role,
                "alert_type": reason,
                "severity": "CRITICAL",
                "message": (
                    f"[{self.state.device_type}] {self.state.name}: "
                    f"{reason} — action={rec.get('action')}, "
                    f"battery={telemetry.get('battery_percent', '?')}%"
                ),
                "recommended_action": rec.get("action"),
                "auto_remediated": True,
                "metadata": {
                    "device_id": self.state.registry_id,
                    "device_type": self.state.device_type,
                    "layer": self.state.layer,
                    "params": rec.get("params", {}),
                    "location": telemetry.get("position", {}),
                },
            })
        except Exception as e:
            logger.debug(f"Critical alert 전송 실패: {e}")

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
        return self.command_controller.apply(self.state, command)

    def _check_sensor_health(self, telemetry: dict[str, Any]) -> None:
        """주기적 센서 상태 확인 및 Event 생성 → Registry 보고 (Ch.15)"""
        if not hasattr(self, '_last_sensor_check'):
            self._last_sensor_check = {}

        # Battery 상태 확인
        battery = telemetry.get("battery", {})
        if isinstance(battery, dict):
            current_level = battery.get("charge_percent", 100.0)
            last_level = self._last_sensor_check.get("battery_level", current_level)

            # 배터리 상태 변화 감지
            if current_level < 20 and last_level >= 20:
                # ✅ Event를 Registry에 보고 (Ch.15)
                event = {
                    "event_id": str(uuid4()),
                    "source_system": "device_agent",
                    "source_agent_id": self.state.registry_id,
                    "source_role": self.state.role,
                    "event_type": "sensor_status_changed",
                    "severity": "WARNING",
                    "message": f"Battery low: {current_level}%",
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
            depth_m = depth.get("depth_meters", 0.0)
            max_depth = 300.0
            if depth_m > max_depth:
                # ✅ Event를 Registry에 보고 (Ch.15)
                event = {
                    "event_id": str(uuid4()),
                    "source_system": "device_agent",
                    "source_agent_id": self.state.registry_id,
                    "source_role": self.state.role,
                    "event_type": "sensor_status_changed",
                    "severity": "CRITICAL",
                    "message": f"Depth exceeded: {depth_m}m > {max_depth}m",
                    "metadata": {
                        "sensor_type": "depth",
                        "sensor_id": "depth_main",
                        "status": "max_depth_exceeded",
                        "depth": depth_m,
                    },
                }
                self.registry_client.ingest_event(event)
                logger.critical(f"⚠️ Depth exceeded event reported: {depth_m}m")

    def can_accept_command(self, command: dict[str, Any]) -> tuple[bool, str | None]:
        action = str(command.get("action") or "").strip().lower()
        if not action:
            return False, "missing_action"
        supported = {str(item).strip().lower() for item in self.skills.list_actions()}
        if action not in supported:
            return False, "unsupported_action"
        if not self.state.connected and self.registry_client.required:
            return False, "device_not_connected"
        return True, None
