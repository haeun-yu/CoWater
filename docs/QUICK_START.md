# CoWater 실행 가이드

## 🚀 빠른 시작

### 1. 모든 서비스 시작

```bash
cd /Users/teamgrit/Documents/CoWater
./cowaterctl.sh start
```

**자동으로 실행:**
- Registry Server (포트 8280)
- System Agent Layer (포트 9110-9116, 6개 role)
- Device Agents (Ship-Middle, USV/AUV/ROV-Lower)

### 2. 상태 확인

```bash
./cowaterctl.sh status
```

모든 포트가 활성화될 때까지 잠시 대기합니다. (10-15초)

### 3. 로그 보기 (선택)

```bash
# 각각 실시간 로그 보기
./cowaterctl.sh logs registry
./cowaterctl.sh logs system-agent
./cowaterctl.sh logs device-ship
./cowaterctl.sh logs device-usv
./cowaterctl.sh logs device-auv
./cowaterctl.sh logs device-rov
```

### 4. Client UI 접속

브라우저에서:

- **Client SPA**: `http://127.0.0.1:5173/`
- **운영 관제**: `http://127.0.0.1:5173/ops`
- **미션 상세**: `http://127.0.0.1:5173/mission/<mission_id>`

### 5. 중지

```bash
./cowaterctl.sh stop
```

---

## 스크립트 명령어

```bash
./cowaterctl.sh start              # 모든 서비스 시작
./cowaterctl.sh stop               # 모든 서비스 중지
./cowaterctl.sh restart            # 재시작
./cowaterctl.sh status             # 상태 확인 (11개 포트 체크)
./cowaterctl.sh logs <service>     # 실시간 로그
```

---

## 고급: 수동 실행

cowaterctl.sh 없이 직접 실행하려면:

### 0단계: venv 활성화

```bash
cd /Users/teamgrit/Documents/CoWater
source .venv/bin/activate
```

### 1단계: Registry Server

```bash
cd server/registration
python device_registration_server.py
```

### 2단계: System Agent Layer

새 터미널:

```bash
cd server/system-agent
python run_system_agents.py
```

### 3단계: Device Agents

각각 새 터미널에서:

```bash
cd device
python device_agent.py --type ship --layer middle
python device_agent.py --type usv --layer lower
python device_agent.py --type auv --layer lower
python device_agent.py --type rov --layer lower
```

---

## 서비스 구조

```
CoWater System
│
├── Registry Server                  포트 8280
│   └── 디바이스 등록 · Event/Approval/Mission 원장
│
├── System Agent Layer
│   ├── DeviceBridge                 포트 9110
│   ├── MissionPlanner               포트 9111
│   ├── PolicyManager                포트 9112
│   ├── SystemSentinel               포트 9113
│   ├── InsightReporter              포트 9114
│   └── RequestHandler               포트 9116
│       └── SYS_INTENT_CLASSIFIED → Proposal → Mission → Task 흐름 조율
│
├── Device Agents
│   ├── USV           (layer=lower)  포트 9201
│   ├── AUV           (layer=lower)  포트 9202
│   ├── ROV           (layer=lower)  포트 9203
│   ├── Relay USV     (layer=middle) 포트 9204
│   └── Control Ship  (layer=middle) 포트 9205
│
├── Moth Broker (외부)               wss://cobot.center:8287
│   └── Pub/Sub 텔레메트리 스트림
│
└── Client
    └── React SPA    — 3D 대시보드 · 운영 관제 · 미션/장비 상세
```

### 포트 정리

| 포트   | 서비스                    |
| ------ | ------------------------- |
| `8280` | Registry Server           |
| `9110` | DeviceBridge              |
| `9111` | MissionPlanner            |
| `9112` | PolicyManager             |
| `9113` | SystemSentinel            |
| `9114` | InsightReporter           |
| `9116` | RequestHandler            |
| `9201` | USV Lower Agent           |
| `9202` | AUV Lower Agent           |
| `9203` | ROV Lower Agent           |
| `9204` | Relay USV Middle Agent    |
| `9205` | Control Ship Middle Agent |

---

## Device Agent 옵션

같은 타입을 여러 개 띄우려면 `--port` 사용:

```bash
python device_agent.py --type usv --layer lower --port 9121
python device_agent.py --type usv --layer lower --port 9122
```

### 옵션 목록

| 옵션       | 필수 | 설명                                  |
|------------|------|---------------------------------------|
| `--type`   | ✅   | `usv` / `auv` / `rov` / `ship`         |
| `--layer`  | ✅   | `lower` / `middle`                    |
| `--port`   |      | 포트 오버라이드 (기본값: config.json) |
| `--host`   |      | 호스트 오버라이드                     |
| `--config` |      | 커스텀 config.json 경로               |

