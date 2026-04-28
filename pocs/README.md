# CoWater Multi-Layer Agent System (POC 00-06)

**구현 완료**: 2026-04-28  
**상태**: Phase 1-4 완료 ✅ | Phase 5-7 미정 🔄

---

## 🎯 요구사항 구현 현황

### ✅ Phase 1: Configuration & Environment (완료)

| 요구사항              | 상태 | 설명                                    |
| --------------------- | ---- | --------------------------------------- |
| .env 파일 작성        | ✅   | heartbeat, rebinding, Moth 설정         |
| 환경변수 override     | ✅   | 12-factor app 패턴                      |
| Device 모델 확장      | ✅   | device_type, layer, location, parent_id |
| Agent Config 업데이트 | ✅   | LLM, Moth, simulation 설정 포함         |

### ✅ Phase 2: Heartbeat & Moth Integration (완료)

| 요구사항                  | 상태 | 설명                                     |
| ------------------------- | ---- | ---------------------------------------- |
| HeartbeatMonitor (POC 00) | ✅   | 타임아웃 감지, 자동 재할당               |
| 10초 주기 heartbeat       | ✅   | 모든 Device가 Moth로 발행                |
| 30초 timeout              | ✅   | offline 표시 및 자동 재할당              |
| 500m 거리 임계값          | ✅   | Dynamic re-binding 판정값                |
| MothPublisher (POC 01-05) | ✅   | WebSocket 연결, heartbeat/telemetry 발행 |
| 자동 재연결               | ✅   | 연결 끊김 감지 후 자동 복구              |

### ✅ Phase 3: Enhanced Tools & Skills (완료)

| 요구사항                  | 상태 | 설명                                              |
| ------------------------- | ---- | ------------------------------------------------- |
| **POC 01 (USV)**          | ✅   | GPS, Battery, IMU, Motor, Route, Obstacle, Safety |
| **POC 02 (AUV)**          | ✅   | Depth, Acoustic Modem, Sonar                      |
| **POC 03 (ROV)**          | ✅   | Camera, Manipulator Arm, Tether Monitor           |
| **POC 04 (USV Mid)**      | ✅   | Child Registry, Acoustic Relay, A2A Router        |
| **POC 05 (Control Ship)** | ✅   | Wired Link Monitor, ROV Tether Controller         |
| 동적 Tools 로드           | ✅   | importlib로 자동 로드                             |
| Simulation Loop 강화      | ✅   | Tools 상태 업데이트 + Decision 적용               |

### ✅ Phase 4: LLM Integration (완료)

| 요구사항           | 상태 | 설명                              |
| ------------------ | ---- | --------------------------------- |
| Rule 기반 decision | ✅   | 배터리 경고, 속도 제한, 자식 조율 |
| LLM 분석 (비동기)  | ✅   | Ollama 지원, 논블로킹             |
| Fallback 처리      | ✅   | LLM 실패 시 rule 기반만 유지      |
| Config 기반 on/off | ✅   | llm.enabled로 제어                |

### 🔄 Phase 5: Integration Testing (미정)

| 요구사항                             | 상태 | 설명   |
| ------------------------------------ | ---- | ------ |
| 단일 Agent 등록 + heartbeat test     | ❌   | 미작성 |
| 다중 Agent + dynamic re-binding test | ❌   | 미작성 |
| ROV 유선 등록 테스트                 | ❌   | 미작성 |
| Moth 텔레메트리 검증                 | ❌   | 미작성 |
| LLM 응답 검증                        | ❌   | 미작성 |

### 🔄 Phase 6: API Server (미정)

| 요구사항                   | 상태 | 설명   |
| -------------------------- | ---- | ------ |
| Device Registry API (CRUD) | ❌   | 미작성 |
| MCP Server 구현            | ❌   | 미작성 |
| WebSocket 대시보드         | ❌   | 미작성 |

### 🔄 Phase 7: Production Deployment (미정)

| 요구사항      | 상태 | 설명   |
| ------------- | ---- | ------ |
| Docker 이미지 | ❌   | 미작성 |
| K8s manifests | ❌   | 미작성 |
| 분산 배포     | ❌   | 미작성 |

