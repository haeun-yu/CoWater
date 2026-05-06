# CoWater 프로젝트 검토 및 개선 보고서

작성일: 2026-05-07  
작업 범위: Registry Server, Device/System Agent runtime, LLM/Ollama 연동 안전장치, Moth 발행 안정성, 3D Dashboard, 테스트 보강, 장시간 실행 검증

## 프로젝트 이해

CoWater는 해양 무인 장비를 계층형 에이전트로 운영하는 관제/시뮬레이션 시스템이다. Registry Server가 장비 등록, 연결 상태, 이벤트, 알림, 대응, 미션 데이터를 관리하고, Ship/USV 같은 middle layer 장비와 ROV/AUV 같은 lower layer 장비가 A2A command endpoint를 통해 명령을 수행한다. `client/index.html`은 Registry와 Moth WebSocket 스트림을 기반으로 장비, 링크, 상태를 3D 대시보드에 표시한다.

이번 검토에서는 단순 API 단위 동작보다 실제 제품 실행에서 중요한 안정성에 초점을 두었다. 특히 Ollama 비활성/활성 환경, 실제 Moth broker 연결, middle 장비 장애, 장시간 실행 중 로그 폭주, 종료 시 background task 누수, UI 데이터 변환 오류를 중점적으로 확인했다.

## 현재 구조 요약

- `server/registration/src/api.py`: FastAPI 기반 Registry API, Moth WebSocket endpoint, Device/Event/Alert/Response/Mission route.
- `server/registration/src/registry/*`: 장비 등록, parent routing, mission/event/alert persistence 도메인 로직.
- `device/agent/*`: 장비 에이전트 runtime, decision engine, Ollama client, 시뮬레이션 루프.
- `device/transport/moth_publisher.py`: 장비 healthcheck/telemetry를 Moth/MEB WebSocket으로 발행.
- `server/system-agent/*`: fleet/system level 판단과 미션/알림 처리 에이전트.
- `client/index.html`: Three.js 기반 3D 작전 대시보드.
- `tests/`: Registry API 회귀 테스트와 runtime 안정성 테스트.

## 핵심 기능과 주요 사용자 흐름

1. Registry Server가 기동되고 장비와 System Agent가 `/devices`에 등록된다.
2. lower layer 장비는 connected middle layer 장비를 parent로 배정받고, ROV는 parent routing을 강제한다.
3. 각 장비는 A2A command endpoint로 명령을 받고 실행 결과를 반환한다.
4. System Agent는 이벤트를 받아 alert/response/mission 흐름으로 연결한다.
5. Dashboard는 `/devices`, `/alerts`, `/missions/stats`와 Moth 구독 상태를 화면에 표시한다.
6. middle layer 장애 시 lower 장비가 살아 있는 middle parent로 재배정되어 관제 링크가 유지되어야 한다.

## 발견한 주요 문제

1. `GET /missions/stats`가 `/missions/{mission_id}`보다 뒤에 선언되어 stats 요청이 mission detail route로 잡힐 수 있었다.
2. `POST /missions`는 query fallback을 의도했지만 JSON body가 필수라 body 없이 호출하면 동작하지 않았다.
3. `update_main_video_track()` 변경값이 SQLite에 저장되지 않아 서버 재시작 후 사라질 수 있었다.
4. middle layer 장비 삭제 또는 장애 후 lower layer 장비 parent assignment가 충분히 갱신되지 않았다.
5. parent 재계산이 disconnected middle 장비도 후보로 삼아, 장애가 난 Ship으로 lower 장비가 되돌아가는 문제가 있었다.
6. Dashboard가 Registry payload의 `layer`, `parent_id`, `registry_id`, submerged/routing 속성을 충분히 보존하지 않아 링크 계산이 틀어질 수 있었다.
7. 값이 없는 telemetry가 `NaNm`, `NaN%`로 표시될 수 있었다.
8. Ollama가 꺼진 환경에서도 LLM 호출을 반복 시도해 로그와 부하 위험이 있었다.
9. Moth broker 또는 `websockets` 의존성이 없는 환경에서 healthcheck 발행 실패가 과도하게 반복될 수 있었다.
10. device runtime의 background task와 publisher가 shutdown 시 명시적으로 닫히지 않아 장시간 실행/반복 테스트에서 누수 위험이 있었다.
11. local demo 스크립트가 기본적으로 LLM을 켜려 할 수 있어, 사용자가 의도하지 않게 Ollama 부하를 만들 가능성이 있었다.
12. System Agent의 LLM fleet summary가 Registry public id 문자열을 `int()`로 변환하려다 예외가 발생해 live command에서 LLM 판단 없이 fallback될 수 있었다.
13. 실제 Moth broker에 이전 실행 또는 외부 실행의 healthcheck가 남아 있을 때 Registry가 unknown device id를 ERROR로 기록했다.

