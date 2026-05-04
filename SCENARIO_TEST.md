# 기뢰 제거 시나리오 테스트 문서

## 목적

이 문서는 CoWater의 대표 시나리오인 `기뢰 탐지 및 제거` 흐름이 현재 구현에서 어떻게 검증되는지 정리한다.

검증 대상:

- System Agent의 이벤트 수신과 Alert 생성
- Registry Server의 Event / Alert / Response 원장
- Middle Layer를 통한 A2A 명령 전파
- Lower Agent의 명령 수신 및 임무 수행 준비

---

## 테스트 대상 구성

| POC | 역할 | 기본 포트 |
| --- | --- | --- |
| `00` | Registry Server | `8280` |
| `01` | USV Lower Agent | `9111` |
| `02` | AUV Lower Agent | `9112` |
| `03` | ROV Lower Agent | `9113` |
| `04` | USV Middle Agent | `9114` |
| `05` | Control Ship Middle Agent | `9115` |
| `06` | System Agent | `9116` |

주의:

- 모든 POC 기본 설정은 Registry Server `http://127.0.0.1:8280` 기준으로 맞춘다.
- 테스트 전에 실제 실행 포트와 각 Agent의 `registry.url`이 일치하는지만 확인한다.

---

## 시나리오 개요

```text
1. Lower Agent 또는 외부 시스템이 mine_detection Event를 System Agent에 A2A로 보고
2. System Agent가 Event를 Registry Server의 event ledger에 기록
3. System Agent가 severity를 판단해 Alert를 생성하고 alert ledger에 저장
4. System Agent가 Alert를 해석해 대상 middle agent 또는 lower agent를 선택
5. System Agent가 task.assign A2A를 전송
6. 작업 결과는 다시 상위로 A2A 보고
7. 대응 계획과 결과는 Response ledger에 기록
```

---

## 사전 확인

### 1. 서버 기동 확인

```bash
curl http://127.0.0.1:8280/health
curl http://127.0.0.1:9116/health
curl http://127.0.0.1:9115/health
curl http://127.0.0.1:9112/health
curl http://127.0.0.1:9113/health
```

### 2. Registry 연결 확인

```bash
curl http://127.0.0.1:8280/devices | jq .
```

확인 항목:

- 각 Agent가 Registry에 등록되어 있는가
- `agent.endpoint`와 `agent.command_endpoint`가 채워져 있는가
- middle agent가 `connected=true`인가

---

## 핵심 검증 항목

### 1. Event 원장 기록

Event를 직접 넣어 Registry API를 확인한다.

```bash
curl -X POST http://127.0.0.1:8280/events/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "mine_detection",
    "severity": "CRITICAL",
    "message": "기뢰 탐지 이벤트",
    "source_system": "scenario_test",
    "source_agent_id": "auv-001",
    "source_role": "auv",
    "metadata": {
      "location": { "lat": 37.003, "lon": 129.425 }
    }
  }'
```

이후 확인:

```bash
curl http://127.0.0.1:8280/events | jq .
```

### 2. Alert 원장 기록

System Agent가 Event를 받아 Alert를 생성하는 흐름이 정상인지 확인한다.

확인 포인트:

- Event가 기록되었는가
- 대응 Alert가 생성되었는가
- Alert severity가 `CRITICAL | WARNING | INFORMATION` 중 하나인가

```bash
curl http://127.0.0.1:8280/alerts | jq .
```

### 3. Response 기록

System Agent가 Alert를 해석한 뒤 Response를 저장하는지 확인한다.

```bash
curl http://127.0.0.1:8280/responses | jq .
```

확인 포인트:

- `alert_id`와 연결된 `response_id`가 생성되었는가
- `target_agent_id`, `action`, `reason`이 들어 있는가
- `response.status`가 `completed`로 갱신되었는가
- `dispatch_result.delivered=true`와 대상 endpoint가 기록되었는가

### 4. A2A 명령 전파

System Agent에서 middle agent 또는 lower agent로 명령이 전파되는지 확인한다.

확인 포인트:

- System Agent `outbox`
- Control Ship `inbox`
- 대상 lower agent `inbox`
- Control Ship `inbox`에 lower의 `mission.result`가 들어오는가
- System Agent `memory`에 `mission_result_received`가 남는가

```bash
curl http://127.0.0.1:9116/state | jq '.outbox'
curl http://127.0.0.1:9115/state | jq '.inbox'
curl http://127.0.0.1:9112/state | jq '.inbox'
curl http://127.0.0.1:9116/state | jq '.memory'
```

---

## 성공 기준

- Event가 Registry event ledger에 저장된다.
- System Agent가 Event를 기반으로 Alert를 생성한다.
- Alert severity가 대문자 enum으로 기록된다.
- Response가 Registry response ledger에 저장된다.
- A2A `task.assign`가 적절한 대상에 전달된다.
- Response가 `planned`에서 끝나지 않고 `completed` 또는 `failed`로 전이된다.
- lower/middle heartbeat에 `battery_percent`와 위치 정보가 포함된다.

---

## 현재 구현 기준 메모

- Event / Alert / Response 원장은 모두 Registry Server가 canonical owner다.
- System Agent는 A2A `event.report`를 수신하면 Event 저장과 Alert 발행을 수행한다.
- System Agent는 Event 수신 직후 Alert 처리를 즉시 시작하며, dispatch 결과로 Response 상태를 갱신한다.
- severity 기본값과 권장 action은 `pocs/06-system-agent/config.json`의 `event_rules`를 따른다.
- heartbeat 배터리 필드는 `battery_percent`를 사용한다.

---

## 후속 점검 항목

- Registry / Agent 기본 포트 조합에 대한 자동 회귀 테스트 추가
- Event -> Alert 승격에 대한 자동 테스트 추가
- severity / recommended_action 매핑에 대한 단위 테스트 추가
- middle offline 시 assignment 재배포 테스트 추가
