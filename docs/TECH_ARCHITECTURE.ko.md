# CoWater 기술 구조 설명서

본 문서는 2026-05-06 현재 저장소 구현 기준으로 작성되었습니다. 현재 구현과 향후 목표를 분리해 기술 구조를 설명합니다.

## 1. 현재 실행 구조

현재 저장소의 핵심 실행 구조는 다음과 같습니다.

| 경로                   | 컴포넌트         | 기본 포트      | 책임                                                                         |
| ---------------------- | ---------------- | -------------- | ---------------------------------------------------------------------------- |
| `server/registration/` | Registry Server  | `8280`         | 디바이스 등록, healthcheck 반영, assignment 계산, Event/Alert/Response 원장  |
| `server/system-agent/` | System Agent     | `9116`         | Event 수신, Alert 생성, Response 계획, A2A dispatch                          |
| `device/`              | Device Agent     | `9111`-`9115`  | USV/AUV/ROV/Control Ship lower/middle agent 실행, telemetry/healthcheck 발행 |
| `client/`              | Static Dashboard | 파일 직접 열기 | Three.js 기반 3D 관제 및 경보 화면                                           |

현재 저장소 기준으로 `services/`, `infra/`, Docker Compose 파일, React/Vue/TypeScript frontend entrypoint는 확인되지 않습니다. 따라서 Docker Compose/Nginx 기반 분산 배포와 React/Vue 전환은 향후 목표로 분류합니다.

## 2. Agent 계층 구조

```text
System Layer  : server/system-agent    System Agent
Middle Layer  : device --type usv --layer middle      USV Middle
                device --type ship --layer middle     Control Ship
Lower Layer   : device --type usv --layer lower       USV
                device --type auv --layer lower       AUV
                device --type rov --layer lower       ROV
Shared Server : server/registration                   Registry Server
```

| 계층            | 책임                                                                                      |
| --------------- | ----------------------------------------------------------------------------------------- |
| Registry Server | 등록/조회 API, healthcheck 반영, 위치/연결 상태 갱신, parent assignment 계산, ledger 제공 |
| System Agent    | 최고 수준의 event/alert/response 처리, target 선정, A2A dispatch                          |
| Middle Agent    | 하위 디바이스 조율, parent routing, A2A 중계                                              |
| Lower Agent     | 실제 임무 수행, telemetry/healthcheck 발행, 결과/이벤트 상향 보고                         |

현재 구현에서 `Detect Agent`, `Analyze Agent`, `Report Agent`, `User Agent`는 독립 실행 서비스가 아닙니다. 해당 역할은 향후 분리 후보입니다.

## 3. 통신 구조

### HTTP A2A

Agent 간 명령과 이벤트 전달은 MCP가 아니라 HTTP A2A를 사용합니다.

```http
POST http://{target_endpoint}/message:send
```

대표 message type은 다음과 같습니다.

| message type       | 용도                                              |
| ------------------ | ------------------------------------------------- |
| `event.report`     | 하위/중간 agent가 발생 사실을 System Agent에 보고 |
| `task.assign`      | System Agent가 대상 agent에 task 배정             |
| `mission.result`   | 현장 실행 결과를 System Agent에 보고              |
| `layer.assignment` | parent/route assignment 반영                      |

### 주요 HTTP API

Registry Server는 canonical 상태와 원장을 제공하고, System Agent는 자신의 의사결정 상태와 수동 개입 필요 항목을 제공합니다.

| 컴포넌트        | API                                          | 용도                             |
| --------------- | -------------------------------------------- | -------------------------------- |
| Registry Server | `GET /health`                                | Registry 상태 확인               |
| Registry Server | `GET /devices`, `POST /devices`              | 디바이스 조회/등록               |
| Registry Server | `PUT /devices/{device_id}/agent`             | Agent endpoint/capability attach |
| Registry Server | `POST /events/ingest`, `GET /events`         | Event 원장                       |
| Registry Server | `POST /alerts/ingest`, `GET /alerts`         | Alert 원장                       |
| Registry Server | `POST /responses/ingest`, `GET /responses`   | Response 원장                    |
| System Agent    | `GET /health`, `GET /state`, `GET /manifest` | System Agent 상태 확인           |
| System Agent    | `POST /message:send`                         | A2A message 수신                 |
| System Agent    | `GET /manual-interventions`                  | 수동 개입 필요 Response 목록     |
| System Agent    | `GET /manual-interventions/{response_id}`    | 특정 수동 개입 건 상세           |

### Moth healthcheck/telemetry

실시간 데이터는 Moth WebSocket을 사용합니다.

```text
Device Agent
  -> Moth WebSocket healthcheck/track telemetry
  -> Registry healthcheck subscriber
  -> Client dashboard WebSocket subscription
```

