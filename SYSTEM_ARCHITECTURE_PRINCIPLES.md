# CoWater 시스템 아키텍처 원칙 및 규칙

**버전**: 1.3  
**최초 작성**: 2026-04-29  
**최종 수정**: 2026-05-04

**목적**: CoWater의 시스템 구조, 책임 경계, 통신 규칙, 상태 소유권을 한 문서에서 일관되게 정의한다.

---

## 1. 문서 사용 원칙

- 이 문서는 "정의"를 한 번만 적는다.
- 세부 구현이나 예시는 정의를 반복하지 않고 해당 정의를 참조한다.
- 현재 구현과 다른 이상적 구조를 섞어 쓰지 않는다.

---

## 2. 시스템 개요

**CoWater**는 해양 무인 시스템(AUV, ROV, USV 등)의 협력 운용을 위한 멀티레이어 분산 에이전트 시스템이다.

### 계층 구조

```text
System Layer  : POC 06  System Agent
Middle Layer  : POC 04  USV Middle, POC 05 Control Ship
Lower Layer   : POC 01  USV, POC 02 AUV, POC 03 ROV
Shared Server : POC 00  Registry Server
```

### 핵심 목표

- 각 에이전트는 자신의 계층 책임 안에서 독립적으로 동작한다.
- 계층 간 의도적 상호작용은 명시적 메시지로만 수행한다.
- 공유 상태는 Registry Server 또는 Moth를 통해서만 접근한다.
- 개별 에이전트 장애가 전체 시스템 정지로 이어지지 않아야 한다.

---

## 3. 용어 정의

| 용어 | 의미 |
| --- | --- |
| `Registry Server` | POC 00. 디바이스 등록, 상태 저장, heartbeat 반영, assignment 계산, alert/response 원장 제공 |
| `System Agent` | POC 06. system-layer 최고 의사결정 에이전트 |
| `Middle Agent` | POC 04, 05. 상위 명령을 하위 디바이스에 분배·중계하는 에이전트 |
| `Lower Agent` | POC 01, 02, 03. 실제 임무를 수행하는 에이전트 |
| `Event` | 실제로 발생한 사실. 예: 기뢰 감지, 통신 두절, 배터리 부족 |
| `Alert` | 대응 결정을 유도하기 위한 알림 레코드 |
| `Response` | Alert에 대해 계획되거나 실행된 대응 레코드 |
| `A2A` | 에이전트 간 직접 메시지 전송 |
| `MCP` | 에이전트가 외부 API 또는 도구를 구조화된 인터페이스로 호출할 때 사용하는 도구 접근 계층 |
| `Telemetry` | 센서·장비 데이터 스트림 |
| `Heartbeat` | 생존·위치·배터리 등의 최소 상태 스냅샷 |

현재 구현/설정 기준으로 MCP 관련 도구는 주로 `System Agent` capability에 선언되며, 일반적인 에이전트 간 명령 전달 수단은 아니다.

---

## 4. 정식 식별자

### Device Type / Layer

```python
DEVICE_TYPES = Literal["USV", "AUV", "ROV", "CONTROL_SHIP", "SYSTEM"]
LAYERS = Literal["lower", "middle", "system"]
ALERT_SEVERITIES = Literal["CRITICAL", "WARNING", "INFORMATION"]
```

- Registry API에는 대문자 `DEVICE_TYPE`만 사용한다.
- `SYSTEM`은 `System Agent`를 의미한다.
- Alert severity는 대문자 enum `CRITICAL`, `WARNING`, `INFORMATION`만 사용한다.

### 포트

| 포트 | 컴포넌트 |
| --- | --- |
| `8280` | Registry Server (POC 00) |
| `9111` | USV Lower Agent (POC 01) |
| `9112` | AUV Lower Agent (POC 02) |
| `9113` | ROV Lower Agent (POC 03) |
| `9114` | USV Middle Agent (POC 04) |
| `9115` | Control Ship Middle Agent (POC 05) |
| `9116` | System Agent (POC 06) |

포트 충돌 시 `config.json`에서 조정한다.

---

## 5. 책임 분담

### 책임 표

