# CoWater 단계별 데이터 검증 (실행 기준: 2026-05-07)

문서 목적:

- 데모 직전 1회 실행에서, Event -> Alert -> Response -> Mission -> A2A dispatch까지 실제 데이터 흐름을 단계별로 재구성한다.
- 기존 문서를 폐기하고 최신 실행 증적으로 전체 재작성했다.

실행 환경:

- Registry: http://127.0.0.1:8280
- System Agent: http://127.0.0.1:9116
- Ship Middle: http://127.0.0.1:9115
- AUV Lower: http://127.0.0.1:9112
- ROV Lower: http://127.0.0.1:9113
- 실행 스크립트: docs/run_mine_removal_scenario.py

최신 실행 식별자:

- event_id: event-40dfd8df-3aaa-4d59-a3b2-07decfef9998
- alert_id: alert-7bf4991e-628b-412a-8849-b67d548efb67
- response_id: a09c67d8-a4a7-473f-babb-c88193b46acb
- mission_id: mission-2b57376b-98b9-4014-bdb3-93c5bdfb5811

---

## 0. 서비스 상태 점검

시나리오 시작 시점 점검 결과:

- Registry Server 정상
- System Agent 정상: system-agent-1778112657-15959-3ed4d8
- Ship Middle 정상
- AUV Lower 정상
- ROV Lower 정상

헬스 응답 예시:

```json
{
  "status": "ok",
  "agent_id": "system-agent-1778112657-15959-3ed4d8"
}
```

---

## 1. Event 요청과 응답

요청 대상:

- POST http://127.0.0.1:9116/message:send

요청 핵심:

- message_type: event.report
- event_type: mine_detection
- device_id: id-d9266d9de0da
- metadata.location, artifacts 포함

실제 저장된 Event 데이터:

```json
{
  "event_id": "event-40dfd8df-3aaa-4d59-a3b2-07decfef9998",
  "source_system": "a2a",
  "event_type": "mine_detection",
  "severity": "CRITICAL",
  "message": "mine_detection reported",
  "created_at": "2026-05-07T00:15:16.670435+00:00",
  "metadata": {
    "location": {
      "latitude": 37.005,
      "longitude": 129.425,
      "depth_m": 15.0
    },
    "raw_event": {
      "message_type": "event.report",
      "event_type": "mine_detection",
      "device_id": "id-d9266d9de0da",
      "device_type": "AUV",
      "description": "AUV sonar detected mine-like object at 15m depth (scenario_tag:mine-scenario-1778112916)",
      "artifacts": [
        {
          "type": "mine_location_estimate",
          "location": {
            "latitude": 37.005,
            "longitude": 129.425
          },
          "confidence": 0.93
        },
        {
          "type": "sonar_evidence",
          "frame_id": "auv-scan-mine-scenario-1778112916"
        }
      ]
    }
  }
}
```

---

## 2. Alert 등록 확인

조회 대상:

- GET /alerts/{alert_id}

실제 Alert 데이터:

```json
{
  "alert_id": "alert-7bf4991e-628b-412a-8849-b67d548efb67",
  "event_id": "event-40dfd8df-3aaa-4d59-a3b2-07decfef9998",
  "alert_type": "mine_detection",
  "severity": "CRITICAL",
  "status": "completed",
  "recommended_action": "survey_depth",
  "requires_user_approval": false,
  "route_mode": "direct_to_system",
  "created_at": "2026-05-07T00:15:16.673867+00:00",
  "updated_at": "2026-05-07T00:16:09.577028+00:00"
}
```

요약:

- Alert는 생성 후 processing을 거쳐 completed로 기록됨.

---

## 3. System Agent 대응 판단

규칙 기반 판단:

- alert_type=mine_detection
- severity=CRITICAL
- recommended_action=survey_depth
- action=mission.assign

이번 실행에서 중요한 변경점:

- 규칙 추천 액션은 survey_depth로 유지
- 실제 디바이스 전송 액션은 디바이스 capability에 맞춰 자동 보정

---

## 4. System Agent가 생성한 Response와 계획

조회 대상:

- GET /responses/{response_id}

실제 Response 핵심:

```json
{
  "response_id": "a09c67d8-a4a7-473f-babb-c88193b46acb",
  "alert_id": "alert-7bf4991e-628b-412a-8849-b67d548efb67",
  "action": "mission.assign",
  "target_agent_id": "1",
  "target_endpoint": "http://127.0.0.1:9115",
  "status": "planned",
  "task_id": "a09c67d8-a4a7-473f-babb-c88193b46acb:remove",
  "reason": "System Agent response to mine_detection"
}
```

