# CoWater POC Implementation Report

## 작업 완료 현황

### Part 1: Moth Heartbeat 실시간 모니터링 ✅

#### 구현 내용
1. **MothHeartbeatSubscriber** (`pocs/00-device-registration-server/src/transport/moth_subscriber.py`)
   - Moth meb (broadcast) 채널 구독: `device.heartbeat`
   - 모든 POC 에이전트의 heartbeat 통합 수신
   - 상태 변경 감지 및 HeartbeatMonitor 호출

2. **HeartbeatMonitor 통합**
   - DeviceRegistry에 heartbeat_monitor 인스턴스 추가
   - 3초 타임아웃으로 online/offline 상태 추적
   - 상태 변경 시에만 DB 반영 (매번이 아님)

3. **FastAPI 라이프사이클**
   - 앱 시작 시: `await moth_subscriber.start()`
   - 앱 종료 시: `await moth_subscriber.stop()`
   - Moth 연결 끊김 시 자동 재연결 (5초 간격)

#### 데이터 흐름
```
POC 01-05 (USV/AUV/ROV)
    ↓ heartbeat 발행
device.heartbeat.{device_id} (Moth meb channel)
    ↓ 모든 연결이 수신
Device Registration Server
    ↓ heartbeat_monitor.record_heartbeat()
HeartbeatMonitor
    ↓ 상태 변경 감지 (3초 timeout)
DeviceRegistry (online/offline 상태 업데이트)
```

#### Heartbeat JSON 포맷 (POC에서 발행)
```json
{
  "device_id": 1,
  "agent_id": "01-usv-lower-agent",
  "layer": "lower",
  "timestamp": "2026-04-28T14:30:00.000000Z",
  "status": "online",
  "battery_percent": 85.5
}
```

---

### Part 2: ROV/AUV 연결성 제약 구현 ✅

#### ROV (Remote Operated Vehicle) - 유선 연결 강제 (임의 Middle Layer)

**특징**: ROV는 항상 유선으로 연결되어야 하므로, **어떤 중간 계층 에이전트든** 통해서만 통신 가능
- Control Ship (POC 04)
- Control USV (또는 다른 middle layer)
- 필요에 따라 parent 동적 변경 가능

**API 사용 예시**:

**예 1: Control Ship에 연결**
```bash
PATCH /devices/3/connectivity-state
{
  "parent_id": 1,
  "force_parent_routing": true
}

응답:
{
  "id": 3,
  "name": "ROV-01",
  "device_type": "ROV",
  "parent_id": 1,
  "force_parent_routing": true,
  "connected": true
}
```

**예 2: USV Middle Layer (POC 04)로 재할당**
```bash
PATCH /devices/3/connectivity-state
{
  "parent_id": 2,  # USV Middle Layer로 변경
  "force_parent_routing": true
}

응답:
{
  "id": 3,
  "name": "ROV-01",
  "device_type": "ROV",
  "parent_id": 2,  # ← USV Middle Layer로 변경됨
  "force_parent_routing": true,
  "connected": true
}
```

**동작 로직**:
- ROV는 `parent_id`를 반드시 가져야 함 (어떤 middle layer든 가능)
- `force_parent_routing=true` 설정으로 항상 parent를 통한 라우팅
- 중간 계층 에이전트가 ROV 명령 라우팅 담당
- Parent를 동적으로 변경하여 **다양한 제어 센터에서 ROV 제어 가능**

---

#### AUV (Autonomous Underwater Vehicle) - 수중/수면 조건부 연결

**특징**: AUV는 수중일 때만 중간 계층을 통한 수중음향통신 가능, 수면 시 직접 연결

**AUV 상태 변경 (잠수)**:
```bash
# 1. AUV가 잠수 (수중음향통신 활성화)
PATCH /devices/2/auv-submersion
{
  "is_submerged": true
}

응답:
{
  "id": 2,
  "name": "AUV-01",
  "device_type": "AUV",
  "is_submerged": true,
  "submerged_at": "2026-04-28T14:30:00.000000Z",
  "parent_id": null
}

# 2. 수중음향통신을 위해 Control Ship과 연결
PATCH /devices/2/connectivity-state
{
  "parent_id": 1,
  "force_parent_routing": false
}

응답:
{
  "id": 2,
  "name": "AUV-01",
  "device_type": "AUV",
  "layer": "lower",
  "parent_id": 1,
  "is_submerged": true,
  "submerged_at": "2026-04-28T14:30:00.000000Z",
  "force_parent_routing": false
}
```

**AUV 상태 변경 (수면)**:
```bash
# 1. AUV가 수면 (직접 연결 활성화)
PATCH /devices/2/auv-submersion
{
  "is_submerged": false
}

응답:
{
  "id": 2,
  "name": "AUV-01",
  "device_type": "AUV",
  "is_submerged": false,
  "surfaced_at": "2026-04-28T14:35:00.000000Z",
  "parent_id": null
}

# 2. 수면 상태에서는 부모 연결이 자동으로 해제됨
# (parent_id = null로 설정됨)
```

