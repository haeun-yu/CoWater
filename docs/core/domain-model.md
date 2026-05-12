# 핵심 도메인 모델 (Domain Model)

**Ubiquitous Language** - 모든 팀이 공유하는 도메인 개념 정의  
**기반**: [ADR-001: Core Design Philosophy](../adr/ADR-001-core-design-philosophy.md)

---

## 역할 정의 (Role Definition)

### 🤖 **Device (장비) - 물리 자원**

**정의**: 해양에서 실제 작업을 수행하는 물리적 자원

- **유형**: USV, AUV, ROV 등
- **상태**: ONLINE / OFFLINE / ERROR / DEGRADED / REMOVED
- **역할**: 할당받은 Task를 실행하고 결과를 보고
- **책임**: 자신이 가능한 actions[]를 명확히 선언

**핵심 원칙**:

> "Device는 **자신이 할 수 있는 것만** 명시해야 하며,  
> System은 **그 목록 안에서만** Task를 할당합니다." (ADR-003)

### 🧠 **Agent (에이전트) - 판단/실행 주체**

**정의**: Device를 제어하거나 System 운영을 담당하는 지능

**종류**:

- **Device Agent**: 특정 Device 1개를 제어 (on-edge 또는 remote)
- **System Agent**: 전체 시스템의 의사결정 (Proposal 생성, Rule 실행 등)

**책임**:

- Device Agent: 자신의 Device만 직접 제어, 할당받은 Task 수행
- System Agent: 자연어 해석, Capability Matching, Proposal 생성, Rule 실행

**중요**: Device와 Agent를 혼동하면 안 됨

- Device = 자원, Agent = 지능
- Device 1개 = 여러 Agent가 제어 불가 (exclusive)
- Agent는 Device와 1:1 또는 System 전체 담당

### 🔗 **AgentConnection - 협력 관계**

**정의**: Device Agent 간의 논리적/물리적 협력 관계

**유형**:

- **RELAY**: 통신 불가능한 장비를 대신 제어/통신
- **COORDINATE**: 여러 장비 간 시간 동기화된 협력
- **SHARE_DATA**: 센서 데이터 공유
- **BACKUP**: 주 Agent 실패 시 백업
- **SWARM_MEMBER**: 집단 제어
- **LEADER_FOLLOWER**: 임시 리더/팔로워 관계

**핵심 원칙**:

> AgentConnection은 **단순 선 연결이 아니라**  
> **협력의 목적과 조건을 명확히 정의**하는 것입니다.

**Endpoint 관리 전략** (ADR-004, endpoint 변경 불가 원칙):

- **기본 원칙**: Agent.endpoint는 등록 후 **변경하지 않음** (모든 AgentConnection에 영향)
- **연결 생성 시점**: Agent 테이블의 endpoint 정보로 AgentConnection.profile 초기화
- **실행 시점**: Task 전달/실행 시 AgentConnection.profile에 저장된 endpoint_a/b 사용
  - endpoint 변경 불가 원칙 하에서는 항상 동일한 값
  - 예외 상황(endpoint 변경 필수): schema.md:144-151의 처리 규칙 따름
- **감사 추적**: Mission/Report 생성 시점의 endpoint는 스냅샷으로 기록
  - 장애 분석 시 "해당 시점에 사용된 통신 정보" 추적 가능

**유효성 판단** (6번 사용자 피드백 기반):

- `deleted_at IS NULL`: 활성 연결
- `deleted_at IS NOT NULL`: 소프트 삭제 상태 (더 이상 사용 불가)
- status 필드는 제거됨 (ACTIVE, DEGRADED, INACTIVE 등 불필요)

**relation_level 상세** (15번 사용자 피드백 기반):

- **PEER**: 두 에이전트가 서로 독립적인 의사결정권을 가지며, 정보를 공유하거나 단순히 통신을 릴레이 (예: 두 대의 AUV 협력 수색)
- **PARENT_CHILD**: 한 에이전트(Parent)가 다른 에이전트(Child)의 생명주기나 명령 실행을 부분적으로 통제하거나, Child가 Parent의 자원에 물리적으로 종속된 관계
  - **예시**: USV(Parent)가 ROV(Child) 유선 연결 (또는 AUV가 수중으로 들어가는 경우)
  - **로직**: USV가 복귀 명령을 받으면, Child인 ROV에게도 자동으로 복귀 또는 수거 준비 명령이 전달됨 (부모의 상태에 자식이 동기화)

---

## 흐름 정의 (Flow Definition)

### **User (사용자) → Proposal → Mission → Task**

