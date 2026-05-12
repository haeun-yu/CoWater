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
  - PostgreSQL (포트 5432) - 데이터베이스
  - Redis (포트 6379) - 메시지 큐
  - Ollama (포트 11434) - LLM 로컬 실행
  - Moth WebSocket (wss://cobot.center:8287) - 실시간 메시지
```

---

## 📚 핵심 개념 (이 4가지만 기억하면 됨)

| 개념 | 정의 | 예시 |
|------|------|------|
| **Device Role** | 디바이스의 운영상 역할 | "순찰 담당", "데이터 수집" |
| **Operation Plan** | 역할 기반 자동 운영 계획 | "매일 09:00 A구역 순찰 시작" |
| **Mission** | 실제로 실행하는 임무 | "지금 A구역 순찰 시작" |
| **Task** | Device에 할당되는 구체적 작업 | "USV로 A구역 이동하고 스캔" |

---

## 🔄 일반적인 운영 흐름

```
1. 사용자가 Device Role 설정
   (예: "USV는 순찰 담당")
   
2. Operation Plan 설정
   (예: "매일 09:00-17:00 A구역 순찰")
   
3. 시간 또는 이벤트 발생
   
4. System Agent가 Mission 생성
   (예: "A구역 순찰 Mission 시작")
   
5. Mission을 Step과 Task로 분해
   - Step 1: "A구역 이동" 
   - Step 2: "스캔 실행"
   - Step 3: "귀환"
   
6. Device Agent에 Task 할당
   (예: "USV여, A구역으로 이동해줘")
   
7. Device 실행 및 결과 보고
   (예: "A구역 스캔 완료, 이상 탐지")
   
8. System Agent 판단 & 대응
   (예: "이상 객체 발견 → 정밀 조사 Mission 생성")
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
└── ops.html               # 운영 대시보드
infra/
└── docker-compose.yml     # PostgreSQL, Redis 등
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

## 🎯 중요한 설계 원칙

**P1. Agent 직접 제어 원칙**
- System Agent는 디바이스를 직접 제어하지 않음
- Task 할당만 함 → Device Agent가 실제 제어

**P2. 책임 경계**
- System Agent: 무엇을 할지 (판단)
- Device Agent: 어떻게 할지 (실행)

**P3. 보고 기반 운영**
- Device Agent의 보고를 기준으로 판단
- 임의로 추측하지 않음

**P4. Task 중복 실행 방지**
- 모든 Task는 고유 task_id
- 동일 task_id 재수신 시 중복 실행 금지

**P5. 정책 기반 자동 대응**
- 사전 정의 정책만 자동 실행
- 정책 없으면 사용자 승인 필수

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
- Device Agent 프로세스 확인 (./dev-harness.sh status)
- 로그 확인 (.logs/)

**"Task가 실행되지 않아요"**
- Device의 available_actions 확인
- Task에 필요한 action과 일치하는지 확인
- Device의 battery, location 확인

**"Mission이 계획대로 안 돼요"**
- Mission 상태 확인 (GET /missions/[mission_id])
- 각 Step/Task 상태 추적
- System Agent 로그 확인 (.logs/system-agent.log)

---

## 📖 더 알아보기

- **상세 아키텍처**: `SYSTEM_ARCHITECTURE.md`
- **빠른 시작**: `QUICK_START.md`
- **프로젝트 메모리**: `.claude/projects/.../memory/`
