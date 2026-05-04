# POC 05 - Control Ship Middle Agent

## 개요

Control Ship Middle Agent는 현장 지휘를 담당하는 middle-layer 에이전트다. System Agent의 명령을 하위 에이전트로 배분하고, A2A 라우팅과 자식 상태 인지를 담당한다.

## 기본 정보

- 포트: `9115`
- Registry 기본 주소: `http://127.0.0.1:8280`
- heartbeat: `1초` 주기
- 주요 heartbeat 필드: `latitude`, `longitude`, `battery_percent`

## 실행

```bash
cd /Users/teamgrit/Documents/CoWater/pocs/05-control-ship-middle-agent
python3 device_agent.py
```

## 주요 기능

- 현장 지휘와 다중 자식 조율
- ROV tether 및 유선 링크 관리
- 상위 명령의 하위 라우팅
- heartbeat 및 telemetry 발행

## Capability 기준

스킬:

- `surface_navigation`
- `field_command_center`
- `rov_tether_management`
- `wired_communication`
- `multi_mission_coordination`

도구:

- `gps_reader`
- `wired_link_monitor`
- `rov_tether_controller`
- `child_registry`
- `a2a_router`
- `command_executor`
- `video_processor`
- `safety_validator`

주요 액션:

- `route_move`
- `hold_position`
- `manage_tether_length`
- `coordinate_children`
- `manage_rov_power`
- `capture_video`
- `relay_data`

## 주요 엔드포인트

- `GET /health`
- `GET /state`
- `GET /manifest`
- `GET /children`
- `POST /message:send`

## 점검 예시

```bash
curl http://127.0.0.1:9115/health | jq .
curl http://127.0.0.1:9115/state | jq .
curl http://127.0.0.1:9115/children | jq .
```
