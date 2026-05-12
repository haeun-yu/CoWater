# ADR-001: CoWater의 핵심 설계 철학

**상태**: Accepted  
**작성일**: 2026-05-12  
**검토자**: CoWater Architecture Team

---

## 상황 (Context)

CoWater는 다양한 무인 해양 기종(USV, AUV, ROV 등)을 통합 관리하는 플랫폼입니다. 각 기종이 갖는 물리적, 통신적 제약을 극복하면서도 확장 가능하고 자율화 가능한 시스템 구조가 필요합니다.

---

## 결정 (Decision)

CoWater의 아키텍처는 다음 **5가지 핵심 철학**을 기반으로 설계됩니다.

### 1️⃣ **추상화된 행동 계층 (Action Abstraction)**

시스템은 장비의 개별 하드웨어 제어 명령을 직접 다루지 않습니다.  
대신 `required_action`이라는 추상화된 인터페이스로 소통합니다.

**이유**:

- USV, AUV, ROV 등 서로 다른 기종이 들어와도 시스템은 동일한 로직(Mission/Task)으로 통제 가능
- 새로운 기종 추가 시 하드웨어 레벨의 변경 최소화 (Heterogeneous Multi-Domain Support)

**구현**:

- `Device.actions[]`: 각 기종이 자기 선언한 원자적 기능 목록
- System Agent는 이 목록 내에서만 Task 할당 가능
- 목록에 없는 작업은 "명시적 거절" (fail-fast)

---

### 2️⃣ **계획과 실행의 분리 (Decoupling Planning and Execution)**

작업을 **정하는 단계(Proposal)**와 **수행하는 단계(Mission)**를 엄격히 분리합니다.

**이유**:

- 현재의 '인간 승인' 구조에서 미래의 'AI 자동 승인' 구조로 시스템 전체를 갈아엎지 않고도 매끄럽게 전환(Migration) 가능
- Policy/Rule 설정만으로 자동화 수준을 단계적으로 높일 수 있음

**구현**:

- Proposal: 시스템이 제시하는 추천안 모음
- Mission: 사용자 승인 후 실제 실행 단위
- `Rule.action.type = AUTO_CREATE_MISSION`으로 자동화 수준 조절 가능

---

### 3️⃣ **에이전트 간 협업 거버넌스 (Inter-Agent Collaboration)**

개별 장비(Device Agent)는 고립된 존재가 아니라, `AgentConnection`을 통해 동적으로 협력 관계를 맺습니다.

**이유**:

- 단일 장비의 한계를 넘어 통신 중계(Relay), 협업 관측, 리더-팔로워 등 복합 미션 수행
- 물리적 통신 불가능한 환경(ROV 등)을 논리적 연결로 해결

**구현**:

- `AgentConnection.connection_type`: RELAY, COORDINATE, SHARE_DATA, BACKUP, SWARM_MEMBER, LEADER_FOLLOWER
- Offline Device 신규 할당 불가, 단 Relay Agent를 통한 우회 전달 가능
- 동적 재평가로 최적 통신 경로 유지

---

### 4️⃣ **사건 기반의 상태 추적성 (Event-Based Traceability)**

시스템에서 발생하는 모든 의미 있는 변화(요청, 감지, 승인, 실패)는 `Event`로 객체화됩니다.

**이유**:

- 단순히 현재 상태를 아는 것을 넘어, "왜 이 미션이 만들어졌는가?"에 대한 원인 분석(Root Cause Analysis) 가능
- 운영 이력 추적, 감사, 사후 리포팅의 근거 제공
- Rule Engine의 트리거(Event-Triggered System)로 작동

**구현**:

- `Event`: 모든 중요한 사건의 기록 (USER_COMMAND, PROBLEM_DETECTED, TASK_FAILED 등)
- `Rule`은 Event 생성 시점에 실행 (매 Heartbeat마다 X, 임계치 초과 시 O)
- Event 기반으로 Proposal 생성, Mission 추천, 자동 대응 트리거

---

### 5️⃣ **물리적 제약의 소프트웨어적 극복 (Bridge the Gap)**

직접 통신이 불가능하거나 불안정한 해양 환경의 물리적 제약을 논리적 연결과 자율성으로 보상합니다.

**이유**:

- 수중 환경의 특수성(불안정성, 대역폭 제한, 지연)을 인정하고 설계
- Edge-Side Resilience: Device Agent는 중앙 연결 끊겨도 진행 중인 Task 완료 가능
- 자연어 기반 사용자 경험: 복잡한 로봇 제어 대신 의도(Intent) 전달

**구현**:

- Device Agent: 자기 Device만 직접 제어, 오프라인 상황에서도 할당된 Task 수행
- AgentConnection: 통신 사각지대의 장비를 대신 제어/통신
- 시스템 Agent: 사용자의 자연어를 Task Sequence로 구체화

---

## 결과 (Consequences)

### ✅ 긍정적 영향

- **확장성**: 새 기종 추가 시 `Device.actions[]` 등록만으로 통합 가능
- **자율화 경로**: Policy/Rule 수정만으로 단계적 자동화 가능, 코드 수정 X
- **신뢰성**: Event 기반 추적으로 모든 의사결정 근거 기록
- **견고성**: 통신 불안정성을 고려한 설계로 해양 환경에 적합

### ⚠️ 설계 제약

- **Device.actions 엄격함**: 장비가 선언하지 않은 기능은 절대 할당 불가 (명시적 거절)
- **Proposal 전체 선택**: Task 개별 조합 불가, 시스템이 제시한 안 전체를 선택/거절
- **Event 의존성**: Rule 실행이 Event에 의존하므로 Event 생성 로직 설계 매우 중요
- **Offline 신규 할당 불가**: Edge-Side Resilience는 진행 중 단절만 대응, 신규 할당은 불가

---

## 참고

- **ADR-002**: Proposal as Solution Set
- **ADR-003**: Capability-Driven Task Assignment
- **ADR-004**: Agent Endpoint Management
- **ADR-005**: Event-Triggered Rule Execution
- **ADR-006**: Adaptive Autonomy Migration Path
- **docs/core/domain-model.md**: 각 엔티티의 역할 정의
- **docs/core/schema.md**: 데이터 스키마 상세
- **docs/scenarios/\***: 구체적 프로세스 흐름
