# A2A Protocol Specification (Agent-to-Agent Communication)

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
| **mission.result** | Device → System | Mission 완료 보고 | `{"mission_id": "m-001", "status": "COMPLETED"}` |
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
    
    # 5. action 지원 확인 (Device가 지원하지 않는 action)
    action = request.message.parts[0].data.get("action")
    if action not in self.device.capabilities:
        return 422, f"Device does not support: {action}"
    
    # 6. 즉시 200 OK 응답, 비동기 처리 시작
    asyncio.create_task(process_message_async(request))
    return 200, "Message received"
```

---

## 6. Device 간 직접 A2A 통신 (Relay)

Device-to-Device 직접 통신도 A2A 프로토콜을 사용:

### 6.1 직접 통신

```
Device A (9201)
    │
    └─ HTTP POST Device B:9202/message:send
        └─ message_type: task.result (relay)

Device B (9202)
    │
    ├─ 메시지 수신
    │
    └─ 목적지가 자신이 아니면 다음 Device로 relay
```

### 6.2 경로 결정 (BFS 알고리즘)

multi-hop relay 경로는 SystemSentinel이 AgentConnection을 기반으로 BFS로 계산하고 MEB로 경로 정보 배포.

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

## 8. Relay와 Direct 통신 구분

### 8.1 Relay (DeviceBridge를 거침)

- **경우**: System Agent ↔ Device
- **경로**: System Agent → DeviceBridge (9110) → Device (9201)
- **목적**: 중앙 감시 & 이벤트 기록

### 8.2 Direct A2A (Device 간 직접)

- **경우**: Device A ↔ Device B (multi-hop)
- **경로**: Device A (9201) → Device B (9202) → ... → Target Device
- **목적**: 신속한 Device 협력, Network latency 최소화

---

## 9. 기존 구현과의 호환성

- **기존 코드**: `device/controller/a2a.py`, `device/agent/message_router.py` 사용
- **메시지 타입**: `task.assign`, `task.result`, `mission.result`, `child.register`, `layer.assignment`
- **변경 없음**: 기존 `task.assign`, `task.result` 구현 재사용

---

**관련 문서**:
- [Port Mapping](./ports.md)
- [Event Types](./event-types.md)
- [System Agent 설계](../SYSTEM_AGENT_DESIGN.md)
