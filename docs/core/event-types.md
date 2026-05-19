# Agent 간 통신 및 이벤트 기록

**문서 버전**: 3.0  
**최종 결정**: A2A (Agent-to-Agent) 동기 통신 + Event (사건 기록) + AgentLog (상세 실행 기록)

---

## 1. A2A (Agent-to-Agent) 동기 통신

### 1.1 구조

Agent는 **HTTP REST API**로 다른 Agent의 `/execute-role` 엔드포인트를 **직접 호출**:

```
RequestHandler (port 9116)
  ├─ A2A POST to MissionPlanner (port 9111): /execute-role
  ├─ A2A POST to DeviceBridge (port 9110): /execute-role
  ├─ A2A POST to PolicyManager (port 9112): /execute-role
  ├─ A2A POST to SystemSentinel (port 9113): /execute-role
  └─ A2A POST to InsightReporter (port 9114): /execute-role
```

### 1.2 A2A 요청/응답 흐름

```python
# RequestHandler가 MissionPlanner에 요청
payload = {
    "request_id": "req-uuid",  # 추적용
    "goal": user_input,
    "location": {...}
}

try:
    # Timeout: 300초 (5분, LLM 응답 시간 고려)
    result = await asyncio.wait_for(
        asyncio.to_thread(
            self._call_system_agent_sync,
            port=9111,  # MissionPlanner
            payload=payload
        ),
        timeout=300.0
    )
    
    # 응답 처리
    proposal = self._unwrap_agent_response(result)
    return self._response_envelope(
        status="ok",
        response=proposal
    )
    
except asyncio.TimeoutError:
    # Timeout 발생
    return self._response_envelope(
        status="needs_clarification",
        response={"summary": "MissionPlanner 응답 시간 초과 (5분)"}
    )
```

**특징**:
- ✅ **동기**: Agent A가 Agent B의 응답을 기다림
- ✅ **직접**: HTTP 호출, 중간 큐/버퍼 없음
- ✅ **추적**: request_id로 요청 추적 가능
- ✅ **안전**: Timeout 300초 설정 (LLM 느림 고려)
- ✅ **명확**: 성공/실패를 즉시 알 수 있음

---

## 2. Event와 AgentLog: 기록 체계

### 2.1 설계 원칙

- **Event**: "무엇이 일어났는가" (사건 자체만, 간결함)
- **AgentLog**: "어떻게 일어났는가" (Agent의 판단과 행동 상세)
- **context_id**: 두 테이블을 연결하는 흐름 ID (같은 사용자 명령, 같은 이상징후 등)

```
사용자 명령 (context_id: ctx-123)
  ├─ Event: USER_COMMAND_RECEIVED (context_id: ctx-123)
  ├─ AgentLog: RequestHandler 의도 분류 (context_id: ctx-123)
  ├─ AgentLog: RequestHandler → MissionPlanner A2A 호출 (context_id: ctx-123)
  ├─ AgentLog: MissionPlanner 수신 및 proposal 생성 (context_id: ctx-123)
  └─ AgentLog: MissionPlanner → RequestHandler 응답 (context_id: ctx-123)
```

### 2.2 Event 발행 시점

**주요 사건이 일어날 때마다 Event 발행** (한 번만):

1. **USER_COMMAND_RECEIVED**: 사용자 명령 수신 (RequestHandler)
2. **SYS_ANOMALY_DETECTED**: 이상징후 감지 (SystemSentinel)  
3. **SYS_POLICY_DECISION**: 정책 결정 완료 (PolicyManager)
4. **SYSTEM_ALERT**: 시스템 알림 필요 시
5. **MISSION_CREATED**: Mission 생성됨 (MissionPlanner)
6. **TASK_ASSIGNED**: Task Device에 할당됨 (DeviceBridge)
7. **TASK_COMPLETED / TASK_FAILED**: Task 완료/실패 (DeviceBridge)

각 Event 발행 시 context_id 포함 → 나중에 AgentLog와 함께 조회 가능

### 2.3 AgentLog 기록 시점

**각 Agent의 행동마다 상세 기록**:

```python
# 예: 사용자 명령 받음 (Event 한 번만)
context_id = f"ctx-{uuid4()}"
self.registry_client.ingest_event({
    "event_type": "USER_COMMAND_RECEIVED",
    "context_id": context_id,
    "actor_type": "USER",
    "actor_id": user_id,
    "severity": "INFO",
    "data": {
        "command": user_input,
        "timestamp": utc_now()
    }
})

# 이후 Agent들의 상세 행동은 AgentLog에 기록
# RequestHandler의 의도 분류
self.registry_client.ingest_agent_log({
    "context_id": context_id,
    "agent_id": self.state.agent_id,
    "agent_role": "REQUEST_HANDLER",
    "action": "classify_intent",
    "input": user_input,
    "output": { "intent": "MISSION", "goal": "..." },
    "reasoning": { "confidence": 0.95, "keywords": ["미션", "실행"] },
    "status": "SUCCESS"
})

# RequestHandler의 A2A 호출
self.registry_client.ingest_agent_log({
    "context_id": context_id,
    "agent_id": self.state.agent_id,
    "agent_role": "REQUEST_HANDLER",
    "action": "call_mission_planner_a2a",
    "input": { "goal": "...", "location": {...} },
    "output": { "proposal_id": "prop-456", "status": "ok" },
    "status": "SUCCESS",
    "duration_ms": 1234
})

# MissionPlanner의 proposal 생성
self.registry_client.ingest_agent_log({
    "context_id": context_id,
    "agent_id": mission_planner_id,
    "agent_role": "MISSION_PLANNER",
    "action": "generate_proposal",
    "input": { "goal": "..." },
    "output": { "proposal": {...}, "task_count": 5 },
    "reasoning": { 
        "llm_reasoning": "사용자의 요청을 분석한 결과...",
        "strategy": "순차 실행 전략 선택"
    },
    "status": "SUCCESS",
    "duration_ms": 5678
})
```

### 2.3 Event와 AgentLog 스키마

schema.md의 **Event** 및 **AgentLog** 섹션 참고:

**Event 필드**:

| 필드 | 용도 | 예 |
|------|------|-----|
| `event_type` | 무슨 일이 일어났는가 | `USER_COMMAND_RECEIVED`, `SYS_ANOMALY_DETECTED` |
| `context_id` | 이 Event와 관련된 흐름 ID | `ctx-123` |
| `actor_type/actor_id` | 누가 이 Event를 발행했는가 | `SYSTEM / mission-planner` |
| `target_type/target_id` | 무엇에 대한 Event인가 | `MISSION / mission-uuid` |
| `severity` | 심각도 | `INFO`, `WARNING`, `CRITICAL` |
| `data` | 사건의 상세 정보 | `{"command": "...", "user_id": "..."}` |

**AgentLog 필드**:

| 필드 | 용도 | 예 |
|------|------|-----|
| `context_id` | Event와 같은 흐름 ID | `ctx-123` |
| `agent_role` | 어떤 Agent의 로그인가 | `REQUEST_HANDLER`, `MISSION_PLANNER` |
| `action` | Agent가 수행한 행동 | `classify_intent`, `generate_proposal` |
| `input/output` | 입출력 데이터 | `{"goal": "..."}` / `{"proposal": {...}}` |
| `reasoning` | Agent의 판단 과정 (왜?) | `{"confidence": 0.95, "llm_reasoning": "..."}` |
| `status` | 성공/실패/타임아웃 | `SUCCESS`, `FAILED`, `TIMEOUT` |
| `duration_ms` | 실행 시간 | `1234` |

### 2.4 Event + AgentLog 조회: 전체 흐름 추적

```python
# 사용자 명령 "ctx-123"의 전체 흐름 조회
event = registry_client.get_event(filters={"context_id": "ctx-123"})
logs = registry_client.list_agent_logs(filters={"context_id": "ctx-123"})

# Event 결과: 사건 1개
# {
#   "id": "ev-1",
#   "event_type": "USER_COMMAND_RECEIVED",
#   "context_id": "ctx-123",
#   "data": { "command": "미션 실행해줘", ... }
# }

# AgentLog 결과: 상세 기록들 (시간 순서)
# 1. RequestHandler의 의도 분류
#    { action: "classify_intent", input: "미션 실행해줘", output: {...}, reasoning: {...} }
# 2. RequestHandler의 A2A 호출
#    { action: "call_mission_planner_a2a", input: {...}, output: {...}, duration_ms: 1234 }
# 3. MissionPlanner의 proposal 생성
#    { action: "generate_proposal", input: {...}, output: {...}, reasoning: {...}, duration_ms: 5678 }
# 4. MissionPlanner의 응답 반환
#    { action: "return_response", output: {...} }

# 이를 통해:
# - "무엇이 일어났는가?" (Event 조회)
# - "Agent들이 어떻게 처리했는가?" (AgentLog 시간순 조회)
# - "RequestHandler의 의도 분류 이유는?" (logs[0].reasoning)
# - "MissionPlanner의 proposal 생성 과정?" (logs[2] 상세)
# - "전체 처리 시간은?" (logs의 duration_ms 합산)
```

---

## 3. 주요 Event 타입

**설계**: 각 Event는 **한 번만 발행** (사건 자체). 상세는 AgentLog에 기록.

