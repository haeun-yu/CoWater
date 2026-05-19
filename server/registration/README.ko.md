# POC 00 - Registry 서버

## 개요

Registry 서버는 CoWater의 공용 서버 컴포넌트다. 디바이스 등록, healthcheck 반영, assignment 계산, Event / Alert / Insight / Approval / Mission 원장을 담당한다.

## 기본 정보

- 포트: `8280`
- 설정 파일: `config.json`
- healthcheck 기준: `1초 주기`, `3초 timeout`
- API 문서: [../API_REFERENCE.ko.md](../API_REFERENCE.ko.md)

## 실행

```bash
cd /Users/teamgrit/Documents/CoWater/server/registration
python3 device_registration_server.py
```

상위 기준 문서:

- [../ARCHITECTURE.ko.md](../ARCHITECTURE.ko.md)
- [../API_REFERENCE.ko.md](../API_REFERENCE.ko.md)

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