---

## 🚀 빠른 시작

### 1️⃣ Server 시작

```bash
cd pocs/00-device-registration-server
python3 device_registration_server.py --host 127.0.0.1 --port 9100
```

### 2️⃣ Lower Agent 시작

```bash
# Terminal 1: USV
python3 pocs/01-usv-lower-agent/device_agent.py --port 9111

# Terminal 2: AUV
python3 pocs/02-auv-lower-agent/device_agent.py --port 9121

# Terminal 3: ROV
python3 pocs/03-rov-lower-agent/device_agent.py --port 9131
```

### 3️⃣ Middle Agent 시작 (선택사항)

```bash
# Terminal 4: Relay USV
python3 pocs/04-usv-middle-agent/device_agent.py --port 9141

# Terminal 5: Control Ship
python3 pocs/05-control-ship-middle-agent/device_agent.py --port 9151
```

---

## 📊 구현 내용

### 🔑 핵심 기능 6가지

#### 1. 위치 기반 동적 계층 연결

- **등록 시**: Device가 위치 포함 → Server가 Haversine 거리로 가장 가까운 Middle Agent 선택
- **실시간**: Moth로 위치 업데이트 → Server가 거리 재계산 → 500m 이상 차이면 재연결
- **유선 케이스**: ROV는 Control Ship이 대신 등록 (connectivity: "wired" + parent_id 명시)

#### 2. Heartbeat & Health Management

```
Device (10초마다)        Server
├─ heartbeat 발행  ──→  ├─ last_seen_at 기록
│                       ├─ 30초 timeout 체크
│                       └─ offline → 자식 재할당
```

#### 3. 실시간 Telemetry Streaming

```
Device Simulator
    ↓
_update_tools_from_telemetry()  (GPS, Battery, IMU 동기화)
    ↓
Decision Engine (Rule + LLM)
    ↓
_apply_decision_to_tools()  (권장사항 적용)
    ↓
Moth WebSocket 발행
```

#### 4. Device-Specific Tools

| POC         | 주요 Tools                                 |
| ----------- | ------------------------------------------ |
| 01 (USV)    | GPS, Battery, IMU, Motor, Route Planner    |
| 02 (AUV)    | Depth Sensor, Acoustic Modem, Sonar        |
| 03 (ROV)    | Camera, Manipulator Arm, Tether Monitor    |
| 04/05 (Mid) | Child Registry, Acoustic Relay, A2A Router |

#### 5. LLM Integration

```
Decision Engine
├─ Rule (동기)
│  ├─ Battery < 30% → return_to_base
│  ├─ Speed > max → slow_down
│  └─ Layer=middle → coordinate_children
│
└─ LLM (비동기, 논블로킹)
   └─ Ollama로 추가 분석 (LLM 실패해도 rule 계속 작동)
```

#### 6. Configuration Management

```
config.json                              .env
├─ agent (device_type, layer)    +  COWATER_LLM_ENABLED=true
├─ registry (heartbeat_interval)  +  COWATER_HEARTBEAT_INTERVAL=10
├─ moth (server_url, enabled)    +  COWATER_REBINDING_THRESHOLD=500
├─ llm (provider, endpoint, model)
└─ simulation (interval_seconds)
```

---

## 📁 프로젝트 구조

```
pocs/
├─ 00-device-registration-server/    ← Server (Heartbeat 모니터링)
├─ 01-usv-lower-agent/               ← Lower Agent (USV)
├─ 02-auv-lower-agent/               ← Lower Agent (AUV)
├─ 03-rov-lower-agent/               ← Lower Agent (ROV)
├─ 04-usv-middle-agent/              ← Middle Agent (Relay)
├─ 05-control-ship-middle-agent/     ← Middle Agent (Control)
├─ 06-system-supervisor-agent/       ← System Agent (미구현)
└─ README.md                          ← 이 문서
```

각 POC 구조:

```
POC/
├─ agent/
│  ├─ runtime.py           ← 메인 실행 엔진
│  ├─ decision.py          ← Rule + LLM
│  ├─ state.py             ← Agent 상태
│  └─ manifest.py          ← Skills 등록
├─ tools/                  ← Device-specific (동적 로드)
├─ transport/
│  ├─ registry_client.py   ← Server 등록
│  └─ moth_publisher.py    ← Moth WebSocket
├─ simulator/              ← 센서 시뮬레이션
├─ config.json             ← Agent 설정
└─ device_agent.py         ← Entry point
```

---

## 🔑 설정 예시

### POC 00 (.env)

```ini
HEARTBEAT_INTERVAL_SECONDS=10
HEARTBEAT_TIMEOUT_SECONDS=30
REBINDING_DISTANCE_DELTA_THRESHOLD_METERS=500
MOTH_SERVER_URL=wss://cobot.center:8287
```

### POC 01-05 (config.json)

```json
{
  "registry": {
    "url": "http://127.0.0.1:9100",
    "heartbeat_interval_seconds": 1
  },
  "moth": {
    "enabled": true,
    "server_url": "wss://cobot.center:8287"
  },
  "llm": {
    "provider": "ollama",
    "endpoint": "http://localhost:11434",
    "enabled": true,
    "timeout_seconds": 3
  }
}
```

---

## 📚 주요 파일 설명

### AgentRuntime (runtime.py)

- **역할**: Agent 실행 엔진
- **주요 메서드**:
  - `register()`: Device Registration Server에 등록
  - `simulation_loop()`: 메인 루프 (센서 → decision → Moth)
  - `_load_tools()`: tools/ 디렉토리 자동 로드
  - `_update_tools_from_telemetry()`: 센서 상태 동기화
  - `_apply_decision_to_tools()`: Decision 적용

### DecisionEngine (decision.py)

- **역할**: 의사결정
- **주요 메서드**:
  - `decide()`: Rule 기반 권장사항 생성 + 비동기 LLM 호출
  - `_analyze_with_llm()`: LLM 분석 (논블로킹)
  - `_build_llm_prompt()`: LLM 프롬프트 생성

### MothPublisher (moth_publisher.py)

- **역할**: Real-time telemetry streaming
- **주요 메서드**:
  - `initialize()`: Server 등록 응답에서 topics 초기화
  - `connect()`: WebSocket 연결
  - `publish_heartbeat()`: 주기적 heartbeat 발행
  - `publish_telemetry()`: 센서 데이터 발행

### HeartbeatMonitor (POC 00, heartbeat_monitor.py)

- **역할**: Server 측 건강 상태 모니터링
- **주요 메서드**:
  - `_check_all_devices()`: Timeout 감지
  - `_reassign_children()`: Offline parent의 자식 재할당

---

## 🔧 확장 포인트

### 새로운 Device Type 추가

1. `tools/` 디렉토리에 센서 클래스 작성
2. `config.json`에 device_type 지정
3. `skills/catalog.py`에 actions 등록
   → Runtime이 자동으로 tools 로드

### 새로운 LLM 백엔드 추가

1. `shared/llm_client.py`에 `LLMClient` 서브클래스 작성
2. `config.json`에 provider 지정
   → `make_llm_client()`가 자동으로 선택

### 새로운 Skill 추가

1. `skills/`에 skill 클래스 작성
2. `catalog.py`에 등록
3. `decision.py`에서 recommendations에 추가

---

## 📋 다음 단계

### 미구현 (선택사항)

**Phase 5: Integration Testing**

- 실제 Agent 간 통신 테스트
- Dynamic re-binding 검증
- Moth 텔레메트리 확인

**Phase 6: API Server**

- Device Registry CRUD API
- MCP Server (System Supervisor 용)
- WebSocket 대시보드

**Phase 7: Production**

- Docker 배포
- K8s manifests
- 모니터링/alerting

---

## 📝 주석

모든 파일에 **한국어 주석** 포함:

- 클래스/메서드: 역할 및 기능 설명
- 주요 로직: 데이터 흐름 및 상호작용
- Config: 파라미터 의미 및 기본값
- Args/Returns: 메서드 입출력 명시

코드 읽기 전에 주석을 먼저 읽으면 전체 구조를 쉽게 파악할 수 있습니다.

---

**구현 완료 현황**: Phase 1-4 (모든 핵심 기능) ✅
