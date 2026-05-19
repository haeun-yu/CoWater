# CoWater 도메인 언어와 아키텍처 컨텍스트

> 이 문서는 CoWater 시스템의 핵심 개념, 아키텍처 설계 원칙, 그리고 용어 정의를 담고 있습니다. 
> 코드, 문서, 의사결정 시 이 언어를 일관되게 사용합니다.

---

## 🌊 CoWater란?

**정의**: 해양 무인체 통합 운영 AI 플랫폼

**핵심**: 여러 해양 무인체(USV, AUV, ROV 등)를 AI Agent로 **실시간 통합 관리**

---

## 🏗️ 아키텍처: 6개 전문 System Agent

CoWater는 **책임 기반 다중 에이전트 아키텍처**로 설계됩니다. 각 에이전트는 명확한 책임 영역과 DB 소유권을 가집니다.

### System Agent 계층 (6개 전문 에이전트)

| 에이전트 | 책임 | 포트 | 주요 역할 |
|---------|------|------|---------|
| **RequestHandler** | 사용자 요청 해석 & 경로 결정 | 9116 | 자연어 → 의도 분류 → 직접 처리 vs 위임 |
| **DeviceBridge** | 양방향 통신 & 상태 동기화 | 9110 | Task 전달 → Device / Heartbeat, Result ← Device |
| **MissionPlanner** | 미션 설계 & 실행 추적 | 9111 | Proposal 생성, Mission 생성, Task 분해 |
| **PolicyManager** | 정책 관리 & 자동 대응 | 9112 | 규칙 매칭, 자동 응급 대응, 장비 생명주기 |
| **SystemSentinel** | 이상 감시 & 건전성 체크 | 9113 | Heartbeat 모니터링, 이상 징후 탐지, Alert 생성 |
| **InsightReporter** | 데이터 조회 & 리포팅 | 9114 | 데이터 분석, Report 생성, 이력 기록 |

### Device Agent 계층

- **Device Agent**: 각 무인체마다 하나씩 실행
  - 개별 디바이스 제어 및 로컬 안전 행동 판단
  - Task 수신 후 **최종 go/no-go 판단** (P5 원칙)
  
- **Communication**: A2A (Agent-to-Agent HTTP) + Moth (실시간 WebSocket)

### 기반 구성요소