```
사용자 요청 (자연어)
  ↓
EVENT: USER_COMMAND
  ↓ [System Agent]
PROPOSAL (솔루션 세트)
  ├─ Proposal-1: [Task-A → Task-B → Task-C]
  └─ Proposal-2: [Task-D → Task-E]
  ↓ [사용자 선택 & 승인]
MISSION (승인된 실행 계획)
  ↓ [Task 할당 & 실행]
TASK (세부 실행 단위)
  ├─ Task-A [Device-X 실행]
  ├─ Task-B [Device-Y 실행]
  └─ Task-C [Device-X 실행]
  ↓
REPORT (결과 요약)
```

**특성**:

- **Proposal**: System이 제시하는 **완전한 솔루션 세트** (ADR-002)
  - 여러 Task의 조합이 사전에 검증됨
  - 사용자는 Proposal 전체를 선택 (개별 Task 조합 불가)
- **Mission**: 사용자 승인 후 **실제 실행 단위**
  - 승인 상태(APPROVED) → 진행 중(IN_PROGRESS) → 완료(COMPLETED/FAILED/CANCELLED)
- **Task**: Mission의 **세부 실행 항목**
  - 대기(PENDING) → Device 수신(ASSIGNED) → 진행 중(IN_PROGRESS) → 완료(COMPLETED/FAILED/CANCELLED/ABORTED)

### **Event - 모든 의사결정의 근거**

```
[Event] 발생
  ↓
[Rule Engine] 조건 확인
  ↓ [Event-Triggered]
[Rule Action] 실행
  ├─ CREATE_PROPOSAL (Proposal 생성)
  ├─ CREATE_EVENT (새로운 Event 발행)
  └─ AUTO_CREATE_MISSION (즉시 Mission 생성)
```

**Event 타입**:

- `USER_COMMAND` - 사용자 요청
- `PROBLEM_DETECTED` - 문제 감지 (LOW_BATTERY, OFFLINE 등)
- `TASK_FAILED` - Task 실패
- `CRITICAL_HAZARD` - 긴급 상황
- 기타 운영 이벤트

**중요 원칙** (ADR-005):

> Rule은 **매 Heartbeat마다 실행되지 않습니다.**  
> **특정 Event가 발생할 때만** Rule Engine이 실행됩니다.

---

## 설정 정의 (Configuration Definition)

### **Policy / Rule / Config - 운영 로직**

```
System Code (고정)
  ↓
Policy (운영 원칙)
  ↓
Rule (조건 + 행동)
  ↓
Config (설정값)
  ↓
System 동작 (변함)
```

**각 역할**:

- **Policy**: "언제 자동화할 것인가?" (개념 수준)
  - 예: "Critical 상황은 자동 대응 허용"
- **Rule**: Policy를 구체화한 규칙 (실행 수준)
  - 예: "CRITICAL_HAZARD 이벤트 발생 시 EMERGENCY_STOP Mission 자동 생성"
- **Config**: Rule/System에서 참조하는 설정값 (파라미터 수준)
  - 예: `low_battery_threshold = 20%`, `max_proposal_options = 3`

**Adaptive Autonomy** (ADR-006):

- Phase 1 (현재): Policy/Rule로 Manual 모드만 (CREATE_PROPOSAL)
- Phase 2: CRITICAL만 자동 (AUTO_CREATE_MISSION 추가)
- Phase 3: 더 많은 조건 자동화 (Rule 추가)
- Phase 4: 대부분 자동화 (Proposal 단계 선택 사항화)

---

## 핵심 원칙 요약

| 원칙                              | 의미                               | 이유                          |
| --------------------------------- | ---------------------------------- | ----------------------------- |
| **Device ≠ Agent**                | Device는 자원, Agent는 지능        | 역할 명확성                   |
| **Fact-Driven**                   | System은 Device.actions[]만 신뢰   | 추측 금지, 신뢰성 확보        |
| **Proposal = Solution Set**       | 여러 Task가 사전 검증된 조합       | 충돌/순서 문제 사전 차단      |
| **Event-Triggered**               | Rule은 Event 발생 시 실행          | 효율성 (불필요한 반복 계산 X) |
| **Code → Policy → Rule → Config** | 자동화 수준은 코드가 아닌 설정으로 | 단계적 자동화 가능            |
| **Explicit Rejection**            | 불가능하면 명확한 이유와 함께 거절 | 사용자 피드백, 시스템 개선    |

---

## 참고

- **[ADR-001](../adr/ADR-001-core-design-philosophy.md)**: 5가지 핵심 철학
- **[ADR-002](../adr/ADR-002-proposal-as-solution-set.md)**: Proposal 구조
- **[ADR-003](../adr/ADR-003-capability-driven-task-assignment.md)**: Capability Matching
- **[ADR-005](../adr/ADR-005-event-triggered-rule-execution.md)**: Event-Triggered Rule
- **[ADR-006](../adr/ADR-006-adaptive-autonomy-migration-path.md)**: 자동화 진화
- **[schema.md](schema.md)**: 데이터 모델 상세
- **[principles.md](principles.md)**: 설계 원칙
