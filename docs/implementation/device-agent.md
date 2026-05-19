# Device Agent 구현 가이드

**문서 버전**: v0.1 (구현 기반)  
**최종 업데이트**: 2026-05-13  
**대상**: Device Agent 개발자  
**목적**: Device Agent의 구현 방법, 알고리즘, 프로토콜을 설명합니다.

> 💡 **이 문서는 구현 가이드입니다.** 역할과 책임, 생명주기 개요는 [SYSTEM_ARCHITECTURE.md](../SYSTEM_ARCHITECTURE.md), 등록 절차는 `scenarios/lifecycle.md`, 통신 설계는 [ADR-009](../adr/ADR-009-physical-communication-routing.md)를 참고하세요.

---

## 1. Device Agent 구현 범위

이 문서는 다음 구현 항목을 설명합니다.

- 초기화와 등록
- Task 수행 가능성 판단
- 통신 드라이버 선택
- Heartbeat와 Health Check
- 로컬 안전 행동
- A2A 통신

구조 개요와 책임 설명은 상위 문서에서 이미 정의되어 있으므로 여기서는 구현 단계만 다룹니다.

---

## 2. Device Agent 초기화와 등록

### 2.1 초기화 흐름

Device Agent는 시작 시 다음 순서로 초기화됩니다:

```
┌─────────────────────────────────────┐
│ Device Agent 시작                    │
└────────┬────────────────────────────┘
         ↓
┌─────────────────────────────────────┐
│ Step 1: 설정 파일 로드               │
│ (device-config.yaml)                │
└────────┬────────────────────────────┘
         ↓
┌─────────────────────────────────────┐
│ Step 2: 로컬 IdentityStore 확인      │
│ (.data/identity/{device_id}.json)   │
└────────┬────────────────────────────┘
         ├─ 있음 → Step 3A (캐시 사용)
         │
         └─ 없음 → Step 3B (등록)
                ↓
         ┌──────────────────────────┐
         │ Step 3B: System Agent에  │
         │ Device/Agent 등록        │
         └──────┬───────────────────┘
                ↓
         ┌──────────────────────────┐
         │ Step 4: 응답 데이터      │
         │ IdentityStore에 저장     │
         └──────┬───────────────────┘
                ↓
┌─────────────────────────────────────┐
│ Step 5: Device Agent 실행 준비 완료 │
│ (System Agent와 통신 가능)          │
└─────────────────────────────────────┘
```

### 2.2 Step 1: 설정 파일 로드

Device Agent는 시작 시 YAML 설정 파일에서 기본 정보를 읽습니다:

```python
from pathlib import Path
import yaml

class DeviceAgentBootstrap:
    """Device Agent 시작 프로세스"""

    def __init__(self, config_path: str = "config/device-config.yaml"):
        self.config_path = Path(config_path)
        self.config = self.load_config()

    def load_config(self) -> dict:
        """설정 파일 로드"""
        with open(self.config_path) as f:
            return yaml.safe_load(f)

    def get_device_info(self) -> dict:
        """설정에서 Device 정보 추출"""
        return {
            "id": self.config["device"]["id"],
            "type": self.config["device"]["type"],
            "name": self.config["device"]["name"],
            "actions": self.config["device"]["actions"],
            "capabilities": self.config["capabilities"]
        }
```

**설정 파일 예시** (`device-config.yaml`):

```yaml
device:
  id: "aauv-01"
  type: "AUV"
  name: "Autonomous Underwater Vehicle 01"
  actions:
    - "MOVE_TO"
    - "HIGH_RES_SCAN"
    - "SONAR_SCAN"

capabilities:
  - "ACOUSTIC"
  - "RF"
  - "INTERNET"

system_agent:
  endpoint:
    host: "192.168.1.100"
    port: 8000
    protocol: "HTTP"
```

### 2.3 Step 2: 로컬 IdentityStore 확인

설정 파일을 로드한 후, Device Agent는 **로컬에 저장된 등록 정보**가 있는지 확인합니다.

```python
from pathlib import Path
import json
import uuid

class IdentityStoreManager:
    """로컬 Device/Agent 등록 정보 캐시 관리"""

    def __init__(self, storage_root: str = ".runtime"):
        self.storage_root = Path(storage_root)
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.instance_id = self._get_or_create_instance_id()

    def _get_or_create_instance_id(self) -> str:
        """Device 인스턴스 고유 ID 관리"""
        id_file = self.storage_root / "instance_id"
        if id_file.exists():
            return id_file.read_text().strip()
        instance_id = str(uuid.uuid4())
        id_file.write_text(instance_id)
        return instance_id

    def get_registration_data(self, device_id: str) -> dict | None:
        """
        로컬에 저장된 등록 정보 조회

        Return:
            등록 정보 (device_id, agent_id, endpoint 등) 또는 None
        """
        file_path = self.storage_root / f"{self.instance_id}.json"

        if not file_path.exists():
            return None

        with open(file_path) as f:
            return json.load(f)

    def save_registration_data(self, device_id: str, data: dict) -> None:
        """
        System Agent에서 받은 등록 응답을 로컬에 저장
        """
        file_path = self.storage_root / f"{self.instance_id}.json"

        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)

        logger.info(f"Registration data saved: {file_path}")
```

**로컬에 저장되는 데이터 구조** (IdentityStore):

