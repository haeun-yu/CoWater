# 05 Regional Orchestrator Agent

이 POC는 A2A 위계에서 `regional_orchestrator` 계층을 모델링합니다.

## 하는 일

- 표준 `POST /message:send` 바인딩으로 HTTP 기반 A2A 메시지를 받습니다.
- `/.well-known/agent-card.json`에 Agent Card를 제공합니다.
- 하위 Agent를 등록하고 디스패치 계획을 관리합니다.
- 상태를 상위 `control_center`로 보고합니다.
- inbox, outbox, dispatches, memory를 저장합니다.

## 실행

```bash
cd pocs/05-control-ship-agent
pip install -r requirements.txt
python3 device_agent_server.py
```

## 주요 엔드포인트

- `GET /.well-known/agent-card.json`
- `GET /manifest`
- `GET /meta`
- `GET /state`
- `GET /children`
- `POST /agents/register`
- `POST /children/register`
- `POST /message:send`
- `GET /tasks`
- `GET /tasks/{task_id}`
- `POST /tasks/{task_id}:cancel`
- `POST /a2a/inbox`
- `POST /dispatch`

## A2A 흐름

- `system_center -> regional_orchestrator`: `task.assign`
- `regional_orchestrator -> system_center`: `task.accept` / `status.report`
- `regional_orchestrator -> device agents`: 하위 디스패치 기록
