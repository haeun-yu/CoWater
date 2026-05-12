# CoWater: 6-Agent 최종 아키텍처

## Agent 구성

| # | Agent | 책임 | Input (Subscribe) | Output (Publish/Request) |
|---|-------|------|-------------------|------------------------|
| 1 | **Linguistic** | 사용자 입력 처리 | 사용자 자연어 | `intent.classified` |
| 2 | **Device Input** | Device 메시지 처리 | Device A2A 메시지 | `device.taskresult`, `device.heartbeat`, `device.reconnected` |
| 3 | **Mission Planning** | Task/Mission 관리 | `intent.classified` (MISSION), `policy.mission_request` | `mission.proposed`, `mission.created`, `task.assigned` |
| 4 | **Policy** | 규칙 & 자동 응답 | `intent.classified` (UPDATE), `device.heartbeat`, `device.taskresult`, `anomaly.detected` | `policy.updated`, `policy.mission_request`, `rule.executed` |
| 5 | **Reporting** | 히스토리 & 리포트 | `intent.classified` (QUERY/DELETE), 모든 상태 이벤트 | `report.generated` |
| 6 | **Supervisor** | 상태 감시 & 대응 | 모든 이벤트 | `anomaly.detected`, `action.triggered` |

---

## 핵심 흐름 (Event-Driven)

### **1️⃣ 사용자 요청 → 미션 생성**

```
사용자: "AUV-01을 표면 정찰해줘"
  ↓
Linguistic Agent
  - intent: MISSION / entities: {device: AUV-01}
  - permission: ✓ OPERATOR
  - publish: intent.classified
  
  ↓ [Moth Event Bus]
  
Mission Planning Agent (subscribe: intent.classified, type=MISSION)
  - Capability matching: AUV-01.actions[] ✓
  - AgentConnection 확인: ✓
  - 여러 Proposal 생성
  - publish: mission.proposed {proposals: [...]}
  
  ↓ [UI에서 사용자가 선택 & 승인]
  
Mission Planning Agent
  - 상태 재검증: Device/Agent 상태 확인
  - Mission 생성 (status: READY)
  - Task 할당
  - publish: mission.created, task.assigned
  
  ↓ [Moth Event Bus]
  
Device Input Agent (subscribe: task.assigned)
  - Task를 Device Agent A2A 프로토콜로 전달
  - Device Agent가 작업 수행
```

---

### **2️⃣ Device 이벤트 처리 (Task Result, Heartbeat)**

```
Device Agent: Task 완료 → Task Result 메시지 전송
  ↓
Device Input Agent (A2A 메시지 수신)
  - Task result 파싱
  - publish: device.taskresult {task_id, status, result, timestamp}
  
  ↓ [Moth Event Bus]
  
┌─→ Mission Planning Agent (subscribe: device.taskresult)
│   - Task 상태 갱신: COMPLETED
│   - 다음 Task 할당 (있으면)
│   - publish: task.assigned (next task)
│
├─→ Reporting Agent (subscribe: device.taskresult)
│   - 이벤트 기록 (timestamp 기반)
│
└─→ Supervisor Agent (subscribe: device.taskresult)
    - 진행 상황 모니터링
    - publish: (필요시 anomaly 감지)
```

---

### **3️⃣ Heartbeat & Anomaly 감지**

```
Device Agent: 주기적 heartbeat 전송
  ↓
Device Input Agent (heartbeat 수신)
  - publish: device.heartbeat {device_id, battery, location, signal_strength, timestamp}
  
  ↓ [Moth Event Bus]
  
┌─→ Mission Planning Agent (subscribe: device.heartbeat)
│   - 불가능한 Device 감지 시 Task 재할당 판단
│
├─→ Reporting Agent (subscribe: device.heartbeat)
│   - 실시간 상태 기록 (대시보드용)
│
└─→ Supervisor Agent (subscribe: device.heartbeat)
    - battery < 20% → publish: anomaly.detected {type: LOW_BATTERY}
    - signal_strength < 30% → publish: anomaly.detected {type: SIGNAL_LOSS}
    - OFFLINE timeout → publish: anomaly.detected {type: OFFLINE}
```

---

