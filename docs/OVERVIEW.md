# CoWater 시스템 개요

본 문서는 2026-05-06 현재 저장소 구현 기준으로 작성되었습니다.

## 디렉토리 구성

| 디렉토리               | 역할                               | 기본 포트 |
| ---------------------- | ---------------------------------- | --------- |
| `server/registration/` | Registry Server                    | `8280`    |
| `server/system-agent/` | System Agent                       | `9116`    |
| `device/`              | Device Agent (타입·계층 옵션 선택) | 9111–9115 |
| `client/`              | 실시간 대시보드 (HTML)             | -         |

## 계층 구조

```text
System Layer  : server/system-agent/
Middle Layer  : device/ --type usv --layer middle     (포트 9114)
                device/ --type ship --layer middle    (포트 9115)
Lower Layer   : device/ --type usv --layer lower      (포트 9111)
                device/ --type auv --layer lower      (포트 9112)
                device/ --type rov --layer lower      (포트 9113)
Shared Server : server/registration/                  (포트 8280)
```

## 현재 구현 핵심

- Registry Server는 디바이스 등록, healthcheck 반영, assignment 계산, Event / Alert / Response 원장을 제공한다.
- System Agent는 A2A `event.report`를 수신하면 Event를 저장하고 severity를 판단해 Alert를 생성한다.
- System Agent는 Alert를 즉시 처리해 A2A dispatch를 시도하고, Response 상태를 `completed` 또는 `failed`로 갱신한다.
- severity enum은 `CRITICAL`, `WARNING`, `INFORMATION`을 사용한다.
- lower / middle agent는 기본적으로 `1초` healthcheck와 telemetry를 발행한다.
- System Agent는 `1초` Registry keepalive로 연결 상태를 유지한다.

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
cd server/registration
python3 device_registration_server.py
```

System Agent:

```bash
cd server/system-agent
python3 system_agent.py
```

Middle Layer:

```bash
cd device && python3 device_agent.py --type usv --layer middle
cd device && python3 device_agent.py --type ship --layer middle
```

Lower Layer:

```bash
cd device && python3 device_agent.py --type usv --layer lower
cd device && python3 device_agent.py --type auv --layer lower
cd device && python3 device_agent.py --type rov --layer lower
```

## 설정 기준

- Registry 기본 주소: `http://127.0.0.1:8280`
- 각 에이전트의 `device/configs/{type}-{layer}.json > registry.url`도 같은 값을 사용한다.
- healthcheck 기본값: `interval_seconds=1`, `timeout_seconds=3`
- Moth는 healthcheck / telemetry 전송용이며, 에이전트 간 명령은 HTTP A2A를 사용한다.

## 참고 문서

- 프로젝트 소개서: [INTRODUCTION.ko.md](./INTRODUCTION.ko.md)
- 기능 명세서: [FEATURE_SPEC.ko.md](./FEATURE_SPEC.ko.md)
- 기술 구조 설명서: [TECH_ARCHITECTURE.ko.md](./TECH_ARCHITECTURE.ko.md)
- 아키텍처 기준: [SYSTEM_ARCHITECTURE_PRINCIPLES.md](../SYSTEM_ARCHITECTURE_PRINCIPLES.md)
- 실행 절차: [SERVER_STARTUP_GUIDE.md](../SERVER_STARTUP_GUIDE.md)
- 전체 서비스 스크립트 실행: [START_GUIDE.md](../START_GUIDE.md)
- 기뢰 제거 시나리오: [MINE_REMOVAL_GUIDE.md](./MINE_REMOVAL_GUIDE.md)
