# CoWater Server API Reference

이 문서는 `registration` 서버와 `system-agent` 서버의 HTTP API를 한 곳에 정리한 참조 문서입니다.

## 공통 규칙

- JSON 요청/응답을 기본으로 합니다.
- 내부 전용 엔드포인트는 `X-CoWater-Internal: system-agent` 헤더가 필요합니다.
- `registration`은 저장 원장(source of truth) 역할을 합니다.
- `system-agent`는 AI Agent의 판단과 오케스트레이션 역할을 맡습니다.

## Registration Server

Base URL: `http://127.0.0.1:8280`

### 상태

- `GET /health`
- `GET /meta`

### 디바이스

- `POST /devices`
- `GET /devices`
- `GET /devices/{device_id}`
- `PATCH /devices/{device_id}`
- `DELETE /devices/{device_id}`
- `GET /devices/{device_id}/assignment`
- `PUT /devices/{device_id}/agent`
- `DELETE /devices/{device_id}/agent`
- `PUT /devices/{device_id}/connectivity`
- `POST /devices/{device_id}/location`
- `PATCH /devices/{device_id}/metadata`
- `PATCH /devices/{device_id}/auv-submersion`
- `PATCH /devices/{device_id}/connectivity-state`
- `PUT /devices/{device_id}/role`

### Alerts / Events / A2A Logs

- `POST /alerts/ingest`
- `GET /alerts`
- `GET /alerts/{alert_id}`
- `POST /alerts/{alert_id}/ack`
- `POST /events/ingest`
- `GET /events`
- `GET /events/{event_id}`
- `POST /a2a-logs/ingest`
- `GET /a2a-logs`

### Policies

- `POST /policies`
- `GET /policies`
- `GET /policies/{policy_id}`
- `PUT /policies/{policy_id}`
- `DELETE /policies/{policy_id}`

### 운영 원장

- `POST /insights`
- `GET /insights`
- `GET /insights/{insight_id}`
- `POST /approvals`
- `GET /approvals`
- `GET /approvals/{approval_id}`
- `POST /approvals/{approval_id}/decision`
- `POST /mission-proposals`
- `GET /mission-proposals`
- `GET /mission-proposals/{proposal_id}`
- `POST /missions`
- `GET /missions`
- `GET /missions/status/{status}`
- `GET /missions/stats`
- `GET /missions/{mission_id}`
- `PUT /missions/{mission_id}`
- `GET /missions/{mission_id}/timeline`
- `POST /missions/{mission_id}/timeline/append`

### 운영 관리

- `POST /admin/reset`
- `WebSocket /ws/missions`
- `WebSocket /ws/dashboard`

### 주의 사항

- `/policies`, `/a2a-logs/ingest`는 내부 전용입니다.
- `device_id`는 내부 숫자 ID와 public ID가 함께 쓰일 수 있으니 호출 전에 응답 포맷을 확인하는 것이 좋습니다.

## System-Agent Server

Base URL: `http://127.0.0.1:9116`

### 상태

- `GET /health`
- `GET /meta`
- `GET /state`
- `GET /manifest`

### Agent Card / A2A

- `GET /.well-known/agent-card.json`
- `GET /.well-known/agent.json`
- `POST /`
- `POST /message:send`
- `POST /agents/{token}/command`

### 계층 연동

- `POST /children/register`
- `GET /children`
- `POST /children/healthcheck`
- `POST /device-recovery`

### 판단 / 오케스트레이션

- `GET /tasks`
- `GET /manual-interventions`
- `GET /manual-interventions/{mission_id}`
- `POST /execute`
- `POST /mission-proposals/generate`
- `POST /approvals/{approval_id}/decision`
- `GET /overview`

### 동작 메모

- `/execute`는 역할별 System Agent 내부 실행 API입니다.
- `/device-recovery`는 복구 보고를 받아 Agent 내부 상태를 갱신합니다.
- `children`, `tasks`, `inbox`, `outbox`는 실행 중 상태로 다뤄집니다.
