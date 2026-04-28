# TechSpec: CoWater PoC 1~6 계층형 Agent 재편

## 목표

PoC 1, 2, 5, 6의 기존 기능을 재조합해 1~6번을 계층형 Agent 시스템으로 다시 구성한다. 각 하위/중간 Agent는 같은 구현을 사용하되, 실행 중 연결된 디바이스의 `tools`, `skills`, `actions`, `tracks`, 하위 Agent 구성에 따라 다른 역할을 수행한다.

## 최종 번호 체계

| 번호 | 이름 | 계층 | 설명 |
| --- | --- | --- | --- |
| 00 | `device-registration-server` | 공통 | id/name/token/agent endpoint 발급 및 저장 |
| 01 | `usv-lower-agent` | 하위 | USV 로컬 실행 판단 |
| 02 | `auv-lower-agent` | 하위 | AUV 로컬 실행 판단 |
| 03 | `rov-lower-agent` | 하위 | ROV 로컬 실행 판단 |
| 04 | `usv-middle-agent` | 중간 | 중계 USV 기반 현장 조율 및 데이터 relay |
| 05 | `control-ship-middle-agent` | 중간 | Control Ship 기반 현장 조율 |
| 06 | `system-supervisor-agent` | 상위 | 전체 시스템 운영 감독 |

## 실행 모델

하위/중간 Agent는 디바이스 1대당 프로세스 1개로 실행한다. 같은 PoC 스크립트를 두 터미널에서 실행하면 서로 다른 `instance_id`가 생성되고, 등록 서버에는 별도의 디바이스로 보인다.

시작 순서:

1. Agent process가 config를 읽는다.
2. `COWATER_INSTANCE_ID`가 있으면 사용하고, 없으면 시간/PID/UUID 기반 instance id를 만든다.
3. 00 등록 서버 `POST /devices`로 name/tracks/actions를 등록한다.
4. 등록 서버가 id/token을 발급한다.
5. Agent가 `PUT /devices/{id}/agent`로 자신의 endpoint, commandEndpoint, role, skills, actions를 갱신한다.
6. 발급받은 id/token은 각 PoC 폴더의 `.runtime/{instance_id}.json`에 저장한다.

## Agent 구현

각 PoC는 자체 구현을 가진다. PoC 간 내부 구현 import는 하지 않는다. 하위/중간 Agent가 같은 구현 철학을 갖는 것은 동일한 디렉터리 구조와 인터페이스로 해결한다.

각 PoC 내부 구조:

```text
agent/       판단 루프, manifest, runtime state
controller/  HTTP, A2A, command endpoint
simulator/   디바이스 상태, 이동, 센서, telemetry 생성
skills/      Agent가 가진 능력 catalog
tools/       skill/agent/controller가 호출하는 실행 도구
transport/   등록 서버와 외부 프로토콜 client
storage/     로컬 id/token 저장
```

공통 endpoint:

- `GET /health`
- `GET /meta`
- `GET /state`
- `GET /manifest`
- `GET /.well-known/agent-card.json`
- `POST /` with JSON-RPC `method: "message/send"`
- `POST /message:send` legacy compatible binding
- `POST /agents/{token}/command`
- `POST /children/register`
- `GET /children`
- `GET /tasks`

## A2A 기준

표준 지향점은 Agent Card discovery와 JSON-RPC `message/send`이다. 기존 PoC와의 연결을 위해 `/message:send`를 동시에 유지한다.

처리 원칙:

- `task.assign`은 로컬 command로 변환한다.
- `child.register`는 중간/상위 Agent의 child registry에 기록한다.
- 결과는 A2A Task 형태의 `artifacts`로 남긴다.

## MCP 기준

현재 범위에서는 MCP를 상위 Agent와 API 서버 사이의 확장 지점으로 정의한다. 06의 manifest에는 `mcp_api_client` tool을 명시한다. API 서버를 실제 MCP server로 노출하는 작업은 후속 단계로 둔다.

## 중간 계층 선택성

중간 계층은 필수가 아니다.

- 중간 Agent가 있으면 System Supervisor -> Middle Agent -> Lower Agent 흐름을 사용한다.
- 중간 Agent가 없으면 System Supervisor -> Lower Agent 직접 라우팅을 허용한다.
- 중계 USV/Control Ship은 `children_required: false`이므로 단독 실행도 가능하다.

## LLM 사용

기본 LLM 설정은 `ollama/gemma4`로 둔다. 다만 실시간 텔레메트리 루프에서는 rule 기반 판단을 먼저 수행한다. LLM은 mission planning, 복합 상황 설명, operator-facing reasoning처럼 지연 허용도가 높은 기능에 붙이는 쪽으로 확장한다.

## 이번 구현 범위

포함:

- 00 등록 서버 번호 반영
- 1~6 새 PoC 디렉터리 추가
- 각 PoC 내부에 Agent/controller/simulator/skills/tools/transport/storage 구현 추가
- 각 PoC별 capabilities/tools/skills/actions/tracks config 추가
- A2A JSON-RPC `message/send`와 legacy `/message:send` 동시 지원
- 디바이스별 독립 실행 및 로컬 identity 저장

제외:

- API 서버의 실제 MCP server 구현
- 새 runtime에서 Moth WebSocket 직접 publish
- 기존 reference PoC 삭제