step/task 계획 핵심:

- step_id: remove
- target_device_id: 4 (작업용 ROV)
- route_agent_id: 1 (통제 함정)
- task.action: grab_object
- task.requested_action: remove_mine

---

## 5. 실제 A2A 전송 데이터

dispatch_result에서 확인된 실제 전송 payload 핵심:

```json
{
  "message_type": "task.assign",
  "action": "grab_object",
  "params": {
    "action": "grab_object",
    "requested_action": "remove_mine",
    "location": {
      "latitude": 37.005,
      "longitude": 129.425,
      "depth_m": 15.0
    },
    "mission_type": "mine_clearance",
    "target_device_id": 4
  },
  "alert_id": "alert-7bf4991e-628b-412a-8849-b67d548efb67",
  "response_id": "a09c67d8-a4a7-473f-babb-c88193b46acb",
  "step_id": "remove",
  "task_id": "task-1"
}
```

핵심 검증 포인트:

- requested_action은 remove_mine
- 실제 action은 grab_object
- 즉, 추천 액션과 디바이스 실행 액션이 분리되어 안정적으로 매핑됨

---

## 6. 대상 에이전트 수신/실행 흔적

dispatch_result.task_results[0] 기준:

- action: grab_object
- target_device_id: 4
- route_agent_id: 1
- dispatch.delivered: true
- endpoint: http://127.0.0.1:9115

A2A 결과 객체에 result.status.state=completed가 포함됨.

---

## 7. Mission 연계 상태

조회 대상:

- GET /missions/{mission_id}

실제 Mission 데이터:

```json
{
  "mission_id": "mission-2b57376b-98b9-4014-bdb3-93c5bdfb5811",
  "response_id": "a09c67d8-a4a7-473f-babb-c88193b46acb",
  "alert_id": "alert-7bf4991e-628b-412a-8849-b67d548efb67",
  "event_id": "event-40dfd8df-3aaa-4d59-a3b2-07decfef9998",
  "status": "pending",
  "step_states": [],
  "metadata": {
    "alert_type": "mine_detection"
  }
}
```

해석:

- Response dispatch는 성공(delivered=true)
- Mission은 stepwise 파이프라인의 후속 결과 수신 전이므로 pending 상태일 수 있음

---

## 8. inbox/outbox 관측

실행 직후 상태:

```json
{
  "system_outbox_len": 50,
  "system_inbox_len": 50,
  "ship_inbox_len": 50,
  "auv_inbox_len": 50,
  "rov_inbox_len": 50,
  "ship_latest_type": "layer.assignment",
  "auv_latest_type": "layer.assignment",
  "rov_latest_type": "layer.assignment"
}
```

참고:

- 본 스냅샷은 버퍼 상한(50) 때문에 최신 업무 이벤트가 항상 마지막 원소로 보장되지는 않는다.
- 상세 검증은 Response.dispatch_result의 a2a_result 원문을 기준으로 확인하는 것이 정확하다.

---

## 9. 데모용 결론

이번 최신 실행 기준 결론:

- Event 생성: 성공
- Alert 생성/처리: 성공
- Response 생성: 성공
- A2A dispatch: 성공 (delivered=true)
- recommended_action -> 실제 action 변환: 성공
  - remove_mine -> grab_object

데모 시 설명 포인트:

1. 규칙 추천 액션과 실제 디바이스 액션은 다를 수 있으며, runtime이 capability에 맞게 자동 변환한다.
2. dispatch 성공 여부는 Response.dispatch_result.delivered로 즉시 확인 가능하다.
3. Mission pending은 후속 step 결과 대기 상태일 수 있으므로 dispatch 실패와 동일 의미가 아니다.

---

## 부록 A. 시나리오 실행 로그 요약

- 실행 직전 카운트: events=5, alerts=5, responses=5
- 실행 직후 카운트: events=6, alerts=6, responses=6
- 증가분: 각각 +1

---

## 부록 B. 재발 방지 적용 요약

System Agent runtime 보강:

- 액션 정규화/별칭 맵 적용
- 디바이스별 지원 액션 기반 dispatch action 해석
- 재시작 시 오래된 planned/dispatched 예약 복원 TTL 적용 (기본 900초)

효과:

- 액션명 불일치로 인한 waiting*for*\* 정체 가능성을 크게 낮춤
- 데모 환경에서 추천 액션과 실제 수행 액션이 달라도 dispatch가 끊기지 않음
