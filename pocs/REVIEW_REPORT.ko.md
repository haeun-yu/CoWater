# pocs 전체 시스템 리뷰 및 수정 보고서

작성일: 2026-04-29

## 검토 범위

- `pocs/00-device-registration-server`
- `pocs/01-usv-lower-agent`
- `pocs/02-auv-lower-agent`
- `pocs/03-rov-lower-agent`
- `pocs/04-usv-middle-agent`
- `pocs/05-control-ship-middle-agent`
- `pocs/06-system-supervisor-agent`
- `pocs/shared`, `pocs/docs`

## 주요 발견 및 수정

### 1. Moth track endpoint 충돌 수정

문제:

- 등록 서버의 `build_track_endpoint()`가 모든 장치와 트랙에 동일한 `/pang/ws/meb?name=health_check&track=base`를 반환했습니다.
- 이 상태에서는 여러 장치/센서가 같은 Moth track으로 발행되어 telemetry 분리와 추적이 불가능합니다.

수정:

- endpoint를 `device-{id}`와 track name 기반으로 생성하도록 변경했습니다.
- 예: `/pang/ws/meb?channel=instant&name=device-3&source=base&track=main_camera`

### 2. AUV 수중/수면 라우팅 정합성 수정

문제:

- 문서상 AUV는 수중일 때만 middle parent를 통해 음향통신해야 하지만, 서버 parent assignment는 AUV 수면/수중 상태를 충분히 반영하지 않았습니다.

수정:

- 등록 위치의 `altitude < 0`이면 AUV를 submerged 상태로 초기화합니다.
- AUV가 수중이면 nearest middle parent를 배정합니다.
- AUV가 수면으로 전환되면 parent를 해제하고 `direct_to_system` 경로로 전환합니다.

### 3. ROV 유선 강제 라우팅 보강

문제:

- ROV는 문서상 반드시 middle layer를 통해 통신해야 하지만, parent가 없을 때 direct route처럼 보일 수 있었습니다.

수정:

- ROV는 기본적으로 `force_parent_routing=True`가 되도록 했습니다.
- parent가 없으면 assignment의 `route_mode`를 `parent_required_unassigned`로 명확히 표시합니다.
- parent가 있으면 `via_parent`로 확인됩니다.

### 4. 위치 변경 시 동적 parent 재계산

문제:

- 위치 업데이트 API가 latitude/longitude만 갱신하고 parent assignment를 다시 계산하지 않았습니다.

수정:

- lower device 위치 변경 시 해당 device의 parent assignment를 재계산합니다.
- middle device 위치 변경 시 lower device들의 assignment를 다시 계산합니다.

### 5. 연결 상태 전이 오류 수정

문제:

- `connected=False`로 agent 정보를 업데이트해도 `connected_at`이 채워질 수 있었습니다.

수정:

- 실제 연결 상태가 `True`일 때만 최초 `connected_at`을 기록하도록 변경했습니다.

### 6. Heartbeat 상태 저장 보강

문제:

- heartbeat monitor가 offline 전환과 location update를 메모리에만 반영할 수 있었습니다.

수정:

- 상태 변경 및 위치 갱신 시 SQLite 저장소에도 반영하도록 보강했습니다.
- `datetime.utcnow()` 대신 timezone-aware UTC timestamp를 사용하도록 정리했습니다.

### 7. 기뢰 제거 시나리오 스모크 테스트 추가

추가:

- `pocs/docs/run_mine_removal_scenario.py`

검증 항목:

- AUV가 수중 상태에서 middle parent를 통해 라우팅되는지
- ROV가 유선 강제 parent 라우팅을 사용하는지
- Moth track endpoint가 장치/트랙별로 고유한지
- 기뢰 제거 단계가 순서대로 구성되는지

실행:

```bash
python pocs/docs/run_mine_removal_scenario.py --format timeline
```

### 8. 문서 정합성 수정

문제:

- `MINE_REMOVAL_GUIDE.md`에 현재 코드와 맞지 않는 실행 명령이 있었습니다.
- 존재하지 않는 `src.main`, 잘못된 `/agents/{token}/message:send` 경로, 과도한 “완성” 표현이 있었습니다.

수정:

- 실제 entrypoint인 `device_agent.py`, `system_agent.py`, `device_registration_server.py` 기준으로 명령을 수정했습니다.
- A2A endpoint를 실제 구현인 `/message:send` 기준으로 수정했습니다.
- 외부 Moth/Ollama/장시간 운영 검증은 별도 필요하다고 명시했습니다.

## 추가 테스트

추가 파일:

- `tests/test_pocs_registry_routing.py`
- `tests/__init__.py`

테스트 항목:

- track endpoint가 device/track별로 고유함
- AUV가 수중일 때 parent를 경유하고 수면일 때 direct로 전환됨
- ROV가 middle parent를 강제하며 disconnected attach 시 `connected_at`이 설정되지 않음

## 실행 검증 결과

성공:

```bash
python3 -m compileall -q pocs tests
/tmp/cowater-pocs-v2-venv/bin/python -m unittest discover -v
/tmp/cowater-pocs-v2-venv/bin/python pocs/docs/run_mine_removal_scenario.py --format timeline
```

API smoke test:

- POC 00: `/health`, `/meta`, `/devices`, `/alerts`, `/responses` 모두 200
- POC 01-06: `/health`, `/meta`, `/state`, `/manifest`, `/.well-known/agent-card.json`, `/tasks` 모두 200

제약:

- 시스템 Python에는 `pytest`가 설치되어 있지 않아 `python3 -m pytest -q`는 실행하지 못했습니다.
- 실제 Moth 서버, Ollama LLM, 장시간 WebSocket 연결, 실제 다중 프로세스 운영은 이번 검증 범위 밖입니다.
- 기뢰 제거 시나리오는 외부 서버 없는 로컬 smoke test로 검증했습니다.
