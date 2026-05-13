# 설계 원칙 (Design Principles)

CoWater 시스템의 핵심 설계 원칙과 책임, 역할을 정의합니다.  
**기반**: [ADR-001: Core Design Philosophy](../adr/ADR-001-core-design-philosophy.md)

---

## 🎯 5가지 핵심 철학 (Why We Design This Way)

### 1️⃣ **추상화된 행동 계층 (Action Abstraction)**

**원칙**:

> 시스템은 장비의 하드웨어 종속적인 명령을 직접 다루지 않습니다.  
> 대신 `required_action`이라는 추상화된 인터페이스로 소통합니다.

**왜 필요한가?**

- USV, AUV, ROV 등 서로 다른 기종이 들어와도 시스템은 동일한 로직으로 통제 가능
- 새로운 기종이 추가될 때 핵심 로직(Mission, Proposal, Task) 수정 불필요
- 이종 기종의 **통합 관리(Heterogeneous Multi-Domain Support)** 실현

**구현**:

```
Device.actions = ["MOVE_TO", "HIGH_RES_SCAN", ...]  ← 각 장비가 선언
System Agent = "이 actions 안에서만 Task 할당"       ← 시스템은 이 목록 신뢰
```

**효과**:

- 첫 번째: Device 추가 시 `actions[]` 등록만으로 통합
- 두 번째: 기존 Mission/Task 로직 수정 불필요

---

### 2️⃣ **계획과 실행의 분리 (Decoupling Planning and Execution)**

**원칙**:

> 작업을 **정하는 단계(Proposal)**와 **수행하는 단계(Mission)**를 엄격히 분리합니다.

**왜 필요한가?**

- 현재: 사용자 승인 기반 (Manual)
- 미래: AI 자동 승인 기반 (Autonomous)  
  → **이 분리 덕분에 시스템 전체를 갈아엎지 않고도 자동화 수준을 단계적으로 상향 가능**

**구현**:

```
Proposal (Planning)       ← 여러 솔루션 세트 제시, 사용자 선택
  ↓
사용자 승인              ← 인간의 판단
  ↓
Mission (Execution)      ← 실제 작업 단위, Device 제어
```

**효과**:

- Policy/Rule 설정만으로 자동화 수준 조절 (코드 수정 X)
- Phase 1 (Manual) → Phase 2 (Partial Auto) → Phase 3 (Full Auto)로 진화 가능

---

### 3️⃣ **에이전트 간 협업 거버넌스 (Inter-Agent Collaboration)**

**원칙**:

> 개별 장비(Device Agent)는 고립된 존재가 아니라,  
> `AgentConnection`을 통해 동적으로 협력 관계를 맺습니다.

**왜 필요한가?**

- 단일 장비의 한계를 넘어 **복합 미션 수행** (통신 중계, 협업 관측, 리더-팔로워 등)
- 수중 환경에서 직접 통신 불가능한 장비(ROV 등)를 **Relay를 통해 논리적으로 연결**
- 이것이 CoWater의 핵심 경쟁력

**구현**:

```
AgentConnection 타입:
├─ RELAY: ROV(통신 불가) ← USV(중계) ← System
├─ COORDINATE: Device-A와 Device-B가 시간 동기화
├─ SHARE_DATA: 센서 데이터 공유
└─ LEADER_FOLLOWER: 임시 리더/팔로워
```

**효과**:

- 물리적으로 고립된 장비도 논리적으로 시스템에 통합
- 복합 해양 미션 수행 가능

---

### 4️⃣ **사건 기반의 상태 추적성 (Event-Based Traceability)**

**원칙**:

> 시스템에서 발생하는 모든 의미 있는 변화는 `Event`로 객체화됩니다.

**왜 필요한가?**

- 단순히 "현재 상태"를 아는 것을 넘어, **"왜 이 상태가 되었는가?"를 추적** 가능
- Rule Engine의 **트리거(구동 에너지)**로 작동
- 운영 이력, 감사, 사후 리포팅의 근거 제공

**구현**:

