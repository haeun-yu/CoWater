# CoWater Project Context

> 이 프로젝트의 아키텍처, 컴포넌트, 용어 빠른 참고서

---

## 🌊 CoWater란?

**정의**: 해양 무인체 통합 운영 AI 플랫폼

**핵심**: 여러 해양 무인체(USV, AUV, ROV 등)를 AI Agent로 실시간 통합 관리

---

## 🏗️ 아키텍처 (5개 독립 서비스)

```
User (운영자)
  ↓
System Agent (포트 9116)
  - Mission 계획 및 조율
  - 위험 상황 판단
  - Agent 간 조정
  ↓
Registry (포트 8280)
  - Device 등록/상태 관리
  - Mission/Task 상태 추적
  
Middle-layer Agent (포트 9115)
  - Ship (선박) 제어
  - 통신 중계
  
Device Agents (포트 9111-9113)
  - USV Lower (9111) - Unmanned Surface Vehicle
  - AUV Lower (9112) - Autonomous Underwater Vehicle  
  - ROV Lower (9113) - Remotely Operated Vehicle
  
Infrastructure
  - SQLite (파일 기반) - Phase 1 데이터베이스
  - Moth WebSocket (wss://cobot.center:8287) - 실시간 메시지
  [Phase 2+: PostgreSQL / Phase 3+: Redis]
```

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
1. 사용자가 Device Role 설정
   (예: "USV는 순찰 담당")

2. Operation Plan 설정
   (예: "매일 09:00-17:00 A구역 순찰")

3. 시간 또는 이벤트 발생

4. System Agent가 Proposal 생성 (Planning 단계)
   (예: "추천안 1: ROV 3시간, 추천안 2: AUV 5시간")

5. 사용자가 Proposal 승인
   (예: "추천안 1 선택")
   → 이 단계가 없으면 Mission이 생성되지 않음

6. Mission 생성 및 Task 분해 (Execution 단계)
   - Task 1: "A구역 이동"
   - Task 2: "스캔 실행"
   - Task 3: "귀환"

7. Device Agent에 Task 할당
   (예: "USV여, A구역으로 이동해줘")

8. Device 실행 및 결과 보고
   (예: "A구역 스캔 완료, 이상 탐지")

9. System Agent 판단 & 대응
   (예: "이상 객체 발견 → 새 Proposal 생성")
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

### A2A (Agent-to-Agent)
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
- System Agent는 디바이스를 직접 제어하지 않음
- Task 할당만 함 → Device Agent가 실제 제어

**P2. 책임 경계 명확화**
- System Agent: 전체 조율과 의사결정
- Device Agent: 자신의 Device 상태·수행 판단

**P3. 보고 기반 운영**
- Device Agent의 보고를 기준으로 판단
- 임의로 추측하지 않음

**P4. Mission 중심 운영**
- CoWater는 단순 명령 전달이 아닌 Mission 중심 플랫폼
- Mission Timeline으로 전체 운영 이력 관리

**P5. Task 수행 가능성 최종 판단 (중요)**
- System Agent: 사전 계획 및 Task 할당
- Device Agent: Task 수신 후 최종 go/no-go 판단
- ABORTED = Task 전달 후 실행 전 Device가 거절 (≠ FAILED)
- FAILED = Task 실행 중(IN_PROGRESS) 오류 발생

**P6. 정책 기반 자동 대응**
- 사전 정의 Policy가 있는 경우에만 자동 실행
- Policy 없으면 사용자 승인 필수

**P7. 사용자 결정 우선**
- 사용자 명령은 시스템 판단보다 우선
- 단, 시스템은 위험을 경고하고 기록해야 함

**P8–P10**: docs/core/principles.md 참고

---

## ⚠️ 구현 시 주의점

### 금지 사항
- ❌ System Agent가 디바이스 직접 제어
- ❌ Device 상태를 임의로 추측
- ❌ 정책 없이 자동 실행
- ❌ 같은 Task 중복 실행
- ❌ Registry 상태를 Agent처럼 취급

### 필수 확인
- ✅ Task할당 전 Device 상태 확인
- ✅ Mission 상태 기록
- ✅ 실패 사유 명확히 기록
- ✅ A2A 통신 로깅
- ✅ Database 마이그레이션으로만 변경

---

## 🔍 문제 해결 팁

**"Device가 응답이 없어요"**
- Registry에서 Device 연결 상태 확인 (GET /devices)
- 서비스 상태 확인 (./cowaterctl.sh status)
- 로그 확인 (.logs/)

**"Task가 실행되지 않아요"**
- Device의 available_actions 확인
- Task에 필요한 action과 일치하는지 확인
- Device의 battery, location 확인

**"Mission이 계획대로 안 돼요"**
- Mission 상태 확인 (GET /missions/[mission_id])
- 각 Step/Task 상태 추적
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