```json
{
  "device_id": "aauv-01",
  "device_type": "AUV",
  "layer": "lower",
  "device_endpoint": {
    "host": "192.168.50.1",
    "port": 9001,
    "protocol": "HTTP"
  },

  "agent_id": "agent-uuid-xxx",
  "agent_type": "DEVICE_AGENT",
  "agent_role": "DEVICE_BRIDGE",
  "agent_endpoint": "http://192.168.1.100:8000/api/agent",
  "capabilities": ["ACOUSTIC", "RF", "INTERNET"],
  "gateway_agent_id": null,
  "parent_id": null,

  "sensors": [
    {
      "name": "camera-01",
      "type": "VIDEO",
      "endpoint": "ws://192.168.1.100:8002/stream/aauv-01/camera-01"
    },
    {
      "name": "sonar-01",
      "type": "SONAR",
      "endpoint": "ws://192.168.1.100:8002/stream/aauv-01/sonar-01"
    }
  ],
  "telemetry_topics": [
    {
      "track_type": "VIDEO",
      "track_name": "camera-01",
      "topic": "device.telemetry.aauv-01.VIDEO"
    },
    {
      "track_type": "SONAR",
      "track_name": "sonar-01",
      "topic": "device.telemetry.aauv-01.SONAR"
    }
  ],

  "healthcheck_topic": "agents",
  "healthcheck_endpoint": "/healthcheck/aauv-01",

  "is_submerged": false,
  "environment_state": "SURFACE",
  "active_mediums": ["RF", "INTERNET", "ACOUSTIC"],
  "force_parent_routing": false,

  "registered_at": "2026-05-13T10:30:45.123Z"
}
```

### 2.4 Step 3A: 캐시된 정보 사용

로컬 IdentityStore에 등록 정보가 **있으면** 다시 등록하지 않고 저장된 데이터를 그대로 사용합니다:

```python
def initialize_device_agent(config: dict) -> dict:
    """Device Agent 초기화"""

    device_id = config["device"]["id"]
    identity_manager = IdentityStoreManager()

    # Step 2: 로컬 등록 정보 확인
    cached_data = identity_manager.get_registration_data(device_id)

    if cached_data:
        # Step 3A: 캐시된 정보 사용
        logger.info(f"Using cached registration: {device_id}")
        return {
            "device": cached_data,
            "is_newly_registered": False
        }

    # Step 3B로 이동 (아래 참고)
```

### 2.5 Step 3B: 새로 등록

로컬 IdentityStore에 등록 정보가 **없으면** DeviceBridge를 통해 System Agent의 Registry에 등록합니다:

```python
from src.device_bridge_client import DeviceBridgeClient

def initialize_device_agent_new_registration(config: dict) -> dict:
    """새 Device/Agent 등록 (DeviceBridge 경유)"""

    device_id = config["device"]["id"]
    device_bridge_client = DeviceBridgeClient(
        endpoint=config["device_bridge"]["url"]
    )

    # Step 3B: DeviceBridge를 통해 등록
    # DeviceBridge가 Device Registration Server(8280)에 대신 등록
    response = device_bridge_client.register(
        device_info={
            "name": config["device"]["name"],
            "type": config["device"]["type"],
            "layer": config["device"]["layer"],
            "tracks": config["device"]["tracks"],  # [{"type": "VIDEO", "name": "camera-01"}, ...]
            "actions": config["device"]["actions"]
        },
        agent_endpoint={
            "host": config["device"]["agent_host"],
            "port": config["device"]["agent_port"],
            "protocol": "HTTP"
        }
    )

    # 응답 데이터: device_id, agent_id, tracks, telemetry_topics, healthcheck_topic
    registration_data = {
        "device_id": response["device_id"],
        "device_type": config["device"]["type"],
        "layer": config["device"]["layer"],
        "registry_id": response["registry_id"],
        "token": response["token"],
        "agent_id": response["agent_id"],
        "tracks": response["tracks"],
        "telemetry_topics": response["telemetry_topics"],
        "healthcheck_topic": response["healthcheck_topic"],
        "healthcheck_endpoint": response.get("healthcheck_endpoint"),
        "capabilities": config["capabilities"],
        "environment_state": "SURFACE",
        "active_mediums": config["capabilities"],
        "registered_at": utc_now_iso()
    }

    return registration_data
```

### 2.6 Step 4: IdentityStore 저장

Device/Agent 등록 후 받은 응답 데이터를 **로컬에 저장**합니다:

```python
def bootstrap_device_agent(config_path: str):
    """Device Agent 완전 초기화"""

    # Step 1: 설정 로드
    bootstrap = DeviceAgentBootstrap(config_path)
    config = bootstrap.config
    device_id = config["device"]["id"]

    # Step 2: 로컬 IdentityStore 확인
    identity_manager = IdentityStoreManager()
    cached_data = identity_manager.get_registration_data(device_id)

    if cached_data:
        # Step 3A: 캐시 사용
        registration_data = cached_data
        is_new = False
    else:
        # Step 3B: 새로 등록
        registration_data = initialize_device_agent_new_registration(config)
        is_new = True

        # Step 4: IdentityStore에 저장
        identity_manager.save_registration_data(device_id, registration_data)

    logger.info(
        f"Device Agent initialized: device_id={device_id}, "
        f"agent_id={registration_data['agent_id']}, newly_registered={is_new}"
    )

    # Step 5: Device Agent 실행 준비 완료
    return {
        "device": registration_data,
        "is_newly_registered": is_new
    }
```

### 2.7 등록 후 통신 구조 (DeviceBridgeAgent)

Device Agent 등록 후, 다음과 같이 System Agent와 통신합니다:

```
Device Agent (9201)
   ↓ (HTTP A2A)
DeviceBridge (9110)
   ├─【송신】MissionPlanner → Task 할당
   ├─【수신】Heartbeat, Task Result, Problem Report
   └─【발행】정규화된 Event 발행
   ↓ (HTTP A2A)
System Agent 전체 (RequestHandler, MissionPlanner, PolicyManager, ...)
```

#### DeviceBridge의 역할

| 역할               | 설명                                                                | 담당자       |
| ------------------ | ------------------------------------------------------------------- | ------------ |
| **Task 할당**      | System Agent → Device Agent로 Task 전달 (A2A 프로토콜)              | DeviceBridge |
| **Heartbeat 수신** | Device의 정기적 상태 보고 수집 (배터리, 위치, 센서)                 | DeviceBridge |
| **결과/문제 수신** | Task 결과 및 즉각적 문제 보고 수집                                  | DeviceBridge |
| **Event 발행**     | 수신한 정보를 정규화된 Event로 변환/발행 (다른 System Agent가 구독) | DeviceBridge |
| **최종 판단**      | Task 실행 가능 여부 판단 (Capability, Resource, Safety)             | Device Agent |