### **4️⃣ Anomaly → Policy → 자동 응답**

```
Supervisor: signal_strength < 30% 감지
  ↓
publish: anomaly.detected {type: SIGNAL_LOSS, device_id, severity: HIGH}
  
  ↓ [Moth Event Bus]
  
Policy Agent (subscribe: anomaly.detected)
  - Rule 확인: "IF signal_strength < 30% THEN auto_response = EMERGENCY_SURFACE"
  - Rule 매칭 O → 자동 처리 결정
  - publish: policy.mission_request {
      type: EMERGENCY_SURFACE,
      target_device: device_id,
      reason: SIGNAL_LOSS,
      priority: CRITICAL
    }
  
  ↓ [Moth Event Bus]
  
Mission Planning Agent (subscribe: policy.mission_request)
  - EMERGENCY_SURFACE 미션 생성
  - Task: RETURN_TO_BASE, SURFACE 할당
  - publish: mission.created, task.assigned
  
  ↓ [Device가 긴급 복귀]
```

---

### **5️⃣ 통신 복구 & 상태 동기화**

```
Device Agent: 네트워크 복구 → reconnect message 전송
{
  device_id: "auv-01",
  offline_period: {disconnected_at, reconnected_at},
  completed_tasks: [{task_id, status, result, timestamp}, ...],
  in_progress_task: {task_id, progress},
  local_events: [{type, timestamp}, ...]
}
  ↓
Device Input Agent (reconnect 메시지 수신)
  - 메시지 파싱
  - publish: device.reconnected {all_data_above, parsed_at}
  
  ↓ [Moth Event Bus, timestamp 기반 정렬]
  
┌─→ Mission Planning Agent (subscribe: device.reconnected)
│   - completed_tasks 처리:
│     ├─ Task 상태 갱신 (COMPLETED)
│     ├─ Mission 상태 재평가 (모든 Task 완료?)
│     └─ 다음 Task 할당
│   - in_progress_task: 진행 상황 업데이트
│
├─→ Reporting Agent (subscribe: device.reconnected)
│   - local_events를 timestamp 순서로 기록
│   - offline_period 마킹
│   - 통신 복구 이벤트 기록
│
├─→ Supervisor Agent (subscribe: device.reconnected)
│   - Device ONLINE으로 상태 변경
│   - 관련 anomaly 해제 (OFFLINE, SIGNAL_LOSS 등)
│
└─→ Policy Agent (subscribe: device.reconnected)
    - 복구 후 적용할 정책 확인
    - 예: "Device 복구 후 다시 배터리 점검"
```

**중요: timestamp 기반 일관성**
```
// Device가 오프라인 중 local_events 발생 시간 기록
local_events = [
  {type: TASK_COMPLETED, timestamp: 2026-05-12T10:05:00Z},
  {type: TASK_COMPLETED, timestamp: 2026-05-12T10:10:00Z},
  {type: LOW_BATTERY, timestamp: 2026-05-12T10:15:00Z}
]

// System은 timestamp 기반 정렬
sort_by(timestamp) → 순서 보장 (동시 처리 가능)
```

---

### **6️⃣ Policy 수정 (UPDATE Intent)**

```
사용자: "수중일 때 telemetry sampling 10배 줄여줘"
  ↓
Linguistic Agent
  - intent: UPDATE / entities: {target: config, param: telemetry_sampling}
  - permission: ADMIN ✓
  - publish: intent.classified {type: UPDATE, ...}
  
  ↓ [Moth Event Bus]
  
Policy Agent (subscribe: intent.classified, type=UPDATE)
  - Config/Rule 수정
  - publish: policy.updated {old_value, new_value, timestamp}
  
  ↓ [Moth Event Bus]
  
Supervisor Agent (subscribe: policy.updated)
  - 정책 변경 기록
```

---

### **7️⃣ 조회 & 리포트 (QUERY Intent)**

```
사용자: "지난 1시간 동안 뭐 했어?"
  ↓
Linguistic Agent
  - intent: QUERY / entities: {time_range: 1h}
  - permission: OPERATOR ✓
  - publish: intent.classified {type: QUERY, ...}
  
  ↓ [Moth Event Bus]
  
Reporting Agent (subscribe: intent.classified, type=QUERY)
  - 조건에 맞는 히스토리 조회
  - Report 생성
  - publish: report.generated {report_id, data, format}
```

