# CoWater 도메인 언어와 아키텍처 컨텍스트

> 이 문서는 CoWater에서 공통으로 써야 하는 핵심 용어와 문서 읽기 기준을 정의합니다.  
> 구조 상세는 `docs/SYSTEM_ARCHITECTURE.md`, 상태와 계약은 `docs/core/*`, 절차는 `docs/scenarios/*`를 정본으로 봅니다.

---

## CoWater란?

CoWater는 해양 무인체를 AI 에이전트로 통합 운영하는 플랫폼입니다.

- 사용자 요청을 해석해 여러 실행안(`Proposal`)을 만듭니다.
- 승인된 실행안만 실제 임무(`Mission`)로 전환합니다.
- 임무는 여러 작업(`Task`)으로 분해되어 Device에 할당됩니다.
- 실행과 판단의 근거는 Event로 남깁니다.

## 이 문서의 역할

이 문서는 다음만 담당합니다.

- 도메인 언어의 정규 의미
- 자주 헷갈리는 개념의 구분
- 어떤 문서를 정본으로 봐야 하는지 안내

이 문서에 두지 않는 내용:

- 6개 System Agent의 상세 구조
- 상태 전이 표
- 이벤트 카탈로그
- 등록/실행/예외의 단계별 절차
- 구현 방법

## 핵심 용어

### Proposal

System Agent가 제시하는 실행안입니다. 사용자가 승인하기 전 단계의 선택지입니다.

### Mission

승인된 Proposal을 실제 실행 단위로 바꾼 임무입니다.

### Task

Mission을 구성하는 개별 실행 항목입니다. 하나의 Task는 특정 Device 또는 특정 시스템 책임 단위에 할당됩니다.

### Device

실제 물리 장비입니다. 자신이 수행 가능한 `actions[]`를 선언합니다.

### Device Agent

특정 Device를 대표하는 실행 주체입니다. 실제 Device 제어와 실행 가능성 최종 판단을 담당합니다.

### System Agent

시스템 차원의 계획, 판단, 감시, 리포팅을 담당하는 에이전트 집합입니다.

### AgentConnection

Device Agent 사이의 협력 관계입니다. 단순 연결 정보가 아니라 릴레이, 데이터 공유, 리더-팔로워 같은 협력 목적을 함께 표현합니다.

### Event

시스템에서 일어난 의미 있는 변화입니다. 추적 기록이자 Rule 실행의 근거입니다.

### Policy / Rule

- `Policy`: 운영 원칙과 자동화 허용 범위를 정의하는 상위 기준
- `Rule`: Event가 발생했을 때 실제로 무엇을 실행할지 결정하는 하위 규칙

## 절대 혼동하면 안 되는 구분

| 잘못된 표현 | 올바른 표현 | 이유 |
|---|---|---|
| 사용자가 Task를 취소한다 | 사용자는 Mission을 취소한다 | Task 거절은 Device Agent가 한다 |
| Mission이 ASSIGNED 상태다 | ASSIGNED는 Task 상태다 | Mission 상태와 Task 상태는 다르다 |
| Proposal을 실행한다 | Proposal을 승인하고 Mission을 실행한다 | Proposal은 실행안, Mission은 실행 대상이다 |
| FAILED와 ABORTED가 같다 | 실행 전 거절은 ABORTED, 실행 중 실패는 FAILED | 원인과 책임 경계가 다르다 |

## 작업 시 기본 원칙

- Device를 직접 제어하는 주체는 Device Agent뿐입니다.
- System Agent는 Task 할당, 정책 판단, 감시, 기록을 담당합니다.
- System은 Device 상태를 추측하지 않고 보고된 정보만 사용합니다.
- 자동 실행은 Policy와 Rule이 허용한 범위에서만 수행합니다.

원칙의 상세 정의는 `docs/core/principles.md`를 기준으로 합니다.

## 어떤 문서를 먼저 읽을까

### 구조를 이해할 때

- `docs/SYSTEM_ARCHITECTURE.md`

### 상태와 데이터 계약을 확인할 때

- `docs/core/schema.md`
- `docs/core/event-types.md`
- `docs/core/a2a-protocol.md`
- `docs/core/agent-connection.md`

### 절차를 확인할 때

- `docs/scenarios/lifecycle.md`
- `docs/scenarios/operation.md`
- `docs/scenarios/exceptions.md`
- `docs/scenarios/reporting.md`
- `docs/scenarios/administration.md`

### 구현 방법을 볼 때

- `docs/implementation/system-agent.md`
- `docs/implementation/device-agent.md`
- `docs/implementation/rule-engine.md`
- `docs/implementation/frontend.md`

## 문서 우선순위

중복되거나 충돌할 때는 다음 기준으로 읽습니다.

1. 상태, 필드, 이벤트, 계약: `docs/core/*`
2. 전체 구조와 책임 경계: `docs/SYSTEM_ARCHITECTURE.md`
3. 절차와 운영 흐름: `docs/scenarios/*`
4. 구현 방법: `docs/implementation/*`
5. 이 문서: 용어와 정본 위치 확인