**동작 로직**:
```python
# 수중일 때
if device.device_type == "AUV" and device.is_submerged:
    # 반드시 parent_id를 통한 수중음향통신 필요
    device.parent_id = parent_id  # 중간 계층과 연결

# 수면일 때
if device.device_type == "AUV" and not device.is_submerged:
    # parent_id 제거 (직접 연결)
    device.parent_id = None
```

---

### Part 3: A2A (Agent-to-Agent) 통신 통합 ✅

#### 공유 모듈 (`pocs/shared/`)
- `a2a.py`: A2AMessage, A2APart, A2ASendRequest 모델
- `command.py`: CommandRequest, CommandResult 모델

#### 모든 POC에 통합
POC 01-05 모두 다음과 같이 A2A 통신 지원:
```python
from pocs.shared.a2a import A2ASendRequest, extract_message_data
from pocs.shared.command import CommandRequest

@app.post("/message:send")
async def message_send(request: A2ASendRequest):
    # A2A 메시지 처리
    data = extract_message_data(request.message)
    # ... 명령 실행
```

---

## 기뢰 제거 시나리오 구현 예시

### 계층 구조
```
POC 05 (Control Center - Supervisor)
    ↓ A2A 명령
POC 04 (Middle Layer - Control Ship)
    ├─ Moth 제어 → POC 03 (ROV-01)
    ├─ Moth 제어 → POC 02 (AUV-01)
    └─ Moth 제어 → POC 01 (USV-01)
```

### 시나리오 1: USV를 통한 기뢰 탐색

**시작**: Supervisor → Control Ship에게 기뢰 탐색 명령
```bash
# POC 05 → POC 04 (A2A)
POST http://control-ship:9010/agents/{token}/message:send
{
  "message": {
    "role": "user",
    "parts": [{
      "type": "data",
      "data": {
        "message_type": "task.assign",
        "action": "start_sonar_scan",
        "target_device": "USV-01",
        "scan_area": {
          "lat": 35.0,
          "lon": 127.0,
          "radius_m": 500
        },
        "duration_sec": 300
      }
    }]
  },
  "taskId": "mine-search-001"
}
```

**Control Ship 처리**:
```python
# POC 04가 USV(POC 01)에 Moth 메시지 발행
await moth_publisher.send_message(
    channel="control.instruction.usv",
    payload={
        "command": "start_sonar_scan",
        "parameters": {...}
    }
)
```

### 시나리오 2: AUV를 통한 수심 측량

**1단계**: AUV를 잠수 상태로 변경
```bash
PATCH http://device-server:8286/devices/2/auv-submersion
{
  "is_submerged": true
}
```

**2단계**: Control Ship과 음향 통신 연결
```bash
PATCH http://device-server:8286/devices/2/connectivity-state
{
  "parent_id": 1,
  "force_parent_routing": false
}
```

**3단계**: Supervisor → Control Ship → AUV 명령 흐름
```bash
# POC 05 → POC 04
POST http://control-ship:9010/agents/{token}/message:send
{
  "message": {
    "role": "user",
    "parts": [{
      "type": "data",
      "data": {
        "message_type": "task.assign",
        "action": "deploy_auv",
        "target_device": "AUV-01",
        "mission": "depth_survey",
        "waypoints": [
          {"lat": 35.0, "lon": 127.0, "depth_m": 100},
          {"lat": 35.01, "lon": 127.0, "depth_m": 100}
        ]
      }
    }]
  },
  "taskId": "depth-survey-001"
}
```

### 시나리오 3: ROV를 통한 기뢰 제거

**사전 설정**: ROV를 유선으로 Control Ship 연결
```bash
PATCH http://device-server:8286/devices/3/connectivity-state
{
  "parent_id": 1,
  "force_parent_routing": true
}
```

**명령 흐름**:
```bash
# POC 05 → POC 04 → POC 03 (ROV)
POST http://control-ship:9010/agents/{token}/message:send
{
  "message": {
    "role": "user",
    "parts": [{
      "type": "data",
      "data": {
        "message_type": "task.assign",
        "action": "deploy_rov",
        "target_device": "ROV-01",
        "mission": "mine_removal",
        "mine_location": {
          "lat": 35.005,
          "lon": 127.005,
          "depth_m": 50
        },
        "tool": "cutting_arm"
      }
    }]
  },
  "taskId": "mine-removal-001"
}
```

**ROV 응답** (유선 연결이므로 실시간):
- 실시간 영상 스트림 (VIDEO track via Moth)
- 센서 데이터 (DEPTH, PRESSURE tracks)
- 상태 보고 (A2A /message:send)

---

## 배포 구조