> **핵심 원칙**:
>
> - DeviceBridge는 **통신을 중개하면서 Event를 발행**합니다
> - Task 할당 **전**에는 정책 검증을 하지 않습니다
> - Device Agent가 Task 수신 후 자신이 할 수 있는지 **최종 판단**합니다 (P5 원칙)
> - PolicyManager는 Rule/Config를 통해 **전역 정책**을 관리하지만, Task 전달 전에 미리 검증하지 않습니다

---

## 3. Task 수행 판단

### 2.1 알고리즘 (3단계)

```
[Task 수신] → [Step 1: Capability Check] → [Step 2: Resource Check] → [Step 3: Safety Check] → [Execute or ABORT]
                    ↓                              ↓                           ↓
           required_action이                배터리, 위치,                로컬 정책,
           Device.actions에                 통신 상태,                  안전 규칙
           있는가?                          시간 제약
```

### 2.2 Step 1: Capability Check (필수)

**원칙**: `Task.required_action` ∈ `Device.actions[]`

```python
def can_perform_task(task: Task, device: Device) -> tuple[bool, str]:
    """
    Task가 실행 가능한지 판단

    Return:
        (True, "") - 실행 가능
        (False, reason) - ABORTED 사유
    """

    # Step 1: required_action 확인
    if task.required_action not in device.actions:
        return False, f"Device cannot perform {task.required_action}"

    # Step 2: 필수 파라미터 확인
    if not validate_parameters(task.parameters, task.required_action):
        return False, "Invalid task parameters"

    return True, ""
```

### 2.3 Step 2: Resource Check (필수)

**리소스**:

- Battery: 권장 최소 임계값 (예: 20%, 사용자 override 가능)
- Position: 목표 위치 도달 가능성 (GPS/SLAM 기반)
- Communication: 필요한 매체 가용성
- Time: Task 완료까지 필요한 시간 vs 배터리 남은 시간

```python
def check_resources(task: Task, device: Device) -> tuple[bool, str]:
    """
    리소스 확인
    """

    # 배터리 확인
    if device.battery_percent < BATTERY_THRESHOLD:  # e.g., 20%, user override 가능
        return False, f"Low battery: {device.battery_percent}%"

    # 위치 확인 (target_area가 있는 경우)
    if task.target_position:
        distance = calculate_distance(device.position, task.target_position)
        max_distance = calculate_max_reachable(device.battery_percent)
        if distance > max_distance:
            return False, f"Target unreachable: {distance}m vs {max_distance}m"

    # 통신 확인 (필요시)
    if task.requires_communication:
        if not has_active_medium():
            return False, "No active communication medium"

    return True, ""
```

### 2.4 Step 3: Safety Check (선택)

**로컬 물리적 제약**:

- 환경 기반 제약 (수중 깊이, 수온 등)

> **참고**: Policy/Rule 기반의 NO_GO_ZONE, 시간대별 작업 제약은 **System Agent의 PolicyManager가 관리**합니다. Device Agent는 Task를 할당받을 때 이미 System Agent에서 검증된 Task만 수신하므로, Device Agent는 물리적 제약(깊이 제한, 수온 범위 등)만 확인하면 됩니다.

```python
def check_safety_rules(task: Task, device: Device) -> tuple[bool, str]:
    """
    로컬 물리적 제약 확인
    System Agent에서 이미 정책 검증을 거친 Task만 수신하므로,
    Device Agent는 장비 자체의 물리적 한계만 확인
    """

    # 환경 기반 제약 (Device 설정에서 정의)
    if device.environment_state == "UNDERWATER":
        max_depth = device.config.get("max_depth_m", 1000)
        if device.depth > max_depth:
            return False, f"Depth limit exceeded: {device.depth}m vs {max_depth}m"

    return True, ""
```

### 2.5 Task 상태 전이

```
[task.assign 수신] (System Agent → Device Agent)
    ↓
[3단계 수행 가능 여부 판단]
    ├─ Capability Check 실패 → status: "ABORTED" 즉시 반환
    ├─ Already Assigned 실패 → status: "ABORTED" 즉시 반환
    └─ Battery Check 실패   → status: "ABORTED" 즉시 반환

[모두 통과]
    → status: "OK" 반환 (수락 알림)
    → 백그라운드 실행 시작 (_execute_task_in_background)

[실행 중 — 텔레메트리 루프가 주기적으로 조건 감시]
    ├─ 배터리 < 임계값 감지
    │       → _abort_active_task()
    │       → task.result FAILED 부모에 전송 (중단 알림)
    │       → 실행 중단
    │
    └─ 실행 완료 (duration_sec 경과)
            → task.result COMPLETED 부모에 전송
            → _active_task 클리어
```

### 2.6 ABORTED vs FAILED 차이

| 상태        | 발생 시점                       | 원인                        | Mission 영향     |
| ----------- | ------------------------------- | --------------------------- | ---------------- |
| **ABORTED** | Task 실행 전 (PENDING/ASSIGNED) | 수행 불가능 판단 (Step 1-3) | Mission → FAILED |
| **FAILED**  | Task 실행 중 (IN_PROGRESS)      | 실행 중 오류/장애           | Mission → FAILED |

---

## 4. 물리 통신 드라이버

### 3.1 매체별 드라이버

#### Wired (유선 - ROV용)

```python
class WiredDriver:
    """유선 통신 드라이버 (USB, Ethernet over tether)"""

    def send_command(self, command: dict) -> dict:
        """
        동기식 명령 전송 (차단 방식, 항상 연결됨)
        """
        try:
            response = self.serial_port.write_and_read(command, timeout=5000)
            return response
        except TimeoutError:
            raise CommunicationError("Wired connection lost")

    def get_status(self) -> dict:
        """현재 센서/상태 읽음"""
        return self.read_sensors()
```