| event_type | 발행자 | 발행 시점 | 용도 |
|------------|--------|---------|------|
| **USER_COMMAND_RECEIVED** | RequestHandler | 사용자 명령 수신 | 사용자 명령의 시작점 |
| **SYS_ANOMALY_DETECTED** | SystemSentinel | 이상징후 감지 (배터리 부족, 연결 끊김 등) | 이상징후 처리의 시작점 |
| **SYS_POLICY_DECISION** | PolicyManager | 정책 결정 완료 (자동 대응, 승인 필요 등) | 정책 기반 의사결정의 기록 |
| **MISSION_CREATED** | MissionPlanner | Mission 생성 완료 | Mission 실행의 시작점 |
| **TASK_ASSIGNED** | DeviceBridge | Task를 Device에 할당 | Task 실행의 시작점 |
| **TASK_COMPLETED** | DeviceBridge | Task 완료 | Task 완료 기록 |
| **TASK_FAILED** | DeviceBridge | Task 실패 | Task 실패 기록 |
| **SYSTEM_ALERT** | 시스템 | 사용자에게 알려야 할 상황 발생 | 사용자 알림용

---

## 4. Event + AgentLog 흐름 예시

### 사용자 명령 → Proposal 생성 → Mission 승인

```
1️⃣ 사용자 명령 수신 (RequestHandler)
   Event: USER_COMMAND_RECEIVED (context_id: "ctx-123")
        ↓
   AgentLog: 의도 분류 (RequestHandler)
   AgentLog: MissionPlanner A2A 호출 (RequestHandler)
        ↓
2️⃣ MissionPlanner Proposal 생성
   AgentLog: Proposal 생성 (MissionPlanner - LLM 판단 과정 포함)
        ↓
3️⃣ 사용자 승인
   Event: MISSION_CREATED (context_id: "ctx-123")
        ↓
   AgentLog: Task 생성 (MissionPlanner)
   AgentLog: DeviceBridge A2A 호출 (MissionPlanner)
        ↓
4️⃣ Device Task 실행
   Event: TASK_ASSIGNED (context_id: "ctx-123")
   Event: TASK_COMPLETED (context_id: "ctx-123")
        ↓
   AgentLog: Task 결과 처리 (DeviceBridge)

✅ 나중에 context_id "ctx-123"로 조회하면:
   Event들의 전체 사건 흐름과
   AgentLog들의 각 단계 상세 내용 (판단 이유, LLM 출력, A2A 데이터)을 볼 수 있음
```

---

## 5. Timeout 정책

| 상황 | Timeout | 대응 |
|------|---------|------|
| **정상** | 1-10초 | 즉시 응답 |
| **LLM 느림** | 10-300초 | 기다림 |
| **300초 초과** | Timeout | `status: "needs_clarification"` 반환 |

---

## 6. Event + AgentLog 조회 사용 예시

### Agent의 결정 과정 상세 조회

```python
# 사용자 명령 "ctx-123"에서 MissionPlanner가 왜 이 proposal을 생성했는가?
logs = registry_client.list_agent_logs(
    filters={
        "context_id": "ctx-123",
        "agent_role": "MISSION_PLANNER",
        "action": "generate_proposal"
    }
)

proposal_log = logs[0]
print(proposal_log["reasoning"])  # LLM의 판단 이유
print(proposal_log["output"])     # 생성된 proposal
print(proposal_log["duration_ms"]) # 소요 시간
```

### Task 실패 원인 추적

```python
# Task가 실패했는데, 왜 실패했는가?
logs = registry_client.list_agent_logs(
    filters={
        "context_id": "ctx-abc",
        "action": "execute_task"
    }
)

task_log = logs[0]
if task_log["status"] == "FAILED":
    print(task_log["error"])      # 에러 메시지
    print(task_log["output"])     # Task 결과 데이터
    print(task_log["reasoning"])  # 실패 이유 분석
```

### 사용자 명령의 전체 흐름 조회

```python
# 사용자 "ctx-123" 명령의 전체 흐름 (Event + 모든 AgentLog)
event = registry_client.get_event(filters={"context_id": "ctx-123"})
logs = registry_client.list_agent_logs(
    filters={"context_id": "ctx-123"}
)

print(f"명령: {event['data']['command']}")
for log in logs:
    print(f"  → {log['agent_role']}: {log['action']} ({log['status']}, {log['duration_ms']}ms)")
    if log['status'] == 'FAILED':
        print(f"     에러: {log['error']}")
```

---

## 관련 문서

- [schema.md](./schema.md) - Event 및 Proposal 스키마
- [principles.md](./principles.md) - P11 원칙 등