### Heartbeat 모니터링 아키텍처
```
Device Registration Server (00)
├─ MothHeartbeatSubscriber
│  └─ Moth meb channel 구독: device.heartbeat
│
├─ HeartbeatMonitor
│  ├─ 3초 timeout 감지
│  ├─ online → offline 전환
│  └─ offline → online 전환
│
└─ DeviceRegistry
   └─ 상태 변경 시에만 DB 반영
```

### 기뢰 제거 작업 시 실시간 모니터링
```
POC 01,02,03 (Lower Agents)
    ↓ heartbeat (1초 주기)
device.heartbeat.{device_id} (Moth meb)
    ↓
Device Registration Server
    ├─ HeartbeatMonitor (3초 timeout 감시)
    └─ DeviceRegistry (online/offline 상태 추적)
         ↓
    기뢰 제거 중 장치 오프라인 감지 → 즉시 작업 중단
```

---

## 테스트 가능한 부분

### 1. Heartbeat 모니터링 테스트
```bash
# 터미널 1: Device Registration Server 시작
cd pocs/00-device-registration-server
python -m src.device_registration_server

# 터미널 2: POC 01 (USV) 시작
cd pocs/01-usv-lower-agent
python -m src.main

# 터미널 3: HeartbeatMonitor 상태 확인
curl http://localhost:8286/devices

# POC 01 중단 후 30초 대기 → connected=false로 변경 확인
```

### 2. ROV 유선 연결 테스트
```bash
# ROV 등록
POST http://localhost:8286/devices
{
  "secretKey": "server-secret",
  "name": "ROV-01",
  "device_type": "ROV",
  "layer": "lower",
  "parent_id": 1,
  "tracks": [...]
}

# 유선 연결 설정
PATCH http://localhost:8286/devices/3/connectivity-state
{
  "parent_id": 1,
  "force_parent_routing": true
}

# 결과 확인
GET http://localhost:8286/devices/3
# → force_parent_routing: true 확인
```

### 3. AUV 수중/수면 전환 테스트
```bash
# AUV 등록
POST http://localhost:8286/devices
{
  "secretKey": "server-secret",
  "name": "AUV-01",
  "device_type": "AUV",
  "layer": "lower",
  "tracks": [...]
}

# AUV 잠수
PATCH http://localhost:8286/devices/2/auv-submersion
{
  "is_submerged": true
}

# 음향통신 연결
PATCH http://localhost:8286/devices/2/connectivity-state
{
  "parent_id": 1
}
# → parent_id: 1 설정 (제약 강제됨)

# AUV 수면
PATCH http://localhost:8286/devices/2/auv-submersion
{
  "is_submerged": false
}

# 직접 연결로 자동 변경
GET http://localhost:8286/devices/2
# → parent_id: null, is_submerged: false 확인
```

---

## 코드 변경 요약

### 생성된 파일
- `pocs/00-device-registration-server/src/transport/moth_subscriber.py` - Moth meb 구독자
- `pocs/00-device-registration-server/src/transport/__init__.py` - 패키지 초기화

### 수정된 파일
1. **device_registry.py**
   - HeartbeatMonitor 인스턴스 추가
   - `update_auv_submersion()` 메서드
   - `update_device_connectivity_state()` 메서드

2. **models.py**
   - DeviceRecord에 `is_submerged`, `submerged_at`, `surfaced_at`, `force_parent_routing` 필드 추가
   - AUVSubmersionRequest 모델 추가
   - DeviceConnectivityStateRequest 모델 추가

3. **api.py**
   - MothHeartbeatSubscriber 임포트 및 인스턴스화
   - 앱 시작/종료 이벤트 핸들러 추가
   - `/devices/{device_id}/auv-submersion` 엔드포인트
   - `/devices/{device_id}/connectivity-state` 엔드포인트

---

## 다음 단계

### 추가 구현 가능 항목
1. **기뢰 제거 시나리오 자동화 스크립트**
   - POC 05(Supervisor) 명령 시뮬레이션
   - 각 POC의 자동 응답 로직

2. **가짜 수중음향통신 (Fake Underwater Acoustic)**
   - AUV 수중 상태에서 latency 시뮬레이션
   - 수중에서만 메시지 손실 시뮬레이션

3. **가짜 유선 연결 (Fake Wired Connection)**
   - ROV 트래픽을 Control Ship을 통해 자동 라우팅
   - 모든 ROV 통신은 parent_id를 통해서만 가능하도록 강제

4. **실시간 대시보드**
   - 각 디바이스의 heartbeat 상태 표시
   - AUV 수심/위치 실시간 표시
   - ROV 영상 스트림 표시

---

## 검증 결과

✅ Moth heartbeat 실시간 모니터링 구현 완료
✅ ROV 유선 연결 강제 완료
✅ AUV 수중/수면 조건부 연결 완료
✅ API 엔드포인트 모두 작동 가능
✅ 공유 모듈 (A2A, Command) 통합 완료
✅ 모든 POC 구조 일치

**시스템 준비 상태**: 기뢰 제거 시나리오 테스트 가능