#### Acoustic (음향 - 수중용)

```python
class AcousticDriver:
    """음향 통신 드라이버 (Underwater modem)"""

    def __init__(self):
        self.modem = AcousticModem(frequency=50000)  # 50kHz
        self.max_range = 1000  # 미터
        self.latency_ms = 500  # 보통 지연

    def send_command(self, command: dict, target_agent_id: str) -> bool:
        """
        비동기식 명령 전송 (지연 고려)
        """
        try:
            self.modem.send_packet(
                data=json.dumps(command),
                target_id=target_agent_id,
                timeout=10000  # 10초 타임아웃
            )
            return True
        except ModemError as e:
            logger.warning(f"Acoustic send failed: {e}")
            return False

    def is_in_range(self, target_position: dict) -> bool:
        """대상이 음향 통신 범위 내인가?"""
        distance = calculate_distance(self.position, target_position)
        return distance <= self.max_range
```

#### RF/Internet (무선 - 수상용)

```python
class RFDriver:
    """RF/WiFi/LTE 통신 드라이버"""

    def send_command(self, command: dict) -> dict:
        """HTTP POST 기반 명령"""
        try:
            response = requests.post(
                url=self.gateway_endpoint,
                json=command,
                timeout=5
            )
            return response.json()
        except requests.exceptions.Timeout:
            raise CommunicationError("RF connection timeout")
```

### 3.2 드라이버 선택 로직 (Dynamic Hand-over)

```python
class CommunicationManager:
    """물리 통신 중재자"""

    def select_medium(self, target_agent_id: str) -> str:
        """
        대상 Agent와의 통신에 최적 매체 선택

        Returns: "WIRED" | "ACOUSTIC" | "RF" | None (불가)
        """

        target = get_agent(target_agent_id)
        my_agent = get_my_agent()

        # Step 1: Gateway 확인 (ROV의 경우)
        if my_agent.gateway_agent_id:
            # ROV는 항상 부모(USV)를 통해서만 통신
            return "WIRED"

        # Step 2: 공통 매체 확인
        common_mediums = set(my_agent.capabilities) & set(target.capabilities)
        if not common_mediums:
            return None  # 통신 불가능

        # Step 3: 환경별 필터
        if my_agent.environment_state == "UNDERWATER":
            # 수중: ACOUSTIC만 가능
            return "ACOUSTIC" if "ACOUSTIC" in common_mediums else None
        else:
            # 수상: 우선순위 순으로 선택
            for preferred in ["RF", "INTERNET", "ACOUSTIC"]:
                if preferred in common_mediums:
                    return preferred

        return None

    def handle_environment_change(self, new_state: str):
        """
        환경 상태 변경 (SURFACE → UNDERWATER)
        Active medium 자동 전환
        """
        old_state = self.environment_state
        self.environment_state = new_state

        if old_state == "SURFACE" and new_state == "UNDERWATER":
            # RF 모듈 Sleep, Acoustic 모듈 활성화
            self.rf_driver.sleep()
            self.acoustic_driver.wake()
            logger.info("Switched to Acoustic mode (underwater)")

            # Registry에 환경 상태 업데이트
            update_agent_environment_state(
                agent_id=self.agent_id,
                environment_state="UNDERWATER",
                active_mediums=["ACOUSTIC"]
            )
```

---

## 5. Heartbeat와 Health Check

### 4.1 Heartbeat 메시지

**주기**: 1초마다 System Agent로 전송

```json
{
  "message_type": "DEVICE_HEARTBEAT",
  "device_id": "aauv-01",
  "timestamp": "2026-05-13T10:30:45.123Z",

  "device_status": {
    "online": true,
    "battery_percent": 75,
    "position": {
      "latitude": 37.5555,
      "longitude": 126.9999
    },
    "depth": 5.2,
    "temperature": 18.3
  },

  "task_status": {
    "current_task_id": "task-123",
    "status": "IN_PROGRESS",
    "progress_percent": 45
  },

  "communication_status": {
    "signal_strength": 85,
    "latency_ms": 120,
    "active_medium": "RF"
  }
}
```

### 4.2 Problem Report (즉각적)

**발생 조건**: 배터리 부족, 센서 오류, 물리적 문제

```python
def send_problem_report(problem_type: str, details: dict):
    """즉각적 문제 보고"""

    report = {
        "message_type": "DEVICE_PROBLEM_REPORT",
        "device_id": self.device_id,
        "timestamp": utc_now_iso(),
        "problem_type": problem_type,  # "LOW_BATTERY", "SENSOR_ERROR", "COLLISION"
        "severity": determine_severity(problem_type),  # "WARNING" | "CRITICAL"
        "details": details
    }

    # System Agent에 즉시 전송
    send_to_system_agent(report)

    # Registry에 Event 기록
    create_event(
        type="SYS_ANOMALY_DETECTED",
        actor_type="DEVICE",
        actor_id=self.device_id,
        severity=report["severity"],
        data=details
    )
```

### 4.3 Heartbeat 타임아웃 처리

**System Agent 관점** (registry 기반 감시):

  - 정상: 10초 내 Heartbeat 수신
  - 10초 이상 미수신 → 장비 오프라인 판단

```python
# System Agent의 monitoring
def check_device_heartbeat(device_id: str):
    device = registry.get_device(device_id)
    last_heartbeat = device.last_seen_at

    if not last_heartbeat:
        # 첫 장비 (등록 후 아직 신호 없음)
        return

    elapsed = utc_now_iso() - last_heartbeat

    if elapsed > 10000:  # 10초
        create_event(
            type="SYS_ANOMALY_DETECTED",
            severity="CRITICAL",
            data={
                "anomaly_type": "HEARTBEAT_TIMEOUT",
                "device_id": device_id,
                "last_seen": last_heartbeat
            }
        )
```

