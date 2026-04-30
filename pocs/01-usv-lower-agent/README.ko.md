# POC 01 - USV Lower Agent (무인 수상 로봇)

## 개요

USV(Unmanned Surface Vehicle) Lower Agent는 무인 수상 로봇의 시뮬레이션 및 제어를 담당하는 하층 에이전트입니다. 같은 스크립트를 여러 번 실행하면 각 실행이 별도의 USV로 등록됩니다.

## 실행 방법

### 가상 환경 활성화 후 실행 (권장)
```bash
source /path/to/.venv/bin/activate
cd /Users/teamgrit/Documents/CoWater/pocs/01-usv-lower-agent
python device_agent.py

# Python3로 직접 실행
python3 device_agent.py

# Instance ID 지정해서 실행 (동일한 USV로 재시작)
COWATER_INSTANCE_ID=usv-001 python device_agent.py

# 다른 포트로 실행 (여러 USV 시뮬레이션)
# config.json에서 server.port 변경 후:
python device_agent.py --config config.yaml
```

## 포트

- **기본 포트**: 9012
- **설정 파일**: `config.json`
- **다중 USV**: 포트를 변경하고 여러 번 실행 가능

## API 엔드포인트

```bash
# 상태 확인
curl http://localhost:9012/health

# 에이전트 상태
curl http://localhost:9012/state | jq .

# 매니페스트 (스킬 목록)
curl http://localhost:9012/manifest | jq .
```

## 주요 기능

### 센서 및 도구
- **GPS**: 위치 결정 및 항법
- **Battery**: 배터리 모니터링
- **IMU**: 관성 측정 장치 (가속도, 회전)
- **Motor Control**: 추진 시스템 제어
- **Obstacle Detector**: 장애물 감지
- **Safety System**: 안전 시스템

### 스킬
- `navigate_to`: 지정된 위치로 항해
- `maintain_course`: 현재 침로 유지
- `deploy_sonar`: 소나 배치
- `return_to_base`: 기지 복귀
- `emergency_stop`: 긴급 정지

## 다중 USV 실행

### 터미널별로 다른 포트로 실행

**터미널 1 - USV 01**:
```bash
cd pocs/01-usv-lower-agent
# config.json의 server.port를 9012로 설정
python device_agent.py
```

**터미널 2 - USV 02**:
```bash
cd pocs/01-usv-lower-agent
# config.json을 복사하고 server.port를 9013으로 변경
cp config.json config2.json
# config2.json 수정 (port: 9013)
python device_agent.py --config config2.json
```

**또는 Instance ID로 관리**:
```bash
COWATER_INSTANCE_ID=usv-001 python device_agent.py
COWATER_INSTANCE_ID=usv-002 python device_agent.py
```

## 시뮬레이션 설정

### config.json의 simulation 섹션
```json
{
  "simulation": {
    "sonar_enabled": true,
    "gps_accuracy": 5,
    "start_position": {
      "latitude": 37.005,
      "longitude": 129.420,
      "altitude": 0
    }
  }
}
```

### 시뮬레이션 데이터
- **위도/경도**: 동해 안면도 해역
- **배터리**: 90% (초기값, 시간에 따라 감소)
- **속도**: 2.0 m/s (기본값)
- **GPS 오차**: ±5m

## Moth 통합

- **하트비트**: 10초 주기 상태 발행 (`device.heartbeat` 채널)
- **텔레메트리**: GPS, 배터리, IMU 데이터 발행 (`device.telemetry` 채널)
- **자동 재연결**: 연결 실패 시 5초마다 재연결 시도

## 상태 확인

```bash
# 서버 정상 작동
curl http://localhost:9012/health | jq .

# GPS 위치 확인
curl http://localhost:9012/state | jq '.last_telemetry | {latitude, longitude}'

# 배터리 레벨
curl http://localhost:9012/state | jq '.last_telemetry.battery'

# IMU 데이터
curl http://localhost:9012/state | jq '.last_telemetry | {heading, speed}'

# 사용 가능한 스킬
curl http://localhost:9012/manifest | jq '.skills[]'
```

## 문제 해결

### "Address already in use" 에러
```bash
# 포트 확인
lsof -i :9012

# 다른 포트로 실행하거나 기존 프로세스 종료
kill -9 <PID>
```

### 같은 USV로 재시작하고 싶을 때
```bash
# Instance ID 사용 (Registry에 저장된 ID 재사용)
COWATER_INSTANCE_ID=usv-001 python device_agent.py
```

### Moth 연결 실패
```bash
# Moth 서버 상태 확인
tail -f logs/device.log | grep Moth

# 재연결 시도 로그
grep "MothPublisher" logs/device.log
```

### "Module not found" 에러
```bash
source .venv/bin/activate
pip install -r requirements.txt
python device_agent.py
```

## 로그 확인

```bash
# 실행 중인 로그 보기
tail -f logs/device.log

# GPS 관련 로그
grep GPS logs/device.log

# 배터리 경고
grep battery logs/device.log

# 에러 확인
grep ERROR logs/device.log
```


python3 pocs/01-usv-lower-agent/device_agent.py --port 9111
```

