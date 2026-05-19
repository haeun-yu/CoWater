# 아키텍처 결정 기록(ADR)

CoWater 시스템의 핵심 아키텍처 결정사항과 설계 철학을 기록합니다.

## 목록

| ADR | 제목 | 상태 | 날짜 |
|-----|------|------|------|
| **[ADR-001](ADR-001-core-design-philosophy.md)** | **Core Design Philosophy** | ✅ Accepted | 2026-05-12 |
| **[ADR-002](ADR-002-proposal-as-solution-set.md)** | **Proposal as Solution Set** | ✅ Accepted | 2026-05-12 |
| **[ADR-003](ADR-003-capability-driven-task-assignment.md)** | **Capability-Driven Task Assignment** | ✅ Accepted | 2026-05-12 |
| **[ADR-004](ADR-004-agent-endpoint-management.md)** | **Agent Endpoint Management** | ✅ Accepted | 2026-05-12 |
| **[ADR-005](ADR-005-event-triggered-rule-execution.md)** | **Event-Triggered Rule Execution** | ✅ Accepted | 2026-05-12 |
| **[ADR-006](ADR-006-adaptive-autonomy-migration-path.md)** | **Adaptive Autonomy Migration Path** | ✅ Accepted | 2026-05-12 |
| **[ADR-007](ADR-007-data-generalization.md)** | **Data Generalization** | ✅ Accepted | 2026-04-28 |
| **[ADR-008](ADR-008-multi-agent-system-architecture.md)** | **Multi-Agent System Architecture** | ✅ Accepted | 2026-05-13 |
| **[ADR-009](ADR-009-physical-communication-routing.md)** | **Physical Communication Routing** | ✅ Accepted | 2026-05-10 |

## 핵심 철학 (Core Philosophy)

CoWater의 아키텍처는 다음 5가지 설계 철학을 중심으로 구성됩니다.

1. **Action Abstraction** - 이종 기종을 추상화된 인터페이스로 통제
2. **Decoupling Planning/Execution** - 계획(Proposal)과 실행(Mission)의 엄격한 분리
3. **Inter-Agent Collaboration** - Device Agent 간 동적 협력 관계 (AgentConnection)
4. **Event-Based Traceability** - 모든 의사결정의 Event 기반 기록 및 추적
5. **Bridge the Gap** - 물리적 제약의 소프트웨어적 극복 (Edge-Side Resilience)

**→ [ADR-001: Core Design Philosophy](ADR-001-core-design-philosophy.md) 참고**

## 주요 설계 결정

### Proposal 구조
- Proposal은 **"완전한 솔루션 세트"** (여러 Task의 조합)
- 사용자는 Proposal 전체를 선택 (개별 Task 조합 불가)
- **→ [ADR-002](ADR-002-proposal-as-solution-set.md) 참고**

### 작업 할당 원칙
- System Agent는 **Fact 기반만 판단** (Device.actions[]에만 의존)
- 불가능한 요청은 **"명시적 거절"** (억지 추측 금지)
- **→ [ADR-003](ADR-003-capability-driven-task-assignment.md) 참고**

### Agent 통신
- Agent는 등록 시 **endpoint 정보 포함**
- AgentConnection이 자동으로 endpoint 조회/연결
- **→ [ADR-004](ADR-004-agent-endpoint-management.md) 참고**

### Rule 실행
- Rule은 **Event 발생 시점에만 실행** (매 Heartbeat마다 X)
- Event-Triggered System으로 효율성 확보
- **→ [ADR-005](ADR-005-event-triggered-rule-execution.md) 참고**

### 자동화 진화
- Rule.action.type으로 자동화 수준 조절 (코드 수정 X)
- Phase 1 (Manual) → Phase 2 (Partial Auto) → Phase 3 (Full Auto)
- **→ [ADR-006](ADR-006-adaptive-autonomy-migration-path.md) 참고**

## 참고
- 각 ADR은 다음 구조를 포함합니다: 상황(Context), 결정(Decision), 결과(Consequences)
- 이전 결정에 대한 수정사항이 생기면 새로운 ADR로 기록
- 모든 ADR은 [docs/core/](../core/) 및 [docs/scenarios/](../scenarios/)의 기반이 됩니다
