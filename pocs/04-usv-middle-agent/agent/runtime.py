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

        # Identity 저장소: agent_id, token 등을 .runtime/{instance_id}.json에 저장
        self.identity_store = IdentityStore(config_path.parent / ".runtime", self.instance_id)
        self.identity = self.identity_store.read()

        # Skills Catalog: 이 Agent가 수행 가능한 모든 skills/actions 등록
        self.skills = SkillCatalog(self.capabilities)
        self.manifest_builder = ManifestBuilder(self.config, self.skills)

        # Agent 상태: agent_id, name, layer, device_type, 마지막 텔레메트리 등
        self.state = AgentState(
            agent_id=self.identity.get("agent_id") or f"{self.agent_config.get('id', 'agent')}-{self.instance_id}",
            role=str(self.agent_config.get("role") or "device_agent"),
            layer=str(self.agent_config.get("layer") or "lower"),  # "lower", "middle", "system"
            device_type=self.agent_config.get("device_type"),  # "usv", "auv", "rov", etc.
            instance_id=self.instance_id,
            name=self.identity.get("name") or f"{self.agent_config.get('name', 'CoWater Agent')} {self.instance_id}",
        )

        # Device Registration Server와의 통신
        self.registry_client = RegistryClient(self.config.get("registry", {}))

        # 의사결정 엔진: Rule 기반 + LLM 분석
        self.decision_engine = DecisionEngine(self.agent_config, self.skills)

        # 텔레메트리 리더: 센서 데이터 정규화
        self.telemetry_reader = TelemetryReader()

        # Device 시뮬레이터: 센서 값 생성
        self.simulator = DeviceSimulator(self.config.get("simulation", {}), self.skills.list_tracks())

        # 명령 제어기: HTTP 또는 A2A로부터 받은 명령 실행
        self.command_controller = CommandController(CommandExecutor())

        # Moth WebSocket 발행자: Heartbeat 및 Telemetry 발행
        self.moth_publisher = MothPublisher(self.config, self.state)

        # 동적 Tool 로드: tools/ 디렉토리에서 센서/제어 클래스 자동 로드
        self.tools: dict[str, Any] = {}
        self._load_tools()
        self._last_assignment_signature: dict[str, Any] | None = None

    def _load_tools(self) -> None:
        """
        tools/ 디렉토리에서 센서/제어 클래스를 동적으로 로드

        메커니즘:
        1. tools/ 디렉토리 스캔
        2. .py 파일 각각에 대해
           - 파일명을 클래스명으로 변환 (battery_monitor → BatteryMonitor)
           - importlib로 동적 로드
           - 인스턴스 생성 후 self.tools 딕셔너리에 저장
        3. 각 POC는 다른 tools를 가질 수 있음 (USV, AUV, ROV 등)

        Example:
            tools/battery_monitor.py → self.tools["battery_monitor"] = BatteryMonitor()
            tools/gps_reader.py → self.tools["gps_reader"] = GPSReader()
        """
        tools_dir = self.config_path.parent / "tools"
        if not tools_dir.exists():
            return

        for py_file in tools_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                # __init__.py 등 내부 파일 스킵
                continue

            module_name = py_file.stem  # "battery_monitor"
            # snake_case → PascalCase: battery_monitor → BatteryMonitor
            class_name = "".join(word.capitalize() for word in module_name.split("_"))

            try:
                # 동적으로 모듈 로드
                module = importlib.import_module(f"tools.{module_name}")
                cls = getattr(module, class_name, None)

                if cls:
                    # 클래스 인스턴스 생성 후 저장
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
            self.state.registry_id = int(self.identity["registry_id"])
            self.state.token = str(self.identity["token"])
            self.state.registered_at = self.identity.get("registered_at")
            try:
                self._upsert_agent()
                self._registration_response = self.registry_client.get_device(self.state.registry_id)
                self._refresh_assignment()
                self.state.connected = True
                self.state.last_seen_at = utc_now()
                logger.info(f"기존 등록 재사용: registry_id={self.state.registry_id}")
                return
            except Exception as exc:
                # 서버가 일시적으로 내려가 있어도 로컬 캐시로 Moth 초기화 가능
                if self.identity.get("tracks") or self.identity.get("heartbeat_topic"):
                    self._registration_response = {
                        "id": self.state.registry_id,
                        "token": self.state.token,
                        "tracks": self.identity.get("tracks", []),
                        "heartbeat_topic": self.identity.get("heartbeat_topic"),
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
        self.state.registry_id = int(created["id"])
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
                "heartbeat_topic": created.get("heartbeat_topic"),
                "telemetry_topics": created.get("telemetry_topics", []),
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

        System Layer (POC 06)인 경우는 heartbeat만 발송
        """
        try:
            if self.state.layer == "system":
                # System layer: heartbeat만, telemetry는 발송하지 않음
                asyncio.create_task(self.moth_publisher.heartbeat_loop())
                return

            # ===== Moth 연결 초기화 =====
            # 1. Registration response에서 topics 초기화
            # 2. WebSocket 연결
            # 3. 자동 재연결 loop, 주기적 heartbeat 시작
            logger.info(f"Simulation loop 시작: registry_id={self.state.registry_id}")

            if hasattr(self, '_registration_response') and self._registration_response:
                logger.info("MothPublisher 초기화 중...")
                await self.moth_publisher.initialize(self._registration_response)
                logger.info(f"MothPublisher 초기화 완료: heartbeat_topic={self.moth_publisher.heartbeat_topic}")
            else:
                logger.warning("_registration_response 없음 - MothPublisher 초기화 스킵")

            logger.info("Moth 연결 중...")
            await self.moth_publisher.connect()
            logger.info(f"Moth 연결 상태: {self.moth_publisher.is_connected}")

            asyncio.create_task(self.moth_publisher._reconnect_loop())
            asyncio.create_task(self.moth_publisher.heartbeat_loop())
            logger.info("Heartbeat loop 시작됨")

            # ===== 메인 simulation loop =====
            while True:
                # 설정된 주기만큼 대기 (interval_seconds, 기본값 2초)
                await asyncio.sleep(self.simulator.interval_seconds())

                # 1️⃣ 센서 데이터 생성 및 정규화
                telemetry = self.telemetry_reader.normalize(self.simulator.next_telemetry(self.state))
                self.state.last_seen_at = utc_now()
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

                # 3️⃣ 의사결정 (Rule 기반 + 비동기 LLM)
                decision = self.decision_engine.decide(self.state, telemetry)
                self.state.remember({"kind": "telemetry", "at": utc_now(), "decision": decision})

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
                # Telemetry의 heading을 IMU reader에 반영
                heading = motion.get("heading") or telemetry.get("navigation", {}).get("cog", 0.0)
                self.tools["imu_reader"].set_orientation(
                    roll=motion.get("roll", 0.0),
                    pitch=motion.get("pitch", 0.0),
                    yaw=float(heading),
                )

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

    def apply_command(self, command: dict[str, Any]) -> dict[str, Any]:
        return self.command_controller.apply(self.state, command)