| 컴포넌트 | 책임 |
| --- | --- |
| Registry Server | 등록·조회 API, heartbeat 반영, 위치/연결 상태 갱신, parent assignment 계산, alert/response ledger |
| System Agent | alert 해석, 타깃 선정, 최고 수준 의사결정, A2A task dispatch, response 기록 |
| Middle Agent | 하위 디바이스 조율, A2A 라우팅/중계, 하위 상태 인지 |
| Lower Agent | 임무 수행, telemetry/heartbeat 발행, 결과/이벤트 상향 보고 |

### 책임 경계 규칙

- 하나의 에이전트는 여러 하위 기능을 가질 수 있다.
- 다만 그 기능들은 하나의 계층/도메인 책임 아래 응집되어 있어야 한다.
- 새 기능이 기존 에이전트의 책임 경계를 넘어선다면 분리 여부를 먼저 검토한다.
- Registry Server는 에이전트가 아니라 공용 서버 컴포넌트다.

### 각 컴포넌트가 할 수 없는 것

| 컴포넌트 | 금지 |
| --- | --- |
| Registry Server | System Agent가 맡아야 할 임무 할당·대응 판단 수행, 하위 에이전트에 직접 임무 명령, 타 에이전트 내부 state 직접 조작 |
| System Agent | 중간 계층이 존재하는데 lower에 직접 명령, 타 디바이스 상태 임의 수정 |
| Middle Agent | 상위 명령 없이 일반 업무 의사결정 수행, System Agent 우회 alert 생성 |
| Lower Agent | 상위 지시 없이 일반 임무 결정, 다른 lower agent 내부 상태 직접 조회 |

### Safety-Critical 예외

| 주체 | 상황 | 허용 조치 |
| --- | --- | --- |
| Middle Agent | 자식 배터리 급락, 충돌 위험, 장기 통신 두절 | 즉시 귀환, 비상정지, 복구 명령 |
| Lower Agent | 자신의 배터리 임계치, 충돌 임박 | 자체 귀환, 비상정지 |

예외 조치 후에는 반드시 상위에 A2A 또는 heartbeat로 상황을 알린다.

---

## 6. 통신 규칙

### 통신 매트릭스

| 용도 | 방식 | 비고 |
| --- | --- | --- |
| 상위 명령 전달 | A2A over HTTP | 중간 계층이 있으면 경유, 없으면 직접 |
| 하위 이벤트 보고 | A2A over HTTP | 중간 계층이 있으면 경유, 없으면 직접 |
| 하위/중간 대응 결과 보고 | A2A over HTTP (`mission.result`) | 수행 결과를 상위로 보고 |
| 생존/위치/배터리 상태 | Moth `device.heartbeat` | Registry Server가 구독 |
| 센서 데이터 | Moth `device.telemetry.*` | 실시간 스트림 |
| Event 조회/기록 | Registry HTTP API | canonical ledger |
| Alert 조회/기록 | Registry HTTP API | canonical ledger |
| Response 기록/조회 | Registry HTTP API | canonical ledger |

### A2A 규칙

- 실제 A2A 전송은 Moth가 아니라 HTTP POST 직접 호출이다.
- 대상 endpoint는 Registry의 `agent.endpoint` 또는 `agent.command_endpoint`에서 얻는다.
- 모든 A2A 메시지는 최소한 다음 필드를 가져야 한다.
  - `message_type`
  - `action` 또는 `event_type`
  - `reason`
- 모든 A2A 메시지는 로깅한다.
- 대응 명령(`task.assign`)을 받은 에이전트는 `incident_decision` 로그를 남겨야 한다.
- 대응 수행 후에는 `mission.result`를 상위(또는 지정된 report endpoint)로 보고해야 한다.

예시:

```http
POST http://{target_endpoint}/message:send
```

### Heartbeat 규칙

- 모든 에이전트는 `1초` 주기로 heartbeat를 발행한다.
- `3초` 이상 heartbeat가 없으면 Registry가 offline으로 처리한다.
- 위치 데이터를 생성하거나 읽을 수 있는 에이전트는 `latitude`, `longitude`를 heartbeat에 포함해야 한다.
- 배터리 데이터를 생성하거나 읽을 수 있는 에이전트는 배터리 값을 heartbeat에 포함해야 한다.
- 현재 구현에서 lower / middle agent는 Moth `device.heartbeat`를 사용하고, System Agent는 Registry keepalive로 `last_seen_at`을 갱신한다.

