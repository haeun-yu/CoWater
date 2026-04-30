# POC 06 - System Supervisor Agent (시스템 감시 및 운영)

## 개요

System Supervisor Agent는 전체 CoWater 시스템의 미션 계획, 승인, 우선순위 결정, 대응 전략을 판단하는 상위 계층 에이전트입니다.

## 실행 방법

### 가상 환경 활성화 후 실행 (권장)
```bash
source /path/to/.venv/bin/activate
cd /Users/teamgrit/Documents/CoWater/pocs/06-system-supervisor-agent
python system_agent.py

# Python3로 직접 실행
python3 system_agent.py

# Config 파일 지정
python system_agent.py --config config.yaml
```

## 포트

- **기본 포트**: 9116
- **설정 파일**: `config.json`

## API 엔드포인트

```bash
# 상태 확인
curl http://localhost:9116/health

# 에이전트 상태
curl http://localhost:9116/state | jq .

# 매니페스트
curl http://localhost:9116/manifest | jq .

# 수신된 알림
curl http://localhost:9116/state | jq '.inbox'

# 발송된 응답
curl http://localhost:9116/state | jq '.outbox'
```

## 주요 기능

### 상위 계층 역할
- **알림 모니터링**: Registry에서 발생한 모든 알림 감지
- **의사결정**: 각 알림에 대한 대응 전략 결정
- **미션 할당**: Control Ship에 A2A 메시지로 미션 전달
- **우선순위 관리**: 여러 알림의 우선순위 결정

### 알림 처리 흐름

1. **알림 수신**: Registry에서 `mine_detection` 등의 알림 감지 (2초 주기)
2. **의사결정**: DecisionEngine에서 대응 전략 결정
3. **응답 생성**: 
   - `action`: task.assign 또는 mission.assign
   - `target_agent_id`: Control Ship
   - `params`: 미션 세부사항
4. **A2A 전송**: Control Ship으로 A2A 메시지 전송 (초록색)
5. **추적**: 응답 및 결과를 Registry에 기록

### 스킬
- `analyze_alert`: 알림 분석
- `route_mission`: 미션 라우팅 (적절한 에이전트 선택)
- `monitor_system`: 전체 시스템 모니터링
- `escalate_alert`: 알림 단계 상향

### Moth 통합
- **하트비트**: 10초 주기 상태 발행
- **A2A 메시지 발행**: `system.a2a` 채널로 Control Ship에 명령 전송

## 기뢰 탐지 시나리오

### 1단계: 기뢰 탐지 알림 생성
```bash
curl -X POST http://localhost:8280/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "alert_type": "mine_detection",
    "severity": "critical",
    "message": "기뢰 탐지됨",
    "metadata": {
      "location": {"lat": 37.003, "lon": 129.425}
    }
  }'
```

### 2단계: System Supervisor가 알림 감지
```
[System Supervisor]
- 주기 루프 (2초마다)
- Registry의 alerts 엔드포인트 조회
- `alert_type: mine_detection` 발견
```

### 3단계: 의사결정 및 A2A 메시지 생성
```
[DecisionEngine]
- 알림 분석
- Control Ship을 target으로 선택
- task.assign 메시지 생성
- action: survey_depth
- params: { mission_type: mine_clearance, location: {...} }
```

### 4단계: Control Ship에 A2A 메시지 전송
```bash
# System Supervisor → Control Ship (초록색 링크)
POST http://localhost:9015/message:send
{
  "message_type": "task.assign",
  "action": "survey_depth",
  "params": {
    "mission_type": "mine_clearance",
    "location": {"lat": 37.003, "lon": 129.425}
  }
}
```

### 5단계: Control Ship이 하위 에이전트에 명령 전송
```bash
# Control Ship → AUV (초록색 링크)
# Control Ship → ROV (초록색 링크)
```

### 6단계: POC 07 대시보드에서 시각화
- System Supervisor → Control Ship: **초록색** (A2A)
- Control Ship → AUV: **초록색** (A2A)
- Control Ship → ROV: **초록색** (A2A)
- 각 링크 2초 유지 후 파란색(하트비트)로 복귀

## 상태 확인

```bash
# 서버 정상 작동
curl http://localhost:9116/health | jq .

# 처리 중인 알림
curl http://localhost:9116/state | jq '.inbox'

# 발송된 응답
curl http://localhost:9116/state | jq '.outbox'

# 알림 처리 이력
curl http://localhost:9116/state | jq '.memory | select(.kind == "alert_processed")'
```

## 로그 확인

```bash
# 실시간 로그 보기
tail -f logs/system_agent.log

# 알림 처리 관련 로그
grep "Alert processing" logs/system_agent.log

# A2A 메시지 전송 로그
grep "A2A task sent" logs/system_agent.log

# 에러 확인
grep ERROR logs/system_agent.log
```

## 문제 해결

### "Address already in use" 에러
```bash
lsof -i :9116
kill -9 <PID>
```

### 알림 감지 실패
```bash
# 1. Registry에서 알림 확인
curl http://localhost:8280/alerts | jq '.[] | select(.status == "waiting")'

# 2. System Supervisor 로그에서 'Alert processing' 검색
tail -f logs/system_agent.log | grep "Alert"

# 3. Moth 연결 상태 확인
tail -f logs/system_agent.log | grep "Moth"
```

### A2A 메시지 전송 실패
```bash
# 1. Control Ship이 실행 중인지 확인
curl http://localhost:9015/health

# 2. Control Ship 로그에서 A2A 메시지 수신 확인
tail -f ../05-control-ship-middle-agent/logs/device_agent.log | grep "A2A\|task.assign"

# 3. System Supervisor 로그에서 에러 확인
tail -f logs/system_agent.log | grep "Failed to send A2A"
```

## 설정 파일 (config.json)

```json
{
  "agent": {
    "role": "system_supervisor",
    "layer": "system",
    "llm": {
      "enabled": false
    }
  },
  "server": {
    "host": "127.0.0.1",
    "port": 9116
  },
  "registry": {
    "url": "http://127.0.0.1:8280",
    "required": true
  },
  "moth": {
    "url": "wss://cobot.center:8287"
  }
}
```


python3 pocs/06-system-supervisor-agent/system_agent.py --port 9161
```