---

## 6. 실행 중 중단 (Mid-Execution Abort)

텔레메트리 루프가 주기적으로 `_check_task_interrupt_conditions()`를 호출하여 실행 중인 태스크의 지속 가능 여부를 감시한다.

### 5.1 중단 조건 감시 루프

```python
async def _check_task_interrupt_conditions(self) -> None:
    """텔레메트리 갱신마다 호출 — 실행 중 태스크의 지속 가능 여부 확인."""
    active = self._active_task  # 현재 실행 중인 태스크
    if active is None:
        return
    if active["is_safe"]:
        return  # return_to_base 등 안전 복귀 명령은 중단하지 않음

    battery = self._battery_percent()
    if battery is not None and battery < BATTERY_THRESHOLD:  # 20%
        await self._abort_active_task(
            reason=f"Battery dropped to {battery:.1f}% during task execution",
            abort_type="BATTERY_INSUFFICIENT",
        )
```

### 5.2 태스크 중단 처리

중단이 결정되면 `_abort_active_task()`가 호출된다:

```python
async def _abort_active_task(self, *, reason: str, abort_type: str) -> None:
    # 1. _active_task 클리어 (중복 트리거 방지)
    active = self._active_task
    self._active_task = None

    # 2. 중단 이력 기록
    self.state.remember({"kind": "task_interrupted", ...})

    # 3. 부모 에이전트에 task.result FAILED 전송 (중단 알림)
    await self._report_task_result_to_parent(
        task_id=active["task_id"],
        mission_id=active["mission_id"],
        status="FAILED",
        error=reason,
        abort_type=abort_type,
    )
```

### 5.3 부모 에이전트로 결과 보고

중단 또는 완료 시 `task.result` A2A 메시지를 부모(`parent_command_endpoint`)로 전송한다.

**중단 보고**:

```json
{
  "message_type": "task.result",
  "task_id": "task-123",
  "mission_id": "mission-456",
  "status": "FAILED",
  "error": "Battery dropped to 18.5% during task execution",
  "abort_type": "BATTERY_INSUFFICIENT",
  "device_id": "42",
  "agent_id": "agent-uuid-xxx",
  "reported_at": "2026-05-20T10:35:30Z"
}
```

**완료 보고**:

```json
{
  "message_type": "task.result",
  "task_id": "task-123",
  "mission_id": "mission-456",
  "status": "COMPLETED",
  "device_id": "42",
  "agent_id": "agent-uuid-xxx",
  "reported_at": "2026-05-20T10:35:30Z"
}
```

### 5.4 통신 단절 시

```python
def handle_communication_loss():
    """System Agent와 통신 불가 상태"""

    if self.mission_is_critical():
        # 중요 미션: 계속 진행 (로컬 판단)
        execute_local_mission_plan()
    else:
        # 일반 미션: 안전 위치 유지 후 복구 대기
        hold_position()

    # 통신 복구 후:
    # - System Agent에 현재 상태 보고
    # - 미처리 Task 확인 및 계속
```

**배터리 상태 보고 타이밍**:
- **정기**: Heartbeat 발송 시 (1초마다) battery_percent 포함
- **즉각 중단**: 배터리 < 20% 도달 시 → task.result FAILED 전송

---

## 7. 환경 상태 감지

### 6.1 SURFACE/UNDERWATER 전환

```python
class EnvironmentMonitor:
    """환경 상태 실시간 감시"""

    def update_environment_state(self):
        """
        정기적으로 (1초마다) 환경 상태 확인
        """

        # 센서 기반 판단
        depth = self.depth_sensor.read()  # 미터

        if depth > SUBMERSION_THRESHOLD:  # e.g., 0.5m
            new_state = "UNDERWATER"
        else:
            new_state = "SURFACE"

        # 상태 변화 감지
        if new_state != self.environment_state:
            self.on_environment_changed(new_state)

    def on_environment_changed(self, new_state: str):
        """환경 상태 변화 처리"""

        old_state = self.environment_state
        self.environment_state = new_state

        # 1. 통신 드라이버 전환
        self.communication_manager.handle_environment_change(new_state)

        # 2. Registry 업데이트
        registry.update_agent(
            agent_id=self.agent_id,
            environment_state=new_state,
            active_mediums=self.get_active_mediums()
        )

        # 3. Event 발행
        create_event(
            type="ENV_STATE_CHANGED",
            actor_type="DEVICE",
            actor_id=self.device_id,
            severity="INFO",
            data={
                "from": old_state,
                "to": new_state,
                "depth": self.depth_sensor.read()
            }
        )

        logger.info(f"Environment changed: {old_state} → {new_state}")
```

### 6.2 Active Mediums 관리

```python
def get_active_mediums(self) -> List[str]:
    """
    현재 사용 가능한 통신 매체

    SURFACE: [RF, INTERNET, ACOUSTIC]
    UNDERWATER: [ACOUSTIC]
    """

    if self.environment_state == "UNDERWATER":
        return ["ACOUSTIC"]
    else:
        # 수상: 신호 강도에 따라 결정
        active = []
        if self.rf_signal_strength > SIGNAL_THRESHOLD:
            active.append("RF")
        if self.internet_available():
            active.append("INTERNET")
        active.append("ACOUSTIC")  # Always available as fallback
        return active
```

---

## 8. A2A 프로토콜 상세

### 7.1 Task 할당 (System Agent → Device Agent)

**요청**:

```json
{
  "message_type": "task.assign",
  "action": "HIGH_RES_SCAN",
  "task_id": "task-123",
  "mission_id": "mission-456",
  "step_id": "step-1",
  "params": {
    "resolution": "high",
    "duration_sec": 300
  },
  "reason": "Mine detection survey"
}
```

**응답 — 수락**:

```json
{
  "status": "OK",
  "acceptance_status": "ACCEPTED",
  "task_id": "task-123",
  "delivered": true
}
```