---

### **8️⃣ Device 제거 (DELETE Intent)**

```
사용자: "ROV-01 제거해줘"
  ↓
Linguistic Agent
  - intent: DELETE / entities: {target: device, id: rov-01}
  - permission: ADMIN ✓
  - publish: intent.classified {type: DELETE, ...}
  
  ↓ [Moth Event Bus]
  
Reporting Agent (subscribe: intent.classified, type=DELETE)
  - Device 제거 전 상태 검증
    ├─ Device.status == OFFLINE? (필수)
    ├─ AgentConnection 조회 (대체 Agent 있나?)
    └─ 진행 중인 Task 있나?
  
  [또는 Policy Agent가 처리?]
  
  - 검증 완료 시:
    ├─ Mission Planning에 요청: 관련 Task 취소
    └─ Device 제거 처리 (removed_at 기록)
  
  - publish: device.removed {device_id, reason}
  
  ↓ [Moth Event Bus]
  
Supervisor Agent (subscribe: device.removed)
  - Device 제거 이벤트 기록
```

**❓ DELETE는 누가 처리할지?**
- Option A: Reporting Agent (히스토리 관점에서)
- Option B: Policy Agent (규칙/설정 관점에서)
- Option C: 새로운 "System Admin Agent"

**제안**: Policy Agent가 통합 처리 (Device 상태 변경 = 정책 범위)

---

## Event 타입 정의

```typescript
// Linguistic → Intent
intent.classified {
  type: MISSION | QUERY | UPDATE | DELETE | CONTROL,
  entities: {...},
  permission: {role, level},
  timestamp
}

// Device Input ← Device Agent
device.taskresult {
  device_id, task_id, status, result, timestamp
}

device.heartbeat {
  device_id, battery_percent, location, signal_strength, timestamp
}

device.reconnected {
  device_id,
  offline_period: {disconnected_at, reconnected_at},
  completed_tasks: [...],
  in_progress_task: {...},
  local_events: [...],
  timestamp
}

// Mission Planning → Mission
mission.proposed {proposals: [...]}
mission.created {mission_id, tasks: [...]}
task.assigned {task_id, device_id, task_data}

// Policy → Policy
policy.updated {old_value, new_value, timestamp}
policy.mission_request {type, target_device, reason, priority}
rule.executed {rule_id, condition, action, timestamp}

// Supervisor → Anomaly
anomaly.detected {type: LOW_BATTERY|SIGNAL_LOSS|OFFLINE|..., device_id, severity}
action.triggered {action, target, reason}

// Reporting → Report
report.generated {report_id, data, format}
device.removed {device_id, reason, timestamp}
```

---

## 선택: DELETE 처리 Agent

| 후보 | 장점 | 단점 |
|------|------|------|
| **Policy Agent** | Device 상태 변경 = 정책 범위, 기존 규칙 시스템 활용 | 책임이 조금 커짐 |
| **Reporting Agent** | 히스토리 관점에서 자연스러움, 과거 기록 삭제도 가능 | 보고서 생성과 무관 |
| **새로운 Admin Agent** | 명확한 책임 분리 | Agent 수 증가 (7개) |

**추천**: **Policy Agent** (Device 상태 변경이 정책 범위에 가까움)

---

## 최종 검증

| 프로세스 | Agent | 이벤트 |
|---------|-------|--------|
| 사용자 입력 | Linguistic | intent.classified |
| Device 메시지 | Device Input | device.* |
| Mission 생성 | Mission Planning | mission.created, task.assigned |
| Policy 적용 | Policy | policy.*, rule.* |
| Anomaly 감지 | Supervisor | anomaly.detected |
| 자동 응답 | Policy + Mission Planning | policy.mission_request → mission.created |
| 통신 복구 | Device Input → 모든 Agent | device.reconnected (timestamp 정렬) |
| Device 제거 | Policy | device.removed |
| 조회 & 리포트 | Reporting | report.generated |

✅ **모든 프로세스 대응 완료**
