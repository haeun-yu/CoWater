# POC 00 - Device Registration Server

## 개요

Device Registration Server는 CoWater 시스템의 중앙 레지스트리입니다. 모든 디바이스의 등록, 관리, 할당(assignment)을 담당합니다.

## 실행 방법

### 가상 환경 활성화 후 실행 (권장)
```bash
source /path/to/.venv/bin/activate
cd /Users/teamgrit/Documents/CoWater/pocs/00-device-registration-server
python device_registration_server.py
```

### Python3로 직접 실행
```bash
cd /Users/teamgrit/Documents/CoWater/pocs/00-device-registration-server
python3 device_registration_server.py
```

### 포트 변경해서 실행
```bash
python device_registration_server.py --port 8281
```

## 포트

- **기본 포트**: 8280
- **설정 파일**: `config.json`

## API 엔드포인트

### 기본 확인
```bash
curl http://localhost:8280/health
```

### 디바이스 목록 조회
```bash
curl http://localhost:8280/devices
```

### 디바이스 상세 정보
```bash
curl http://localhost:8280/devices/1
```

### 디바이스 등록
```bash
curl -X POST http://localhost:8280/devices \
  -H "Content-Type: application/json" \
  -d '{
    "secretKey": "server-secret",
    "name": "AUV-01",
    "device_type": "AUV",
    "layer": "lower",
    "location": {"latitude": 37.003, "longitude": 129.425, "altitude": -25}
  }'
```

## 주요 기능

- **디바이스 등록**: 새로운 디바이스 등록 및 ID 발급
- **레이어 할당**: 디바이스의 parent_id 설정 (lower → middle → system)
- **하트비트 모니터링**: 주기적인 디바이스 상태 확인 (10초 주기, 30초 타임아웃)
- **자동 재할당**: 오프라인 디바이스의 자식 자동 재할당
- **Moth 통합**: 하트비트 메시지를 Moth pub-sub 시스템으로 발행

## 설정

`config.json` 파일에서 다음 설정 가능:
- `port`: 서버 포트 (기본값: 8280)
- `heartbeat_interval`: 하트비트 체크 간격 (초)
- `heartbeat_timeout`: 하트비트 타임아웃 (초)
- `moth`: Moth 서버 연결 설정

## 문제 해결

### "Address already in use" 에러
```bash
# 포트 확인
lsof -i :8280

# 프로세스 종료
kill -9 <PID>
```

### "Module not found" 에러
```bash
source .venv/bin/activate
pip install -r requirements.txt
python device_registration_server.py
```

## 상태 확인

```bash
# 서버 정상 작동 확인
curl http://localhost:8280/health | jq .

# 등록된 디바이스 확인
curl http://localhost:8280/devices | jq '.[].name'
```
