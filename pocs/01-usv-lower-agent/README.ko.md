# POC 01 - USV Lower Agent

## 개요

USV Lower Agent는 수상 임무를 수행하는 lower-layer 에이전트다. telemetry와 heartbeat를 발행하고, 상위에서 내려온 task를 수행한다.

## 기본 정보

- 포트: `9111`
- Registry 기본 주소: `http://127.0.0.1:8280`
- heartbeat: `1초` 주기
- 주요 heartbeat 필드: `latitude`, `longitude`, `battery_percent`

## 실행

```bash
cd /Users/teamgrit/Documents/CoWater/pocs/01-usv-lower-agent
python3 device_agent.py
```

같은 에이전트를 다시 식별하고 싶으면:

```bash
COWATER_INSTANCE_ID=usv-001 python3 device_agent.py
```

## 주요 기능

- 수상 이동과 경로 추종 수행
- GPS, IMU, 배터리 상태 기반 로컬 상태 판단
- 장애물 감지와 안전 제약 적용
- heartbeat 및 telemetry 발행

## Capability 기준

스킬:

- `surface_navigation`
- `route_following`
- `target_tracking`
- `local_safety_judgement`
- `battery_management`

도구:

- `gps_reader`
- `imu_reader`
- `battery_monitor`
- `motor_control`
- `route_planner`
- `obstacle_detector`
- `safety_validator`

주요 액션:

- `route_move`
- `hold_position`
- `return_to_base`
- `slow_down`
- `follow_target`
- `abort_mission`
- `emergency_stop`

## 주요 엔드포인트

- `GET /health`
- `GET /state`
- `GET /manifest`
- `POST /message:send`

## 점검 예시

```bash
curl http://127.0.0.1:9111/health | jq .
curl http://127.0.0.1:9111/state | jq '.last_telemetry | {latitude, longitude, battery_percent}'
curl http://127.0.0.1:9111/manifest | jq .
```
