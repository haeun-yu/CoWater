# CoWater 프로젝트 컨텍스트

> 이 프로젝트의 아키텍처, 컴포넌트, 용어 빠른 참고서

---

## 🌊 CoWater란?

**정의**: 해양 무인체 통합 운영 AI 플랫폼

**핵심**: 여러 해양 무인체(USV, AUV, ROV 등)를 AI 에이전트로 실시간 통합 관리

---

## 🏗️ 아키텍처 (6개 전문 에이전트)

CoWater는 책임 기반 다중 에이전트 아키텍처로 설계됩니다. 각 에이전트는 명확한 책임 영역과 DB 소유권을 가집니다.

```
User Interface (운영자)
  ↓
【System Agent Layer - 6개 전문 에이전트】
  ├─ 1️⃣ RequestHandler (포트 9116)
  │  └─ 사용자 요청 해석 → 직접 처리 vs 위임 결정
  │
  ├─ 2️⃣ DeviceBridge (포트 9110)
  │  └─ 양방향 통신: Task 전달 → Device, Heartbeat/Result/Problem ← Device 수집
  │
  ├─ 3️⃣ MissionPlanner (포트 9111)
  │  └─ 미션/태스크 설계, 실행 추적, 생명주기 관리
  │
  ├─ 4️⃣ PolicyManager (포트 9112)
  │  └─ 정책/규칙 관리, 자동 대응, 장비 생명주기
  │
  ├─ 5️⃣ SystemSentinel (포트 9113)
  │  └─ 시스템 감시, 이상 징후 감지, Alert/Event 생성
  │
  └─ 6️⃣ InsightReporter (포트 9114)
     └─ 데이터 조회, 통계/분석, 리포트 생성

【Device Agent Layer】
  ├─ Device Agent (각 무인체마다)
  │  └─ 개별 디바이스 제어, 로컬 안전 행동
  │
  └─ Communication: A2A (Agent-to-Agent HTTP) + Moth (실시간)

【Infrastructure】
  ├─ Registry (포트 8280) - Device/Agent 등록, 상태 추적
  ├─ SQLite (Phase 1) - 로컬 데이터베이스
  └─ Moth WebSocket (wss://cobot.center:8287) - 실시간 메시지
     [Phase 2+: PostgreSQL / Phase 3+: Redis]

【핵심 원칙】
入力 → 判断 → 計画 → 実行 → 監視 → 記録
(입력 → 판단 → 계획 → 실행 → 감시 → 기록)

RequestHandler → PolicyManager/MissionPlanner → DeviceBridge 
  → SystemSentinel → InsightReporter
```

**각 에이전트의 책임**:

| 에이전트 | 입력 | 처리 | 출력 | DB 권한 |
|---------|------|------|------|--------|
| **RequestHandler** | 사용자 자연어 명령 | 의도 해석 → 경로 결정 | RESPONSE 또는 COMMAND_REQUEST | Read-only |
| **DeviceBridge** | 장비 A2A 메시지 + 명령 | 상태 동기화, Task 전달 | device.heartbeat, task.result, device.reconnected 이벤트 | Device, Sensor |
| **MissionPlanner** | intent.classified, policy.decision | Proposal 생성, Mission 관리 | mission.*, task.* 이벤트 | Mission, Task, Proposal |
| **PolicyManager** | intent.classified, anomaly.detected | 정책 적용, 자동 대응 | policy.decision, policy.mission_request 이벤트 | Policy, Rule, Config |
| **SystemSentinel** | device.heartbeat + 모든 이벤트 | 이상 감시, 건전성 체크 | anomaly.detected 이벤트 | Alert, Event |
| **InsightReporter** | intent.classified (QUERY) | 데이터 조회, 분석 | report.generated 이벤트 | Read-only |
| **Device Agent** | Task + 환경 정보 | 실행 판단, Task 수행 | task.result, device.heartbeat | Device 상태 |

---

## 📚 핵심 개념 (이 5가지만 기억하면 됨)

