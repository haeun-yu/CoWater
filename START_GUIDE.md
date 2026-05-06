# CoWater 3D Dashboard - 시작 가이드 (Start Guide)

## 📋 개요 (Overview)

이 가이드는 CoWater 3D Dashboard의 모든 서비스를 시작하고 관리하는 방법을 설명합니다.
This guide explains how to start and manage all CoWater 3D Dashboard services.

---

## 🚀 빠른 시작 (Quick Start)

### 1단계: 스크립트 권한 설정

```bash
cd /Users/teamgrit/Documents/CoWater
chmod +x cowaterctl.sh START_SERVICES.sh STOP_SERVICES.sh STATUS_SERVICES.sh
```

### 2단계: 모든 서비스 시작

```bash
./cowaterctl.sh start
```

### 3단계: 브라우저에서 열기

- **3D 대시보드**: `file:///Users/teamgrit/Documents/CoWater/client/index.html`
- **경보 관리**: `file:///Users/teamgrit/Documents/CoWater/client/alerts.html`

### 4단계: 중지

```bash
./cowaterctl.sh stop
```

### 5단계: 상태 확인

```bash
./cowaterctl.sh status
```

---

## 📁 서비스 구조 (Service Architecture)

```
CoWater System
├── Device Registration Server (Registry)
│   └── 포트: 8280
│   └── 역할: 디바이스 등록 및 메타데이터 관리
│
├── Device Agents (4개)
│   ├── Ship (device_id=1, layer=middle)
│   ├── USV (device_id=2, layer=lower)
│   ├── AUV (device_id=3, layer=lower)
│   └── ROV (device_id=4, layer=lower)
│
├── Moth Broker (외부)
│   └── wss://cobot.center:8287
│   └── 역할: Pub/Sub 텔레메트리 스트림
│
└── Client (3D Dashboard)
    └── file:///.../.../client/index.html
    └── 역할: 실시간 3D 시각화
```

---

## ⚙️ 각 서비스 역할 (Service Roles)

### Device Registration Server

- **파일**: `server/registration/device_registration_server.py`
- **역할**:
  - 디바이스 등록 및 추적
  - 경고 모니터링
  - Registry API 제공 (`/devices`, `/alerts`, `/responses`)
  - Healthcheck 수신 및 기록

### Device Agents

각 에이전트는 다음을 수행합니다:

- 센서 데이터 시뮬레이션
- Registry에 등록
- Moth Broker로 텔레메트리 발행:
  - **Healthcheck**: 위치, 배터리, 상태 (1초마다)
  - **Track Streams**: 개별 트랙별 데이터
    - `ODOMETRY`: 위치 + 방향 + 속도
    - `GPS`: GPS 좌표
    - `DEPTH`: 수심 (AUV/ROV만)
    - `BATTERY`: 배터리 상태
    - `TOPIC`: 센서 데이터

### Client (3D Dashboard)

- **파일**: `client/index.html`
- **역할**:
  - Registry에서 디바이스 목록 조회
  - 각 디바이스의 track streams 구독
  - Three.js로 3D 시각화
  - 실시간 객체 위치/방향/깊이 업데이트

---

## 🔧 수동 시작 (Manual Startup)

### 터미널 1: Registry Server

```bash
cd /Users/teamgrit/Documents/CoWater/server/registration
/Users/teamgrit/Documents/CoWater/.venv/bin/python device_registration_server.py
```

### 터미널 2: Ship Agent

```bash
cd /Users/teamgrit/Documents/CoWater/device
/Users/teamgrit/Documents/CoWater/.venv/bin/python device_agent.py --type ship --layer middle
```

### 터미널 3: USV Agent

```bash
cd /Users/teamgrit/Documents/CoWater/device
/Users/teamgrit/Documents/CoWater/.venv/bin/python device_agent.py --type usv --layer lower
```

### 터미널 4: AUV Agent

```bash
cd /Users/teamgrit/Documents/CoWater/device
/Users/teamgrit/Documents/CoWater/.venv/bin/python device_agent.py --type auv --layer lower
```

### 터미널 5: ROV Agent

```bash
cd /Users/teamgrit/Documents/CoWater/device
/Users/teamgrit/Documents/CoWater/.venv/bin/python device_agent.py --type rov --layer lower
```

---

## 📊 상태 확인 (Status Check)

### Registry 상태 확인

```bash
curl http://127.0.0.1:8280/health
```

### 등록된 디바이스 확인

```bash
curl http://127.0.0.1:8280/devices | python -m json.tool
```

### 경고 확인

```bash
curl http://127.0.0.1:8280/alerts | python -m json.tool
```

### 프로세스 확인

```bash
ps aux | grep -E "device_agent|device_registration_server" | grep -v grep
```

---

## 🔍 로그 위치 (Log Files)

스크립트로 실행 시 로그는 다음 위치에 저장됩니다:

