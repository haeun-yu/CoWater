# CoWater 서버 실행 가이드

이 문서는 현재 POC 기본 포트와 최소 실행 순서를 정리한다.

## 기본 포트

| 구성요소 | POC | 포트 |
| --- | --- | --- |
| Registry Server | `00` | `8280` |
| USV Lower Agent | `01` | `9111` |
| AUV Lower Agent | `02` | `9112` |
| ROV Lower Agent | `03` | `9113` |
| USV Middle Agent | `04` | `9114` |
| Control Ship Middle Agent | `05` | `9115` |
| System Agent | `06` | `9116` |

## 사전 준비

```bash
cd /Users/teamgrit/Documents/CoWater
source .venv/bin/activate
```

## 권장 실행 순서

### 1. Registry Server

```bash
cd pocs/00-device-registration-server
python3 device_registration_server.py
```

확인:

```bash
curl http://127.0.0.1:8280/health | jq .
```

### 2. System Agent

```bash
cd /Users/teamgrit/Documents/CoWater/pocs/06-system-agent
python3 system_agent.py
```

확인:

```bash
curl http://127.0.0.1:9116/health | jq .
```

### 3. Middle Agent

```bash
cd /Users/teamgrit/Documents/CoWater/pocs/04-usv-middle-agent
python3 device_agent.py
```

```bash
cd /Users/teamgrit/Documents/CoWater/pocs/05-control-ship-middle-agent
python3 device_agent.py
```

### 4. Lower Agent

```bash
cd /Users/teamgrit/Documents/CoWater/pocs/01-usv-lower-agent
python3 device_agent.py
```

```bash
cd /Users/teamgrit/Documents/CoWater/pocs/02-auv-lower-agent
python3 device_agent.py
```

```bash
cd /Users/teamgrit/Documents/CoWater/pocs/03-rov-lower-agent
python3 device_agent.py
```

## 한 번에 점검할 항목

Registry 등록 여부:

```bash
curl http://127.0.0.1:8280/devices | jq '.[] | {id, name, layer, device_type, connected}'
```

System Agent 상태:

```bash
curl http://127.0.0.1:9116/state | jq .
```

하위 에이전트 상태:

```bash
curl http://127.0.0.1:9112/state | jq '.last_telemetry'
curl http://127.0.0.1:9113/state | jq '.last_telemetry'
```

## 기본 설정 기준

- 모든 에이전트 `config.json > registry.url` 기본값은 `http://127.0.0.1:8280`
- heartbeat 기본값은 `1초 주기`, Registry timeout은 `3초`
- heartbeat 배터리 필드는 `battery_percent`
- Event / Alert / Response canonical ledger는 Registry Server에 있다
- lower / middle agent는 Moth heartbeat를 사용하고, System Agent는 Registry keepalive를 사용한다

## 대표 검증

Event 원장 확인:

```bash
curl http://127.0.0.1:8280/events | jq .
```

Alert 원장 확인:

```bash
curl http://127.0.0.1:8280/alerts | jq .
```

Response 원장 확인:

```bash
curl http://127.0.0.1:8280/responses | jq .
```

완료 상태 확인(권장):

```bash
curl http://127.0.0.1:8280/responses | jq '.[] | {response_id, alert_id, status, dispatch_result}'
```

## 문제 해결

포트 충돌:

```bash
lsof -i :8280
lsof -i :9116
```

Registry 등록이 안 될 때:

```bash
curl http://127.0.0.1:8280/devices | jq .
```

각 agent의 `config.json > registry.url`이 `http://127.0.0.1:8280`인지 확인한다.
