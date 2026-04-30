# POC 05 - Control Ship Middle Agent (지휘함)

## 개요

Control Ship Middle Agent는 여러 하위 에이전트(AUV, ROV, USV)의 상태를 종합하고 현장 단위 미션을 조율하는 중간 계층 에이전트입니다.

## 실행 방법

### 가상 환경 활성화 후 실행 (권장)
```bash
source /path/to/.venv/bin/activate
cd /Users/teamgrit/Documents/CoWater/pocs/05-control-ship-middle-agent
python device_agent.py

# Python3로 직접 실행
python3 device_agent.py

# Config 파일 지정
python device_agent.py --config config.yaml
```

## 포트

- **기본 포트**: 9015
- **설정 파일**: `config.json`

## API 엔드포인트

```bash
# 상태 확인
curl http://localhost:9015/health

# 에이전트 상태 (자식 디바이스 포함)
curl http://localhost:9015/state | jq .

# 매니페스트
curl http://localhost:9015/manifest | jq .

# 자식 디바이스 목록
curl http://localhost:9015/children | jq .

# 작업 목록
curl http://localhost:9015/tasks | jq .
```

## 주요 기능

### 중간 계층 역할
- **하위 에이전트 관리**: AUV, ROV, USV 상태 모니터링
- **미션 조율**: System Supervisor로부터 받은 명령을 하위 에이전트에 배분
- **A2A 라우팅**: System Supervisor ↔ Lower Agents 간 A2A 메시지 라우팅
- **상태 종합**: 모든 하위 에이전트의 상태를 수집 및 보고

### 스킬
- `deploy`: 하위 에이전트 배치
- `survey_depth`: 깊이 탐사 (AUV에 라우팅)
- `remove_mine`: 기뢰 제거 (ROV에 라우팅)
- `return_to_base`: 기지 복귀
- `coordinate_mission`: 다중 에이전트 미션 조율

### Moth 통합
- **하트비트**: 10초 주기 상태 발행
- **자식 하트비트 릴레이**: 하위 에이전트의 하트비트를 Moth로 재발행
- **A2A 메시지 수신**: `system.a2a` 채널에서 System Supervisor 메시지 수신

## 자식 디바이스 관리

### 자식 등록
```bash
# 자동: Device Registry에서 parent_id 설정
# 수동: /children/register 엔드포인트

curl -X POST http://localhost:9015/children/register \
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
# 자식 디바이스에서 Control Ship으로 하트비트 전송
curl -X POST http://localhost:9015/children/heartbeat \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "auv-001",
    "timestamp": "2026-04-29T10:30:00Z",
    "battery": 85,
    "depth": -25
  }'
```

## A2A 메시지 흐름

### System Supervisor → Control Ship → Lower Agent

1. **System Supervisor** (POC 06)가 기뢰 탐지 알림 수신
2. **A2A 메시지**: `system.a2a` 채널로 Control Ship에 `task.assign` 전송
   - Action: `survey_depth`
   - Target: Control Ship
3. **Control Ship**이 메시지 수신 및 처리
4. **A2A 라우팅**: 하위 에이전트(AUV, ROV)에 명령 전송
   - AUV: `survey_depth` (탐사)
   - ROV: `remove_mine` (제거)

## 상태 확인

```bash
# 서버 정상 작동
curl http://localhost:9015/health | jq .

# 자식 디바이스 상태
curl http://localhost:9015/children | jq '.children[].last_heartbeat_at'

# 진행 중인 작업
curl http://localhost:9015/tasks | jq '.tasks[] | {id, status}'

# A2A 수신 기록
curl http://localhost:9015/state | jq '.inbox[-5:]'
```

## 문제 해결

### "Address already in use" 에러
```bash
lsof -i :9015
kill -9 <PID>
```

### 자식 디바이스 연결 실패
```bash
# 1. 자식 디바이스가 실행 중인지 확인
curl http://localhost:9010/health  # AUV
curl http://localhost:9011/health  # ROV

# 2. Registry에서 parent_id 확인
curl http://localhost:8280/devices/5 | jq '.parent_id'

# 3. Control Ship 로그 확인
tail -f logs/device.log | grep child
```

### A2A 메시지 수신 실패
```bash
# 1. System Supervisor가 실행 중인지 확인
curl http://localhost:9116/health

# 2. Moth 연결 상태 확인
tail -f logs/device.log | grep Moth

# 3. 수신된 메시지 확인
curl http://localhost:9015/state | jq '.inbox'
```


python3 pocs/05-control-ship-middle-agent/device_agent.py --port 9151
```

