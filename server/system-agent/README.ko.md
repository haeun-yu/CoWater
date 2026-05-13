# POC 06 - System Agent Layer

## 개요

System Agent Layer는 system-layer 다중 에이전트 시스템이다. 역할별 프로세스가 RequestHandler, DeviceBridge, MissionPlanner, PolicyManager, SystemSentinel, InsightReporter로 분리되어 `SYS_INTENT_CLASSIFIED → Proposal → Mission → Task` 흐름을 처리한다.

## 기본 정보

- 포트: `9110` DeviceBridge, `9111` MissionPlanner, `9112` PolicyManager, `9113` SystemSentinel, `9114` InsightReporter, `9116` RequestHandler
- Registry 기본 주소: `http://127.0.0.1:8280`
- role: `request_handler`, `device_bridge`, `mission_planner`, `policy_manager`, `system_sentinel`, `insight_reporter`
- severity enum: `CRITICAL`, `WARNING`, `INFORMATION`
- 상태 유지 방식: `1초` Registry keepalive
- API 문서: [../API_REFERENCE.ko.md](../API_REFERENCE.ko.md)

## 실행

```bash
cd /Users/teamgrit/Documents/CoWater/server/system-agent
python3 run_system_agents.py
```

상위 기준 문서:

- [../ARCHITECTURE.ko.md](../ARCHITECTURE.ko.md)
- [../API_REFERENCE.ko.md](../API_REFERENCE.ko.md)

## 주요 기능

- RequestHandler: 사용자 입력을 `SYS_INTENT_CLASSIFIED`로 기록하고 Proposal 흐름 시작
- MissionPlanner: Mission Proposal 생성
- PolicyManager: 자동화 정책 생성/갱신 및 정책 기반 대응
- DeviceBridge: Device Agent 명령 적용
- SystemSentinel: Registry 기반 상태 감시
- InsightReporter: Device, Mission, Insight 요약 제공

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
- 이후 이벤트 위치 기준으로 가장 가까우면서 해당 대응을 수행할 수 있는 디바이스를 고른다.
- 선택된 디바이스에 middle parent가 있으면 middle agent로 보내고, 없으면 해당 lower agent에 직접 보낸다.
- 원래 최적 디바이스가 예약 중이어도 대체 가능한 available 디바이스가 있으면 즉시 그 디바이스로 재선정한다.
- 동시 incident가 들어오면 이미 다른 mission에 예약된 lower device는 새 incident 후보에서 제외한다.
- 현재 구현은 최소 reservation만 지원하고, mission 간 선점(preemption)은 지원하지 않는다.
- 하나의 incident는 `steps[].tasks[]` 구조로 계획한다. `step`은 순서 단위이고, `task`는 개별 디바이스 실행 단위다.
- 같은 step 안의 task들은 함께 dispatch한다.
- 앞 step의 task 결과들은 다음 step 입력의 `previous_step_results`로 전달한다.
- step 종료 후에는 `step evaluation`을 수행한다. 이때 `step execution status`와 `evaluation decision`은 분리된다.
- 예를 들어 일부 task가 실패해도 `evaluation_policy`가 충분한 결과라고 판단하면 다음 step으로 진행할 수 있다.
- 현재 구현은 `proceed_next_step`, `retry_same_step`, `reassign_failed_tasks`, `manual_intervention_required`, `abort_mission` decision을 사용한다.
- `needs_review` Mission이 발생하면 `dispatch_state.manual_intervention`에 개입이 필요한 step과 사유를 남긴다.
- `GET /manual-interventions`로 현재 수동 개입이 필요한 Mission 목록을 조회할 수 있다.
- `GET /manual-interventions/{mission_id}`로 특정 수동 개입 건의 상세 정보와 `recommended_operator_actions`를 조회할 수 있다.
- dispatch 성공/실패 결과를 Mission의 `dispatch_state`와 Timeline에 반영한다.
- 현장 수행 결과(`mission.result`)를 수신하면 `dispatch_result.execution_results`에 실행 주체별 결과를 누적한다.
- lower task 실행 결과에는 최소 `status`, `usable_output`, `failure_reason`, `confidence`, `artifacts`가 포함될 수 있다.
- 테스트 시에는 lower task `params.simulate_outcome`으로 `status`, `usable_output`, `failure_reason`, `confidence`, `artifacts`를 강제할 수 있다.
- 예약 가능한 장비가 없으면 현재 구현은 Mission Proposal만 생성하고 승인 후에도 dispatch가 실패하면 Mission을 실패로 기록한다.
- 동일 `mission_id + step_id + task_id + 실행 주체`의 `mission.result`는 중복으로 보고 기존 완료 결과를 덮어쓰지 않는다.
- 실행 결과 집계(`dispatch_result.execution_aggregate_status`)는 하나라도 실패이면 `failed`, 모두 성공이면 `completed`다.
- 다만 최종 Mission 상태는 evaluation 결과를 반영하므로 `needs_review`가 될 수 있다.

기본 매핑 예시:

| event_type | severity | recommended_action |
| --- | --- | --- |
| `mine_detection` | `CRITICAL` | `survey_depth` |
| `battery_low` | `WARNING` | `return_to_base` |

## 점검 예시

```bash
curl http://127.0.0.1:9116/health | jq .
curl http://127.0.0.1:9110/health | jq .
curl http://127.0.0.1:9116/state | jq '.outbox'
curl http://127.0.0.1:8280/events | jq .
curl http://127.0.0.1:8280/alerts | jq .
curl http://127.0.0.1:8280/insights | jq .
curl http://127.0.0.1:8280/approvals | jq .
curl http://127.0.0.1:8280/missions | jq .
```