```
Event: 모든 중요한 사건 객체화
├─ SYS_INTENT_CLASSIFIED (사용자 요청 해석)
├─ SYS_ANOMALY_DETECTED (배터리 부족, 오프라인, 긴급 위험 등)
├─ SYS_TASK_RESULT (작업 완료/실패/거절)
├─ SYS_MISSION_UPDATED (Mission 상태 변화)
└─ ...

Rule Engine: Event 발생 시 실행
└─ "SYS_ANOMALY_DETECTED(anomaly_type=LOW_BATTERY) → RETURN_TO_BASE Mission 생성"
```

**효과**:

- 모든 의사결정의 원인 추적 가능 (Root Cause Analysis)
- Event-Triggered System으로 효율성 확보 (매 Heartbeat 체크 X, 필요한 순간만)

---

### 5️⃣ **물리적 제약의 소프트웨어적 극복 (Bridge the Gap)**

**원칙**:

> 직접 통신이 불가능하거나 불안정한 해양 환경의 물리적 제약을  
> 논리적 연결과 에지 자율성으로 보상합니다.

**왜 필요한가?**

- 수중/해상 환경: 통신 불안정, 대역폭 제한, 높은 지연
- 이러한 현실을 **인정하고 설계**해야만 실제로 작동하는 시스템 가능

**구현**:

```
Physical Constraint      Software Solution
├─ 직접 통신 불가       → AgentConnection (Relay, Proxy)
├─ 네트워크 단절         → Edge-Side Resilience (Device가 로컬 진행, 복귀 시 동기화)
├─ 복잡한 제어 명령      → 자연어 기반 Proposal (사용자는 의도만 전달)
└─ 장비 다양성           → Action Abstraction (하나의 로직으로 통제)
```

**효과**:

- 불안정한 환경에서도 **미션 연속성 보장**
- 사용자: 장비 제어 세부사항 신경 쓰지 않음 (의도만 전달)
- Device: 중앙 연결 끊겨도 할당받은 Task 완료 가능

---

## 📋 핵심 설계 원칙 (10가지 - CoWater의 헌법)

> **이 원칙들은 모든 아키텍처 결정, 기능 구현, 운영 프로세스의 근거입니다.**  
> 의심될 때는 이 원칙으로 돌아가세요.

### **P1. Agent 직접 제어 원칙 (Agent Direct Control)**

**원칙**:

> 각 Agent는 **자신이 소유한 자원만 직접 제어**합니다.  
> 다른 Agent의 자원에 접근하려면 해당 Agent와 명시적으로 소통해야 합니다.

**구체화**:

- System Agent는 디바이스 하드웨어를 직접 제어하지 않음 → Device Agent를 통함
- Device Agent는 자신의 Device만 제어 → 다른 Device 제어 불가
- Middle-layer Agent는 하위 Device를 직접 조작하지 않음 → 해당 Device Agent를 통함

**왜 필요한가?**

- **이종 기종 통합 관리의 핵심**: USV, AUV, ROV 등 다양한 플랫폼을 하나의 원칙으로 관리
- 각 Agent이 자신의 영역에만 책임을 가지므로 경계가 명확
- Device 추가 시 기존 로직 수정 불필요 (Action Abstraction과 결합)

**효과**:

- Device 종류별 복잡한 제어 로직을 System Agent에서 격리
- 새로운 Device 추가 시 자신의 actions[]만 등록하면 즉시 통합

**관련 ADR**: [ADR-001](../adr/ADR-001-core-design-philosophy.md), [ADR-003](../adr/ADR-003-capability-driven-task-assignment.md)

---

### **P2. 책임 경계 명확화 원칙 (Clear Responsibility Boundary)**

**원칙**:

> System Agent가 모든 것을 검증하고 통제하지 않습니다.  
> 각 Agent은 자신의 영역에서 1차 책임을 가집니다.

**구체화**:

- Device Agent는 자신의 상태, capability, Task 수행 판단을 책임짐
- System Agent는 전체 조율과 의사결정을 책임짐
- 센서 상태의 1차 판단은 Device Agent에게 있음

**왜 필요한가?**

- 중앙 집중식 설계의 병목 현상 방지
- Device의 로컬 정보(e.g., 배터리 상태)를 가장 정확히 알고 있는 주체가 판단

