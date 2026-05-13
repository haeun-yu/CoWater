# System Agent 아키텍처

**문서 버전**: 1.0  
**목적**: 6개 전문 에이전트의 책임과 역할 정의

---

## 1. System Agent Layer 개요

CoWater의 System Agent Layer는 6개의 전문 에이전트로 구성됩니다.

### 포트 배정

| 에이전트 | 포트 | 책임 |
|---------|------|------|
| **RequestHandler** | 9116 | 사용자 요청 해석 & 라우팅 |
| **DeviceBridge** | 9110 | Device ↔ System 통신 게이트웨이 |
| **MissionPlanner** | 9111 | 미션/Task 설계 및 생명주기 관리 |
| **PolicyManager** | 9112 | 정책 기반 자동 대응 |
| **SystemSentinel** | 9113 | 시스템 건전성 감시 & AgentConnection 관리 |
| **InsightReporter** | 9114 | 데이터 조회 & 분석 리포트 생성 |

---

## 2. 각 에이전트의 책임

### RequestHandler (포트 9116)
- 사용자 자연어 명령을 intent (QUERY/MISSION/POLICY/EMERGENCY/DIRECT)로 분류
- 적절한 System Agent로 라우팅 또는 직접 처리
- **LLM**: 명령 해석 및 의도 분류

### DeviceBridge (포트 9110)
- Device Agent와의 A2A 통신 (task.assign, task.result)
- Device healthcheck 수신 및 정규화
- Task 할당 & 결과 수집
- **LLM**: Task 전달 실패 시 대체 Device 선택, relay 대상 판단

### MissionPlanner (포트 9111)
- 사용자 intent로부터 여러 대안 Proposal 생성 (3단계: 규칙 기반 + LLM + 검증)
- Mission 생명주기 관리 (PROPOSED → APPROVED → COMPLETED)
- Task 분배 & 진행 상황 추적
- **LLM**: 3가지 Proposal 생성 (최적/빠른/안전)

### PolicyManager (포트 9112)
- 등록된 정책 관리 & 자동 대응 결정
- 이상 징후 → 정책 매칭 → 자동 실행 (if auto_execute=true)
- **LLM**: 정책 매칭 및 대응 결정

### SystemSentinel (포트 9113)
- Device 건전성 감시 (2초 interval)
- 규칙 기반: 배터리, Heartbeat timeout, 센서 이상 감지
- AgentConnection 3단계 필터링 (Gateway, 매체, 환경)
- AgentConnection CRUD & 상태 관리
- **LLM**: 복합 패턴 분석 (배터리 급감 + 신호 약화 = 고장 의심)

### InsightReporter (포트 9114)
- Stateless: Registry에서 실시간 데이터 조회
- Mission 이력, Device 상태, Event 로그 분석
- 한국어 리포트 생성
- **LLM**: 수치 데이터를 자연어 분석 리포트로 변환

---

## 3. MEB 이벤트 구독 구조

**단일 "agents" meb 채널** (송수신):
- event_type + target_agents로 라우팅
- 각 Agent는 자신이 대상인 이벤트만 처리

자세한 이벤트 정의: [Event Types](core/event-types.md)

---

## 4. BaseAgent 공통 클래스

모든 에이전트가 상속:
```python
class BaseAgent:
    async def start()           # 에이전트 시작
    async def call_llm()        # LLM 호출 (Circuit Breaker + 재시도)
    async def publish_event()   # MEB 이벤트 발행
    async def subscribe_to_meb() # MEB 구독
```

---

## 5. 상태 관리 전략

| 에이전트 | 메모리 캐시 | Registry 저장 |
|---------|-----------|------------|
| RequestHandler | 최근 명령 10개 | Event (ingest) |
| DeviceBridge | Device 목록 (30초 TTL) | Device 상태 |
| MissionPlanner | 활성 Mission | Mission, Task, Proposal |
| PolicyManager | Policy 목록 | Policy (변경 시 PUT) |
| SystemSentinel | heartbeat 타임스탐프 | Alert (ingest) |
| InsightReporter | 없음 (완전 stateless) | 실시간 조회 |

---

## 6. 통신 채널 정리

자세한 내용:
- [A2A Protocol](core/a2a-protocol.md) - Device ↔ System/Device A2A 통신
- [AgentConnection](core/agent-connection.md) - Device 간 통신 관리
- [Communication Driver](core/communication-driver.md) - 물리 계층 드라이버 선택 & relay

---

**관련 문서**:
- [Event Types](core/event-types.md) - 13개 MEB 이벤트 정의
- [A2A Protocol](core/a2a-protocol.md) - 메시지 구조 & 타입
- [System Architecture](SYSTEM_ARCHITECTURE.md) - 전체 아키텍처
