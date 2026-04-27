# PoC 01: Device Streams - Moth 서버 시뮬레이터

Moth 서버로 다중 디바이스 실시간 데이터를 스트리밍하는 시뮬레이터입니다 (RSSP/WebSocket).

## 목표

해양 디바이스가 Moth 서버에 여러 독립적인 실시간 스트림을 발행할 수 있으며, parent-child 디바이스 구조와 정적/동적 데이터 전송 패턴을 혼합할 수 있는지 검증합니다.

## 범위

포함:

- **6가지 디바이스 타입**: Control Center, Control Ship, Ocean Power Tower (정적); USV, AUV, ROV (동적)
- **실시간 스트리밍**: Moth 서버로 WebSocket 연결 (wss://cobot.center:8287)
- **센서 시뮬레이션**: GPS, IMU, 소나, 압력, 온도, 카메라, 조명, 자력계
- **설정 기반**: `config.json`으로 쉬운 커스터마이징
- **라이브 대시보드**: HTML 뷰어로 스트림 모니터링 (디바이스당 최신 10개 데이터)
- **스마트 전송**: 정적 디바이스는 변경 시에만 전송, 동적 디바이스는 지속 스트리밍

제외:

- 프로토콜 파싱 (NMEA, ROSNav 등) - moth-bridge가 처리
- Redis/NATS 전송 - Moth WebSocket 직접 사용
- Core 저장 - 데이터는 moth-bridge → core로 흐름
- Detection/Response Agent - 데이터 생성에 집중

## 아키텍처

### 디바이스 타입

**정적 디바이스** (위치 전용, 변경 시 전송):
- Control Center: 고정 해안 스테이션
- Control Ship: 이동 지휘 함선 (시간 경과에 따라 위치 변경)
- Ocean Power Tower: 고정 해양 시설

**동적 디바이스** (실시간 센서, 지속 스트리밍):
- USV (Unmanned Surface Vehicle): 2초 간격 업데이트 + 3개 센서
- AUV (Autonomous Underwater Vehicle): 3초 간격 업데이트 + 4개 센서
- ROV (Remotely Operated Vehicle): 1초 간격 업데이트 + 5개 센서

### 데이터 흐름

```
Moth 서버 (wss://cobot.center:8287)
    ▲
    │ JSON WebSocket 프레임
    │
MothSimulator (Python)
├─ 정적 루프: Control Center, Control Ship, Ocean Power Tower
└─ 동적 루프: USV, AUV, ROV (센서 포함)
    ▲
    └─ HTML 대시보드 (index.html)
       • 디바이스 카드 그리드
       • 클릭해서 선택
       • 디바이스당 라이브 10개 포인트 스트림
```

## 설정

`config.json` 편집:

```json
{
  "static_devices": [
    {
      "device_id": "control-center-01",
      "device_type": "control_center",
      "name": "Control Center 01",
      "position": { "latitude": 37.265, "longitude": 127.008, "altitude": 10.0 },
      "transmission_interval": 3600
    }
  ],
  "dynamic_devices": [
    {
      "device_id": "usv-01",
      "device_type": "usv",
      "transmission_interval": 2,
      "start_position": { "latitude": 37.268, "longitude": 127.012, "altitude": 0.5 },
      "movement": {
        "speed_range": [0.5, 3.0],
        "heading_change_max": 15,
        "depth_range": [0.5, 50.0]
      },
      "sensors": [
        { "sensor_id": "usv-gps-01", "sensor_type": "gps" },
        { "sensor_id": "usv-imu-01", "sensor_type": "imu" },
        { "sensor_id": "usv-sonar-01", "sensor_type": "sonar" }
      ]
    }
  ],
  "moth_server": {
    "url": "wss://cobot.center:8287",
    "channel": "instant"
  },
  "registration_server": {
    "enabled": true,
    "url": "http://localhost:8003",
    "secret_key": "server-secret",
    "fallback_on_failure": false
  }
}
```

## 실행

### 시뮬레이터

```bash
cd pocs/01-device-streams

# 의존성 설치
pip install websockets

# 시뮬레이터 실행
python3 src/moth_simulator.py
```

출력:
```
2026-04-23 14:30:22 - MothSimulator - INFO - Connecting to Moth server: wss://cobot.center:8287
2026-04-23 14:30:25 - MothSimulator - INFO - ✓ Connected to Moth server
2026-04-23 14:30:25 - MothSimulator - INFO - 🚀 Starting simulation...
2026-04-23 14:30:26 - MothSimulator - INFO - 📍 Sent static device: Control Center 01
2026-04-23 14:30:26 - MothSimulator - DEBUG - 📡 Sent dynamic device: USV 01
```

### 대시보드

```bash
# 옵션 1: 직접 파일 열기
open index.html

# 옵션 2: 로컬 서버 (권장)
python3 -m http.server 8000
# http://localhost:8000 방문
```

**기능**:
- Moth 연결 상태 실시간 표시
- 6개 디바이스 카드 (클릭해서 선택)
- 디바이스당 라이브 10개 데이터 스트림
- 자동 스크롤, 반응형 디자인

## 성공 기준

- `registration_server.enabled = true`일 때 6개 모든 디바이스가 등록 성공
- 정적 디바이스는 위치 변경 또는 타임아웃 시에만 전송
- 동적 디바이스는 현실적인 센서 데이터로 지속 스트리밍
- HTML 대시보드가 실시간으로 데이터 수신 및 표시 (디바이스당 최신 10개)
- 설정 기반: 디바이스 및 센서 추가/수정이 용이

등록 실패 시 `fallback_on_failure = false`이면, 시뮬레이터는 해당 디바이스 전송을 중단하고 공유 트랙으로 몰래 fallback 하지 않습니다.

## 페이로드 예제

### 정적 디바이스 (Control Ship)

```json
{
  "device_id": "control-ship-01",
  "device_type": "control_ship",
  "name": "Control Ship 01",
  "data_type": "position",
  "timestamp": "2026-04-23T14:30:26.123456+00:00",
  "position": {
    "latitude": 37.2701,
    "longitude": 127.0152,
    "altitude": 5.0
  }
}
```

### 동적 디바이스 (센서가 있는 ROV)

```json
{
  "device_id": "rov-01",
  "device_type": "rov",
  "name": "ROV 01",
  "timestamp": "2026-04-23T14:30:28.456789+00:00",
  "position": {
    "latitude": 37.2671,
    "longitude": 127.0112,
    "altitude": -48.3
  },
  "motion": {
    "heading": 254.67,
    "speed": 0.82
  },
  "sensors": {
    "rov-camera-01": {
      "type": "hd_camera",
      "resolution": "1080p",
      "fps": 30
    },
    "rov-pressure-01": {
      "type": "pressure",
      "depth_m": 48.3
    }
  }
}
```

## CoWater와의 통합

1. Moth 서버가 `instant` 채널 데이터 수신
2. moth-bridge가 `PlatformReport` schema로 정규화
3. Redis pub/sub이 에이전트로 브로드캐스트
4. core가 TimescaleDB에 저장, 프론트엔드로 WebSocket 전송
5. 프론트엔드가 위치, 경보, 항적 시각화