**효과**:

- 네트워크 단절 상황에서도 Device Agent는 자신의 영역에서 자율적으로 행동 가능
- System Agent의 과부하 방지

---

### **P3. 보고 기반 운영 원칙 (Report-Based Operation)**

**원칙**:

> System Agent는 **Device Agent가 보고한 정보**를 기준으로만 운영합니다.  
> 보고되지 않은 정보를 임의로 추측하지 않습니다.

**구체화**:

- Device의 위치, 배터리, 센서 상태는 Device Agent의 보고에만 의존
- "아마 ~일 것 같다"는 판단은 하지 않음
- capability 정보(Device.actions[])는 등록 시점의 선언을 신뢰

**왜 필요한가?**

- 불확실한 추정으로 인한 잘못된 Task 할당 방지
- Device의 정확한 상태 파악이 미션 성공의 기초

**효과**:

- Device Agent가 보고할 책임을 명확히 함
- System Agent의 의사결정 근거가 명확

---

### **P4. Mission 중심 운영 원칙 (Mission-Centric Operation)**

**원칙**:

> CoWater는 단순 명령 전달 시스템이 아니라 **Mission 중심의 운영 플랫폼**입니다.

**구체화**:

- 각 Mission은 Task로 구성되며, 실행 흐름이 명확
- Mission 상태는 사용자가 추적할 수 있어야 함

**왜 필요한가?**

- 단순한 명령/응답이 아니라 목표 달성을 위한 계획적 수행
- Mission 기반 추적으로 복잡한 운영을 가시화

**효과**:

- Mission Timeline을 통한 전체 운영 이력 관리
- 실패 시 어느 Task에서 어떻게 실패했는지 명확

---

### **P5. Task 수행 가능성 최종 판단 원칙 (Final Task Feasibility Decision)**

**원칙** (5번 사용자 피드백 기반):

> System Agent가 계획(Proposal) → 할당(Task 전달)까지 담당  
> Device Agent가 Task 수신 후 **최종 판단(실행 가능 여부)** 담당

**구체화**:

**System Agent의 역할** (계획가):

- Device.actions[] 목록에 required_action이 있는가? (Strict Capability Matching)
- Device의 현재 status가 작업 가능 상태인가? (ONLINE, DEGRADED 등)
- 현재 배터리, 위치가 충분한가?
- 이미 다른 Mission에 할당되어 있지 않은가?
- 조건을 만족하는 Device를 찾아 Task 생성 및 할당

**Device Agent의 역할** (최종 판단자 - System Agent가 확인하지 않는 항목 판단):

- Task를 수신(ASSIGNED 상태)한 후 실제 수행 가능 여부를 **최종 판단**
- **IN_PROGRESS**: Task 실행 시작 (수행 가능 판단)
- **ABORTED**: Task 거절 (schema.md 기준 - reason 포함)
  - **Sensor 확인**: 필요한 센서 부재 또는 고장 (System Agent는 확인 범위 외)
  - **배터리 정확도**: 최신 배터리 수치로 다시 판단
  - **이미 할당됨**: 다른 Mission 할당 여부 실시간 확인
  - **안전 규칙**: Device의 로컬 안전 규칙 위반 판단
- ⚠️ ABORTED는 Task가 이미 Device로 전달된 후 판단 (PENDING/ASSIGNED 상태)

**ABORTED vs FAILED의 차이** (schema.md 기준):

- **ABORTED**: Task 전송받은 후 실행 전에 수행 불가능 판단 → Device Agent가 거절 (상태: PENDING/ASSIGNED → ABORTED)
- **FAILED**: Task 실행 중(IN_PROGRESS)에 오류 발생 또는 완료 불가 → Device Agent가 실패 보고 (상태: IN_PROGRESS → FAILED)

**왜 필요한가?**

- **Strict Capability Matching의 근거**: Device는 선언한 것만 할 수 있다는 신뢰
- 통신 지연이나 상태 변화로 인한 예상치 못한 실패 방지
- Device Agent가 자신의 상태를 가장 정확히 알고 있음 (로컬 센서, 안전 규칙 등)

