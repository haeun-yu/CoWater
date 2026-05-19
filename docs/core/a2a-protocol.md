# A2A 프로토콜 명세

**문서 버전**: 1.0  
**목적**: Device Agent와 System Agent 간의 동기식 메시지 통신 정의

---

## 1. 프로토콜 개요

### 1.1 기본 설계

- **기반**: Google A2A 프로토콜 기반, JSON-RPC 확장
- **전송**: HTTP POST (JSON)
- **비동기**: Device Agent가 메시지 수신 후 비동기로 실행, 결과는 별도 POST로 보고
- **인증**: metadata에 sender_id, sender_device_id 포함
- **신뢰성**: contextId를 통한 멱등성(idempotent) 보장

### 1.2 엔드포인트 & 포트

| 에이전트 | 포트 | 엔드포인트 | 용도 |
|---------|------|-----------|------|
| **DeviceBridge** | 9110 | `POST /message:send` | Device로부터 메시지 수신, Device에 메시지 전달 |
| **Device Agent** | 9201~9215 | `POST /message:send` | System/다른 Device로부터 메시지 수신 |

### 1.3 Device 설정 (DeviceBridge 정보만 필요)

**핵심 원칙**: Device Agent는 **DeviceBridge 연결 정보만 소유**, Registry나 다른 System Agent 정보는 불필요

**Device 설정 파일** (`device/configs/a2a.yaml`):
```yaml
device:
  device_id: "AUV-01"
  agent_id: "auv-01-agent"

device_bridge:
  host: "127.0.0.1"
  port: 9110

capabilities:
  - scan_area
  - remove_mine
  - hold_position
  - return_to_base
```

---

## 2. 메시지 구조

### 2.1 Pydantic 모델

모든 A2A 메시지는 다음 구조를 따름:

```python
from pydantic import BaseModel

class A2APart(BaseModel):
    """메시지 본문 한 부분"""
    type: str  # "data", "text" 등
    data: dict | str | bytes

class A2AMessage(BaseModel):
    """A2A 프로토콜 메시지"""
    role: str  # "user" (sender) 또는 "assistant" (receiver)
    parts: list[A2APart]

class A2ASendRequest(BaseModel):
    """A2A 송신 요청"""
    message: A2AMessage
    metadata: dict = {
        "sender_id": str,           # 송신자 에이전트 ID
        "sender_device_id": str,    # 송신자 Device ID (optional)
        "contextId": str,           # 멱등성 키 (24시간 TTL)
        "timestamp": int,           # Unix timestamp (ms)
        "urgent": bool = False
    }
```

### 2.2 메시지 타입 (message_type)

모든 메시지는 `parts[0].data.message_type` 필드로 분류:

| message_type | 방향 | 설명 | 예시 |
|--------------|------|------|------|
| **task.assign** | System → Device | Task 할당 | `{"task_id": "task-001", "action": "scan_area", "params": {...}}` |
| **task.result** | Device → System | Task 실행 결과 | `{"task_id": "task-001", "status": "COMPLETED", "result": {...}}` |
| **event.report** | Device → System | Device에서 감지한 이벤트 보고 | `{"event_type": "SENSOR_FAILURE", "severity": "CRITICAL", "device_id": "AUV-01"}` |
| **mission.result** | System → Device | Mission 완료/취소 결과 보고 | `{"mission_id": "mission-001", "status": "COMPLETED"}` |
| **child.register** | Device → Parent | 자신을 부모로 등록 요청 | `{"device_id": "ROV-01", "parent_id": "USV-01"}` |
| **layer.assignment** | System → Device | 계층 정보 할당 | `{"parent_gateway": {"id": "USV-01", "port": 9201}, "layer": 2}` |

---

## 3. 메시지 흐름

### 3.1 Task 할당 & 실행

```
System Agent (DeviceBridge:9110)
    │
    ├─ HTTP POST Device:9201/message:send
    │   └─ message_type: task.assign
    │
Device Agent (9201)
    │
    ├─ 즉시 200 OK 응답
    │
    └─ (비동기) Task 실행 후 결과 전송
        │
        └─ HTTP POST DeviceBridge:9110/message:send
            └─ message_type: task.result
```

---

## 4. 요청/응답 패턴

### 4.1 Task 할당 요청 예시

