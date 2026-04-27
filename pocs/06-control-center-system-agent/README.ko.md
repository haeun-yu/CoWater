# 06 System Center Agent

이 POC는 플릿을 감시하고 문제를 분석하며 대응을 조정하는 시스템 단 `system_center` 계층을 모델링합니다.

## 하는 일

- 표준 `POST /message:send` 바인딩으로 HTTP 기반 A2A 메시지를 받습니다.
- `POST /events/ingest`로 시스템 이벤트를 직접 받을 수 있습니다.
- `/.well-known/agent-card.json`에 Agent Card를 제공합니다.
- 03 디바이스 등록 서버에서 하위 Agent manifest를 동기화합니다.
- 이벤트를 분석해 알림을 만들고 대응 상태를 추적합니다.
- 경로가 허용되면 `regional_orchestrator`를 거치지 않고 디바이스의 command endpoint로 직접 보낼 수 있습니다.
- inbox, outbox, dispatches, events, memory를 로컬에 저장하고, alerts/responses는 03 레지스트리에 canonical record로 게시합니다.

## 구조

```text
src/
├─ app.py
├─ core/
│  ├─ analysis.py
│  ├─ alerts.py
│  ├─ config.py
│  ├─ responses.py
│  ├─ routing.py
│  ├─ state.py
│  └─ models.py
├─ events/
│  ├─ ingest.py
│  └─ models.py
├─ registry/
│  ├─ child_registry.py
│  └─ manifest.py
├─ transport/
│  ├─ a2a.py
│  └─ http.py
└─ __init__.py
```

`app.py`는 FastAPI 라우팅을 담당하고, `core/`는 분석/상태/라우팅 헬퍼를, `events/`는 이벤트 입력과 ingest 로직을, `registry/`는 manifest와 child registry 헬퍼를, `transport/`는 재사용 가능한 HTTP 전송 헬퍼를 담습니다.

## UI 페이지

- `ui/index.html`: 대시보드
- `ui/events.html`: 이벤트 수집과 이벤트/inbox/outbox 화면
- `ui/alerts.html`: 알림 원장과 승인 화면
- `ui/responses.html`: 대응 원장과 디스패치 기록 화면

## 실행

```bash
cd pocs/06-control-center-system-agent
pip install -r requirements.txt
python3 device_agent_server.py
```

## 주요 엔드포인트

- `GET /.well-known/agent-card.json`
- `GET /manifest`
- `GET /meta`
- `GET /state`
- `GET /registry`
- `GET /children`
- `GET /missions`
- `POST /agents/register`
- `POST /children/register`
- `POST /message:send`
- `POST /events/ingest`
- `POST /events/ingest/a2a`
- `GET /events`
- `GET /alerts`
- `GET /responses`
- `POST /registry/sync`
- `GET /tasks`
- `GET /tasks/{task_id}`
- `POST /tasks/{task_id}:cancel`
- `POST /missions`
- `POST /missions/{mission_id}/assign`
- `POST /a2a/inbox`
- `POST /dispatch`
- `POST /alerts/{alert_id}/ack`

## A2A 흐름

- `system event -> analysis -> alert -> response`
- `system_center -> regional_orchestrator`: `task.assign`
- `system_center -> device agents`: 직접 command 디스패치 가능
- `regional_orchestrator -> system_center`: `status.report`
