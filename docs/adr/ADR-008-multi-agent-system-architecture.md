# ADR-008: 다중 에이전트 시스템 아키텍처

**상태**: Accepted  
**작성일**: 2026-05-13  
**검토자**: CoWater Architecture Team

---

## 상황

CoWater는 자율 해양 무인기 운영을 위해 복잡한 의사결정 체계가 필요합니다:

1. **사용자 자연어 처리** → 명령 해석 및 의도 추출
2. **미션 계획** → 여러 장비를 활용한 작업 시뮬레이션
3. **정책 기반 자동화** → 규칙 엔진 기반 자동 대응
4. **장비 상태 관리** → 심박 모니터링, 통신 관리, 데이터 수집
5. **이상 감시** → 시스템 건전성 모니터링, 자동 알림
6. **데이터 리포팅** → 분석, 통계, 사후 분석

기존의 모놀리식 설계는 이들 책임을 혼재시켜 복잡도가 높았으며, 새로운 기능 추가 시 영향 범위를 예측하기 어려웠습니다. 또한 자동화 수준을 높이는 과정에서 기존 코드를 대폭 수정해야 하는 한계가 있었습니다.

---

## 결정

CoWater는 **책임 기반 다중 에이전트 아키텍처**로 전환합니다. 6개의 전문 에이전트가 명확한 책임 영역과 데이터베이스 소유권을 가집니다.

### **핵심 원칙**

> **RequestHandler는 사용자 요청의 처리 책임자이며, 각 도메인 데이터의 변경은 해당 도메인을 소유한 전문 Agent가 수행한다.**

이를 통해 다음 생명주기를 완벽하게 커버합니다:  
**입력 → 판단 → 계획 → 실행 → 감시 → 기록**

---

## 에이전트 아키텍처

### **1️⃣ RequestHandler (운영 요청 처리)**

**책임**: 사용자 자연어 명령의 해석 및 처리 경로 결정

**입력**:
- 사용자 자연어 명령

**처리**:
1. **명령 해석** (Intent, Entity, Permission 추출)
2. **경로 결정**:
   - 경로 A: 간단한 조회 → DB 읽기 → 직접 응답
   - 경로 B: 복잡한 처리 → 해당 전문 Agent 위임

**출력**:
- 간단한 조회: `{type: RESPONSE, data: {...}, timestamp}`
- 복잡한 처리: `{type: COMMAND_REQUEST, target_agent, command, timestamp}`

**DB 권한**: Read-only (모든 테이블)

---

### **2️⃣ DeviceBridge (장비 브릿지) - 양방향 통신**

**책임**: 물리 장비와의 양방향 통신 중계, 상태 동기화 (시스템의 심장)

**입력 (양방향)**:

【MissionPlanner로부터】
- Task 할당 요청: "Device-01에 Task-1 할당해줘"

【Device Agent로부터 - 정기적 및 즉각적】
- Heartbeat (정기적, 예: 5초마다): 배터리, 신호강도, 위치, 온도, 센서 데이터
- Task Result (Task 완료/실패): 작업 결과 및 산출물
- Reconnect Message (오프라인 후): "다시 연결됨"
- Problem Report (즉각적): 오류, 센서 고장, 물리적 문제 알림

**처리**:

【송신 방향】
1. **Task 할당** → Device에 A2A 프로토콜로 전달
   - MissionPlanner의 명령 → Device Agent에게 HTTP POST /task

【수신 방향】
2. **Heartbeat 수신** (정기적) → Device 상태 즉시 갱신
   - 배터리, 신호강도, 위치, 온도, 센서 데이터
   - SystemSentinel이 모니터링할 수 있도록 Event로 발행

3. **Task Result 수신** → 작업 결과 수집
   - Task 완료: 성공 상태, 결과 데이터
   - Task 실패: 실패 사유, 오류 코드
   - MissionPlanner에 즉시 보고

4. **Problem Report** (즉각적) → 긴급 문제 알림
   - 센서 고장, 배터리 급저하, 물리적 충돌 감지
   - 정규화된 Event로 발행 → SystemSentinel 긴급 처리

