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
- `mine_detection`처럼 여러 장비가 필요한 경우에는 하나의 `mission_plan` 안에 순차 step을 만들고 앞 step 결과를 다음 step 입력으로 넘긴다.

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
  - `action=task.assign`
  - `target_agent_id=195` (Control Ship Middle Agent)
  - `dispatch_result.endpoint=http://127.0.0.1:9115`
  - `dispatch_result.delivered=true`

Response 원장에 저장되는 계획 데이터 예시:

```json
{
  "action": "mission.assign",
  "params": {
    "location": { "lat": 37.003, "lon": 129.425 },
    "mission_plan": [
      {
        "step_id": "survey",
        "action": "survey_depth",
        "target_device_id": 196
      },
      {
        "step_id": "remove",
        "action": "remove_mine",
        "target_device_id": 197,
        "depends_on": "survey"
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
- `step_id`를 함께 전달해 순차 미션의 각 단계를 구분한다.
- 앞 step 결과가 있으면 다음 step `params.previous_step_result`로 넘긴다.
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
    "command": { "action": "survey_depth" }
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
    "command": { "action": "remove_mine" }
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

- dedup key는 `response_id + step_id + 실제 실행 주체(source_agent_id)`이다.
- Control Ship이 전달자라면 `execution_log.source_agent_id` 또는 `execution_log.payload.source_agent_id`를 실제 실행 주체로 본다.
- 같은 실행 주체가 같은 `response_id + step_id`로 다시 보고하면 `duplicate=true`로 응답하고 Response ledger를 덮어쓰지 않는다.
- 서로 다른 실행 주체(AUV, ROV)가 같은 `response_id`로 보고하는 것은 정상 집계 대상이다.
- 같은 실행 주체라도 `step_id`가 다르면 별개의 정상 결과로 집계한다.
- 집계 상태는 하나라도 `failed`면 `failed`, 모든 실행 결과가 성공이면 `completed`로 저장한다.

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
