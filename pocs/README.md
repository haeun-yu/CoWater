# CoWater POC 개요

이 문서는 `pocs/00`부터 `pocs/06`까지의 현재 구현 기준 구성과 실행 기준을 짧게 정리한다.

## 구성

| POC | 역할 | 기본 포트 |
| --- | --- | --- |
| `00` | Registry Server | `8280` |
| `01` | USV Lower Agent | `9111` |
| `02` | AUV Lower Agent | `9112` |
| `03` | ROV Lower Agent | `9113` |
| `04` | USV Middle Agent | `9114` |
| `05` | Control Ship Middle Agent | `9115` |
| `06` | System Agent | `9116` |

계층 구조:

```text
System Layer  : POC 06  System Agent
Middle Layer  : POC 04  USV Middle, POC 05 Control Ship
Lower Layer   : POC 01  USV, POC 02 AUV, POC 03 ROV
Shared Server : POC 00  Registry Server
```

## 현재 구현 핵심

- Registry Server는 디바이스 등록, heartbeat 반영, assignment 계산, Event / Alert / Response 원장을 제공한다.
- System Agent는 A2A `event.report`를 수신하면 Event를 저장하고 severity를 판단해 Alert를 생성한다.
- System Agent는 Alert를 즉시 처리해 A2A dispatch를 시도하고, Response 상태를 `completed` 또는 `failed`로 갱신한다.
- severity enum은 `CRITICAL`, `WARNING`, `INFORMATION`을 사용한다.
- lower / middle agent는 기본적으로 `1초` heartbeat와 telemetry를 발행한다.
- System Agent는 `1초` Registry keepalive로 연결 상태를 유지한다.
- heartbeat에 위치 데이터와 `battery_percent`를 포함할 수 있는 에이전트는 해당 필드를 포함한다.

## 기본 API

Registry Server의 주요 엔드포인트:

- `GET /health`
- `GET /devices`
- `POST /devices`
- `PUT /devices/{device_id}/agent`
- `POST /events/ingest`
- `GET /events`
- `POST /alerts/ingest`
- `GET /alerts`
- `POST /responses/ingest`
- `GET /responses`

System Agent의 주요 엔드포인트:

- `GET /health`
- `GET /state`
- `GET /manifest`
- `POST /message:send`

## 빠른 실행

Registry Server:

```bash
cd pocs/00-device-registration-server
python3 device_registration_server.py
```

System Agent:

```bash
cd pocs/06-system-agent
python3 system_agent.py
```

중간 계층:

```bash
python3 pocs/04-usv-middle-agent/device_agent.py
python3 pocs/05-control-ship-middle-agent/device_agent.py
```

하위 계층:

```bash
python3 pocs/01-usv-lower-agent/device_agent.py
python3 pocs/02-auv-lower-agent/device_agent.py
python3 pocs/03-rov-lower-agent/device_agent.py
```

## 설정 기준

- Registry 기본 주소: `http://127.0.0.1:8280`
- 각 에이전트의 `config.json > registry.url`도 같은 값을 사용한다.
- heartbeat 기본값: `interval_seconds=1`, `timeout_seconds=3`
- Moth는 heartbeat / telemetry 전송용이며, 에이전트 간 명령은 HTTP A2A를 사용한다.

## 참고 문서

- 아키텍처 기준: [SYSTEM_ARCHITECTURE_PRINCIPLES.md](/Users/teamgrit/Documents/CoWater/SYSTEM_ARCHITECTURE_PRINCIPLES.md)
- 실행 절차: [SERVER_STARTUP_GUIDE.md](/Users/teamgrit/Documents/CoWater/SERVER_STARTUP_GUIDE.md)
- 대표 검증 흐름: [SCENARIO_TEST.md](/Users/teamgrit/Documents/CoWater/SCENARIO_TEST.md)
- 기뢰 제거 시나리오: [pocs/docs/MINE_REMOVAL_GUIDE.md](/Users/teamgrit/Documents/CoWater/pocs/docs/MINE_REMOVAL_GUIDE.md)