**응답 — 거절**:

```json
{
  "status": "ABORTED",
  "acceptance_status": "REJECTED",
  "abort_type": "BATTERY_INSUFFICIENT | ALREADY_ASSIGNED | SENSOR_MISSING",
  "task_id": "task-123",
  "reason": "Battery too low: 15.0% (threshold 20%)"
}
```

### 7.2 Task 결과 보고 (Device Agent → System Agent)

**완료**:

```json
{
  "message_type": "task.result",
  "task_id": "task-123",
  "status": "COMPLETED",
  "result": {
    "images_captured": 150,
    "data_size_mb": 2500,
    "duration_sec": 285
  },
  "timestamp": "2026-05-13T10:35:30.123Z"
}
```

**실패**:

```json
{
  "message_type": "task.result",
  "task_id": "task-123",
  "status": "FAILED",
  "error": {
    "type": "SENSOR_ERROR",
    "message": "Camera sensor malfunction",
    "logs": ["2026-05-13T10:35:20Z: Camera init failed", "...]
  },
  "timestamp": "2026-05-13T10:35:30.123Z"
}
```

---

## 9. 설정 가이드

### 8.1 Device Agent 설정 파일 (device-config.yaml)

```yaml
device:
  id: "aauv-01"
  type: "AUV"
  name: "Autonomous Underwater Vehicle 01"
  actions:
    - "MOVE_TO"
    - "HIGH_RES_SCAN"
    - "SONAR_SCAN"
    - "SAMPLE_COLLECTION"

capabilities:
  - "ACOUSTIC"
  - "RF"
  - "INTERNET"

system_agent:
  endpoint:
    host: "192.168.1.100"
    port: 8000
    protocol: "HTTP"
    path: "/api/agent"
  heartbeat_interval_sec: 1
  heartbeat_timeout_sec: 10

physical_constraints:
  battery:
    critical_threshold_percent: 10
    warning_threshold_percent: 30
  depth:
    max_depth_m: 1000
  communication:
    acoustic_range_m: 1000
    acoustic_latency_ms: 500

safety_rules:
  return_to_base_on_battery_critical: true
  hold_position_on_communication_loss: true
  no_go_zones:
    - name: "Shallow reef"
      center: { lat: 37.5555, lon: 126.9999 }
      radius_m: 500
```

---

## 10. 고급 프로세스

### 10.1 Device Agent 종료/정리 (Graceful Shutdown)

Device Agent가 종료될 때의 정리 절차:

```python
class DeviceAgentShutdown:
    """Device Agent 안전한 종료"""

    def shutdown(self):
        """단계별 종료"""
        
        # Step 1: 진행 중인 Task 안전화
        self.abort_in_progress_tasks()
        
        # Step 2: Heartbeat 중단 신호
        self.send_final_heartbeat(status="SHUTTING_DOWN")
        
        # Step 3: 통신 채널 정리
        self.close_device_bridge_connection()
        self.close_telemetry_streams()
        
        # Step 4: 로컬 상태 저장 (재시작 시 복구)
        self.save_runtime_state()
        
        # Step 5: 로그 최종화
        logger.info("Device Agent shutdown complete")
        
    def abort_in_progress_tasks(self):
        """
        IN_PROGRESS 상태의 Task를 ABORTED로 마크하고 
        DeviceBridge에 알림
        """
        for task in self.task_queue.in_progress():
            task.status = "ABORTED"
            task.status_reason = "Device Agent shutting down"
            self.report_task_result(task)
```

**DeviceBridge의 대응**:
- Device Agent의 SHUTTING_DOWN Heartbeat 수신 → Device 상태를 OFFLINE으로 변경
- Task ABORTED 결과 수신 → Event 발행 → System Agent에 알림

---

### 10.2 Heartbeat 실패 처리 & 재시도 (Heartbeat Failure Retry)

DeviceBridge와의 통신이 일시적으로 단절되었을 때의 재시도 알고리즘:

```python
class HeartbeatRetryHandler:
    """Heartbeat 전송 실패 처리"""
    
    RETRY_CONFIG = {
        "initial_interval_sec": 3,
        "max_interval_sec": 60,
        "backoff_multiplier": 1.5,
        "max_retries": 10
    }
    
    def send_heartbeat_with_retry(self):
        """지수 백오프로 재시도"""
        
        retry_count = 0
        interval = self.RETRY_CONFIG["initial_interval_sec"]
        
        while retry_count < self.RETRY_CONFIG["max_retries"]:
            try:
                response = self.send_heartbeat_to_device_bridge()
                if response.status_code == 200:
                    logger.info("Heartbeat sent successfully")
                    return True
            except Exception as e:
                logger.warning(f"Heartbeat failed: {e}")
            
            # 대기 후 재시도
            time.sleep(interval)
            
            # 다음 재시도 간격 계산
            interval = min(
                interval * self.RETRY_CONFIG["backoff_multiplier"],
                self.RETRY_CONFIG["max_interval_sec"]
            )
            retry_count += 1
        
        # 모든 재시도 실패 → Local Safety Failsafe 진입
        logger.critical("Heartbeat retry exhausted. Entering failsafe mode.")
        self.enter_failsafe_mode()
        return False
```

**행동**:
- 1차 실패 → 3초 후 재시도
- 2차 실패 → 4.5초 후 재시도
- 최대 10회 시도 후에도 실패 → Failsafe 진입

---

### 10.3 Task ABORTED 감지 후 System Agent 동작

Device Agent가 Task를 ABORTED로 반환하면 DeviceBridge와 System Agent의 연쇄 동작:

```python
class TaskAbortionHandler:
    """Task ABORTED 처리"""
    
    def handle_task_aborted(self, task):
        """
        Device Agent가 보고한 ABORTED Task 처리
        """
        
        # 1. Event 발행 (System Agent가 구독)
        create_event(
            type="SYS_TASK_ABORTED_BY_DEVICE",
            actor_type="DEVICE",
            actor_id=task.assigned_device_id,
            severity="WARNING",
            target_type="TASK",
            target_id=task.task_id,
            data={
                "mission_id": task.mission_id,
                "reason": task.status_reason,
                "timestamp": utc_now_iso()
            }
        )
        
        # 2. Task 상태 업데이트
        task.status = "ABORTED"
        task.status_updated_at = utc_now_iso()
        task.save()
        
        # 3. MissionPlanner에 통보 → 다음 Task 재협상
        notify_mission_planner_task_aborted(task.mission_id, task)
```

**MissionPlanner의 대응**:
- ABORTED Task를 포함한 Mission 상태 평가
- 다른 Device에 Task를 재할당할 수 있는지 검토
- 재할당 불가능하면 → Mission 전체를 FAILED로 변경

---

### 10.4 Local Safety Failsafe 의사결정

DeviceBridge와의 통신이 단절되었을 때 Device Agent의 자동 행동:

```python
class LocalSafetyFailsafe:
    """로컬 안전 행동 (통신 단절 시)"""
    
    def on_communication_loss(self):
        """
        DeviceBridge와의 통신이 HEARTBEAT_TIMEOUT_SEC 동안 
        없을 때 발동
        """
        
        logger.critical("Communication loss detected. Activating failsafe.")
        
        # Step 1: 진행 중인 Task 판단
        current_task = self.task_queue.current_task()
        
        if current_task:
            # Step 2: Task 성질에 따른 판단
            
            if is_safety_critical_task(current_task):
                # 예: RETURN_TO_BASE, HOLD_POSITION
                self.execute_failsafe_action(current_task.failsafe_action)
            else:
                # 예: 탐사, 센싱 Task
                # → 안전한 위치로 이동 후 대기
                self.move_to_safe_location()
        else:
            # 진행 중인 Task 없음 → 현재 위치 유지
            self.hold_position()
        
        # Step 3: 로컬 로그 기록
        log_failsafe_event()
        
        # Step 4: 통신 복구 대기
        self.wait_for_recovery()
    
    def wait_for_recovery(self):
        """
        DeviceBridge와의 통신 복구 대기 (최대 N분)
        """
        recovery_timeout = 10 * 60  # 10분
        start_time = time.time()
        
        while time.time() - start_time < recovery_timeout:
            if self.test_device_bridge_connection():
                logger.info("Communication restored")
                self.exit_failsafe_mode()
                return
            
            time.sleep(5)  # 5초마다 체크
        
        # 복구 실패 → 자동 종료 (배터리 절감)
        logger.critical("Recovery timeout. Initiating auto-shutdown.")
        self.shutdown()
```

---

### 10.5 Device 간 A2A 통신 장애 처리

Device-Device 간 직접 통신(릴레이, 협력)이 실패했을 때:

```python
class InterDeviceCommunicationFailureHandler:
    """Device 간 통신 장애 처리"""
    
    def handle_peer_communication_failure(self, peer_device_id: str, error: Exception):
        """
        다른 Device와의 A2A 통신 실패
        """
        
        # Step 1: 실패 원인 판단
        if isinstance(error, TimeoutError):
            failure_reason = "TIMEOUT"
        elif isinstance(error, ConnectionRefusedError):
            failure_reason = "UNREACHABLE"
        else:
            failure_reason = "UNKNOWN"
        
        # Step 2: AgentConnection 상태 업데이트
        agent_conn = AgentConnection.get(
            source_agent_id=self.agent_id,
            target_agent_id=peer_device_id
        )
        agent_conn.status = "DEGRADED"
        agent_conn.last_error = failure_reason
        agent_conn.save()
        
        # Step 3: Event 발행
        create_event(
            type="SYS_AGENT_CONNECTION_DEGRADED",
            actor_type="DEVICE",
            actor_id=self.device_id,
            severity="WARNING",
            data={
                "peer_device_id": peer_device_id,
                "failure_reason": failure_reason,
                "timestamp": utc_now_iso()
            }
        )
        
        # Step 4: System Agent에 통보 (DeviceBridge 경유)
        self.report_communication_failure_to_system(peer_device_id, failure_reason)
```

**System Agent의 대응**:
- AgentConnection 재설정 검토
- 다른 경로(다중홉 릴레이) 가능성 검토
- 통신 복구 불가능 → 대체 Device로 Mission 재계획

---

### 10.6 Heartbeat 타임아웃 정책 (SystemSentinel 담당)

SystemSentinel이 Device Agent의 Heartbeat 부재를 감지하여 offline 처리:

**아키텍처**:
- **Device Agent**: Moth MEB을 통해 **1초마다** Heartbeat 발송
- **SystemSentinel**: MEB 구독하여 Heartbeat 수신 → **10초 이상 없으면 offline 처리**

```python
class HeartbeatTimeoutPolicy:
    """Heartbeat 타임아웃 감시 (SystemSentinel)"""
    
    HEARTBEAT_TIMEOUT_SEC = 10  # Device는 1초마다 Heartbeat 발송 (Moth MEB)
                                 # 10초 이상 없으면 offline으로 판정
    
    def monitor_heartbeats(self):
        """
        등록된 모든 Device의 Heartbeat 감시 (SystemSentinel)
        
        Flow:
        1. SystemSentinel이 "agents" MEB 채널을 구독
        2. Device Agent가 1초마다 DEVICE_HEALTHCHECK 이벤트 발행
        3. SystemSentinel이 수신하여 last_heartbeat_at 갱신
        4. 10초 이상 수신 없으면 offline 처리
        """
        
        for device in self.get_all_devices():
            if device.status != "ONLINE":
                continue
            
            last_heartbeat_time = device.last_heartbeat_at
            time_since_last = time.time() - last_heartbeat_time.timestamp()
            
            if time_since_last > self.HEARTBEAT_TIMEOUT_SEC:
                # Step 1: 경고 Event 발행
                create_event(
                    type="SYS_DEVICE_HEARTBEAT_TIMEOUT",
                    severity="WARNING",
                    actor_type="SYSTEM",
                    target_type="DEVICE",
                    target_id=device.device_id,
                    data={
                        "last_heartbeat_time": last_heartbeat_time.isoformat(),
                        "timeout_sec": time_since_last
                    }
                )
                
                # Step 2: Device 상태 업데이트
                device.status = "OFFLINE"
                device.save()
                
                # Step 3: 진행 중인 Task 처리
                self.handle_device_offline_tasks(device.device_id)
```

