# ADR-009: 물리 통신 라우팅 및 동적 핸드오버

**상태**: Accepted
**작성일**: 2026-05-12  
**선행 ADR**: ADR-001, ADR-004

---

## 상황 (Context)

Device들이 물리 환경을 오가면서(수면 ↔ 수중) 사용 가능한 통신 매체가 동적으로 변합니다.

**문제**:
- AUV는 수면에서는 LTE/RF 사용 가능, 수중에서는 음파만 가능
- ROV는 유선 연결된 USV를 통해서만 통신
- System Agent는 이러한 물리 제약을 자동으로 감지하고 통신 경로를 전환해야 함

**현재 설계의 한계**:
- Agent.capabilities는 고정 (변하지 않음)
- 환경 변화에 따른 dynamic routing 미정의
- Gateway (유선 연결) 시나리오 미지원

---

## 결정 (Decision)

**3가지 메커니즘으로 동적 통신을 관리**:

### 1️⃣ Agent의 2가지 상태 분리

```typescript
Agent {
  // 고정 (등록 시)
  capabilities: ["WIRED", "ACOUSTIC", "RF", "INTERNET"]  // H/W 가능성
  
  // 동적 (실시간 변경)
  environment_state: "SURFACE" | "UNDERWATER"  // 현재 위치
  active_mediums: ["RF", "ACOUSTIC"]           // 지금 사용 가능한 것
}
```

**규칙**:
- `active_mediums ⊆ capabilities` (항상)
- 환경 변화 시 `active_mediums` 자동 업데이트

### 2️⃣ 매체별 우선순위 및 특성

| 매체 | 우선순위 | 환경 | 대역폭 | 지연 | 특징 |
|------|---------|------|--------|------|------|
| **Wired** | 1순위 | - | 매우 높음 | 극저 | 물리 탯줄 필수 |
| **RF/Internet** | 2순위 | Surface | 높음 | 저 | 수중 진입시 즉시 단절 |
| **Acoustic** | 3순위 | Submerged | 낮음 | 높음 | 유일한 수중 수단 |

### 3️⃣ 실시간 통신 모드 전환 (Dynamic Hand-over)

#### 트리거: 환경 변화 감지

```
Device Agent가 감지:
  "내 GPS/센서에서 수심이 5m를 넘었어"
    ↓
Event 발행:
  {
    type: "ENV_STATE_CHANGED",
    actor_id: "agent-auv-1",
    data: { from: "SURFACE", to: "UNDERWATER" }
  }
    ↓
System Agent (Event Listener):
  1. Agent.environment_state 갱신
  2. Agent.active_mediums 재계산
  3. 기존 AgentConnection 재평가
  4. Policy 적용
```

#### 실시간 활성 매체 변경

```
AUV 수중 진입 시나리오:

Before (수면):
  AUV.active_mediums = ["RF", "INTERNET", "ACOUSTIC"]
  AgentConnection[RF] = 생성됨
  AgentConnection[ACOUSTIC] = 필요 시 생성 가능

Event: ENV_STATE_CHANGED (SURFACE → UNDERWATER)
  ↓

After (수중):
  AUV.active_mediums = ["ACOUSTIC"]  // ← 자동 업데이트
  기존 RF 기반 AgentConnection = soft-delete
  Acoustic 기반 AgentConnection = 재생성
```

#### Policy 기반 응답

```
Rule 1: "수중 진입 시 대역폭 제한"
  IF (Event: ENV_STATE_CHANGED to="UNDERWATER")
  THEN (
    SET Task.priority = "essential_only"
    QUEUE file_transfers for later
  )

Rule 2: "음파 신호 약화 시 자동 복귀"
  IF (signal_strength < 30%)
  THEN (
    CREATE_MISSION type="EMERGENCY_SURFACE"
    NOTIFY System Agent
  )

Rule 3: "유선 연결 감지 시 무선 비활성화"
  IF (Agent.gateway_agent_id exists)
  THEN (
    DISABLE active_mediums except "wired"
    POWER_SAVE other_interfaces
  )
```

---

## 구현 세부사항

### 환경 상태 추적

```typescript
// Device Agent가 환경 상태 주기적으로 보고
class DeviceAgent {
  private lastEnvironmentState = "SURFACE"
  
  async monitorEnvironment() {
    const depth = await sensor.getWaterDepth()
    const newState = depth > 2 ? "UNDERWATER" : "SURFACE"
    
    if (newState !== this.lastEnvironmentState) {
      // 환경 변화 감지
      await registry.updateAgent(this.id, {
        environment_state: newState
      })
      
      // Event 발행
      await moth.publish("agents", {
        event_type: "ENV_STATE_CHANGED",
        agent_id: this.id,
        from: this.lastEnvironmentState,
        to: newState
      })
      
      this.lastEnvironmentState = newState
    }
  }
}
```

### Active Mediums 자동 갱신

