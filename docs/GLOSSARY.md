# CoWater 도메인 용어 사전

**목적**: 용어 정의만 짧게 확인하는 사전입니다.  
상태, 필드, 흐름, 설계 이유는 각 정본 문서를 봅니다.

---

## 사용 원칙

- 기술 문서와 코드에서는 영문 용어를 우선합니다.
- 사용자 안내나 운영 문서에서는 한국어 표현을 함께 쓸 수 있습니다.
- 처음 등장할 때만 영문과 한국어를 함께 쓰고, 이후에는 한 문서 안에서 표기를 섞지 않습니다.

## 핵심 엔티티

### Mission

승인된 Proposal을 실제 실행하는 임무입니다.  
상세 상태는 `core/schema.md#8-mission-실행-계획`을 봅니다.

### Task

Mission을 구성하는 개별 실행 항목입니다.  
상세 상태는 `core/schema.md#9-task-실행-단위`를 봅니다.

### Proposal

사용자가 승인 전 검토하는 실행안입니다.  
구조와 상태는 `core/schema.md#6-proposal-추천안`을 봅니다.

### Device

실제 물리 장비입니다. 수행 가능한 `actions[]`를 선언합니다.

### Agent

Device를 제어하거나 시스템을 조율하는 소프트웨어 주체입니다.

### AgentConnection

에이전트 간 협력 관계입니다. RELAY, COORDINATE, SHARE_DATA 같은 목적을 함께 표현합니다.

### Event

시스템의 의미 있는 변화 기록이며 Rule 실행의 트리거입니다.

## 역할

### ADMIN

정책, 규칙, 설정을 관리하는 역할입니다.

### OPERATOR

Proposal 승인, Mission 실행, 상태 확인을 담당하는 역할입니다.

### VIEWER

읽기 전용으로 상태와 결과를 확인하는 역할입니다.

## 운영 개념

### Planning / Execution

- `Planning`: 어떻게 실행할지 제안하는 단계
- `Execution`: 승인 후 실제로 실행하는 단계

### Policy

무엇이 허용되고 무엇을 자동 실행할지 정하는 상위 기준입니다.

### Rule

특정 Event가 발생했을 때 어떤 액션을 실행할지 정하는 하위 규칙입니다.

### Event 기반 시스템

Rule은 매 주기마다 실행되지 않고 의미 있는 Event가 발생했을 때만 평가됩니다.

## 자주 틀리는 표현

| 잘못된 표현 | 올바른 표현 |
|---|---|
| Proposal을 실행한다 | Proposal을 승인하고 Mission을 실행한다 |
| 사용자가 Task를 거절한다 | Device Agent가 Task를 ABORTED로 거절한다 |
| Mission이 ASSIGNED 상태다 | ASSIGNED는 Task 상태다 |

## 정본 위치

- 상태와 필드: `core/schema.md`
- 설계 원칙: `core/principles.md`
- 구조와 책임: `SYSTEM_ARCHITECTURE.md`
- 절차와 흐름: `scenarios/*.md`
