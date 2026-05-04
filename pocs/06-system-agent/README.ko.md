# POC 06 - System Agent

## 개요

System Agent는 system-layer 최고 의사결정 에이전트다. Event를 수신해 Alert를 생성하고, 대상 에이전트를 선택해 A2A 명령을 배정하며, Response를 기록한다.

## 기본 정보

- 포트: `9116`
- Registry 기본 주소: `http://127.0.0.1:8280`
- role: `system_agent`
- severity enum: `CRITICAL`, `WARNING`, `INFORMATION`
- 상태 유지 방식: `1초` Registry keepalive

## 실행

```bash
cd /Users/teamgrit/Documents/CoWater/pocs/06-system-agent
python3 system_agent.py
```

## 주요 기능

- Event 수신과 Alert 생성
- Alert 해석과 대응 우선순위 판단
- 대상 에이전트 선택과 `task.assign` 전송
- Response 기록 및 `planned -> completed/failed` 상태 갱신

## Capability 기준

스킬:

- `mission_planning`
- `fleet_supervision`
- `priority_decision`
- `response_strategy`
- `approval_control`
- `performance_analysis`

도구:

- `device_registry_reader`
- `mcp_api_client`
- `a2a_router`
- `mission_planner`
- `alert_response_planner`
- `fleet_monitor`
- `analytics_engine`

주요 액션:

- `mission.plan`
- `mission.assign`
- `task.assign`
- `approve_response`
- `route_direct`
- `route_via_middle`
- `escalate_alert`

## 주요 엔드포인트

- `GET /health`
- `GET /state`
- `GET /manifest`
- `POST /message:send`

## Event 처리

- A2A `event.report`를 수신한다.
- Event를 Registry Server의 event ledger에 저장한다.
- `config.json > event_rules`를 기준으로 severity와 `recommended_action`을 결정한다.
- Alert를 Registry Server에 저장한다.
- 이후 적절한 middle agent 또는 lower agent에 `task.assign`를 전송한다.
- dispatch 성공/실패 결과를 `dispatch_result`에 반영하고 Response 상태를 갱신한다.

기본 매핑 예시:

| event_type | severity | recommended_action |
| --- | --- | --- |
| `mine_detection` | `CRITICAL` | `survey_depth` |
| `battery_low` | `WARNING` | `return_to_base` |

## 점검 예시

```bash
curl http://127.0.0.1:9116/health | jq .
curl http://127.0.0.1:9116/state | jq '.outbox'
curl http://127.0.0.1:8280/events | jq .
curl http://127.0.0.1:8280/alerts | jq .
curl http://127.0.0.1:8280/responses | jq .
```
