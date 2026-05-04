# 기뢰 제거 시나리오 가이드

이 문서는 현재 구현 기준의 `기뢰 탐지 -> Event 기록 -> Alert 생성 -> 대응 배정` 흐름을 정리한다.

## 시나리오 참여 구성

| POC | 역할 |
| --- | --- |
| `00` | Registry Server |
| `02` | AUV Lower Agent |
| `03` | ROV Lower Agent |
| `05` | Control Ship Middle Agent |
| `06` | System Agent |

필요에 따라 `04` USV Middle Agent도 중간 라우팅에 참여할 수 있다.

## 기본 흐름

```text
1. Lower Agent가 mine_detection Event를 상위로 보고
2. System Agent가 event.report를 수신
3. System Agent가 Event를 Registry Server에 저장
4. System Agent가 severity를 판단해 Alert를 생성
5. System Agent가 target agent를 선택하고 task.assign 전송
6. 현장 수행 결과를 다시 상위로 보고
7. Response를 Registry Server에 저장
```

## Event / Alert / Response 기준

- Event는 발생 사실이다.
- Alert는 대응이 필요한 상태다.
- Response는 계획되거나 실행된 대응 기록이다.
- 세 도메인의 canonical owner는 모두 Registry Server다.

severity enum:

- `CRITICAL`
- `WARNING`
- `INFORMATION`

## event_type 기본 매핑

`pocs/06-system-agent/config.json > event_rules` 기준:

| event_type | severity | recommended_action |
| --- | --- | --- |
| `mine_detection` | `CRITICAL` | `survey_depth` |
| `collision_risk` | `CRITICAL` | `escalate_alert` |
| `distress` | `CRITICAL` | `escalate_alert` |
| `battery_low` | `WARNING` | `return_to_base` |
| `communication_loss` | `WARNING` | `escalate_alert` |
| `tether_warning` | `WARNING` | `escalate_alert` |

## 실행 준비

```bash
python3 pocs/00-device-registration-server/device_registration_server.py
python3 pocs/06-system-agent/system_agent.py
python3 pocs/05-control-ship-middle-agent/device_agent.py
python3 pocs/02-auv-lower-agent/device_agent.py
python3 pocs/03-rov-lower-agent/device_agent.py
```

기본 Registry 주소는 `http://127.0.0.1:8280`이다.

## 확인 절차

### 1. Registry 등록 상태

```bash
curl http://127.0.0.1:8280/devices | jq '.[] | {id, name, layer, device_type, parent_id, connected}'
```

### 2. Event 기록 확인

```bash
curl -X POST http://127.0.0.1:8280/events/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "mine_detection",
    "severity": "CRITICAL",
    "message": "기뢰 탐지",
    "source_system": "scenario_test",
    "source_agent_id": "auv-001",
    "source_role": "auv"
  }'
```

```bash
curl http://127.0.0.1:8280/events | jq .
```

### 3. Alert 기록 확인

```bash
curl http://127.0.0.1:8280/alerts | jq .
```

### 4. Response 기록 확인

```bash
curl http://127.0.0.1:8280/responses | jq .
```

### 5. A2A 전달 확인

```bash
curl http://127.0.0.1:9116/state | jq '.outbox'
curl http://127.0.0.1:9115/state | jq '.inbox'
```

## 성공 기준

- Event가 Registry Server에 기록된다.
- System Agent가 Alert를 생성한다.
- Alert severity가 대문자 enum으로 기록된다.
- Response가 Alert와 연결되어 저장된다.
- middle agent 또는 lower agent로 `task.assign`가 전달된다.

## 현재 구현 메모

- System Agent는 `event.report`를 직접 수신해 Event 저장과 Alert 발행을 수행한다.
- assignment 계산은 Registry Server가 맡고, 임무 판단은 System Agent가 맡는다.
- heartbeat 위치와 배터리 값은 가능한 경우 `latitude`, `longitude`, `battery_percent`로 발행한다.