---

### 10.7 Device Reconnection 프로세스

오프라인 Device가 다시 온라인되었을 때의 재연결 프로세스:

```python
class DeviceReconnectionHandler:
    """Device 재연결 처리"""
    
    def handle_device_reconnection(self, device_id: str):
        """
        Device가 Heartbeat를 다시 보냈을 때
        """
        
        # Step 1: Device 상태 변경
        device = Device.get(device_id)
        was_offline = device.status == "OFFLINE"
        
        device.status = "ONLINE"
        device.last_heartbeat_at = utc_now()
        device.save()
        
        if was_offline:
            # Step 2: Reconnection Event 발행
            create_event(
                type="SYS_DEVICE_RECONNECTED",
                severity="INFO",
                actor_type="SYSTEM",
                target_type="DEVICE",
                target_id=device_id,
                data={"previous_offline_duration_sec": ...}
            )
            
            # Step 3: 오프라인 중 발생한 Task 재평가
            self.reassess_pending_tasks_for_device(device_id)
```

---

### 10.8 Configuration Update 중 상태 일관성

실행 중인 Device Agent의 설정이 변경되었을 때:

```python
class ConfigurationUpdateHandler:
    """설정 변경 처리"""
    
    def on_config_changed(self, changed_fields: dict):
        """
        설정 파일이나 System Registry에서 Device 설정이 변경됨
        예: actions[], capabilities[], safety_rules 등
        """
        
        # Step 1: 현재 Task 상태 확인
        current_task = self.task_queue.current_task()
        
        # Step 2: 변경사항 적용 가능 여부 판단
        if current_task:
            # Task 진행 중 → 설정 변경 미연기, 완료 후 적용
            logger.info("Task in progress. Config update deferred.")
            self.deferred_config_updates = changed_fields
        else:
            # Task 없음 → 즉시 적용
            self.apply_config_updates(changed_fields)
            
            # DeviceBridge에 변경사항 알림
            self.notify_device_bridge_config_changed()
```

---

## 11. 구현 체크리스트

```
[ ] 1. Device Agent 초기화 & 등록
    [ ] 1.1. 설정 파일 로드 (device-config.yaml)
    [ ] 1.2. IdentityStore 확인 (.runtime/{instance_id}.json)
    [ ] 1.3. 캐시된 정보 있으면 재사용
    [ ] 1.4. 없으면 DeviceBridge를 통해 등록
    [ ] 1.5. 등록 응답을 IdentityStore에 저장

[ ] 1.5.1 고급 프로세스
    [ ] 1.5.1.1. Device Agent 종료/정리 프로세스
    [ ] 1.5.1.2. Heartbeat 실패 처리 & 재시도 알고리즘
    [ ] 1.5.1.3. Task ABORTED 감지 후 System 동작
    [ ] 1.5.1.4. Local Safety Failsafe 의사결정
    [ ] 1.5.1.5. Device 간 A2A 통신 장애 처리
    [ ] 1.5.1.6. Heartbeat 타임아웃 정책
    [ ] 1.5.1.7. Device Reconnection 프로세스
    [ ] 1.5.1.8. Configuration Update 중 상태 일관성

[ ] 2. Task 수행 판단 구현
    [ ] 2.1. Capability Check
    [ ] 2.2. Resource Check (배터리, 위치)
    [ ] 2.3. Safety Check (로컬 물리적 제약)
    [ ] 2.4. ABORTED vs FAILED 상태 처리

[ ] 3. 물리 통신 드라이버
    [ ] 3.1. Wired Driver
    [ ] 3.2. Acoustic Driver (음향)
    [ ] 3.3. RF/WiFi/LTE Driver
    [ ] 3.4. 드라이버 선택 로직

    [ ] 4. Heartbeat & Health Check
        [ ] 4.1. 정기 Heartbeat 전송 (1초)
        [ ] 4.2. Problem Report (즉각적)
        [ ] 4.3. 센서 데이터 수집

[ ] 5. Local Safety Behavior
    [ ] 5.1. 배터리 부족 대응
    [ ] 5.2. 통신 단절 대응
    [ ] 5.3. 충돌 감지

[ ] 6. 환경 상태 관리
    [ ] 6.1. SURFACE/UNDERWATER 감지
    [ ] 6.2. Active Medium 동적 전환
    [ ] 6.3. Event 발행

[ ] 7. A2A Protocol 구현
    [ ] 7.1. Task 할당 수신
    [ ] 7.2. Task 결과 보고
    [ ] 7.3. Device-Device 협력 (선택)

[ ] 8. Registry 동기화
    [ ] 8.1. Agent 상태 정기 업데이트
    [ ] 8.2. Task 상태 리포팅
    [ ] 8.3. Environment State 동기화

[ ] 9. 설정 및 배포
    [ ] 9.1. Configuration file 작성
    [ ] 9.2. Logging setup
    [ ] 9.3. Test suite
```

---

## 12. 참고

- [SYSTEM_ARCHITECTURE.md](../SYSTEM_ARCHITECTURE.md) - Device Agent 역할 개요
- [a2a-protocol.md](../core/a2a-protocol.md) - A2A Protocol 규격
- [communication-driver.md](../core/communication-driver.md) - 물리 통신 추상화
- [ADR-009: Physical Communication Routing](../adr/ADR-009-physical-communication-routing.md)
- [schema.md](../core/schema.md) - Task, Agent 데이터 구조