**출력 (Event로 발행)**:
- `DEVICE_HEALTHCHECK` → SystemSentinel 구독 (지속적 모니터링)
- `ENV_STATE_CHANGED` → SystemSentinel 구독 (환경 상태 변화 전달)
- `SYS_TASK_COMPLETED` / `SYS_TASK_FAILED` → MissionPlanner 구독 (Task 진행 추적)
- 목적지 라우팅 정보가 필요한 경우 적절한 Agent로 전달
- DB 쓰기: devices 상태 (배터리, 위치, 신호, 마지막_하트비트), sensors 센서 데이터

**경계**:
- DeviceBridge는 수신, 정규화, 전달 대상 판단까지 수행
- DeviceBridge는 anomaly를 판단하거나 `SYS_ANOMALY_DETECTED`를 발행하지 않음

**DB 권한**: Device, Sensor (읽기/쓰기)
- devices: id, name, type, status, battery, location, last_heartbeat, ...
- sensors: device_id, sensor_type, last_value, timestamp, ...

---

### **3️⃣ MissionPlanner (임무 계획)**

**책임**: 미션/태스크 설계, 실행 추적, 생명주기 관리

**입력**:
- `SYS_INTENT_CLASSIFIED` (type=MISSION)
- `SYS_POLICY_DECISION`
- `SYS_TASK_COMPLETED` / `SYS_TASK_FAILED` 이벤트 (DeviceBridge로부터)
- `SYS_AGENT_CONNECTION_CREATED` 이벤트 (SystemSentinel로부터)

**처리**:
1. **Proposal 생성** (Capability Matching, AgentConnection 확인)
2. **사용자 선택 → Mission 생성** (상태 재검증)
3. **Task 할당** → DeviceBridge에 요청
4. **진행 추적** → SYS_TASK_COMPLETED / SYS_TASK_FAILED 수신 후 상태 갱신
5. **규칙 기반 임무** (PolicyManager로부터 긴급 미션 요청 처리)

**출력**:
- `SYS_MISSION_UPDATED` 이벤트 (모든 Mission 상태 변화)
- DB 쓰기: proposals, missions, tasks

**DB 권한**: Mission, Task, Proposal (읽기/쓰기)

---

### **4️⃣ PolicyManager (정책 관리)**

**책임**: 정책/규칙 관리, 자동 대응 결정, 장비 생명주기 관리

**입력**:
- `SYS_INTENT_CLASSIFIED` (type=UPDATE, type=DELETE)
- `SYS_ANOMALY_DETECTED` (SystemSentinel로부터)

**처리**:
1. **Policy/Rule 수정** (UPDATE intent)
2. **Device 제거 프로세스** (DELETE intent)
   - Device 상태 확인 (OFFLINE 필수)
   - AgentConnection 확인
   - 진행 중 Task 취소 요청 (MissionPlanner)
   - Registry API: DELETE /devices/{device_id}
3. **Anomaly 대응** (Rule 매칭 → 자동 응답)

**출력**:
- `SYS_POLICY_DECISION` 이벤트 (MissionPlanner 요청)
- 긴급 미션 생성 요청 이벤트
- 정책 실행 추적 이벤트
- DB 쓰기: policies, rules, configs

**DB 권한**: Policy, Rule, Config (읽기/쓰기)

---

### **5️⃣ SystemSentinel (시스템 감시)**

**책임**: 시스템 건전성 모니터링, 이상 징후 감시

**입력**:
- `DEVICE_HEALTHCHECK` (DeviceBridge로부터)
- 모든 이벤트 (감시 목적)

**처리**:
- Battery < 30% → `SYS_ANOMALY_DETECTED {anomaly_type: LOW_BATTERY}`
- Signal < 30% → `SYS_ANOMALY_DETECTED {anomaly_type: SIGNAL_LOSS}`
- Heartbeat timeout → `SYS_ANOMALY_DETECTED {anomaly_type: DEVICE_OFFLINE}`
- Mission overdue → `SYS_ANOMALY_DETECTED {anomaly_type: MISSION_TIMEOUT}`
- State inconsistency → `SYS_ANOMALY_DETECTED {anomaly_type: STATE_MISMATCH}`
- Task failed → `SYS_ANOMALY_DETECTED {anomaly_type: TASK_FAILURE}`

