# POC 04 - USV Middle Agent (무인 수상 플랫폼)

## 개요

USV(Unmanned Surface Vehicle) Middle Agent는 수중 음향/저대역 하위 디바이스 데이터를 중계하고, 현장 하위 에이전트를 조율할 수 있는 중간 계층 에이전트입니다.

## 실행 방법

### 가상 환경 활성화 후 실행 (권장)
```bash
source /path/to/.venv/bin/activate
cd /Users/teamgrit/Documents/CoWater/pocs/04-usv-middle-agent
python device_agent.py

# Python3로 직접 실행
python3 device_agent.py

# Config 파일 지정
python device_agent.py --config config.yaml
```

## 포트

- **기본 포트**: 9014
- **설정 파일**: `config.json`

## API 엔드포인트

```bash
# 상태 확인
curl http://localhost:9014/health

# 에이전트 상태
curl http://localhost:9014/state | jq .

# 매니페스트
curl http://localhost:9014/manifest | jq .

# 자식 디바이스 목록
curl http://localhost:9014/children | jq .
```

## 주요 기능

### 중간 계층 역할
- **데이터 중계**: 하위 수중 디바이스(AUV 등)의 음향 데이터 중계
- **통신 릴레이**: 수상(네트워크 접근)과 수중(음향) 간 통신 중개
- **하위 에이전트 관리**: 자식 디바이스들의 상태 모니터링

### 센서 및 도구
- **GPS**: 위치 결정
- **Acoustic Link**: 음향 통신
- **Relay Antenna**: 신호 중계
- **Battery**: 배터리 모니터링
- **Navigation System**: 항법 시스템

### 스킬
- `relay_acoustic_signal`: 음향 신호 중계
- `maintain_position`: 위치 유지
- `provide_network_access`: 네트워크 접근 제공

## 자식 디바이스 관리

### 자식 등록
```bash
curl -X POST http://localhost:9014/children/register \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "auv-001",
    "device_id": 5,
    "name": "AUV-01",
    "endpoint": "http://127.0.0.1:9010"
  }'
```

### 자식 하트비트 수신
```bash
curl -X POST http://localhost:9014/children/heartbeat \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "auv-001",
    "timestamp": "2026-04-29T10:30:00Z",
    "battery": 80,
    "depth": -30
  }'
```

## Moth 통합

- **하트비트**: 10초 주기 상태 발행
- **자식 하트비트 릴레이**: 수중 디바이스 하트비트를 수상에서 Moth로 중계
- **텔레메트리 중계**: 음향 신호로 받은 센서 데이터를 Moth로 발행

## 상태 확인

```bash
# 서버 정상 작동
curl http://localhost:9014/health | jq .

# 자식 디바이스 목록
curl http://localhost:9014/children | jq '.children[] | {device_id, name, last_heartbeat_at}'

# 신호 강도 확인
curl http://localhost:9014/state | jq '.last_telemetry.signal_strength'

# 배터리 레벨
curl http://localhost:9014/state | jq '.last_telemetry.battery'
```

## 문제 해결

### "Address already in use" 에러
```bash
lsof -i :9014
kill -9 <PID>
```

### 자식 디바이스 연결 실패
```bash
# 1. 자식 디바이스가 실행 중인지 확인
curl http://localhost:9010/health  # AUV

# 2. Registry에서 parent_id 확인
curl http://localhost:8280/devices/5 | jq '.parent_id'

# 3. 음향 신호 상태 확인
curl http://localhost:9014/state | jq '.last_telemetry.signal_strength'
```

### Moth 중계 실패
```bash
# 1. Moth 연결 상태 확인
tail -f logs/device.log | grep Moth

# 2. 수신된 메시지 확인
curl http://localhost:9014/state | jq '.inbox'

# 3. 발송된 중계 메시지 확인
tail -f logs/device.log | grep relay
```


python3 pocs/04-usv-middle-agent/device_agent.py --port 9141
```

