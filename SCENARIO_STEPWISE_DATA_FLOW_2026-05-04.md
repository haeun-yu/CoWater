# CoWater 단계별 데이터 검증 (실행 기준: 2026-05-04)

아래는 실제 실행 1건(`response_id=59ec169d-93d3-4b19-b1e6-715609a4cf54`)을 기준으로, 요청하신 1~9 단계를 그대로 맞춘 증적 문서다.

## 1. Event 요청과 응답

- 요청 대상: `POST http://127.0.0.1:9116/message:send`
- 요청 핵심:
  - `message_type=event.report`
  - `event_type=mine_detection`
  - `source_agent_id=auv-001`
  - `metadata.evidence.frame_id=F-STEP9-20260504`
- 응답 핵심:
  - `event_id=event-b415b03c-e5e4-4d0e-8976-fabc5e034dec`
  - `alert_id=alert-5487ea4f-7bcb-4573-8290-3689297938eb`
  - `severity=CRITICAL`

실제 요청 데이터:

```json
{
  "message": {
    "role": "user",
    "parts": [
      {
        "type": "data",
        "data": {
          "message_type": "event.report",
          "event_type": "mine_detection",
          "reason": "step-1-9 verification run",
          "source_agent_id": "auv-001",
          "source_role": "auv",
          "metadata": {
            "location": { "lat": 37.003, "lon": 129.425 },
            "evidence": {
              "sonar_confidence": 0.98,
              "frame_id": "F-STEP9-20260504"
            }
          }
        }
      }
    ]
  }
}
```

실제 응답 데이터:

```json
{
  "received": true,
  "message_type": "event.report",
  "event_id": "event-b415b03c-e5e4-4d0e-8976-fabc5e034dec",
  "alert_id": "alert-5487ea4f-7bcb-4573-8290-3689297938eb",
  "severity": "CRITICAL"
}
```

## 2. Alert 등록 확인

- 조회: `GET /alerts/alert-5487ea4f-7bcb-4573-8290-3689297938eb`
- 확인값:
  - `event_id=event-b415b03c-e5e4-4d0e-8976-fabc5e034dec`
  - `alert_type=mine_detection`
  - `severity=CRITICAL`
  - `status=approved`

## 3. System Agent가 대응 판단한 로그

- `GET /9116/tasks`에서 `id=03f5b374-dca7-4f04-9d0c-236ced6291df` 확인
- artifacts 결과:
  - `event_id`, `alert_id`, `severity` 즉시 반환
- `GET /9116/state`의 `last_decision`:
  - `mode=rule`
  - `llm.provider=ollama`, `model=gemma4:e2b`
  - `recommendations[0].action=mission.assign`
  - `severity=CRITICAL`

대응 방법을 얻는 규칙:

- `event_type=mine_detection`은 `pocs/06-system-agent/config.json > event_rules`에서 `severity=CRITICAL`, `recommended_action=survey_depth`로 정의된다.
- System Agent의 Decision Engine은 이 Alert를 rule 모드로 해석해 `mission_type=mine_survey_and_removal` 권고를 만든다.
- 실제 dispatch 대상 선택은 이벤트 위치와 각 디바이스 위치를 비교해 `가장 가까우면서 해당 step을 수행할 수 있는 디바이스`를 고르는 방식으로 바뀌었다.
- 선택된 디바이스에 middle parent가 있으면 그 middle을 경유하고, 없으면 해당 lower에 직접 전달한다.
- 가장 가까운 디바이스가 reservation 중이어도 대체 가능한 available 디바이스가 있으면 queue에 넣지 않고 즉시 그 디바이스로 다시 계획한다.
- `mine_detection`처럼 여러 장비가 필요한 경우에는 `steps[].tasks[]` 구조로 계획한다.
- `step`은 순서 단위이고, 같은 step 안의 모든 `task`가 완료되어야 다음 step으로 넘어간다.
- 앞 step의 task 결과들은 다음 step 입력의 `previous_step_results`로 넘긴다.
- step 종료 후에는 `step evaluation`을 수행하고, `step execution status`와 별도로 `decision`을 기록한다.
- 탐색 step에서는 일부 task 실패가 있어도 usable output이 있으면 `proceed_next_step`이 가능하다.
- usable output이 없으면 현재 구현은 상황에 따라 `retry_same_step`, `reassign_failed_tasks`, `manual_intervention_required`, `abort_mission` 중 하나를 기록한다.

판단 로그 핵심 데이터:

```json
{
  "mode": "rule",
  "llm": {
    "provider": "ollama",
    "model": "gemma4:e2b",
    "enabled": true
  },
  "recommendations": [
    {
      "action": "mission.assign",
      "priority": "critical",
      "mission_type": "mine_survey_and_removal",
      "params": {
        "location": { "lat": 37.003, "lon": 129.425 }
      }
    }
  ],
  "alert_type": "mine_detection",
  "severity": "CRITICAL"
}
```

## 4. System Agent가 보낸 명령과 대상