```bash
curl -X POST http://127.0.0.1:9110/message:send \
  -H 'Content-Type: application/json' \
  -d '{
    "message": {
      "role": "user",
      "parts": [
        {
          "type": "data",
          "data": {
            "message_type": "task.assign",
            "task_id": "task-001",
            "action": "scan_area",
            "params": {
              "target_lat": 37.2808,
              "target_lon": 127.0091,
              "radius_m": 100,
              "timeout_s": 3600
            }
          }
        }
      ]
    },
    "metadata": {
      "sender_id": "device-bridge-agent",
      "sender_device_id": "system",
      "contextId": "ctx-20260513-001",
      "timestamp": 1715592000000,
      "urgent": false
    }
  }'
```

### 4.2 Task 결과 응답 예시

```bash
curl -X POST http://127.0.0.1:9110/message:send \
  -H 'Content-Type: application/json' \
  -d '{
    "message": {
      "role": "assistant",
      "parts": [
        {
          "type": "data",
          "data": {
            "message_type": "task.result",
            "task_id": "task-001",
            "status": "COMPLETED",
            "result": {
              "scanned_area_m2": 31400,
              "scan_time_s": 1823,
              "mine_count": 3,
              "mine_locations": [
                {"lat": 37.2810, "lon": 127.0095},
                {"lat": 37.2805, "lon": 127.0088},
                {"lat": 37.2812, "lon": 127.0092}
              ]
            }
          }
        }
      ]
    },
    "metadata": {
      "sender_id": "auv-01-agent",
      "sender_device_id": "AUV-01",
      "contextId": "ctx-20260513-001",
      "timestamp": 1715592300000
    }
  }'
```

### 4.3 Event 보고 예시

```bash
curl -X POST http://127.0.0.1:9110/message:send \
  -H 'Content-Type: application/json' \
  -d '{
    "message": {
      "role": "assistant",
      "parts": [
        {
          "type": "data",
          "data": {
            "message_type": "event.report",
            "event_type": "SENSOR_FAILURE",
            "severity": "CRITICAL",
            "device_id": "AUV-01",
            "description": "Sonar sensor not responding",
            "timestamp": 1715592400000
          }
        }
      ]
    },
    "metadata": {
      "sender_id": "auv-01-agent",
      "sender_device_id": "AUV-01",
      "contextId": "ctx-20260513-002",
      "timestamp": 1715592400000
    }
  }'
```

### 4.4 Mission 결과 예시

```bash
curl -X POST http://127.0.0.1:9201/message:send \
  -H 'Content-Type: application/json' \
  -d '{
    "message": {
      "role": "user",
      "parts": [
        {
          "type": "data",
          "data": {
            "message_type": "mission.result",
            "mission_id": "mission-001",
            "status": "COMPLETED",
            "summary": "Mission completed successfully",
            "completion_time_s": 3600
          }
        }
      ]
    },
    "metadata": {
      "sender_id": "device-bridge-agent",
      "sender_device_id": "system",
      "contextId": "ctx-20260513-003",
      "timestamp": 1715592500000
    }
  }'
```

---

## 5. 검증 & 에러 처리

### 5.1 HTTP 응답 코드

| 상태 | 코드 | 설명 |
|------|------|------|
| **성공** | 200 | 메시지 수신 완료 (비동기 처리 시작) |
| **요청 오류** | 400 | 메시지 형식 오류 (Pydantic 검증 실패) |
| **인증 오류** | 401 | 송신자 미승인 |
| **검증 실패** | 422 | 메시지 내용 유효성 실패 (예: 미지원 action) |
| **서버 오류** | 500 | 내부 서버 오류 |

### 5.2 검증 로직

```python
# Device Agent 수신 시 검증

SUPPORTED_MESSAGE_TYPES = {
    "task.assign",      # System → Device: Task 할당
    "task.result",      # Device → System: Task 결과
    "event.report",     # Device → System: 이벤트 보고
    "mission.result",   # System → Device: Mission 결과
    "child.register",   # Device → Parent: 자식 등록
    "layer.assignment"  # System → Device: 계층 정보
}

async def handle_message_send(request: A2ASendRequest):
    # 1. Pydantic 검증 (자동)
    # 2. 송신자 검증
    if not is_authorized(request.metadata.sender_id):
        return 401, "Unauthorized sender"
    
    # 3. contextId 중복 확인 (멱등성)
    if await taskstore.exists(request.metadata.contextId):
        return 200, "Already processed"  # 재전송 무시
    
    # 4. message_type 지원 확인
    msg_type = request.message.parts[0].data.get("message_type")
    if msg_type not in SUPPORTED_MESSAGE_TYPES:
        return 422, f"Unsupported message_type: {msg_type}"
    
    # 5. message_type별 추가 검증
    if msg_type == "task.assign":
        action = request.message.parts[0].data.get("action")
        if action not in self.device.capabilities:
            return 422, f"Device does not support: {action}"
    
    elif msg_type == "event.report":
        event_type = request.message.parts[0].data.get("event_type")
        if not event_type:
            return 422, "event_type required for event.report"
    
    elif msg_type == "child.register":
        child_device_id = request.message.parts[0].data.get("device_id")
        if not child_device_id:
            return 422, "device_id required for child.register"
    
    # 6. 즉시 200 OK 응답, 비동기 처리 시작
    asyncio.create_task(process_message_async(request))
    return 200, "Message received"
```

