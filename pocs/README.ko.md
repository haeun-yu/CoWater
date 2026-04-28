# CoWater PoC 워크스페이스

이 워크스페이스는 계층형 무인체 Agent 시스템을 1~6번 PoC로 다시 정리합니다. `00-device-registration-server`는 번호 체계 밖의 공통 인프라로, 각 하위/중간 Agent가 시작 시 자신의 디바이스 정보를 등록하고 id/token을 발급받는 역할을 합니다.

## PoC 경계

| PoC | 목적 | 실행 단위 |
| --- | --- | --- |
| `00-device-registration-server` | 디바이스 id/name/token/agent endpoint 등록 | 공통 API 서버 |
| `01-usv-lower-agent` | USV 시뮬레이터 + 하위 실행 판단 Agent | USV 1대당 프로세스 1개 |
| `02-auv-lower-agent` | AUV 시뮬레이터 + 하위 실행 판단 Agent | AUV 1대당 프로세스 1개 |
| `03-rov-lower-agent` | ROV 시뮬레이터 + 하위 실행 판단 Agent | ROV 1대당 프로세스 1개 |
| `04-usv-middle-agent` | 중계/조율 USV 시뮬레이터 + 중간 계층 Agent | 현장 relay USV 1대당 프로세스 1개 |
| `05-control-ship-middle-agent` | Control Ship 시뮬레이터 + 중간 계층 Agent | Control Ship 1대당 프로세스 1개 |
| `06-system-supervisor-agent` | 상위 System Supervisor Agent | 시스템 운영 감독 프로세스 |

기존 `01-device-streams`, `02-device-agent-contract`, `05-control-ship-agent`, `06-control-center-system-agent`는 재편 전 참고 구현으로 남아 있습니다.

## 실행

먼저 공통 등록 서버를 실행합니다.

```bash
python3 pocs/00-device-registration-server/device_registration_server.py --host 127.0.0.1 --port 8003
```

각 Agent는 독립 터미널에서 실행합니다. 같은 PoC를 두 번 실행하면 `COWATER_INSTANCE_ID`가 없는 한 런타임 instance id가 새로 생성되어 서로 다른 디바이스로 등록됩니다.

```bash
python3 pocs/01-usv-lower-agent/device_agent.py --port 9111
python3 pocs/01-usv-lower-agent/device_agent.py --port 9112
python3 pocs/02-auv-lower-agent/device_agent.py --port 9121
python3 pocs/03-rov-lower-agent/device_agent.py --port 9131
python3 pocs/04-usv-middle-agent/device_agent.py --port 9141
python3 pocs/05-control-ship-middle-agent/device_agent.py --port 9151
python3 pocs/06-system-supervisor-agent/system_agent.py --port 9161
```

## 통신 경계

- MCP: 상위 System Supervisor Agent와 API 서버 사이의 확장 지점입니다. 이번 구현에서는 상위 Agent manifest에 `mcp_api_client` tool을 명시하고, 실제 MCP 서버화는 API 서버 쪽 후속 작업으로 남깁니다.
- A2A: Agent 간 이벤트/작업 통신입니다. 새 런타임은 최신 A2A 형태의 JSON-RPC `message/send`를 `/`에서 받고, 기존 PoC 호환을 위해 `/message:send`도 제공합니다.
- Moth: 실시간 디바이스 데이터 스트림 경계입니다. 이번 재편의 각 PoC simulator는 telemetry 상태와 track manifest를 생성하고, 기존 Moth 직접 송신 구현은 `01-device-streams`를 참고 구현으로 유지합니다.

## 설계 규칙

- 하위 Agent와 중간 Agent는 같은 디렉터리 구조와 인터페이스를 사용하지만, 구현 파일은 각 PoC 내부에 둡니다.
- 디바이스별 차이는 각 PoC의 `config.json`과 `agent/`, `simulator/`, `skills/`, `tools/` 구현으로 표현합니다.
- 중간 계층은 선택 사항입니다. 상위 Agent는 중간 Agent가 없으면 하위 Agent로 직접 라우팅할 수 있습니다.
- 각 디바이스 프로세스는 시작 시 등록 서버에 등록하고, 받은 id/token을 `.runtime/{instance_id}.json`에 저장합니다.
- LLM은 `gemma4` 설정을 기본으로 manifest에 남기되, 실시간 판단 루프는 안전한 rule 기반 결정을 먼저 수행합니다.
