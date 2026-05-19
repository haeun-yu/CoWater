# System Agent 아키텍처

**목적**: System Agent 계층에서만 필요한 설계 메모를 정리합니다.  
전체 구조는 `SYSTEM_ARCHITECTURE.md`, 구현 방법은 `implementation/system-agent.md`를 정본으로 봅니다.

---

## 이 문서의 범위

이 문서는 다음만 다룹니다.

- 6개 System Agent의 역할 분할 기준
- 이벤트 구독 구조
- 공통 BaseAgent가 가져야 할 최소 인터페이스
- Agent별 메모리 캐시와 Registry 저장 전략

이 문서에 두지 않는 내용:

- CoWater 전체 아키텍처 개요
- Proposal → Mission → Task 전체 흐름 설명
- Device Agent 구조 설명
- 구현 코드 상세

## 6개 Agent 역할 분할

| 에이전트 | 포트 | 핵심 책임 |
|---|---:|---|
| RequestHandler | 9116 | 사용자 요청 해석과 라우팅 |
| DeviceBridge | 9110 | Device ↔ System 통신 게이트웨이 |
| MissionPlanner | 9111 | Proposal, Mission, Task 설계와 생명주기 관리 |
| PolicyManager | 9112 | 정책 기반 자동 대응 |
| SystemSentinel | 9113 | 건전성 감시와 AgentConnection 상태 관리 |
| InsightReporter | 9114 | 조회와 리포트 생성 |

## 역할 분리 원칙

- RequestHandler는 해석과 라우팅만 담당하고 도메인 상태를 직접 변경하지 않습니다.
- DeviceBridge는 통신 중개와 상태 정규화만 담당합니다.
- MissionPlanner는 Proposal, Mission, Task 상태의 정본 소유자입니다.
- PolicyManager는 Rule 평가와 자동 대응 판단을 담당합니다.
- SystemSentinel은 이상 탐지와 감시를 담당합니다.
- InsightReporter는 읽기 전용 조회와 보고를 담당합니다.

## MEB 이벤트 구독 구조

- 단일 `agents` 채널을 사용합니다.
- 각 이벤트는 `event_type`과 `target_agents`로 라우팅합니다.
- Agent는 자신이 대상인 이벤트만 처리합니다.

이벤트 타입 정본은 `core/event-types.md`를 봅니다.

## BaseAgent 공통 인터페이스

모든 System Agent는 최소한 아래 인터페이스를 공유합니다.

```python
class BaseAgent:
    async def start()
    async def call_llm()
    async def publish_event()
    async def subscribe_to_meb()
```

구현 상세는 `implementation/system-agent.md`를 봅니다.

## 상태 관리 전략

| 에이전트 | 메모리 캐시 | Registry 저장 |
|---|---|---|
| RequestHandler | 최근 명령 | Event |
| DeviceBridge | Device 목록 단기 캐시 | Device 상태 |
| MissionPlanner | 활성 Mission | Mission, Task, Proposal |
| PolicyManager | 활성 Policy 목록 | Policy, Rule, Config |
| SystemSentinel | heartbeat 타임스탬프 | Alert, Event |
| InsightReporter | 없음 | 실시간 조회 |

## 관련 정본

- 전체 구조: `SYSTEM_ARCHITECTURE.md`
- 이벤트: `core/event-types.md`
- 계약: `core/a2a-protocol.md`
- 구현: `implementation/system-agent.md`
