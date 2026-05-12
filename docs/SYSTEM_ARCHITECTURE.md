# CoWater 시스템 아키텍처

**문서 버전**: v0.2  
**최종 업데이트**: 2026-05-12  
**목적**: CoWater 시스템의 전체 구조, 설계 철학, 컴포넌트 관계를 상위 수준에서 개요합니다.

> 💡 **이 문서는 개요 문서입니다.** 세부 내용은 각 섹션의 링크를 통해 확인하세요.

---

## 1. CoWater 정의

CoWater는 **자율 운영을 지원하는 AI Agent 기반 해양 무인체 통합 운영 플랫폼**입니다.

- 다양한 해양 무인체(USV, AUV, ROV 등)를 단일 시스템으로 관리
- 사용자 승인 기반 운영과 정책 기반 자동 대응을 병행
- **계획(Proposal)과 실행(Mission)을 분리**하여 자동화 수준을 단계적으로 상향 가능
- 모든 의사결정의 근거를 Event로 추적

---

## 2. 핵심 설계 철학

CoWater의 모든 설계는 5가지 핵심 철학을 기반합니다.

| 철학                                 | 설명                                                      | 상세                                                                                           |
| ------------------------------------ | --------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| **1️⃣ Action Abstraction**            | 하드웨어 종속적 명령 대신 추상화된 `required_action` 사용 | [principles.md#1️⃣](core/principles.md#1️⃣-추상화된-행동-계층-action-abstraction)                |
| **2️⃣ Decoupling Planning/Execution** | Proposal(계획)과 Mission(실행)의 엄격한 분리              | [principles.md#2️⃣](core/principles.md#2️⃣-계획과-실행의-분리-decoupling-planning-and-execution) |
| **3️⃣ Inter-Agent Collaboration**     | `AgentConnection`을 통한 Device Agent 간 동적 협력        | [principles.md#3️⃣](core/principles.md#3️⃣-에이전트-간-협업-거버넌스-inter-agent-collaboration)  |
| **4️⃣ Event-Based Traceability**      | 모든 중요 변화를 Event로 객체화하여 추적성 확보           | [principles.md#4️⃣](core/principles.md#4️⃣-사건-기반의-상태-추적성-event-based-traceability)     |
| **5️⃣ Bridge the Gap**                | 물리적 제약(통신 단절, 대역폭 제한)을 소프트웨어로 보상   | [principles.md#5️⃣](core/principles.md#5️⃣-물리적-제약의-소프트웨어적-극복-bridge-the-gap)       |

👉 자세한 설명: [**설계 원칙 문서**](core/principles.md)

---

## 3. 전체 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                       User Interface                          │
│  (Proposal 승인, Mission 추적, Event 확인, Override)          │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│                    System Agent Layer                         │
│  (의도 해석 → Proposal 생성 → Task 분배 → 규칙 실행)         │
└─────────────────────────────────────────────────────────────┘
              ↙                                    ↖
    ┌──────────────────┐              ┌──────────────────┐
    │ Middle-layer      │              │   Direct         │
    │ Agent Layer       │              │   Connection     │
    │ (Relay, Proxy)    │              │                  │
    └──────────────────┘              └──────────────────┘
            ↓                                 ↓
    ┌──────────────────────────────────────────────────────┐
    │         Device Agent Layer                            │
    │  (Device 1, Device 2, ... Device N)                  │
    │  - Task 수행 판단 및 실행                              │
    │  - 로컬 안전 행동 (Edge-Side Resilience)              │
    └──────────────────────────────────────────────────────┘
            ↓
    ┌──────────────────────────────────────────────────────┐
    │    Physical Devices & Sensors (USV, AUV, ROV...) │
    └──────────────────────────────────────────────────────┘

Registry Server (공용 상태 저장소 - 모든 레이어에서 접근)
├─ Device 등록 정보
├─ Mission / Task 상태
├─ Event (모든 의사결정 기록)
└─ A2A 통신 로그

Stream Layer (Moth - 실시간 데이터)
├─ A2A 메시지
├─ Telemetry
└─ Healthcheck
```

---

## 4. 핵심 컴포넌트와 역할

### 4.1 Agent 계층

| 계층                   | 역할                            | 책임                                   |
| ---------------------- | ------------------------------- | -------------------------------------- |
| **System Agent**       | 전체 운영 판단 및 조율          | Proposal 생성, Mission 관리, Rule 실행 |
| **Middle-layer Agent** | 직접 통신 불가능한 Device 중계  | Device 등록 중계, Task 전달, 상태 보고 |
| **Device Agent**       | 개별 디바이스 제어 및 상태 관리 | Task 수행 판단, 실행, 로컬 안전 행동   |

👉 자세한 책임과 규칙: [**도메인 모델**](core/domain-model.md), [**역할 정의**](core/principles.md#역할-정의-who-what)

### 4.2 핵심 데이터 모델

| 개념                | 설명                                                         | 상세                                        |
| ------------------- | ------------------------------------------------------------ | ------------------------------------------- |
| **Device**          | 물리 무인체 (USV, AUV, ROV)                                  | [schema.md#device](core/schema.md)          |
| **Proposal**        | 여러 솔루션 세트 (PROPOSED → PENDING_APPROVAL → APPROVED)    | [schema.md#proposal](core/schema.md)        |
| **Mission**         | 승인된 Proposal을 기반으로 실행되는 임무                     | [schema.md#mission](core/schema.md)         |
| **Task**            | Mission의 세부 실행 항목 (PENDING → ASSIGNED → IN_PROGRESS)  | [schema.md#task](core/schema.md)            |
| **Event**           | 시스템에서 발생한 중요한 사건 (Rule Engine 트리거)           | [schema.md#event](core/schema.md)           |
| **AgentConnection** | Device Agent 간 협력 관계 (RELAY, COORDINATE 등, 소프트삭제) | [schema.md#agentconnection](core/schema.md) |

👉 전체 데이터 구조: [**스키마 정의**](core/schema.md)

---

## 5. 핵심 운영 프로세스

CoWater의 5가지 시나리오별 프로세스:

### 5.1 Device Lifecycle (장비 생명주기)

**등록 → 준비 → 운영 → 제거**

- 1-1 Device 등록
- 1-2 Device 온라인 상태 관리
- 1-3 Device 제거
- 1-4 Device 복구

👉 [**Device Lifecycle**](scenarios/lifecycle.md)

### 5.2 Operation (운영 흐름)

**명령 해석 → 계획(Proposal) → 승인 → 실행(Mission) → 결과 처리**

- 2-1 사용자 명령 해석
- 2-2 System Agent의 업무 추천
- 2-3 Device 선택 (Capability-Driven Assignment)
- 2-4 Mission 생성 및 Task 분해
- 2-5 Task 할당 및 실행
- 2-6 실행 결과 보고
- 2-7 Operation Plan 관리
- 2-8 통신 복구 후 상태 동기화
- 2-9 Business Logic 실행 (Policy/Rule/Config)
- 2-10 Failed Task 재실행

👉 [**Operation 프로세스**](scenarios/operation.md)

### 5.3 Exception Handling (예외 상황)

**위험 감지 → 격리 및 격상 → 자동 대응 또는 사용자 승인**

- 3-1 LOST/OFFLINE 처리
- 3-2 Communication Failure 처리
- 3-3 Resource Shortage (배터리, 스토리지 등)
- 3-4 Sensor Failure 처리
- 3-5 CRITICAL_HAZARD 프리엠션 및 긴급 정지

👉 [**Exception Handling**](scenarios/exceptions.md)

### 5.4 Reporting (기록 및 분석)

**Event 기록 → Report 생성 → 분석 및 피드백**

- 4-1 Event 기록
- 4-2 Mission/Task 이력 추적
- 4-3 Report 생성
- 4-4 운영 이력 조회
- 4-5 실패 분석
- 4-6 사용자 피드백 수집
- 4-7 개선 후보 추적

👉 [**Reporting & Analytics**](scenarios/reporting.md)

### 5.5 Administration (시스템 관리)

**설정 관리 → 정책 관리 → 모니터링**

- 5-1 AgentConnection 관리 (거리/신호/배터리/지연 임계값)
- 5-2 사용자/권한 관리 (ADMIN/OPERATOR/VIEWER)
- 5-3 시스템 설정 (heartbeat, timeout, min_battery 등)
- 5-4 문제 감지 설정 (debouncing, check interval)
- 5-5 자동 대응 정책 (Policy/Rule/Config)
- 5-6 업무 추천 우선순위 (가용성/배터리/거리/성공율)
- 5-7 승인 요구사항 (위험도/지속시간/구역별)

👉 [**Administration & Configuration**](scenarios/administration.md)

---

## 6. 아키텍처 결정 기록

모든 핵심 아키텍처 결정은 ADR(Architecture Decision Record)로 기록됩니다.

- **ADR-000**: [아키텍처 결정 색인](adr/ADR-000-index.md)
- **ADR-001**: [5가지 핵심 설계 철학](adr/ADR-001-core-design-philosophy.md)
- **ADR-002**: [Proposal as Solution Set](adr/ADR-002-proposal-as-solution-set.md)
- **ADR-003**: [Capability-Driven Task Assignment](adr/ADR-003-capability-driven-task-assignment.md)
- **ADR-004**: [Agent Endpoint Management](adr/ADR-004-agent-endpoint-management.md)
- **ADR-005**: [Event-Triggered Rule Execution](adr/ADR-005-event-triggered-rule-execution.md)
- **ADR-006**: [Adaptive Autonomy Migration Path](adr/ADR-006-adaptive-autonomy-migration-path.md)

👉 [**전체 ADR 색인**](adr/ADR-000-index.md)

---

## 7. 핵심 설계 원칙 (10가지)

설계 원칙은 모든 기능 구현의 기준입니다.

1. **Event는 사건 기록이면서 Rule 트리거**
2. **Proposal은 여러 솔루션 세트** (조합 불가, 사용자는 선택만)
3. **Mission은 승인 후 실제 실행 단위** (Proposal 수정 후 실행 불가)
4. **Task는 PENDING → ASSIGNED → IN_PROGRESS → COMPLETED/FAILED**
5. **Device는 물리 자원, Agent는 지능형 제어 주체**
6. **Device Agent는 자신의 Device만 직접 제어**
7. **AgentConnection은 Device Agent 간 협력** (System ↔ Device가 아님)
8. **Sensor는 stream endpoint 정보만 관리**
9. **Policy/Rule/Config로 자동화 수준 조절** (코드 수정 X)
10. **모든 의사결정은 Event 기반으로 추적**

👉 [**상세 설계 원칙**](core/principles.md#📋-핵심-설계-원칙-10가지)

---

## 8. 자동화 수준 (Phase Model)

CoWater는 Proposal-Mission 분리를 통해 단계적 자동화를 지원합니다.

```
Phase 1: Manual Approval
  └─ 모든 Proposal은 사용자 승인 필요

Phase 2: Partial Automation
  └─ 정책이 정의된 상황에서만 자동 Mission 생성/실행
  └─ LOW_BATTERY, CRITICAL_HAZARD 등 사전 정의된 규칙만 자동화

Phase 3: Full Autonomous
  └─ Device 자율성 강화
  └─ AI 기반 정책 학습
  └─ 최소 사용자 개입
```

각 단계는 **코드 수정 없이** Policy/Rule/Config 변경으로 전환 가능합니다.

👉 [**Adaptive Autonomy**](adr/ADR-006-adaptive-autonomy-migration-path.md)

---

## 9. 통신 모델

### 9.1 A2A (Agent-to-Agent)

- Agent 간 의도적 상호작용: Mission, Task, Event 전달
- 모든 A2A 메시지 로깅

### 9.2 Moth (Stream Layer)

- 실시간 데이터 전달: A2A, Telemetry, Healthcheck
- 구현: WebSocket 기반 pub-sub (wss://cobot.center:8287)

### 9.3 Registry Server

- 공용 상태 저장소: Device, Mission, Task, Event, Alert, Insight
- 모든 레이어에서 접근 가능한 Single Source of Truth

---

## 10. 상태 소유권 (Canonical Owner)

| 정보                       | 소유자                  |
| -------------------------- | ----------------------- |
| Device 등록 정보           | Registry                |
| Mission/Task 상태          | Registry                |
| Event (모든 의사결정 기록) | Registry                |
| Device 로컬 Task 실행 상태 | Device Agent            |
| 센서 상태 (1차)            | Device Agent            |
| 센서 데이터 스트림         | Device 또는 별도 저장소 |

**규칙**: 같은 정보는 하나의 Canonical Owner만 가짐. 다중 저장 시 동기화 규칙 명시.

---

## 11. 설계 원칙 리뷰 체크리스트

새 기능 구현 시 확인 사항:

- [ ] Agent 계층 구조 위반 안 함?
- [ ] 각 Agent이 자신의 리소스만 직접 제어?
- [ ] Device Agent가 Task 수행 가능 여부를 최종 판단?
- [ ] Event/Alert/Insight 개념 구분?
- [ ] Alert 중복 방지를 위한 fingerprint?
- [ ] 정책 없는 상황에서 자동 실행 안 함?
- [ ] 상태의 Canonical Owner 명확?

👉 자세한 체크리스트: [**principles.md - 리뷰 가이드**](core/principles.md)

---

## 12. 향후 확장 (Out of Scope)

현재 설계에 포함되지 않는 항목 (향후 확장):

- 세분화된 사용자 권한 체계
- Soul.md 기반 자동 정책 학습
- 고도화된 센서 신뢰도 모델
- 전역 스케줄 최적화
- Middle-layer Agent의 로컬 자율 운영 강화

---

## 13. 문서 구조

```
docs/
├─ SYSTEM_ARCHITECTURE.md (이 문서)
├─ roadmap.md
├─ adr/
│  ├─ ADR-000-index.md
│  ├─ ADR-001-core-design-philosophy.md
│  ├─ ADR-002-proposal-as-solution-set.md
│  ├─ ADR-003-capability-driven-task-assignment.md
│  ├─ ADR-004-agent-endpoint-management.md
│  ├─ ADR-005-event-triggered-rule-execution.md
│  └─ ADR-006-adaptive-autonomy-migration-path.md
├─ core/
│  ├─ principles.md (5대 철학 + 10가지 원칙 + 역할 정의)
│  ├─ domain-model.md (엔티티 관계, 상태 다이어그램)
│  └─ schema.md (14개 데이터 모델 정의)
└─ scenarios/
   ├─ lifecycle.md (1: Device Lifecycle)
   ├─ operation.md (2: Operation Workflow)
   ├─ exceptions.md (3: Exception Handling)
   ├─ reporting.md (4: Reporting & Analytics)
   └─ administration.md (5: Administration)
```

---

## 14. 빠른 시작

1. **철학 이해**: [설계 원칙](core/principles.md) 읽기
2. **데이터 모델**: [스키마](core/schema.md) 확인
3. **구체적 프로세스**: [scenarios/](scenarios/) 폴더의 5개 문서
4. **아키텍처 결정**: [ADR 목록](adr/ADR-000-index.md)
5. **전체 개요**: [System Architecture](SYSTEM_ARCHITECTURE.md) (이 문서)

---

## 15. 최종 요약

CoWater는 **5가지 핵심 철학 기반의 Event-Driven, Proposal-Mission 분리 아키텍처**입니다.

- ✅ **다양한 해양 무인체 통합 제어** (Action Abstraction)
- ✅ **사용자 승인과 자동화의 점진적 전환** (Decoupling, Adaptive Autonomy)
- ✅ **복잡한 협력 미션 지원** (AgentConnection)
- ✅ **모든 의사결정의 추적 가능성** (Event-Based Traceability)
- ✅ **통신 불안정 환경 대응** (Bridge the Gap)

**다음 단계**: [로드맵](roadmap.md)에서 구현 계획 확인