## 실제 수정한 내용

- `server/registration/src/api.py`
  - `/missions/stats` route를 동적 mission detail route보다 앞에 배치.
  - `MissionCreateRequest`를 body 없이도 사용할 수 있게 변경.

- `server/registration/src/registry/device_registry.py`
  - main video track 변경 시 DB에 즉시 저장.
  - middle 삭제 후 lower assignment 재계산 보강.
  - connected 상태인 middle 장비만 parent 후보로 사용하도록 수정.
  - `COWATER_DEVICE_DB_PATH` 테스트/실행 격리용 환경변수 지원.

- `client/index.html`
  - Registry device 변환 시 `layer`, `parent_id`, `is_submerged`, `force_parent_routing` 보존.
  - link lookup에서 public id와 numeric `registry_id`를 모두 사용.
  - index fallback으로 parent를 추정하던 불안정한 로직 제거.
  - 숫자 필드 표시를 finite number 기준으로 보강해 `NaN` 표시 제거.

- `device/agent/llm_client.py`, `server/system-agent/agent/llm_client.py`
  - `COWATER_LLM_ENABLED` 환경변수로 LLM/Ollama 사용 여부를 명시 제어.
  - Ollama 실패 시 circuit breaker/backoff를 적용해 반복 호출과 로그 폭주 방지.

- `device/agent/decision.py`, `server/system-agent/agent/decision.py`
  - Registry에 보고되는 `llm_enabled`가 실제 환경변수 설정을 반영하도록 수정.
  - System Agent fleet summary가 Registry public id와 numeric `registry_id`를 안전하게 구분하도록 수정해 live LLM command 경로를 복구.

- `device/transport/moth_publisher.py`
  - `COWATER_MOTH_ENABLED`로 Moth 발행을 비활성화할 수 있게 보강.
  - WebSocket connect timeout 추가.
  - 연결/발행 실패 로그를 throttle 처리.
  - publisher `close()`와 종료 상태 플래그 추가.

- `device/agent/runtime.py`
  - background task 추적과 `stop()` 구현.
  - Moth task를 추적 가능한 task로 생성.
  - shutdown 시 Moth publisher를 닫고 task를 cancel/await하도록 수정.

- `device/controller/api.py`, `server/system-agent/controller/api.py`
  - startup simulation task를 app state에 저장.
  - shutdown hook에서 simulation task를 취소하고 runtime 정리를 수행.

- `server/system-agent/agent/runtime.py`
  - identity가 없을 때 System Agent 이름이 매번 instance suffix로 바뀌지 않도록 안정화.
  - Registry upsert 시 실제 LLM 활성 상태를 보고하도록 수정.

- `cowaterctl.sh`
  - 로컬 demo 기본값을 `COWATER_LLM_ENABLED=false`로 설정.
  - Ollama는 사용자가 명시적으로 `COWATER_LLM_ENABLED=true`를 줄 때만 사용하도록 안전 기본값 적용.

- `server/registration/src/registry/healthcheck_monitor.py`
  - Moth broker에서 수신한 unknown/stale device healthcheck를 ERROR가 아니라 debug ignore로 처리.

- `device/requirements.txt`, `server/system-agent/requirements.txt`
  - 실제 Moth/Ollama 실행에 필요한 `websockets`, `httpx` 의존성을 명시.

## 추가하거나 보완한 테스트

새 파일:

- `tests/test_registration_api.py`
- `tests/test_runtime_stability.py`

검증 항목:

- `/missions/stats`가 정상적으로 200 응답을 반환한다.
- `/missions` 생성이 JSON body 없이 query parameter만으로도 동작한다.
- main video track 변경이 SQLite 재로드 후에도 유지된다.
- middle parent 삭제 시 ROV lower 장비가 남은 connected middle parent로 재할당된다.
- `COWATER_LLM_ENABLED=false`에서 device/system decision engine의 LLM이 비활성화된다.
- `COWATER_MOTH_ENABLED=false`에서 Moth publisher가 비활성화되고 발행 호출이 안전하게 무시된다.
- System Agent fleet summary가 Registry public id 문자열을 받아도 예외 없이 parent/child 구조를 만든다.
- Moth broker에서 unknown device healthcheck가 들어와도 Registry가 실패하지 않고 무시한다.

## 실행한 검증 명령과 결과

- `PYTHONPATH=server/registration .venv/bin/python -m pytest -q`
  - 결과: 9 passed.
  - 참고: FastAPI `on_event` deprecation warning 4건 발생. 기능 실패는 아님.

- `.venv/bin/python -m compileall server/registration/src device server/system-agent -q`
  - 결과: 통과.

- 격리 DB 기반 전체 실행:
  - `COWATER_DEVICE_DB_PATH=/tmp/cowater-long-devices.db COWATER_STORAGE=memory COWATER_LLM_ENABLED=false ./cowaterctl.sh start`
  - 추가 middle USV: `COWATER_LLM_ENABLED=false .venv/bin/python device/device_agent.py --type usv --layer middle --port 9124`
  - 정적 UI: `python3 -m http.server 8080`
  - 결과: Registry, System Agent, Ship middle, USV/AUV/ROV lower, 추가 middle USV가 정상 등록.

- 장시간 실행/soak:
  - 약 3분 이상 전체 스택을 실행하며 healthcheck, A2A command, event/report, mission lifecycle, failover, UI 확인을 함께 수행.
  - Ollama는 실행하지 않았고 `llm_enabled=false` 상태가 Registry payload에 반영됨.
  - Moth broker가 없거나 비활성인 경로에서는 경고가 30초 단위로 제한되어 로그 폭주가 발생하지 않음.

- 실제 Ollama LLM 실행:
  - `COWATER_LLM_ENABLED=true`로 전체 스택 실행.
  - Ollama `/api/tags`, `/api/ps` 응답 확인 및 `gemma4:e2b` 모델 로드 확인.
  - standalone System Agent decision 호출이 실제 Ollama 추론으로 56.91초 후 JSON action/reasoning을 반환.
  - live System Agent command endpoint 호출이 실제 Ollama 추론으로 95.82초 후 `command_llm_interpreted` memory와 `llm_reasoning` 포함 결과를 반환.
  - LLM은 AUV 선행 탐색, ROV 제거 계획을 fleet 상태와 배터리 기준으로 선택.

- 실제 Moth broker 실행:
  - `websockets` 설치 후 기본 `wss://cobot.center:8287` 설정으로 전체 스택 실행.
  - Registry Moth subscriber 수신 확인.
  - device healthcheck publish 및 GPS/VIDEO/A2A/BATTERY 등 track publish 연결 성공 확인.
  - 이전 실행에서 온 unknown device healthcheck는 debug ignore로 처리되어 ERROR 로그가 발생하지 않음.

## 브라우저에서 확인한 UI 시나리오

Playwright Chromium으로 `http://127.0.0.1:8080/client/index.html`을 직접 열어 확인했다.

- desktop viewport: 1440x900
- mobile viewport: 390x844
- 확인 결과:
  - Three.js canvas 생성 확인.
  - Registry 연결 상태에서 offline banner 숨김 확인.
  - active devices 4개, links 3개 표시 확인.
  - 비LLM failover 시나리오에서는 Ship middle 장애 후 lower 장비들이 추가 middle USV parent로 재배정된 상태가 UI 데이터에 반영됨.
  - LLM/Moth 활성 최종 실행에서는 active devices 4개, links 3개, LIVE telemetry 표시 확인.
  - `NaN` 텍스트 미표시 확인.
  - 모바일 폭에서 body width가 viewport width와 일치해 큰 가로 깨짐 없음 확인.
  - pageerror 없음.
  - WebGL `GPU stall due to ReadPixels` 경고는 headless Chromium 렌더링 환경 경고로, 앱 런타임 실패는 아니었다.

