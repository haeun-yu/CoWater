# CoWater 실행 가이드

## ⚡ 초급 사용자: 한 줄로 실행 & 테스트

```bash
cd /Users/teamgrit/Documents/CoWater
./run_full_test.sh
```

**자동으로 수행되는 작업:**
1. ✅ 모든 서비스 자동 시작 (이미 실행 중이면 스킵)
2. ✅ 서비스 상태 확인 (Registry, System Agent, Device Agents)
3. ✅ API 연결성 테스트
4. ✅ 통합 테스트 실행 (mine_removal_scenario)
5. ✅ 테스트 결과 분석 & 리포트 출력
6. ✅ Client UI 접속 링크 제공

---

## 🎯 표준 실행

서비스 시작:

```bash
cd /Users/teamgrit/Documents/CoWater
./cowaterctl.sh start
```

중지 / 재시작 / 상태:

```bash
./cowaterctl.sh stop
./cowaterctl.sh restart
./cowaterctl.sh status
```

로그 실시간 보기:

```bash
./cowaterctl.sh logs Registry
./cowaterctl.sh logs System-Agent
./cowaterctl.sh logs AUV-Lower
# 가능한 이름: Registry | System-Agent | Ship-Middle | USV-Lower | AUV-Lower | ROV-Lower
```

브라우저에서 열기:

- **Client SPA**: `http://127.0.0.1:5173/`
- **운영 관제**: `http://127.0.0.1:5173/ops`
- **미션 상세**: `http://127.0.0.1:5173/mission/<mission_id>`

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

## 수동 실행 순서

venv 활성화:

```bash
cd /Users/teamgrit/Documents/CoWater
source .venv/bin/activate
```

### 1. Registry Server

```bash
cd server/registration
python device_registration_server.py
```

```bash
curl http://127.0.0.1:8280/health
```

### 2. System Agent Layer

```bash
cd server/system-agent
python run_system_agents.py
```

```bash
curl http://127.0.0.1:9116/health
curl http://127.0.0.1:9110/health
```

### 3. Middle Agent

```bash
cd device
python device_agent.py --type ship --layer middle
```

Device Agent 시작 시 자동으로 다음이 수행됩니다:

```
1️⃣ 설정 파일 로드      → device/configs/{type}-{layer}.json 읽음
                         (Device ID, capabilities, System Agent endpoint)
                         ↓
2️⃣ IdentityStore 확인  → .data/identity/{device_id}.json 존재?
                         ↓
         ┌─ 있음 → 캐시된 agent_id/endpoint 사용
         │
         └─ 없음 → System Agent Registry에 등록
                   (device_id, agent_id, stream URLs 획득)
                   → 로컬에 저장
                   ↓
3️⃣ Heartbeat 시작      → 1초 주기로 System Agent로 상태 보고
```

**주요 파일:**
- 설정: `device/configs/{type}-{layer}.json`
- 로컬 캐시: `.data/identity/{device_id}.json`
- 로그: `.logs/{Type}-{Layer}.log`

### 4. Lower Agents

```bash
cd device
python device_agent.py --type usv --layer lower
python device_agent.py --type auv --layer lower
python device_agent.py --type rov --layer lower
```

같은 타입을 여러 개 띄울 때는 `--port`로 구분:

```bash
python device_agent.py --type usv --layer lower --port 9121
python device_agent.py --type usv --layer lower --port 9122
```

각 Device Agent는 자신의 설정파일에서 Device ID를 읽어 독립적으로 등록됩니다.

### Device Agent 설정 파일 예시

`device/configs/auv-lower.json`:
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

### device_agent.py 옵션

| 옵션       | 필수 | 설명                                           |
| ---------- | ---- | ---------------------------------------------- |
| `--type`   | ✅   | 디바이스 타입: `usv` / `auv` / `rov` / `ship`  |
| `--layer`  | ✅   | 에이전트 계층: `lower` / `middle`              |
| `--port`   |      | 포트 오버라이드 (기본값: config.json)          |
| `--host`   |      | 호스트 오버라이드                              |
| `--config` |      | 커스텀 config.json 경로                        |

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