```
.logs/
├── Registry.log
├── Ship-Middle.log
├── USV-Lower.log
├── AUV-Lower.log
└── ROV-Lower.log
```

### 로그 실시간 보기

```bash
tail -f .logs/Registry.log
tail -f .logs/Ship-Middle.log
# 등등...
```

---

## 🐛 문제 해결 (Troubleshooting)

### Registry 연결 실패

```bash
# 포트 사용 여부 확인
lsof -i :8280

# 포트 해제 (필요한 경우)
kill -9 <PID>

# Registry 재시작
```

### Moth 연결 실패

- Moth Broker 상태 확인: `wss://cobot.center:8287`
- 네트워크 연결 확인
- 방화벽 설정 확인

### 디바이스가 등록되지 않음

1. Registry 서버가 실행 중인지 확인
2. Device Agent 로그에서 오류 메시지 확인
3. Registry 포트(8280)가 접근 가능한지 확인

### 3D 대시보드에 디바이스가 표시되지 않음

1. 브라우저 콘솔 열기 (F12)
2. Moth WebSocket 연결 확인
3. Network 탭에서 subscribeDeviceTrackStreams 구독 확인
4. 데이터 도착 확인: console에 Track 구독 메시지

---

## 📱 클라이언트 인터페이스 (Client Interfaces)

### 1. 3D 대시보드 (index.html)

**주요 기능:**

- 실시간 3D 객체 시각화
- 위치, 방향, 깊이 표시
- 배터리 상태 표시
- 카메라 제어

**상단 정보:**

- 현재 선택된 객체
- 위치 (LAT, LON)
- 방향 (Heading)
- 깊이 (Depth)
- 배터리 (Battery)

**카메라 제어:**

- 마우스 드래그: 회전
- 마우스 휠: 줌
- 우클릭 드래그: 팬

### 2. 경보 관리 (alerts.html)

**주요 기능:**

- 활성 경보 목록
- 경보 응답 버튼
- 응답 상태 추적

---

## 🔄 데이터 흐름 (Data Flow)

```
Simulator (각 Agent)
    ↓
MothPublisher (Track별 발행)
    ↓
Moth Broker (pub/sub)
    ↓
Client (WebSocket 구독)
    ↓
subscribeDeviceTrackStreams()
    ↓
Track Type 파싱
    ├── ODOMETRY → position + heading
    ├── GPS → position
    ├── DEPTH → depth
    └── BATTERY → battery_percent
    ↓
3D Scene 업데이트
    ├── mesh.position 설정
    ├── mesh.rotation 설정 (heading)
    └── object.depth 저장
    ↓
Render Loop (Three.js)
    ↓
화면 표시
```

---

## 📝 주요 파일 (Key Files)

### 시작/중지 스크립트

- `cowaterctl.sh` - 통합 관리 (`start|stop|status|restart|logs`)
- `START_SERVICES.sh` - 시작 래퍼 (`cowaterctl.sh start`)
- `STOP_SERVICES.sh` - 중지 래퍼 (`cowaterctl.sh stop`)
- `STATUS_SERVICES.sh` - 상태 래퍼 (`cowaterctl.sh status`)

### Server

- `server/registration/device_registration_server.py` - Registry 서버
- `server/registration/src/registry/device_registry.py` - 디바이스 레지스트리

### Device

- `device/device_agent.py` - 디바이스 에이전트 메인
- `device/transport/moth_publisher.py` - Moth 발행기 (Track 기반)
- `device/simulator/*.py` - 센서 시뮬레이터

### Client

- `client/index.html` - 3D 대시보드 (메인)
- `client/alerts.html` - 경보 관리

---

## 🔐 환경 설정 (Configuration)

### Python 버전

```bash
python --version
# Python 3.9 이상 필요
```

### 필수 패키지

```bash
pip list | grep -E "websockets|fastapi|uvicorn|three"
```

### 주요 설정 파일

- `device/configs/ship-middle.json` - Ship 설정
- `device/configs/usv-lower.json` - USV 설정
- `device/configs/auv-lower.json` - AUV 설정
- `device/configs/rov-lower.json` - ROV 설정

---

## 🎯 성능 최적화 (Performance Tips)

### 3D 렌더링 최적화

현재 설정:

- TILE_RADIUS: 1 (초기 로드 ~2-3초)
- 다이나믹 타일 로딩 활성

### 데이터 전송 최적화

- Track 기반 Pub/Sub (개별 채널)
- 선택적 구독
- 배치 업데이트

---

## 📞 지원 (Support)

문제 발생 시:

1. 로그 파일 확인
2. 프로세스 상태 확인
3. 포트 사용 여부 확인
4. 네트워크 연결 확인

---

## 📅 최종 업데이트

- **2026-05-06**
- **Track 기반 데이터 파이프라인**
- **통합 시작 스크립트**

---