- **Registry** (포트 8280) — Device/Agent 등록, 상태 추적
- **SQLite** (Phase 1) — 로컬 데이터베이스
- **Moth WebSocket** (wss://cobot.center:8287) — 실시간 메시지 (RSSP 프로토콜)

---

## 📚 5가지 핵심 개념

이 5가지만 기억하면 CoWater 운영 흐름을 이해할 수 있습니다.

| 개념 | 정의 | 예시 |
|------|------|------|
| **Device Role** | 디바이스의 운영상 역할 | "순찰 담당", "데이터 수집" |
| **Operation Plan** | 역할 기반 자동 운영 계획 | "매일 09:00 A구역 순찰 시작" |
| **Proposal** | System Agent가 제시하는 **완전한 솔루션 세트**; 사용자가 선택 | "추천안 1: ROV 3시간 / 추천안 2: AUV 5시간" |
| **Mission** | Proposal 승인 후 **실제로 실행되는 임무** | "지금 A구역 순찰 시작" |
| **Task** | Mission을 구성하는 **개별 실행 항목**, 하나의 Device에 할당 | "USV로 A구역 이동하고 스캔" |

**핵심 관계**:
```
User Request → Proposal (여러 개) → User Selects
                                      ↓
                                   Mission (1개 선택된 Proposal)
                                      ↓
                                   Tasks (Mission → 개별 Device)
```

---

## 🔄 일반적인 운영 흐름

```
1. 사용자 입력 (자연어 명령)
   "A 구역 고해상도 촬영해줘"

2. RequestHandler: 의도 해석 & 경로 결정
   ├─ [경로 A] 간단한 조회 → DB 읽기 → 직접 응답
   └─ [경로 B] 복잡한 처리 → MissionPlanner에 위임

3. MissionPlanner: Proposal 생성 (Planning 단계)
   ├─ Capability Matching: 수행 가능한 Device 확인
   ├─ AgentConnection 확인: 통신 경로 검증
   └─ 여러 Proposal 생성 (예: ROV 3시간 안, AUV 5시간 안)

4. 사용자가 Proposal 선택 & 승인
   "추천안 1 선택" → 이 단계 없으면 Mission 생성 X

5. MissionPlanner: Mission 생성 및 Task 분해 (Execution 단계)
   ├─ Mission 상태 = READY
   ├─ Task 1: "A구역 이동"
   ├─ Task 2: "고해상도 촬영"
   └─ Task 3: "귀환"

6. DeviceBridge: Task 할당 & 상태 동기화
   ├─ A2A로 Device에 Task 전달
   └─ 정기적 Heartbeat 수신

7. Device 실행 및 결과 보고
   "A구역 촬영 완료, 이상 탐지"

8. SystemSentinel: 지속적 감시
   ├─ Heartbeat 모니터링
   ├─ 이상 징후 감지
   └─ 필요 시 PolicyManager에 이상 보고

9. PolicyManager: 자동 대응 규칙 적용
   ├─ Rule 매칭
   └─ 필요 시 긴급 Mission 요청

10. InsightReporter: 결과 기록 & 리포팅
```

---

## 🎯 설계 원칙 (10가지)

### P1. 에이전트 직접 제어 원칙
- **Device Agent만** 자신의 Device를 직접 제어
- 다른 Agent들(RequestHandler, MissionPlanner 등)은 **Task 할당/위임만** 수행
- Device Agent: Task 수신 후 **최종 go/no-go 판단**

### P2. 책임 경계 명확화
- **RequestHandler**: 사용자 요청 해석 & 경로 결정
- **MissionPlanner**: 미션/태스크 설계, 실행 추적
- **PolicyManager**: 정책 적용, 자동 대응
- **SystemSentinel**: 이상 감시, 건전성 체크
- **DeviceBridge**: Task 할당(→) & Heartbeat/Result/Problem 수집(←)
- **InsightReporter**: 데이터 조회, 분석, 리포팅
- **Device Agent**: 자신의 Device 상태·수행 판단

### P3. 보고 기반 운영
- Device Agent의 보고(Heartbeat, Task Result)를 기준으로 판단
- **임의로 추측하지 않음**

### P4. Mission 중심 운영
- CoWater는 **단순 명령 전달이 아닌 Mission 중심** 플랫폼
- Mission Timeline으로 전체 운영 이력 관리

### P5. Task 수행 가능성 최종 판단 (중요)
- **MissionPlanner**: 사전 계획 및 Task 할당
- **Device Agent**: Task 수신 후 최종 go/no-go 판단
- **ABORTED** = Task 전달 후 실행 전 Device가 거절 (≠ FAILED)
- **FAILED** = Task 실행 중(IN_PROGRESS) 오류 발생

### P6. 정책 기반 자동 대응
- **PolicyManager**가 Rule 매칭 후 자동 실행
- 사전 정의 Policy가 있는 경우에만 자동 실행
- Policy 없으면 사용자 승인 필수

### P7. 사용자 결정 우선
- 사용자 명령은 시스템 판단보다 우선
- 단, 시스템은 위험을 경고하고 기록해야 함

### P8–P10
상세 내용은 `docs/core/principles.md` 참고

---

## ⚠️ 용어 오용 주의 (공통 실수 3가지)

| 틀린 표현 | 올바른 표현 | 이유 |
|-----------|------------|------|
| "사용자가 Task를 취소" | "사용자는 Mission을 취소" | Task 거절은 Device Agent가 (ABORTED) |
| "Mission이 ASSIGNED 상태" | "ASSIGNED는 Task 상태" | Mission 상태에 ASSIGNED 없음 |
| "이 Proposal을 실행하세요" | "Proposal을 승인하고 Mission을 실행" | Proposal = 승인, Mission = 실행 |

자세한 용어 사전은 `docs/GLOSSARY.md` 참고

---

## ❌ 구현 시 금지 사항

- RequestHandler/MissionPlanner/PolicyManager가 **Device 직접 제어**
- RequestHandler가 **도메인 데이터 직접 수정** (DB 쓰기 금지)
- **Device 상태를 임의로 추측** (DeviceBridge의 보고만 신뢰)
- **PolicyManager 없이 자동 실행**
- 같은 **Task 중복 실행**
- **Registry 상태를 Agent처럼 취급**
- **Event 생성 권한 혼동** (각 Agent은 자신의 Event만 발행)

---

## ✅ 구현 시 필수 확인

- MissionPlanner: Task 할당 전 Device 상태 확인 (DeviceBridge 보고 기반)
- SystemSentinel: 모든 이상 징후 감시 & Alert 생성
- PolicyManager: Rule 매칭 후 자동 대응 결정
- InsightReporter: 모든 Event 기록 & Report 생성
- 실패 사유 명확히 기록 (Event data에 근거 포함)
- A2A 통신 로깅 (DeviceBridge의 Task 할당/결과 추적)
- Database 마이그레이션으로만 변경
- Agent 간 통신: Event 발행/구독으로만 (직접 호출 금지)

---

## 📚 관련 문서

**첫 읽기:**
- [`docs/SYSTEM_ARCHITECTURE.md`](docs/SYSTEM_ARCHITECTURE.md) — 아키텍처 개요
- [`docs/GLOSSARY.md`](docs/GLOSSARY.md) — 전체 용어 사전
- [`docs/QUICK_START.md`](docs/QUICK_START.md) — 빠른 시작 가이드

**상세 내용:**
- [`docs/core/domain-model.md`](docs/core/domain-model.md) — 도메인 모델
- [`docs/core/principles.md`](docs/core/principles.md) — 10가지 설계 원칙 (P1-P10)
- [`docs/core/schema.md`](docs/core/schema.md) — 데이터베이스 스키마

**아키텍처 결정:**
- [`docs/adr/ADR-000-index.md`](docs/adr/ADR-000-index.md) — ADR 목록
- [`docs/adr/ADR-001-core-design-philosophy.md`](docs/adr/ADR-001-core-design-philosophy.md) — 핵심 설계 철학
- [`docs/adr/ADR-008-multi-agent-system-architecture.md`](docs/adr/ADR-008-multi-agent-system-architecture.md) — 다중 에이전트 시스템

**프로젝트 컨텍스트:**
- [`.claude/COWATER_CONTEXT.md`](.claude/COWATER_CONTEXT.md) — 빠른 참고서
- [`.claude/projects/-Users-teamgrit-Documents-CoWater/memory/`](.claude/projects/-Users-teamgrit-Documents-CoWater/memory/) — 프로젝트 메모리

---

## 🔍 문제 해결 팁

**"Device가 응답이 없어요"**
- DeviceBridge에서 Device Heartbeat 확인
- SystemSentinel에서 `anomaly.detected` 이벤트 확인
- Registry에서 Device 연결 상태 확인

**"Proposal이 생성되지 않아요"**
- MissionPlanner의 Capability Matching 실패 확인
- Device.actions[]에 필요한 action이 있는지 확인
- Device 상태가 ONLINE인지 확인

**"Task가 실행되지 않아요"**
- Device.actions[] 확인
- Device의 battery, location 확인
- DeviceBridge의 task.result 이벤트 확인

**"Mission이 계획대로 안 돼요"**
- MissionPlanner의 mission 상태 추적
- 각 Task 상태 확인 (PENDING → ASSIGNED → IN_PROGRESS → COMPLETED)
- SystemSentinel의 이상 감시 이벤트 확인
- 시스템 로그 확인 (`.logs/System-Agent.log`)