- Response 조회: `GET /responses/59ec169d-93d3-4b19-b1e6-715609a4cf54`
- 확인값:
  - `action=mission.assign`
  - `target_agent_id=195` (Control Ship Middle Agent)
  - 첫 dispatch 대상은 첫 step 첫 task의 route hop 기준으로 선택됨

Response 원장에 저장되는 계획 데이터 예시:

```json
{
  "action": "mission.assign",
  "params": {
    "location": { "lat": 37.003, "lon": 129.425 },
    "steps": [
      {
        "step_id": "survey",
        "depends_on": [],
        "tasks": [
          {
            "task_id": "task-1",
            "action": "survey_depth",
            "target_device_id": 196
          }
        ]
      },
      {
        "step_id": "remove",
        "depends_on": ["survey"],
        "tasks": [
          {
            "task_id": "task-1",
            "action": "remove_mine",
            "target_device_id": 197
          }
        ]
      }
    ]
  }
}
```

실제 첫 step A2A 전송 데이터 예시:

```json
{
  "message_type": "task.assign",
  "action": "survey_depth",
  "response_id": "59ec169d-93d3-4b19-b1e6-715609a4cf54",
  "alert_id": "alert-5487ea4f-7bcb-4573-8290-3689297938eb",
  "step_id": "survey",
  "task_id": "task-1",
  "reason": "System Agent response to mine_detection",
  "params": {
    "action": "survey_depth",
    "location": { "lat": 37.003, "lon": 129.425 },
    "mission_type": "mine_clearance",
    "target_device_id": 196
  }
}
```

## 5. 대상(Control Ship/Lower)의 대응 판단 로그

- Control Ship의 `tasks`에서 `id=59ec...` 확인:
  - lower에서 올라온 `mission.result`를 수신
  - `source_agent_id`가 AUV/ROV로 기록됨
- Lower의 `tasks`에서 `id=59ec...` 확인:
  - AUV: `action=survey_depth`
  - ROV: `action=remove_mine`

주의:
- `layer.assignment` 로그는 변경 시에만 남기도록 코드가 보강되었다.
- `incident_decision`은 현재 각 agent state memory에 남는다.
- 장기 조회가 필요하면 `incident_decision`도 Registry ledger/API로 승격하는 편이 맞다.

Control Ship의 하위 분배 규칙:

- System Agent가 특정 `target_device_id`를 지정하면 Control Ship은 그 대상 lower에만 전달한다.
- `step_id`, `task_id`를 함께 전달해 순차/병렬 실행 단위를 구분한다.
- 앞 step 결과가 있으면 다음 step `params.previous_step_results`로 넘긴다.
- 하위 명령에는 `report_to_endpoint=http://127.0.0.1:9115`를 넣어 결과가 Control Ship으로 돌아오게 한다.

## 6. 대상이 실제로 어떻게 대응했는지

- AUV task artifacts:
  - `delivered=true`
  - 명령 파라미터(`location`, `mission_type`, `report_to_endpoint`) 포함
- ROV task artifacts:
  - `delivered=true`
  - `remove_mine` 수행 명령 포함

AUV 수신/응답 데이터:

```json
{
  "message_type": "task.assign",
  "step_id": "survey",
  "action": "survey_depth",
  "params": {
    "location": { "lat": 37.003, "lon": 129.425 },
    "mission_type": "mine_clearance",
    "report_to_endpoint": "http://127.0.0.1:9115"
  },
  "response": {
    "delivered": true,
    "status": "completed",
    "usable_output": true,
    "failure_reason": null,
    "confidence": 0.93,
    "artifacts": [
      {
        "type": "mine_location_estimate",
        "location": { "lat": 37.003, "lon": 129.425 },
        "confidence": 0.93
      },
      {
        "type": "sonar_evidence",
        "frame_id": "auv-survey-..."
      }
    ]
  }
}
```

ROV 수신/응답 데이터:

```json
{
  "message_type": "task.assign",
  "step_id": "remove",
  "action": "remove_mine",
  "params": {
    "location": { "lat": 37.003, "lon": 129.425 },
    "mission_type": "mine_clearance",
    "report_to_endpoint": "http://127.0.0.1:9115"
  },
  "response": {
    "delivered": true,
    "status": "completed",
    "usable_output": true,
    "failure_reason": null,
    "confidence": 0.95,
    "artifacts": [
      {
        "type": "mine_removal_confirmation",
        "location": { "lat": 37.003, "lon": 129.425 },
        "used_previous_step_results": true
      },
      {
        "type": "manipulator_log",
        "action": "remove_mine"
      }
    ]
  }
}
```

## 7. 대응 후 System Agent로 재전달 확인

- Control Ship `tasks`의 `id=59ec...` 메시지:
  - `message_type=mission.result`
  - `response_id=59ec...`
  - `alert_id=alert-5487...`
  - `execution_status=completed`
  - `execution_log`에 하위 실행 결과 포함

하위에서 Control Ship으로 올라온 데이터:

```json
{
  "message_type": "mission.result",
  "response_id": "59ec169d-93d3-4b19-b1e6-715609a4cf54",
  "alert_id": "alert-5487ea4f-7bcb-4573-8290-3689297938eb",
  "execution_status": "completed",
  "source_agent_id": "rov-local-agent-1777881917-63772-5a3b4e",
  "execution_log": {
    "executor": "rov-local-agent-1777881917-63772-5a3b4e",
    "result": {
      "delivered": true,
      "command": { "action": "remove_mine" }
    }
  }
}
```

Control Ship에서 System Agent로 재전달된 데이터:

```json
{
  "message_type": "mission.result",
  "response_id": "59ec169d-93d3-4b19-b1e6-715609a4cf54",
  "alert_id": "alert-5487ea4f-7bcb-4573-8290-3689297938eb",
  "execution_status": "completed",
  "source_agent_id": "control-ship-middle-agent-1777881914-63667-4e04d2",
  "execution_log": {
    "forwarded_by": "control-ship-middle-agent-1777881914-63667-4e04d2",
    "source_agent_id": "rov-local-agent-1777881917-63772-5a3b4e",
    "payload": { "...": "하위 mission.result 원문" }
  }
}
```

## 8. System Agent가 수신 후 response 저장한 결과

- `GET /responses/59ec...` 최종 상태:
  - `status=completed`
- `dispatch_result.delivered=true`
- `dispatch_result.execution_result`에 최신 실행 결과 저장
- `dispatch_result.execution_results`에 실행 주체별 결과 누적
  - `notes=Mission result from control-ship-middle-agent-...`

중복 수신 방지 정책:

- dedup key는 `response_id + step_id + task_id + 실제 실행 주체(source_agent_id)`이다.
- Control Ship이 전달자라면 `execution_log.source_agent_id` 또는 `execution_log.payload.source_agent_id`를 실제 실행 주체로 본다.
- 같은 실행 주체가 같은 `response_id + step_id + task_id`로 다시 보고하면 `duplicate=true`로 응답하고 Response ledger를 덮어쓰지 않는다.
- 서로 다른 실행 주체(AUV, ROV)가 같은 `response_id`로 보고하는 것은 정상 집계 대상이다.
- 같은 실행 주체라도 `step_id` 또는 `task_id`가 다르면 별개의 정상 결과로 집계한다.
- 집계 상태는 하나라도 `failed`면 `failed`, 모든 실행 결과가 성공이면 `completed`로 저장한다.

평가/재계획 기록:

- `dispatch_result.step_evaluations.{step_id}`에 step별 판단 결과가 저장된다.
- `dispatch_result.replan_history`에는 `retry_same_step`, `reassign_failed_tasks`, `manual_intervention_required`, `abort_mission` 등 후속 판단 이력이 저장된다.
- `manual_intervention_required`가 선택되면 Response 상태는 `manual_intervention_required`로 저장되고, `dispatch_result.manual_intervention`에 개입이 필요한 step, 사유, 최신 step 결과가 함께 저장된다.
- 이후 `GET /manual-interventions` 또는 `GET /manual-interventions/{response_id}`로 수동 개입 대상과 권장 운영자 조치를 확인할 수 있다.

동시 incident 처리 규칙:

- System Agent는 lower device를 step/task dispatch 시점에 reservation 한다.
- reservation 중인 device는 다른 incident의 target 후보에서 제외된다.
- task 결과를 받거나 mission이 종료되면 reservation을 해제한다.
- 현재 구현은 preemption을 지원하지 않으므로, 예약 가능한 장비가 없으면 해당 incident 대응은 즉시 실패로 기록될 수 있다.
- 다만 capability는 있으나 장비가 모두 reservation 중이면 대응은 `queued` 상태로 저장될 수 있다.
- queue 재검토 시에는 당시 시점의 alert 유효성과 현재 사용 가능한 device를 다시 확인한다.
- queue 재검토 시 원래 장비가 아니어도 동일 task 수행이 가능한 대체 device가 있으면 그 device로 재계획한다.

실패 시뮬레이션 방법:

- lower task `params`에 `simulate_failure=true`를 넣으면 실패 결과를 강제할 수 있다.
- 더 세밀하게는 `params.simulate_outcome`으로 아래 값을 강제할 수 있다.
  - `status`
  - `usable_output`
  - `failure_reason`
  - `confidence`
  - `artifacts`

## 9. 분석 리포트 생성 가능 여부

- 현재 구현에는 별도 `incident 분석 리포트` 전용 원장/API가 없다.
- 현재 남는 분석 근거:
  - `System state.last_decision`
  - `Alert/Response metadata + dispatch_result.execution_result`
- 권장 보완:
  - `incident_decision_records`(또는 `analysis_reports`) API/ledger 추가
  - `response_id` 기준으로 판단근거/실행결과/최종판정을 단일 문서화

## 현재 없는(또는 약한) 시나리오

- `incident_decision` 장기 조회 API(현재는 state memory 의존)
- 별도 “분석 리포트 생성 완료” 상태 전이