---

## 설정 파일 구조

각 Device Agent는 `device/configs/{type}-{layer}.json`에서 설정을 읽습니다.

예시 (`device/configs/auv-lower.json`):
```json
{
  "device": {
    "id": "aauv-01",
    "type": "AUV",
    "name": "Autonomous Underwater Vehicle 01",
    "actions": ["MOVE_TO", "HIGH_RES_SCAN", "SAMPLE_COLLECTION"]
  },
  "capabilities": ["ACOUSTIC", "RF", "INTERNET"],
  "system_agent": {
    "endpoint": {
      "host": "127.0.0.1",
      "port": 9110,
      "protocol": "HTTP",
      "path": "/api/agent"
    },
    "heartbeat_interval_sec": 1,
    "heartbeat_timeout_sec": 10
  },
  "physical_constraints": {
    "battery": {
      "critical_threshold_percent": 10,
      "warning_threshold_percent": 30
    },
    "depth": {
      "max_depth_m": 1000
    }
  }
}
```

**설정 항목:**
- `device.id`: 고유 Device ID (System Registry에 등록)
- `device.type`: 장비 종류 (USV, AUV, ROV, SHIP)
- `device.actions`: 이 Device가 수행 가능한 작업
- `capabilities`: 통신 매체 (ACOUSTIC, RF, INTERNET 등)
- `system_agent.endpoint`: DeviceBridge 주소/포트

---

## 상태 확인

```bash
# 등록 디바이스
curl http://127.0.0.1:8280/devices | jq '.[] | {id, name, layer, device_type, connected}'

# Event / Approval / Mission 원장
curl http://127.0.0.1:8280/events    | jq .
curl http://127.0.0.1:8280/approvals | jq .
curl http://127.0.0.1:8280/mission-proposals | jq .
curl http://127.0.0.1:8280/missions  | jq .

# System Agent 내부 상태
curl http://127.0.0.1:9116/state | jq .
curl http://127.0.0.1:9110/state | jq .  # DeviceBridge

# 디바이스 에이전트 상태
curl http://127.0.0.1:9202/state | jq '.last_telemetry'  # AUV
curl http://127.0.0.1:9203/state | jq '.last_telemetry'  # ROV
```


## 운영 흐름 스모크 테스트

서비스 전체 기동 후:

```bash
curl -X POST http://127.0.0.1:9116/mission-proposals/generate \
  -H 'Content-Type: application/json' \
  -d '{"goal":"항만 주변 기뢰 탐지 및 제거"}'
```

이후 `http://127.0.0.1:5173/ops`에서 다음 흐름이 보여야 합니다.

- SYS_INTENT_CLASSIFIED Event 기록
- Mission Proposal 생성
- Approval 승인/거절
- 승인된 Mission의 Step / Task / Timeline 진행

---

## 로그 위치

```
.logs/
├── Registry.log
├── System-Agent.log
├── Ship-Middle.log
├── USV-Lower.log
├── AUV-Lower.log
└── ROV-Lower.log
```

---

## 주요 설정 파일

| 파일                               | 역할                    |
| ---------------------------------- | ----------------------- |
| `device/configs/ship-middle.json`  | Control Ship 설정       |
| `device/configs/usv-lower.json`    | USV 설정                |
| `device/configs/auv-lower.json`    | AUV 설정 (LLM 포함)     |
| `device/configs/rov-lower.json`    | ROV 설정                |
| `server/system-agent/config.json`  | System Agent · LLM 설정 |

모든 에이전트의 `registry.url` 기본값: `http://127.0.0.1:8280`

---

## 문제 해결

**포트 충돌**

```bash
lsof -i :8280
lsof -i :9116
kill -9 <PID>
```

**디바이스가 Registry에 등록 안 될 때**

```bash
curl http://127.0.0.1:8280/devices | jq .
# device/configs/{type}-{layer}.json > registry.url 확인
```

**Moth 연결 실패**

- 외부 서버 `wss://cobot.center:8287` 접근 가능 여부 확인
- Moth 비활성화 데모 실행: `COWATER_LLM_ENABLED=false ./cowaterctl.sh start`

**3D 대시보드에 디바이스가 안 보일 때**

1. 브라우저 콘솔(F12) 열기
2. Registry 응답 확인: `curl http://127.0.0.1:8280/devices`
3. Moth WebSocket 구독 메시지 콘솔 확인

**미션이 `waiting_for_survey_device`로 막힐 때**

이전 실행의 stale 응답이 AUV를 점유한 경우. 전체 재시작으로 해결:

```bash
./cowaterctl.sh restart
```
