# CoWater 서버 실행 가이드

## 디렉토리 구조

| 디렉토리 | 역할 |
| --- | --- |
| `server/registration/` | Registry Server (포트 8280) |
| `server/system-agent/` | System Agent (포트 9116) |
| `device/` | Device Agent — 타입·계층을 옵션으로 선택 |
| `client/` | 실시간 대시보드 (HTML) |

## 기본 포트

| 포트 | 컴포넌트 |
| --- | --- |
| `8280` | Registry Server |
| `9111` | USV Lower Agent |
| `9112` | AUV Lower Agent |
| `9113` | ROV Lower Agent |
| `9114` | USV Middle Agent |
| `9115` | Control Ship Middle Agent |
| `9116` | System Agent |

## 사전 준비

```bash
cd /Users/teamgrit/Documents/CoWater
source .venv/bin/activate
```

## 권장 실행 순서

### 1. Registry Server

```bash
cd server/registration
python3 device_registration_server.py
```

확인:

```bash
curl http://127.0.0.1:8280/health | jq .
```

### 2. System Agent

```bash
cd server/system-agent
python3 system_agent.py
```

확인:

```bash
curl http://127.0.0.1:9116/health | jq .
```

### 3. Middle Agents

하나의 터미널에서 하나의 디바이스를 실행한다.

```bash
cd device
python3 device_agent.py --type usv --layer middle
```

```bash
cd device
python3 device_agent.py --type ship --layer middle
```

### 4. Lower Agents

```bash
cd device
python3 device_agent.py --type usv --layer lower
```

```bash
cd device
python3 device_agent.py --type auv --layer lower
```

```bash
cd device
python3 device_agent.py --type rov --layer lower
```

### 동일 타입 여러 인스턴스 실행

같은 타입의 디바이스를 여러 개 띄울 때는 `--port`로 포트를 구분한다.

```bash
# 터미널 1
cd device && python3 device_agent.py --type usv --layer lower --port 9121

# 터미널 2
cd device && python3 device_agent.py --type usv --layer lower --port 9122
```

## device_agent.py 옵션

| 옵션 | 필수 | 설명 |
| --- | --- | --- |
| `--type` | ✅ | 디바이스 타입: `usv` / `auv` / `rov` / `ship` |
| `--layer` | ✅ | 에이전트 계층: `lower` / `middle` |
| `--port` | - | 서버 포트 오버라이드 (기본값: config.json 값) |
| `--host` | - | 서버 host 오버라이드 |
| `--config` | - | 커스텀 config.json 경로 |

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

- 모든 에이전트 `configs/{type}-{layer}.json > registry.url` 기본값은 `http://127.0.0.1:8280`
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

완료 상태 확인:

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

`device/configs/{type}-{layer}.json > registry.url`이 `http://127.0.0.1:8280`인지 확인한다.
