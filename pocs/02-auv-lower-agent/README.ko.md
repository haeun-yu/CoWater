# POC 02 - AUV Lower Agent (자율수중로봇)

## 개요

AUV(Autonomous Underwater Vehicle) Lower Agent는 수중 드론의 시뮬레이션 및 제어를 담당하는 하층 에이전트입니다.

## 실행 방법

### 가상 환경 활성화 후 실행 (권장)
```bash
source /path/to/.venv/bin/activate
cd /Users/teamgrit/Documents/CoWater/pocs/02-auv-lower-agent
python device_agent.py
```

### Python3로 직접 실행
```bash
cd /Users/teamgrit/Documents/CoWater/pocs/02-auv-lower-agent
python3 device_agent.py
```

### Instance ID 지정해서 실행
```bash
COWATER_INSTANCE_ID=auv-001 python device_agent.py
```

### 커스텀 포트로 실행
```bash
# config.json에서 server.port 변경 후:
python device_agent.py --config config.yaml
```

## 포트

- **기본 포트**: 9010
- **설정 파일**: `config.json`
- **포트 변경**: `config.json`의 `server.port` 수정

## API 엔드포인트

### 기본 확인
```bash
curl http://localhost:9010/health
```

### 에이전트 상태
```bash
curl http://localhost:9010/state | jq .
```

### 매니페스트 (스킬 목록)
```bash
curl http://localhost:9010/manifest | jq .
```

## 주요 기능

### 센서 및 도구
- **Depth Sensor**: 수심 감지
- **Acoustic Modem**: 음향 통신
- **Sonar**: 초음파 탐지 (기뢰 탐지 용)
- **Battery**: 배터리 모니터링
- **Motor Control**: 추진 제어

### 스킬 (수행 가능한 작업)
- `survey_depth`: 깊이 탐사
- `scan_area`: 영역 탐색
- `deploy`: 배치
- `return_to_base`: 기지 복귀
- `remove_mine`: 기뢰 제거 (ROV와 협력)

### Moth 통합
- **하트비트**: 10초 주기 상태 발행 (`device.heartbeat` 채널)
- **텔레메트리**: 센서 데이터 발행 (`device.telemetry` 채널)
- **자동 재연결**: 연결 실패 시 5초마다 재연결 시도

## 시뮬레이션 설정

### config.json의 simulation 섹션
```json
{
  "simulation": {
    "sonar_enabled": true,
    "sonar_update_interval": 3,
    "mine_detection_probability": 0.3,
    "start_position": {
      "latitude": 37.002,
      "longitude": 129.428,
      "altitude": -25
    }
  }
}
```

### 시뮬레이션 데이터
- **수심**: -25m (기본값)
- **배터리**: 85% (초기값, 시뮬레이션 시 감소)
- **속도**: 1.5 m/s (기본값)
- **위치**: 37.002°N, 129.428°E (동해)

## 상태 확인

```bash
# 서버 정상 작동 확인
curl http://localhost:9010/health | jq .

# 현재 수심 확인
curl http://localhost:9010/state | jq '.last_telemetry.depth'

# 배터리 레벨 확인
curl http://localhost:9010/state | jq '.last_telemetry.battery'

# 사용 가능한 스킬 확인
curl http://localhost:9010/manifest | jq '.skills[]'
```

## 문제 해결

### "Address already in use" 에러
```bash
# 포트 확인
lsof -i :9010

# 기존 프로세스 종료
kill -9 <PID>

# 또는 다른 포트로 실행
# config.json에서 server.port 변경
```

### Moth 연결 실패
```bash
# Moth 서버 연결 상태 확인
# wss://cobot.center:8287이 응답하는지 확인

# 또는 로그에서 확인
grep "Moth" logs/device.log
```

### "Module not found" 에러
```bash
# 가상 환경 활성화
source .venv/bin/activate

# 의존성 설치
pip install -r requirements.txt

# 다시 실행
python device_agent.py
```

## 로그 확인

```bash
# 실행 중인 로그 보기
tail -f logs/device.log

# 에러 메시지 필터링
grep ERROR logs/device.log

# Moth 관련 메시지
grep Moth logs/device.log
```

## 시나리오: 기뢰 탐지 및 제거

### 1단계: AUV 실행
```bash
python device_agent.py
```

### 2단계: Registry에서 기뢰 탐지 알림 생성
```bash
curl -X POST http://localhost:8280/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "alert_type": "mine_detection",
    "severity": "critical",
    "message": "기뢰 탐지됨",
    "metadata": {"location": {"lat": 37.002, "lon": 129.428}}
  }'
```

### 3단계: System Supervisor에서 Control Ship으로 명령 전송
- System Supervisor가 알림 수신
- Control Ship으로 A2A 메시지 전송 (초록색으로 표시)

### 4단계: Control Ship에서 AUV로 명령 전송
- Control Ship이 AUV로 `survey_depth` 명령 전송 (A2A)
- AUV가 소나 데이터 수집 시작

### 5단계: POC 07 대시보드에서 시각화 확인
- System Supervisor → Control Ship: 초록색 링크
- Control Ship → AUV: 초록색 링크
- AUV의 소나 활동: 노란색 링크