**출력**:
- `SYS_ANOMALY_DETECTED` 이벤트 (PolicyManager 구독)
- DB 쓰기: alerts, events

**DB 권한**: Alert, Event (읽기/쓰기)

---

### **6️⃣ InsightReporter (인사이트 보고)**

**책임**: 데이터 조회, 분석, 리포트 생성

**입력**:
- `SYS_INTENT_CLASSIFIED` (type=QUERY)
- 모든 테이블 (읽기)

**처리**:
- 조건에 맞는 데이터 조회
- 통계 생성 (완료율, 실패율, 평균 시간 등)
- Report 형식으로 정리

**출력**:
- `SYS_INSIGHT_REPORT` 이벤트
- 사용자 보고

**DB 권한**: Read-only (모든 테이블)

---

## 생명주기 흐름 (입력 → 판단 → 계획 → 실행 → 감시 → 기록)

```
1. 사용자 입력 (자연어 명령)
   ↓
2. RequestHandler (운영 요청 처리)
   ├─ [경로 A] 간단한 조회 → 직접 처리
   │  └─ DB 조회 → 사용자에게 직접 응답
   │
   └─ [경로 B] 복잡한 처리 → 해당 System Agent 위임
      ↓
3. 대상 Agent (MissionPlanner, PolicyManager, ...)
   └─ 명령 실행 (Event 발행)
   ↓
4. DeviceBridge (양방향 통신 - 심장 역할)
   ├─【송신】Device Agent에게 Task 전달 (A2A 프로토콜)
   │  └─ MissionPlanner의 명령 → Device Agent로 중계
   │
   └─【수신】Device Agent로부터 상태/결과 수집 및 Event 발행
      ├─ DEVICE_HEALTHCHECK (정기적: 배터리, 신호, 위치)
      ├─ SYS_TASK_COMPLETED / SYS_TASK_FAILED (Task 완료/실패)
      ├─ ENV_STATE_CHANGED (환경 상태 변화)
      └─ 즉각적 문제 보고 (오류, 센서 이상, 안전 경고)
   ↓
5. Device Agent (각 무인체)
   ├─ Task 수행 판단 → 실행 → 결과 보고
   ├─ 정기적 Heartbeat 송신
   └─ 문제 발생 시 즉시 보고
   ↓
6. SystemSentinel (지속적 감시)
   ├─ DEVICE_HEALTHCHECK Event 모니터링 → 상태 추적
   ├─ SYS_TASK_COMPLETED / SYS_TASK_FAILED Event 분석 → Task 진행 추적
   ├─ 이상 징후 감지 (배터리 부족, 신호 손실, Heartbeat 타임아웃)
   └─ SYS_ANOMALY_DETECTED Event 발행 → PolicyManager로 연쇄
   ↓
7. InsightReporter (필요한 경우)
   └─ 모든 Event 기록 → Report 생성 → 사용자 보고
```

---

## Agent 간 통신 패턴

### **Event-Driven Architecture**

- **발행/구독**: 각 Agent은 이벤트를 발행하고, 관심 있는 Agent이 구독
- **비동기**: Agent 간 직접 호출 없음, 모두 이벤트로 통신
- **Decoupling**: 발행자와 구독자가 느슨하게 결합

### **예시 흐름: 사용자 미션 요청**