### Telemetry 규칙

- telemetry는 센서 데이터 스트림이다.
- Registry의 canonical 상태 갱신 기준은 telemetry가 아니라 heartbeat다.
- telemetry만 발행하고 heartbeat에 위치를 넣지 않으면 Registry 위치 정보는 stale해질 수 있다.

### Event / Alert / Response 규칙

| 도메인 | 역할 | canonical 저장 위치 |
| --- | --- | --- |
| Event | 발생 사실 전달 | Registry Server event ledger |
| Alert | 대응 필요 알림 | Registry Server alert ledger |
| Response | Alert 대응 계획/결과 | Registry Server response ledger |

현재 구현 기준에서 System Agent는 A2A로 Event를 수신한 뒤 Event를 Registry Server에 기록하고, severity를 판단해 Alert를 생성하며, 이후 approve/dispatch/response 기록을 담당한다.
또한 `event.report` 수신 직후 Alert 처리를 비동기로 즉시 시작하며, dispatch 성공 시 Response 상태를 `completed`, 실패 시 `failed`로 갱신한다.

기본 `event_type` 매핑은 `System Agent`의 `config.json > event_rules`에서 정의한다.

| event_type | 기본 severity | 기본 recommended_action |
| --- | --- | --- |
| `mine_detection` | `CRITICAL` | `survey_depth` |
| `collision_risk` | `CRITICAL` | `escalate_alert` |
| `distress` | `CRITICAL` | `escalate_alert` |
| `battery_low` | `WARNING` | `return_to_base` |
| `communication_loss` | `WARNING` | `escalate_alert` |
| `tether_warning` | `WARNING` | `escalate_alert` |

규칙:

- A2A `event.report`에 severity가 명시되면 그 값을 우선 사용한다.
- severity가 없으면 `event_rules`의 기본값을 사용한다.
- 매핑이 없으면 severity는 `INFORMATION`으로 본다.
- Response 상태는 최소 `planned -> completed/failed` 전이를 가져야 한다.
- `dispatch_result`에는 A2A 전송 결과(성공 여부, 대상 endpoint, 응답 본문 또는 오류)를 기록한다.
- `mission.result`가 수신되면 System Agent는 해당 response를 현장 실행 결과 기준으로 다시 갱신한다.

---

## 7. 상태 소유권

### Single Source of Truth

| 정보 | 소유자 |
| --- | --- |
| 디바이스 위치 | Registry Server |
| 디바이스 연결 상태 | Registry Server |
| `parent_id`, `route_mode`, `force_parent_routing` | Registry Server |
| 현재 활성 임무 | 해당 에이전트 state |
| Event | Registry Server |
| Alert | Registry Server |
| Response | Registry Server |
| A2A 통신 이력 | Moth 시각화 + 각 에이전트 inbox/outbox |

### 상태 규칙

- 하나의 사실은 하나의 canonical owner만 가져야 한다.
- 같은 정보를 여러 위치에 유지하면 동기화 기준을 명시해야 한다.
- Registry 상태와 로컬 체감 상태가 다르면, 다음 heartbeat 전까지 Registry를 공용 기준으로 본다.

---

## 8. Assignment 규칙

Registry Server는 lower-layer에 대해 다음 정보를 계산·배포한다.

- `parent_id`
- `parent_endpoint`
- `parent_command_endpoint`
- `route_mode`
- `force_parent_routing`

기본 규칙:

- middle-layer 후보가 있으면 lower-layer는 가능한 parent를 가진다.
- ROV는 parent 기반 라우팅이 강제될 수 있다.
- AUV는 submerged 상태에 따라 라우팅이 달라질 수 있다.
- middle-layer가 offline이면 Registry가 자식을 재할당하거나 `direct_to_system`으로 전환한다.

---

## 9. 장애 처리 및 복원력

### 장애 표

| 장애 | 기본 대응 |
| --- | --- |
| Heartbeat timeout | offline 처리, 필요 시 자식 재할당 |
| Registry 연결 실패 | 재시도, 가능한 범위에서 로컬 캐시로 기본 동작 유지 |
| Moth 연결 실패 | 재연결 시도, 핵심 명령 흐름은 중단하지 않음 |
| A2A 전송 실패 | timeout, 로깅, 재시도 또는 상위 보고 |
| LLM 기능 실패 | 규칙 기반 처리로 폴백 |

