# POC 00 - Registry Server

## 개요

Registry Server는 CoWater의 공용 서버 컴포넌트다. 디바이스 등록, healthcheck 반영, assignment 계산, Event / Alert / Insight / Approval / Mission 원장을 담당한다.

## 기본 정보

- 포트: `8280`
- 설정 파일: `config.json`
- healthcheck 기준: `1초 주기`, `3초 timeout`

## 실행

```bash
cd /Users/teamgrit/Documents/CoWater/server/registration
python3 device_registration_server.py
```

상위 기준 문서:

- [SYSTEM_ARCHITECTURE.md](/Users/teamgrit/Documents/CoWater/SYSTEM_ARCHITECTURE.md)
- [START_GUIDE.md](/Users/teamgrit/Documents/CoWater/START_GUIDE.md)

## 주요 API

- `GET /health`
- `GET /devices`
- `POST /devices`
- `PUT /devices/{device_id}/agent`
- `POST /events/ingest`
- `GET /events`
- `POST /alerts/ingest`
- `GET /alerts`
- `GET /device-roles`
- `POST /operation-plans`
- `GET /operation-plans`
- `POST /insights`
- `GET /insights`
- `POST /approvals`
- `GET /approvals`
- `POST /mission-proposals`
- `GET /mission-proposals`
- `POST /missions`
- `GET /missions`

## 점검 예시

```bash
curl http://127.0.0.1:8280/health | jq .
curl http://127.0.0.1:8280/devices | jq .
curl http://127.0.0.1:8280/events | jq .
curl http://127.0.0.1:8280/alerts | jq .
curl http://127.0.0.1:8280/insights | jq .
curl http://127.0.0.1:8280/approvals | jq .
curl http://127.0.0.1:8280/mission-proposals | jq .
curl http://127.0.0.1:8280/missions | jq .
```
