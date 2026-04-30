# POC 03 - ROV Lower Agent (수중 로봇팔)

## 개요

ROV(Remotely Operated Vehicle) Lower Agent는 수중 작업 로봇(로봇팔 포함)의 시뮬레이션 및 제어를 담당하는 하층 에이전트입니다.

## 실행 방법

### 가상 환경 활성화 후 실행 (권장)
```bash
source /path/to/.venv/bin/activate
cd /Users/teamgrit/Documents/CoWater/pocs/03-rov-lower-agent
python device_agent.py

# Python3로 직접 실행
python3 device_agent.py

# Instance ID 지정
COWATER_INSTANCE_ID=rov-001 python device_agent.py
```

## 포트

- **기본 포트**: 9011
- **설정 파일**: `config.json`

## API 엔드포인트

```bash
# 상태 확인
curl http://localhost:9011/health

# 에이전트 상태
curl http://localhost:9011/state | jq .

# 매니페스트
curl http://localhost:9011/manifest | jq .
```

## 주요 기능

### 센서 및 도구
- **Main Camera**: 메인 카메라 (영상 스트리밍)
- **Manipulator Arm**: 로봇팔 (물체 조작)
- **Depth Sensor**: 수심 감지
- **Pressure Sensor**: 압력 감지
- **Tether Monitor**: 케이블 모니터링 (wired connection)

### 스킬
- `remove_mine`: 기뢰 제거
- `manipulate_object`: 물체 조작
- `inspect_area`: 영역 검사
- `sample_collection`: 샘플 수집

### Moth 통합
- **하트비트**: 10초 주기 상태 발행
- **텔레메트리**: 카메라, 센서 데이터 발행
- **재연결**: 자동 재연결 (5초 간격)

## 상태 확인

```bash
# 서버 정상 작동
curl http://localhost:9011/health | jq .

# 수심 확인
curl http://localhost:9011/state | jq '.last_telemetry.depth'

# 스킬 목록
curl http://localhost:9011/manifest | jq '.skills[]'
```

## 문제 해결

### "Address already in use" 에러
```bash
lsof -i :9011
kill -9 <PID>
```

### Moth 연결 실패
```bash
tail -f logs/device.log | grep Moth
```

### "Module not found" 에러
```bash
source .venv/bin/activate
pip install -r requirements.txt
python device_agent.py
```


python3 pocs/03-rov-lower-agent/device_agent.py --port 9131
```