```
1. 사용자: "AUV-01 표면 정찰"
   ↓
2. RequestHandler: SYS_INTENT_CLASSIFIED {type: MISSION} 발행
   ↓
3. MissionPlanner: Proposal 생성 → `SYS_MISSION_UPDATED` 발행
   ↓
4. 사용자가 Proposal 선택 & 승인
   ↓
5. MissionPlanner: Mission 생성 → DeviceBridge에 Task 할당 요청
   ↓
6. DeviceBridge【송신】: A2A로 Device에 Task 전달
   └─ `SYS_TASK_DISPATCHED` 이벤트 발행
   ↓
7. Device Agent (AUV-01): Task 수행 판단
   ├─ Go/No-Go 판단 후
   ├─ Task 시작 전 상태 전송 (healthcheck)
   └─ Task 진행 중 정기적 healthcheck 송신
   ↓
8. DeviceBridge【수신】: Device로부터 정보 수집 및 Event 발행
   ├─ DEVICE_HEALTHCHECK Event: 배터리 80%, 신호 강도 90%
   ├─ 진행 상황: Task 진행 중
   └─ 문제 없음: 정상 진행
   ↓
9. SystemSentinel: DeviceBridge의 Event 구독
   ├─ DEVICE_HEALTHCHECK 모니터링
   ├─ 배터리/신호 정상 확인
   └─ 이상 없음: 계속 감시
   ↓
10. Device Agent (AUV-01): Task 완료
    ├─ 최종 healthcheck 전송 (완료 상태)
    └─ SYS_TASK_COMPLETED Event 발행: COMPLETED
    ↓
11. DeviceBridge【수신】: A2A task.result 메시지 수신
    └─ MissionPlanner에 Task 완료 알림
    ↓
12. MissionPlanner: Task 상태 업데이트
    ├─ 모든 Task 완료 확인
    └─ SYS_MISSION_UPDATED Event 발행
    ↓
13. InsightReporter: 모든 Event 기록
    └─ Report 생성 및 사용자 보고
```

---

## 핵심 설계 원칙

| 원칙 | 설명 |
|------|------|
| **책임 명확화** | 각 Agent은 자신의 영역만 담당 |
| **DB 소유권** | 해당 Agent만 쓰기, 다른 Agent는 읽기 |
| **Event 기반** | Agent 간 통신은 이벤트 발행/구독 |
| **생명주기 커버** | 입력 → 판단 → 계획 → 실행 → 감시 → 기록 |
| **중복 제거** | 한 기능은 한 Agent만 담당 |

---

## 결과

### ✅ 긍정적 영향

- **책임 명확화**: 각 Agent의 역할이 명확하여 버그 추적 용이
- **확장성**: 새로운 기능 추가 시 해당 Agent만 수정
- **자동화 진화**: Policy/Rule 수정만으로 자동화 수준 조절 (코드 수정 X)
- **추적성**: 모든 의사결정이 Event로 기록됨
- **유지보수**: Agent 간 낮은 결합도로 코드 이해도 향상

### ⚠️ 설계 제약

- **Event 스키마 중요**: 이벤트 설계가 잘못되면 Agent 간 통신 불가능
- **순서 보장 필요**: 이벤트 처리 순서를 timestamp로 관리 필수
- **Stateless Agent**: 각 Agent은 기본적으로 stateless이어야 함 (DB 의존)
- **DB 스키마 변경**: Agent 간 DB 소유권이 명확해야 스키마 수정 가능

---

## 다음 단계

1. **Event Schema 정의** (각 Agent이 발행하는 이벤트 구조)
2. **Database Schema 설계** (각 Agent의 테이블 소유권 명시)
3. **Agent 구현 순서 정의** (RequestHandler → MissionPlanner → ... 순서)
4. **A2A Protocol 상세화** (Agent 간 직접 호출 필요 시)
5. **Error Handling & Retry 전략**

---

## 참고

- **ADR-001**: Core Design Philosophy (Action Abstraction, Event-Based Traceability)
- **ADR-002**: Proposal as Solution Set
- **ADR-003**: Capability-Driven Task Assignment
- **ADR-004**: Agent Endpoint Management
- **ADR-005**: Event-Triggered Rule Execution
- **ADR-006**: Adaptive Autonomy Migration Path
- **docs/core/domain-model.md**: 각 엔티티의 역할
- **docs/core/schema.md**: 데이터 스키마
- **docs/scenarios/lifecycle.md**: 구체적 프로세스