### 복원력 규칙

- 모든 외부 호출에는 timeout이 있어야 한다.
- 연결 실패는 로깅되어야 한다.
- 선택적 기능 실패가 핵심 기능을 막아서는 안 된다.
- 재시도 정책은 무한 대기가 아니라 backoff를 가져야 한다.

예시:

```python
urllib.request.urlopen(req, timeout=5)
```

---

## 10. 구현 원칙

### 코드 작성

- 설정값은 코드에 하드코딩하지 않고 `config.json`에서 읽는다.
- 에러를 삼키지 않고 로깅 또는 폴백 경로를 남긴다.
- 메시지 포맷 변경 시 하위 호환성 영향을 먼저 검토한다.
- 외부 에이전트 내부 상태를 직접 조회하지 않는다.

### HTTP 클라이언트

- 기본 표준은 `urllib.request`
- 예외적으로 비동기 LLM 호출에 한해 별도 클라이언트 사용 가능

### MCP 사용 원칙

- MCP는 에이전트의 외부 도구/API 접근에 사용한다.
- 에이전트 간 명령/이벤트 전달은 MCP가 아니라 A2A를 사용한다.
- 공용 상태 조회/기록은 MCP가 아니라 Registry Server 또는 Moth 규칙을 따른다.

### 동작 검증

- `GET /health`가 정상 응답해야 한다.
- Registry 없이도 가능한 기본 동작은 유지되어야 한다.
- Moth 없이도 서비스 전체가 즉시 중단되면 안 된다.
- heartbeat, telemetry, A2A 로그가 실제로 남아야 한다.
- `layer.assignment` 로그는 할당 변경 시에만 남겨 핵심 incident 로그가 밀리지 않게 유지한다.

---

## 11. 대표 시나리오

### 기뢰 탐지

```text
1. Lower Agent 또는 외부 시스템이 mine_detection Event를 상위로 보고
2. System Agent가 Event를 Registry Server event ledger에 기록한다
3. System Agent가 Event의 위험도를 판단해 Alert를 생성하고 Registry Server alert ledger에 적재한다
4. System Agent가 Alert를 해석하고 가용 디바이스를 조회
5. middle-layer가 있으면 middle에 task.assign, 없으면 lower에 직접 task.assign
6. 수행 결과는 상위로 다시 A2A 보고
7. 대응 계획과 결과는 Response로 기록
```

### 의사결정 권한

| 질문 | System | Middle | Lower |
| --- | --- | --- | --- |
| 어느 middle agent에 맡길까 | ✅ | ❌ | ❌ |
| 어느 lower agent에 분배할까 | ❌ | ✅ | ❌ |
| 실제 장비를 어떻게 움직일까 | ❌ | ❌ | ✅ |
| 자기 안전 때문에 임무를 중단할까 | ❌ | 부분 허용 | ✅ |

---

## 12. 리뷰 체크리스트

- 계층 구조를 위반하지 않는가
- 책임 경계가 기존 정의와 맞는가
- Registry Server를 에이전트처럼 취급하지 않는가
- A2A와 Moth 역할을 혼동하지 않는가
- canonical state owner가 명확한가
- heartbeat 필수 필드가 빠지지 않았는가
- 외부 호출에 timeout과 에러 로깅이 있는가
- 새 메시지/API 변경의 호환성 영향을 검토했는가

---

## 13. 나쁜 예와 좋은 예

### 나쁜 예

- Middle Agent가 lower agent의 `/state`를 직접 조회해 임무를 결정한다.
- Registry Server가 직접 lower agent에 임무 명령을 내린다.
- telemetry만 위치를 발행하고 heartbeat에는 위치를 넣지 않는다.

### 좋은 예

- Middle Agent는 Registry의 공개 정보만 조회하고, 명령은 A2A로 보낸다.
- System Agent는 Registry의 alert를 읽고 대상만 결정한다.
- Lower Agent는 자신의 상태를 heartbeat로 주기적으로 발행한다.