**효과**:

- 불가능한 Task 할당 사전 방지 (System 계획 → Device 최종 검증)
- Task 실패율 감소
- Device Agent의 자율성 확보

**관련 ADR**: [ADR-003](../adr/ADR-003-capability-driven-task-assignment.md)

---

### **P6. 정책 기반 자동 대응 원칙 (Policy-Based Autonomous Response)**

**원칙**:

> 사전 정의된 정책이 있는 Critical 상황에서만 제한적 자동 대응이 가능합니다.  
> 정책이 없는 상황에서는 Agent가 분석과 추천만 할 수 있으며, 사용자 승인 없이 자동 실행하지 않습니다.

**구체화**:

- Policy가 정의된 경우: `SYS_ANOMALY_DETECTED(anomaly_type=LOW_BATTERY)` → RETURN_TO_BASE Mission 자동 생성
- Policy가 없는 경우: "배터리가 낮으니 귀환하시겠습니까?" 제안 (사용자 선택)
- `SYS_ANOMALY_DETECTED(anomaly_type=CRITICAL_HAZARD)`는 예외: 즉시 자동 대응 후 보고

**왜 필요한가?**

- Phase 1 (Manual) → Phase 2 (Partial Auto) → Phase 3 (Full Auto)의 점진적 전환
- 정책 없이 자동화하면 예상치 못한 행동 발생 가능
- 사용자가 시스템을 신뢰할 수 있는 근거

**효과**:

- 자동화 수준을 코드 수정 없이 Policy/Rule/Config로 조절
- 운영 안정성 확보

**관련 ADR**: [ADR-006](../adr/ADR-006-adaptive-autonomy-migration-path.md)

---

### **P7. 사용자 결정 우선 원칙 (User Decision Priority)**

**원칙**:

> 사용자 명령은 시스템 판단보다 우선될 수 있습니다.  
> **단, 다음의 경우는 예외입니다:**
>
> 1. System Agent는 위험을 명확히 경고하고 기록해야 함
> 2. Device Agent는 물리적으로 수행 불가능한 Task는 거절 가능

**구체화**:

- 사용자가 "이 Device에 이 Task를 할당하라"고 명령하면, System은 우선 수행
- 하지만 시스템이 위험을 감지했다면 경고: "배터리 10%인데 먼 곳으로 보내려 합니다"
  - 이것은 정책상 경고이지만, 사용자의 override 선택을 존중함
- Device Agent는 **실제로 수행 불가능한 경우** 거절:
  - **물리적 불가능**: 센서가 없음, 깊이/거리 초과, 하드웨어 오류
  - (배터리 20% 미만 같은 정책 판단은 System과 협의하지만, 절대적 위험이면 거절 가능)
- 모든 override 사항은 기록됨

**왜 필요한가?**

- 사용자가 현장 상황을 더 잘 알 수도 있음
- System의 과도한 제약으로 운영 유연성 상실 방지
- 하지만 위험은 기록하여 책임 추적성 확보

**효과**:

- 운영자의 자율성 확보
- 위험 인식과 기록을 통한 학습 가능
- 사용자-시스템 간의 협력적 운영

---

### **P8. 최소 중앙 상태 원칙 (Minimal Central State)**

**원칙**:

> 중앙 시스템(Registry Server)은 모든 Raw Data와 센서 데이터를 지속 구독하지 않습니다.  
> 운영에 필요한 **최소 상태, Event, Mission 상태, Task 결과**만 관리합니다.

**구체화**:

- ✅ 관리: Device 위치, 배터리 %, Mission/Task 상태, Event
- ❌ 비관리: Raw 센서 데이터(대용량), 영상 스트림, Real-time 텔레메트리 전체
- 센서 데이터는 별도 저장소로 관리

**왜 필요한가?**

- 네트워크 대역폭과 Registry 용량 최소화
- 해양 환경의 통신 제약 극복
- 필요한 정보만 빠르게 조회 가능

**효과**:

- 빠른 의사결정
- 불안정한 네트워크에서도 핵심 운영 유지

---

### **P9. 기록 가능성 원칙 (Traceability)**

**원칙**:

> 모든 중요한 판단, 승인, 거절, 실패, 결과는 추적 가능하게 기록되어야 합니다.

**구체화**:

- 기록 대상: Device 등록, Role 설정, Proposal 생성, 승인/거절, Task 할당/거절, 실패, override
- 기록 형태: Event, Mission Timeline, Task Result
- 기록 목적: 원인 분석, 감사, 개선 후보 발굴

**왜 필요한가?**

- 실패 원인 분석 (Root Cause Analysis)
- 규제 준수 및 감사
- 운영 개선 데이터 수집

**효과**:

- "왜 이런 일이 일어났나?"를 항상 추적 가능
- 반복되는 문제 조기 발견

**관련 ADR**: [ADR-005](../adr/ADR-005-event-triggered-rule-execution.md)

---

### **P10. 구현 세부 비노출 원칙 (Implementation Detail Abstraction)**

**원칙**:

> 시스템의 상위 운영 도메인은 **Mission, Step, Task**까지만 다룹니다.  
> 디바이스 내부의 저수준 제어 명령(e.g., "모터 RPM을 X로 설정")은 **Device Agent의 내부 구현 세부사항**으로 취급하며, System Agent가 관여하지 않습니다.

**구체화**:

- System Agent가 하는 것:
  - "MOVE_TO (x, y, z)" Task 할당
  - "HIGH_RES_SCAN (area_id)" Task 할당
  - 위치, 배터리, 상태 조회
- System Agent가 하지 않는 것:
  - 모터 제어
  - 센서 캘리브레이션
  - 펌웨어 업그레이드 명령
- Device Agent가 해석:
  - "MOVE_TO"를 자신의 추진 시스템에 맞게 구현
  - USV는 스크루 제어, AUV는 스러스터 제어 등 각각 다르게 수행

**왜 필요한가?**

- Action Abstraction의 핵심: 하드웨어 다양성을 추상화
- Device 내부 구현이 바뀌어도 System Agent의 로직 수정 불필요
- 각 Device Agent가 자신의 플랫폼에 최적화된 구현 가능

**효과**:

- 새로운 Device 추가 시 System Agent 수정 불필요
- Device 펌웨어 업그레이드가 System에 영향 없음
- 진정한 이종 기종 통합 관리 실현

**관련 ADR**: [ADR-001](../adr/ADR-001-core-design-philosophy.md)

---

### **종합: P1~P10의 관계도**

```
P1 (Agent 직접 제어)
  ↓ 기반이 되어
P2 (책임 경계 명확화)
  ↓ 함께 실현
P3 (보고 기반 운영)

P5 (Task 수행 판단 - Device Agent)
  ↑
P10 (구현 세부 비노출) ← P1과 함께 이종 기종 통합 실현

P4 (Mission 중심)
  ↓ 운영 흐름
P6 (정책 기반 자동 대응)
  ↓ 점진적 자동화
P7 (사용자 우선 + 안전장치)

P8 (최소 중앙 상태) + P9 (기록)
  ↓
안정적이고 추적 가능한 시스템
```

---

## 역할 정의 (WHO/WHAT)

| 역할                | 책임                                          | 경계                         |
| ------------------- | --------------------------------------------- | ---------------------------- |
| **User**            | 자연어로 의도 전달                            | 장비 제어 세부사항 X         |
| **System Agent**    | 의도를 Proposal로 구체화, Rule 실행, 의사결정 | 실제 Device 제어 X           |
| **Device Agent**    | 자신의 Device 제어, Task 수행                 | 다른 Device 제어 X           |
| **Device**          | 할당받은 Task 실행                            | 다른 Task와의 조율 X         |
| **AgentConnection** | Device Agent 간 협력 관계 정의                | 실제 통신 중계 아님 (설정만) |

---

## 참고

- **[ADR-001](../adr/ADR-001-core-design-philosophy.md)**: 5가지 핵심 철학 상세
- **[domain-model.md](domain-model.md)**: 각 엔티티의 역할과 관계
- **[schema.md](schema.md)**: 데이터 구조 정의
- **[scenarios/](../scenarios/)**: 구체적 프로세스 흐름