| 개념 | 정의 | 예시 |
|------|------|------|
| **Device Role** | 디바이스의 운영상 역할 | "순찰 담당", "데이터 수집" |
| **Operation Plan** | 역할 기반 자동 운영 계획 | "매일 09:00 A구역 순찰 시작" |
| **Proposal** | System Agent가 제시하는 완전한 솔루션 세트; 사용자가 선택 | "추천안 1: ROV 3시간 / 추천안 2: AUV 5시간" |
| **Mission** | Proposal 승인 후 실제로 실행되는 임무 | "지금 A구역 순찰 시작" |
| **Task** | Mission을 구성하는 개별 실행 항목, 하나의 Device에 할당 | "USV로 A구역 이동하고 스캔" |

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
   "추천안 1 선택"
   → 이 단계 없으면 Mission 생성 X

5. MissionPlanner: Mission 생성 및 Task 분해 (Execution 단계)
   ├─ Mission 상태 READY
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
   ├─ Rule 매칭 (예: "이상 객체 발견")
   └─ 필요 시 MissionPlanner에 응급 미션 요청

10. InsightReporter: 결과 기록 & 리포팅
    ├─ Event/Alert 기록
    ├─ 사용자 조회 시 Report 생성
    └─ 분석 데이터 제공
```

---

## 📂 주요 파일 구조

```
server/
├── registration/          # Registry 서버
│   └── device_registration_server.py
├── system-agent/          # System Agent
│   ├── system_agent.py
│   ├── agent/             # Agent 로직
│   ├── domain/            # 비즈니스 로직
│   └── storage/           # 상태 관리
device/
├── device_agent.py        # Device Agent 메인
└── simulator/             # 테스트용 시뮬레이터
client/
├── index.html             # 3D 대시보드
├── ops.html               # 운영 대시보드
└── mission.html           # 미션 상세 추적 (?id=<mission_id>)
```

---

## 🔌 주요 통신 프로토콜

### A2A (에이전트 간 통신)
- System Agent ↔ Device Agent 간 Task/Result 전달
- 예: POST /task, POST /result

### Registry API
- `/devices` - 등록된 디바이스 조회
- `/missions` - Mission 상태
- `/health` - 헬스 체크

### Moth WebSocket
- 실시간 메시지 (A2A, 텔레메트리, 하트비트)
- wss://cobot.center:8287

---

## 🎯 중요한 설계 원칙 (10가지, 자세한 내용: docs/core/principles.md)

**P1. Agent 직접 제어 원칙**
- Device Agent만 자신의 Device를 직접 제어
- 다른 Agent들(RequestHandler, MissionPlanner 등)은 Task 할당/위임만 수행
- Device Agent: Task 수신 후 최종 go/no-go 판단

**P2. 책임 경계 명확화**
- **RequestHandler**: 사용자 요청 해석 & 경로 결정
- **MissionPlanner**: 미션/태스크 설계, 실행 추적
- **PolicyManager**: 정책 적용, 자동 대응
- **SystemSentinel**: 이상 감시, 건전성 체크
- **DeviceBridge**: Task 할당(→) & Heartbeat/Result/Problem 수집(←)
- **InsightReporter**: 데이터 조회, 분석, 리포팅
- **Device Agent**: 자신의 Device 상태·수행 판단

**P3. 보고 기반 운영**
- Device Agent의 보고(Heartbeat, Task Result)를 기준으로 판단
- 임의로 추측하지 않음

**P4. Mission 중심 운영**
- CoWater는 단순 명령 전달이 아닌 Mission 중심 플랫폼
- Mission Timeline으로 전체 운영 이력 관리

**P5. Task 수행 가능성 최종 판단 (중요)**
- **MissionPlanner**: 사전 계획 및 Task 할당
- **Device Agent**: Task 수신 후 최종 go/no-go 판단
- ABORTED = Task 전달 후 실행 전 Device가 거절 (≠ FAILED)
- FAILED = Task 실행 중(IN_PROGRESS) 오류 발생

**P6. 정책 기반 자동 대응**
- **PolicyManager**가 Rule 매칭 후 자동 실행
- 사전 정의 Policy가 있는 경우에만 자동 실행
- Policy 없으면 사용자 승인 필수

**P7. 사용자 결정 우선**
- 사용자 명령은 시스템 판단보다 우선
- 단, 시스템은 위험을 경고하고 기록해야 함

**P8–P10**: docs/core/principles.md 참고

---

## ⚠️ 구현 시 주의점

### 금지 사항
- ❌ RequestHandler/MissionPlanner/PolicyManager가 Device 직접 제어
- ❌ RequestHandler가 도메인 데이터 직접 수정 (DB 쓰기 금지)
- ❌ Device 상태를 임의로 추측 (DeviceBridge의 보고만 신뢰)
- ❌ PolicyManager 없이 자동 실행
- ❌ 같은 Task 중복 실행
- ❌ Registry 상태를 Agent처럼 취급
- ❌ Event 생성 권한 혼동 (각 Agent은 자신의 Event만 발행)

### 필수 확인
- ✅ MissionPlanner: Task 할당 전 Device 상태 확인 (DeviceBridge 보고 기반)
- ✅ SystemSentinel: 모든 이상 징후 감시 & Alert 생성
- ✅ PolicyManager: Rule 매칭 후 자동 대응 결정
- ✅ InsightReporter: 모든 Event 기록 & Report 생성
- ✅ 실패 사유 명확히 기록 (Event data에 근거 포함)
- ✅ A2A 통신 로깅 (DeviceBridge의 Task 할당/결과 추적)
- ✅ Database 마이그레이션으로만 변경
- ✅ Agent 간 통신: Event 발행/구독으로만 (직접 호출 금지)

---

## 🔍 문제 해결 팁

**"Device가 응답이 없어요"**
- DeviceBridge에서 Device Heartbeat 확인 (마지막 heartbeat 타임스탬프)
- SystemSentinel에서 anomaly.detected 이벤트 확인 (OFFLINE 감지)
- Registry에서 Device 연결 상태 확인 (GET /devices)
- 서비스 상태 확인 (./cowaterctl.sh status)
- 로그 확인 (.logs/)

**"Proposal이 생성되지 않아요"**
- MissionPlanner의 Capability Matching 실패 확인
- Device.actions[]에 필요한 action이 있는지 확인
- Device 상태가 ONLINE인지 확인 (OFFLINE은 할당 불가)
- PolicyManager에서 policy.decision 이벤트 확인

**"Task가 실행되지 않아요"**
- Device.actions[] 확인 (Task에 필요한 action이 있는지)
- Device의 battery, location 확인 (DeviceBridge 보고 기반)
- DeviceBridge의 task.result 이벤트 확인
- Device가 Task 수신 후 go/no-go 판단 (P5 원칙)

**"Mission이 계획대로 안 돼요"**
- MissionPlanner의 mission 상태 추적 (GET /missions/[mission_id])
- 각 Task 상태 확인 (PENDING → ASSIGNED → IN_PROGRESS → COMPLETED)
- SystemSentinel의 anomaly.detected 이벤트 확인 (중간 이상 발생)
- PolicyManager의 policy.mission_request 이벤트 확인 (긴급 대응)
- System Agent 로그 확인 (.logs/System-Agent.log)

---

## ⚠️ 용어 오용 주의 (3가지 공통 실수)

| 틀린 표현 | 올바른 표현 | 이유 |
|-----------|------------|------|
| "사용자가 Task를 취소" | "사용자는 Mission을 취소" | Task 거절은 Device Agent가 (ABORTED) |
| "Mission이 ASSIGNED 상태" | "ASSIGNED는 Task 상태" | Mission 상태에 ASSIGNED 없음 |
| "이 Proposal을 실행하세요" | "Proposal을 승인하고 Mission을 실행" | Proposal = 승인, Mission = 실행 |

> 자세한 내용: `docs/GLOSSARY.md`

---

## 📖 더 알아보기

- **상세 아키텍처**: `docs/SYSTEM_ARCHITECTURE.md`
- **빠른 시작**: `docs/QUICK_START.md`
- **용어 사전**: `docs/GLOSSARY.md`
- **도메인 모델**: `docs/core/domain-model.md`
- **설계 원칙 전문**: `docs/core/principles.md`
- **스키마**: `docs/core/schema.md`
- **ADR 목록**: `docs/adr/ADR-000-index.md`
- **프로젝트 메모리**: `.claude/projects/.../memory/`
