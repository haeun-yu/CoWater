# 핵심 도메인 모델

**목적**: 엔티티 간 관계와 책임 경계를 설명합니다.  
필드 정의는 `schema.md`, 절차는 `scenarios/*`, 구현 방법은 `implementation/*`를 봅니다.

---

## 이 문서가 다루는 것

- Device와 Agent의 관계
- Proposal, Mission, Task의 관계
- AgentConnection의 의미
- IdentityStore가 어떤 역할을 하는지

이 문서가 다루지 않는 것:

- 상세 등록 절차
- 단계별 실행 흐름
- 상태 전이 전체 표
- 구현 코드 예시

## 역할 정의

### Device

실제 작업을 수행하는 물리 자원입니다.

- 유형: USV, AUV, ROV
- 책임: 가능한 `actions[]`를 선언하고 실제 작업을 수행
- 상태와 필드: `schema.md#2-device-장비---hw-스펙`

### Agent

판단과 실행을 담당하는 소프트웨어 주체입니다.

- Device Agent: 특정 Device 하나를 제어
- System Agent: 전체 시스템의 계획, 정책, 감시, 리포팅을 담당

핵심 구분:

- Device = 물리 자원
- Agent = 지능 또는 제어 주체

### Device와 Agent의 결합

- Device Agent는 특정 Device에 결합됩니다.
- System Agent는 특정 Device에 결합되지 않습니다.
- 하나의 Device를 여러 Agent가 동시에 직접 제어하지 않습니다.

## IdentityStore의 의미

IdentityStore는 Device Agent가 재시작 후에도 자신과 시스템의 연결 정보를 복구할 수 있게 하는 로컬 저장소입니다.

여기에 저장하는 대표 정보:

- `device_id`
- `agent_id`
- 등록 시 받은 token, track, telemetry 관련 정보

이 문서에서는 역할만 정의합니다.  
구조는 `schema.md`, 등록 절차는 `scenarios/lifecycle.md`, 구현은 `implementation/device-agent.md`를 봅니다.

## AgentConnection

AgentConnection은 에이전트 사이의 협력 관계를 표현합니다.

대표 유형:

- `RELAY`
- `COORDINATE`
- `SHARE_DATA`
- `BACKUP`
- `SWARM_MEMBER`
- `LEADER_FOLLOWER`

대표 관계 수준:

- `PEER`
- `PARENT_CHILD`

핵심 원칙:

- 단순 선 연결이 아니라 협력 목적과 조건을 함께 표현합니다.
- 삭제는 보통 soft delete로 다룹니다.
- 통신 경로와 협력 방식의 정본은 `agent-connection.md`를 봅니다.

## 핵심 흐름 관계

### 사용자 요청에서 실행까지

```text
사용자 요청
→ Proposal 생성
→ Proposal 승인
→ Mission 생성
→ Task 분해 및 할당
→ Device / System Agent 실행
→ Event 기록 및 보고
```

### Event의 역할

Event는 다음 두 역할을 동시에 갖습니다.

- 시스템 변화 기록
- Policy / Rule 평가의 입력

## 정본 참조

- 필드와 상태: `schema.md`
- 설계 원칙: `principles.md`
- AgentConnection 상세: `agent-connection.md`
- 절차: `../scenarios/*.md`
- 구현: `../implementation/*.md`
