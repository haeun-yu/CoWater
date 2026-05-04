# POC 04 - USV Middle Agent

## 개요

USV Middle Agent는 현장 중간 계층 에이전트다. lower agent 상태를 모니터링하고, 필요한 경우 상위 명령을 하위로 라우팅한다.

## 기본 정보

- 포트: `9114`
- Registry 기본 주소: `http://127.0.0.1:8280`
- heartbeat: `1초` 주기
- 주요 heartbeat 필드: `latitude`, `longitude`, `battery_percent`

## 실행

```bash
cd /Users/teamgrit/Documents/CoWater/pocs/04-usv-middle-agent
python3 device_agent.py
```

## 주요 기능

- lower agent 상태 인지와 현장 조율
- 음향/저대역 통신 릴레이
- 상위 명령의 하위 라우팅
- heartbeat 및 telemetry 발행

## Capability 기준

스킬:

- `surface_navigation`
- `field_coordination`
- `acoustic_relay`
- `mission_redistribution`
- `child_monitoring`
- `battery_management`

도구:

- `gps_reader`
- `battery_monitor`
- `motor_control`
- `child_registry`
- `acoustic_relay`
- `a2a_router`
- `route_planner`
- `command_executor`
- `safety_validator`

주요 액션:

- `route_move`
- `hold_position`
- `return_to_base`
- `coordinate_children`
- `relay_acoustic_data`
- `redistribute_mission`
- `monitor_children_health`

## 주요 엔드포인트

- `GET /health`
- `GET /state`
- `GET /manifest`
- `GET /children`
- `POST /message:send`

## 점검 예시

```bash
curl http://127.0.0.1:9114/health | jq .
curl http://127.0.0.1:9114/state | jq '.last_telemetry | {latitude, longitude, battery_percent}'
curl http://127.0.0.1:9114/children | jq .
```