```typescript
// System Agent가 환경 상태에 따라 active_mediums 결정
function updateActiveMediums(agent: Agent): string[] {
  const { environment_state, capabilities, gateway_agent_id } = agent
  
  // Step 1: Gateway인 경우 wired만
  if (gateway_agent_id) {
    return ["WIRED"]
  }
  
  // Step 2: 환경에 따라 필터링
  if (environment_state === "UNDERWATER") {
    return ["ACOUSTIC"]  // 수중: acoustic만
  }
  
  // Step 3: 수면 시 모든 고속 매체 활성화
  return capabilities.filter(m => m !== "ACOUSTIC")
}
```

### AgentConnection 모니터링

```typescript
// 주기적으로 AgentConnection 유효성 재검증
async function validateConnections() {
  const connections = getActiveConnections()
  
  for (const conn of connections) {
    const agentA = getAgent(conn.agent_a_id)
    const agentB = getAgent(conn.agent_b_id)
    
    // 현재 환경에서 이 연결이 여전히 유효한가?
    const isValid = conn.profile.network_type in agentA.active_mediums &&
                    conn.profile.network_type in agentB.active_mediums
    
    if (!isValid) {
      // 매체 비활성화
      conn.deleted_at = datetime.utcnow()  # 소프트 삭제
      
      // 대체 매체 찾기
      const alternatives = findAlternativeConnections(agentA, agentB)
      if (alternatives.length > 0) {
        // 자동 전환
        activateConnection(alternatives[0])
      } else {
        // 통신 불가능 상태
        raiseAlert("COMMUNICATION_LOSS", conn.id)
      }
    }
  }
}
```

---

## 예시 시나리오

### 시나리오 1: ROV 유선 연결

```
USV-01 (Surface)
  ├─ Agent: agent-usv-01
  ├─ capabilities: [WIRED, RF, INTERNET, ACOUSTIC]
  └─ active_mediums: [RF, INTERNET, ACOUSTIC]

  ├─ ROV-01 (Tethered via cable)
  │   ├─ Agent: agent-rov-01
  │   ├─ gateway_agent_id: agent-usv-01  ← 핵심!
  │   ├─ capabilities: [WIRED]
  │   └─ active_mediums: [WIRED]  (always)

Flow:
  System Agent → Task → USV
                          └─ (케이블로) → ROV
  
  ROV는 인터넷 직접 안 찾음, USV가 게이트웨이 역할
```

### 시나리오 2: AUV 수면 ↔ 수중 전환

```
초기 상태 (수면):
  AUV-01.environment_state = "SURFACE"
  AUV-01.active_mediums = ["RF", "INTERNET", "ACOUSTIC"]
  AgentConnection[RF]: 생성됨
  AgentConnection[ACOUSTIC]: 필요 시 생성 가능

1️⃣ 수심 진입 감지:
  AUV 센서: depth = 10m (잠수 시작)

2️⃣ Event 발행:
  ENV_STATE_CHANGED {
    agent_id: "agent-auv-01",
    from: "SURFACE",
    to: "UNDERWATER"
  }

3️⃣ System Agent 응답:
  a. Agent.environment_state = "UNDERWATER" 갱신
  b. Agent.active_mediums = ["ACOUSTIC"] 자동 변경
  c. RF Module Sleep (배터리 절감)
  d. Policy 실행:
     - Task priority = "essential_only"
     - Telemetry sampling = 1/10으로 감소
     - File transfer = Queue

4️⃣ 실시간 통신:
  - 음파로 Task 진행 상황 보고
  - Acoustic 지연(~500ms) 때문에 응답성 낮아짐
  - 하지만 수중 작업 계속

5️⃣ 수면 복귀:
  AUV 센서: depth = 0.5m (수면 도달)
    ↓
  ENV_STATE_CHANGED: "UNDERWATER" → "SURFACE"
    ↓
  System Agent:
    a. Agent.active_mediums = ["RF", "INTERNET", "ACOUSTIC"]
    b. RF Module Wake (약 1초)
    c. 대역폭 제한 해제
    d. 대기 중인 파일 전송 재개
```

---

## 결과 (Consequences)

### ✅ 이점
- **자동화**: 환경 변화를 System Agent가 자동 감지/응답
- **최적화**: 우선순위에 따라 가장 효율적인 매체 선택
- **복원력**: 유선 연결, Gateway 패턴으로 신뢰성 강화
- **에너지 효율**: 필요없는 모듈 Sleep → 배터리 절감

### ⚠️ 제약
- **지연시간**: 음파 통신 시 응답성 저하 (수백ms 이상)
- **대역폭**: 수중에선 테스트 위주만 가능
- **정책 의존**: Dynamic hand-over는 Policy가 정의되어야 작동

---

## 참고

- **[ADR-004](ADR-004-agent-endpoint-management.md)**: Agent Endpoint & 3단계 필터링
- **[SYSTEM_ARCHITECTURE.md](../SYSTEM_ARCHITECTURE.md)**: 물리 통신 관리 섹션
- **[core/schema.md](../core/schema.md)**: Agent, Device 스키마
- **[core/principles.md](../core/principles.md#event-based-traceability)**: Event-Based Traceability