## 실제 데모/운영 시나리오 확인

- 직접 A2A 명령:
  - ROV `record_video` 명령 완료.
  - AUV `surface` 명령 완료.

- System Agent 이벤트 처리:
  - `mine_detection` event report 전송.
  - critical alert 생성 및 dispatched 상태 확인.
  - response/mission planning 흐름 확인.

- Mission lifecycle:
  - manual event/alert/response 생성.
  - mission 생성, step execution 기록, mission complete 처리.
  - `/missions/stats`에서 completed/pending 집계 확인.

- 장애/failover:
  - Ship middle 프로세스를 종료해 disconnected 상태 유도.
  - USV/AUV/ROV lower 장비가 offline Ship이 아니라 connected 추가 middle USV로 parent 재배정되는지 확인.
  - 재검증 결과 lower 장비 parent가 모두 추가 middle USV로 유지됨.

- LLM 운용 명령:
  - System Agent command endpoint에 기뢰 의심 물체 대응 계획을 live 요청.
  - 실제 Ollama 추론이 95.82초 수행됨.
  - 결과에 `llm_reasoning`이 포함되었고, AUV 정찰 후 ROV 제거 계획을 제안함.

- Moth 실연결:
  - `wss://cobot.center:8287` MEB healthcheck publish 성공.
  - Registry subscriber가 Moth publish 메시지를 수신하고 현재 실행 장비의 healthcheck를 기록함.
  - broker에 남아 있던 unknown device id는 ERROR 없이 무시함.

## 해결하지 못했거나 보류한 문제

- FastAPI `@app.on_event` deprecation warning은 후속으로 lifespan 방식 전환 권장.
- `client/index.html`은 여전히 단일 대형 HTML/JS 파일이라 장기 유지보수 위험이 크다.
- 실제 Moth broker 연결은 확인했지만, broker 자체의 메시지 보존/중복 전달 정책은 외부 시스템 영역이라 장기 관찰이 필요하다.
- 실제 Ollama inference는 확인했지만 추론 시간이 56~96초로 길어, 운영 UI에는 장기 요청 상태 표시와 timeout 정책이 필요하다.
- Playwright UI 검증은 임시 스크립트로 수행했으며, 저장소 내 정식 E2E 테스트로 고정하지는 않았다.

## 다음에 이어서 해야 할 작업

1. FastAPI startup/shutdown을 lifespan으로 전환.
2. Moth broker mock과 실제 broker smoke test를 정식 E2E로 추가.
3. Dashboard JS를 Registry adapter, WebSocket manager, renderer, UI state 모듈로 분리.
4. Playwright 기반 UI smoke/failover test를 정식 테스트로 추가.
5. 장비 장애, Registry 재시작, agent 재연결, 중복 등록 cleanup 시나리오를 자동화.
6. 실제 Ollama 사용 모드의 timeout, 진행 상태 표시, 취소 정책을 운영 절차와 UI에 반영.

## 비개발자용 개선 요약

이번 작업은 CoWater가 실제 데모나 운영 테스트 중 더 안정적으로 버티도록 만드는 개선이다. 장비 연결 관계가 잘못 표시되거나 장애 난 중계 장비로 다시 연결되는 문제를 고쳤고, Ollama가 꺼져 있을 때 불필요한 반복 호출을 막았으며, 켜져 있을 때는 실제 LLM 판단이 live command에 반영되는지 확인했다. Moth는 실제 broker에 연결해 healthcheck와 telemetry publish를 확인했고, 이전 실행의 잔여 메시지가 들어와도 Registry가 흔들리지 않게 했다. 실제로 여러 장비를 띄우고 명령, 이벤트, 미션, 장애 전환, LLM 판단, Moth 연결, 브라우저 UI까지 확인했다.
