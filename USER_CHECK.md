# USER_CHECK

## 문서 간 최종 확인 필요

- `AgentConnection` 기준 필드가 문서마다 다릅니다. `docs/core/schema.md`는 `agent_a_id`, `agent_b_id`, `profile.network_type` 중심이고, `docs/core/agent-connection.md`는 `source_device_id`, `target_device_id`, `primary_medium`, `active_mediums` 중심입니다. 현재 구현은 `schema.md`를 우선해 `agent_a_id`/`agent_b_id` 구조를 기준으로 유지하고, 물리 라우팅 정보는 `profile`에 보관하는 방식으로 진행했습니다.

- Event 타입 표준이 일부 문서와 기존 코드에서 다릅니다. `docs/core/event-types.md`의 `SYS_*`, `DEVICE_HEALTHCHECK`, `ENV_STATE_CHANGED` 대문자 표준을 최종 기준으로 적용했습니다. 기존 `sys.task.result` 같은 dotted 형식은 입력 시 표준 타입으로 변환하는 방식으로 처리했습니다.

- A2A 엔드포인트 표준이 문서마다 다릅니다. `docs/core/a2a-protocol.md`는 `POST /message:send`를 표준으로 정의하고, `docs/TECH_STACK.md`는 `/task`, `/result` 예시를 포함합니다. 현재 구현은 상세 프로토콜 문서인 `a2a-protocol.md`를 우선해 `/message:send`를 기준으로 진행했습니다.

- `docs/core/schema.md`에는 `Alert`, `Improvement`, `RecommendationSuppression` 상세 스키마가 없지만, `docs/scenarios/exceptions.md`와 `docs/scenarios/reporting.md`에는 해당 구조가 나옵니다. 현재 구현은 기존 `Alert` 저장소를 유지하고, `Improvement`와 `RecommendationSuppression`은 별도 엔티티로 확장하지 않았습니다.

- `docs/scenarios/operation.md`의 재시도 예시는 `source_mission_id`, `retry_count`, `retry_strategy`를 사용하지만 `docs/core/schema.md`의 `Mission` 스키마에는 없습니다. 현재 구현은 `schema.md`를 우선해 Mission 기본 스키마에는 추가하지 않았고, 필요하면 `metadata`에 보관하는 방향을 추천합니다.

- Device 타입 표준은 `docs/core/schema.md`에서 `USV | AUV | ROV | OTHER`로 정의되어 있지만, 실행 설정에는 `CONTROL_SHIP`과 `SYSTEM`이 남아 있습니다. 현재 API 응답의 문서 스키마 필드 `type`은 비표준 타입을 `OTHER`로 노출하고, 기존 실행용 `device_type`은 보조 필드로 유지했습니다.
