# 06 Control Center System Agent

이 POC는 A2A 위계에서 최상위 `control_center` 계층을 모델링합니다.

## 하는 일

- 표준 `POST /message:send` 바인딩으로 HTTP 기반 A2A 메시지를 받습니다.
- `/.well-known/agent-card.json`에 Agent Card를 제공합니다.
- 미션과 하위 Agent 등록을 관리합니다.
- inbox, outbox, dispatches, memory를 저장합니다.
- 직접 라우팅이 허용되면 하위 Agent로 바로 디스패치할 수 있습니다.

## 실행

```bash
cd pocs/06-control-center-system-agent
pip install -r requirements.txt
python3 device_agent_server.py
```

## 주요 엔드포인트

- `GET /.well-known/agent-card.json`
- `GET /meta`
- `GET /state`
- `GET /children`
- `GET /missions`
- `POST /children/register`
- `POST /message:send`
- `GET /tasks`
- `GET /tasks/{task_id}`
- `POST /tasks/{task_id}:cancel`
- `POST /missions`
- `POST /missions/{mission_id}/assign`
- `POST /a2a/inbox`
- `POST /dispatch`

## A2A 흐름

- `control_center -> control_ship`: `task.assign`
- `control_center -> device agents`: 직접 디스패치 가능
- `control_ship -> control_center`: `status.report`
