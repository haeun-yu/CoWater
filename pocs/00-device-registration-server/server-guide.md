# Registry Server 사용 가이드

이 문서는 `POC 00` Registry Server의 현재 구현 기준 역할과 API를 정리한다.

## 역할

Registry Server는 다음을 담당한다.

- 디바이스 등록과 조회
- heartbeat 기반 연결 상태 갱신
- 위치 정보와 assignment 정보 보관
- `parent_id`, `route_mode`, `force_parent_routing` 계산
- Event / Alert / Response 원장 제공

Registry Server는 에이전트가 아니라 공용 서버 컴포넌트다.

## 실행

```bash
cd pocs/00-device-registration-server
python3 device_registration_server.py
```

기본 포트는 `8280`이다.

상태 확인:

```bash
curl http://127.0.0.1:8280/health | jq .
```

## 주요 API

### 디바이스

- `GET /devices`
- `GET /devices/{device_id}`
- `POST /devices`
- `PUT /devices/{device_id}/agent`
- `DELETE /devices/{device_id}/agent`

등록 예시:

```bash
curl -X POST http://127.0.0.1:8280/devices \
  -H "Content-Type: application/json" \
  -d '{
    "secretKey": "server-secret",
    "name": "AUV-01",
    "device_type": "AUV",
    "layer": "lower",
    "location": {
      "latitude": 37.003,
      "longitude": 129.425,
      "altitude": -25
    }
  }'
```

에이전트 endpoint 등록 예시:

```bash
curl -X PUT http://127.0.0.1:8280/devices/1/agent \
  -H "Content-Type: application/json" \
  -d '{
    "secretKey": "server-secret",
    "endpoint": "http://127.0.0.1:9112",
    "commandEndpoint": "http://127.0.0.1:9112/command",
    "connected": true
  }'
```

### Event 원장

- `POST /events/ingest`
- `GET /events`
- `GET /events/{event_id}`

예시:

```bash
curl -X POST http://127.0.0.1:8280/events/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "mine_detection",
    "severity": "CRITICAL",
    "message": "기뢰 탐지",
    "source_system": "demo",
    "source_agent_id": "auv-001",
    "source_role": "auv"
  }'
```

### Alert 원장

- `POST /alerts/ingest`
- `GET /alerts`
- `GET /alerts/{alert_id}`
- `POST /alerts/{alert_id}/ack`

severity는 `CRITICAL`, `WARNING`, `INFORMATION`만 사용한다.

### Response 원장

- `POST /responses/ingest`
- `GET /responses`
- `GET /responses/{response_id}`

## heartbeat와 assignment

- Registry는 `device.heartbeat`를 구독해 연결 상태를 갱신한다.
- 기본 heartbeat 기준은 `1초 주기`, `3초 timeout`이다.
- middle agent가 offline이면 Registry가 자식 재할당 또는 직접 라우팅 전환을 계산한다.

## 점검 포인트

디바이스 확인:

```bash
curl http://127.0.0.1:8280/devices | jq .
```

Event 확인:

```bash
curl http://127.0.0.1:8280/events | jq .
```

Alert 확인:

```bash
curl http://127.0.0.1:8280/alerts | jq .
```

Response 확인:

```bash
curl http://127.0.0.1:8280/responses | jq .
```
