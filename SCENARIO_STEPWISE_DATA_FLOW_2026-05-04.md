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

## 4. System Agent가 보낸 명령과 대상

- Response 조회: `GET /responses/59ec169d-93d3-4b19-b1e6-715609a4cf54`
- 확인값:
  - `action=task.assign`
  - `target_agent_id=195` (Control Ship Middle Agent)
  - `dispatch_result.endpoint=http://127.0.0.1:9115`
  - `dispatch_result.delivered=true`

## 5. 대상(Control Ship/Lower)의 대응 판단 로그

- Control Ship의 `tasks`에서 `id=59ec...` 확인:
  - lower에서 올라온 `mission.result`를 수신
  - `source_agent_id`가 AUV/ROV로 기록됨
- Lower의 `tasks`에서 `id=59ec...` 확인:
  - AUV: `action=survey_depth`
  - ROV: `action=remove_mine`

주의:
- 현재 `state.memory`는 `layer.assignment` 갱신 로그가 많아 `incident_decision`이 빨리 밀릴 수 있다.
- 코드상 `incident_decision` 기록은 이미 추가되어 있으나, 장기 보존은 별도 원장화가 필요하다.

## 6. 대상이 실제로 어떻게 대응했는지

- AUV task artifacts:
  - `delivered=true`
  - 명령 파라미터(`location`, `mission_type`, `report_to_endpoint`) 포함
- ROV task artifacts:
  - `delivered=true`
  - `remove_mine` 수행 명령 포함

## 7. 대응 후 System Agent로 재전달 확인

- Control Ship `tasks`의 `id=59ec...` 메시지:
  - `message_type=mission.result`
  - `response_id=59ec...`
  - `alert_id=alert-5487...`
  - `execution_status=completed`
  - `execution_log`에 하위 실행 결과 포함

## 8. System Agent가 수신 후 response 저장한 결과

- `GET /responses/59ec...` 최종 상태:
  - `status=completed`
  - `dispatch_result.delivered=true`
  - `dispatch_result.execution_result`에 Control Ship 경유 결과 저장
  - `notes=Mission result from control-ship-middle-agent-...`

## 9. 분석 리포트 생성 가능 여부

- 현재 구현에는 별도 `incident 분석 리포트` 전용 원장/API가 없다.
- 현재 남는 분석 근거:
  - `System state.last_decision`
  - `Alert/Response metadata + dispatch_result.execution_result`
- 권장 보완:
  - `incident_decision_records`(또는 `analysis_reports`) API/ledger 추가
  - `response_id` 기준으로 판단근거/실행결과/최종판정을 단일 문서화

## 현재 없는(또는 약한) 시나리오

- `mission.result` 중복 수신 방지(동일 `response_id` de-dup) 정책
- 하위 성공/실패를 모두 집계한 최종 판정 규칙
- `incident_decision` 장기 조회 API(현재는 state memory 의존)
- 별도 “분석 리포트 생성 완료” 상태 전이