현재 구현에서 Moth는 healthcheck와 telemetry stream 용도입니다. A2A 명령 전달 경로가 아닙니다.

## 4. 데이터 모델

| 모델     | canonical owner | 설명                                                       |
| -------- | --------------- | ---------------------------------------------------------- |
| Device   | Registry Server | 이름, 타입, 계층, track, action, agent endpoint, 연결 상태 |
| Event    | Registry Server | 실제 발생한 사실                                           |
| Alert    | Registry Server | 대응이 필요한 알림 레코드                                  |
| Response | Registry Server | Alert에 대해 계획되거나 실행된 대응 기록                   |

severity enum은 `CRITICAL`, `WARNING`, `INFORMATION`입니다. Green/Yellow/Red는 UI 또는 발표용 표시 개념으로 사용할 수 있으나, 현재 저장 모델의 표준 값은 아닙니다.

## 5. Assignment 및 라우팅

Registry Server는 lower-layer 디바이스에 대해 parent assignment를 계산하고 다음 값을 제공합니다.

| 필드                      | 설명                                                                          |
| ------------------------- | ----------------------------------------------------------------------------- |
| `parent_id`               | 경유해야 하는 middle-layer 디바이스 ID                                        |
| `parent_endpoint`         | parent agent의 A2A endpoint                                                   |
| `parent_command_endpoint` | parent agent의 command endpoint                                               |
| `route_mode`              | `direct_to_system`, `via_parent`, `parent_required_unassigned` 등 라우팅 상태 |
| `force_parent_routing`    | parent 경유 강제 여부                                                         |

현재 구현 기준의 주요 규칙은 다음과 같습니다.

- ROV는 유선 연결 특성상 parent 기반 라우팅이 강제될 수 있습니다.
- AUV는 수중/submerged 상태에 따라 parent 경유 여부가 달라질 수 있습니다.
- middle-layer가 offline이면 Registry가 lower-layer assignment를 재계산합니다.
- System Agent는 target device에 parent가 있으면 parent를 경유하고, 없으면 직접 dispatch합니다.

## 6. 실행 및 배포 방식

현재 기준 실행 방식은 Python 직접 실행 또는 helper script 사용입니다.

```bash
cd server/registration
python3 device_registration_server.py
```

```bash
cd server/system-agent
python3 system_agent.py
```

```bash
cd device
python3 device_agent.py --type usv --layer lower
python3 device_agent.py --type auv --layer lower
python3 device_agent.py --type rov --layer lower
python3 device_agent.py --type usv --layer middle
python3 device_agent.py --type ship --layer middle
```

전체 실행 helper는 루트의 `cowaterctl.sh`와 `START_SERVICES.sh`, `STOP_SERVICES.sh`, `STATUS_SERVICES.sh`를 사용합니다.

Docker Compose, Nginx reverse proxy, 물리 PC 다중 배포는 현재 저장소 기준 구현 확인 대상이 아니며 향후 배포 목표입니다.

## 7. 문서/구현 정합성 체크리스트

문서를 수정할 때는 다음 항목을 확인합니다.

- 실행 명령이 `SERVER_STARTUP_GUIDE.md`와 일치하는가
- Agent 계층과 책임이 `SYSTEM_ARCHITECTURE_PRINCIPLES.md`와 일치하는가
- API 경로가 실제 FastAPI endpoint와 일치하는가
- A2A와 Moth의 역할을 혼동하지 않는가
- `Green/Yellow/Red`가 내부 enum이 아니라 표시 개념임을 명시했는가
- `CRITICAL`, `WARNING`, `INFORMATION` severity enum을 대문자로 표기했는가
- 구현되지 않은 기능을 현재 기능처럼 쓰지 않았는가

## 8. 구현 한계 및 개선 예정

| 항목            | 현재 한계                             | 개선 방향                                     |
| --------------- | ------------------------------------- | --------------------------------------------- |
| 자연어/음성 UI  | 사용자-facing 명령 UI 없음            | Chat/Voice command interface 추가             |
| Agent 역할 분리 | System/Middle/Lower 중심              | Detect/Analyze/Report 등 독립 agent 분리 검토 |
| AI 판단         | rule 기반이 중심, LLM hook은 보조     | LLM 판단 결과의 검증/권한/추적 체계 추가      |
| Frontend        | 정적 HTML/JS                          | TypeScript 기반 app 구조 전환 검토            |
| 배포            | 로컬 Python 실행 중심                 | Docker Compose/Nginx 분산 배포 구성           |
| 보안            | 기본 secret key와 local endpoint 중심 | 인증, 권한, 네트워크 보안 정책 추가           |