---

## 6. Device 간 Peer-to-Peer A2A 통신

Device-to-Device 직접 통신도 A2A 프로토콜을 사용합니다.

**핵심**: Device 간 통신은 **계층 구조가 아니라 협력 관계**입니다. 
- Device A와 Device B는 대등한 관계
- 물리적 제약(USV가 ROV를 수중으로 운반)은 있지만, A2A 통신상 부모-자식 관계가 아님
- 데이터 공유, 상태 조회, 협력 요청 등으로 상호작용

### 6.1 Peer-to-Peer 직접 통신

```
Device A (9201) [예: USV]
    │
    └─ HTTP POST Device B:9202/message:send
        └─ message_type: task.result | event.report | data.share 등
           (어떤 메시지 타입이든 사용 가능)

Device B (9202) [예: ROV]
    │
    ├─ 메시지 수신
    ├─ 처리 또는 필요시 다른 Device로 전달
    │
    └─ (비동기) 결과 또는 상태 보고
        └─ HTTP POST Device A:9201/message:send
```

**경로 결정**: 
- SystemSentinel이 AgentConnection 정보를 기반으로 통신 가능한 Device들을 파악
- BFS 알고리즘으로 최적 경로 계산
- 각 Device는 자신이 처리할 수 없는 메시지를 다음 Device로 전달 가능 (multi-hop)

---

## 7. 동시 Task 처리

### 7.1 Device의 Task 제한

Device Agent는 동시에 하나의 Task만 처리 가능:

```python
async def handle_task_assign(task: Task):
    if self.current_task_id is not None:
        # 이미 Task 처리 중
        return {
            "status": "REJECTED",
            "reason": "already_assigned",
            "current_task_id": self.current_task_id,
            "estimated_completion_time": self.get_completion_time()
        }
    
    # 새 Task 처리 시작
    self.current_task_id = task.task_id
    asyncio.create_task(execute_task(task))
    return {"status": "ACCEPTED"}
```

---

## 8. 통신 경로: System-Bridge vs Device-to-Device

### 8.1 System ↔ Device 통신 (DeviceBridge 경유)

- **참여자**: System Agent ↔ DeviceBridge ↔ Device Agent
- **경로**: System Agent (포트 9110) ↔ DeviceBridge (9110) ↔ Device (9201~9215)
- **메시지 타입**: task.assign, task.result, event.report, mission.result 등
- **목적**: 
  - 중앙 감시 (System이 모든 Task/Event를 추적)
  - 이벤트 기록 (모든 통신을 Registry에 로깅)
  - 안전성 (System의 명령이 Device에 정확히 전달되는지 보증)

### 8.2 Device ↔ Device 통신 (Peer-to-Peer, Direct)

- **참여자**: Device Agent ↔ Device Agent (대등 관계)
- **경로**: Device A (9201) → Device B (9202) → ... → Target Device (multi-hop 가능)
- **메시지 타입**: 모든 메시지 타입 가능 (task.assign, event.report, data.share 등)
- **목적**:
  - Device 간 협력 (데이터 공유, 상태 조회)
  - 낮은 latency (System을 거치지 않아 빠름)
  - 자율적 협업 (System의 승인 없이 Device끼리 소통 가능)
- **제약**:
  - 물리적 연결이 있어야 함 (AgentConnection이 정의된 Device들끼리만 통신 가능)

---

## 9. 기존 구현과의 호환성

- **기존 코드**: `device/controller/a2a.py`, `device/agent/message_router.py` 사용
- **메시지 타입**: `task.assign`, `task.result`, `child.register`, `layer.assignment`
- **Mission 완료 판단**: 별도 `mission.result` 없이 System Agent가 `task.result`들을 집계해 Mission 완료를 계산
- **변경 없음**: 기존 `task.assign`, `task.result` 구현 재사용

---

**관련 문서**:
- [Port Mapping](./ports.md)
- [Event Types](./event-types.md)
- [System Agent 설계](../SYSTEM_AGENT_DESIGN.md)
