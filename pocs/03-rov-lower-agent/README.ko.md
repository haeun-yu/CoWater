# POC 03 - ROV Lower Agent

## 개요

ROV Lower Agent는 정밀 수중 작업을 수행하는 lower-layer 에이전트다. 기본적으로 parent 기반 라우팅을 따르며, 유선 연결 특성을 가진다.

## 기본 정보

- 포트: `9113`
- Registry 기본 주소: `http://127.0.0.1:8280`
- heartbeat: `1초` 주기
- 주요 heartbeat 필드: `latitude`, `longitude`, `battery_percent`

## 실행

```bash
cd /Users/teamgrit/Documents/CoWater/pocs/03-rov-lower-agent
python3 device_agent.py
```

고정 식별자로 실행:

```bash
COWATER_INSTANCE_ID=rov-001 python3 device_agent.py
```

## 주요 기능

- 정밀 수중 조작과 근접 작업 수행
- 카메라 기반 고해상도 관측
- tether 상태 모니터링
- parent 기반 라우팅 환경에서 heartbeat 및 telemetry 발행

## Capability 기준

스킬:

- `precise_manipulation`
- `high_resolution_inspection`
- `deep_water_operations`
- `tether_management`

도구:

- `high_def_camera`
- `lights`
- `manipulator_arm`
- `tether_monitor`
- `pressure_sensor`
- `safety_validator`

주요 액션:

- `move_forward`
- `move_up`
- `rotate`
- `grab_object`
- `release_object`
- `adjust_lights`
- `record_video`

## 주요 엔드포인트

- `GET /health`
- `GET /state`
- `GET /manifest`
- `POST /message:send`

## 점검 예시

```bash
curl http://127.0.0.1:9113/health | jq .
curl http://127.0.0.1:9113/state | jq '.last_telemetry'
curl http://127.0.0.1:9113/manifest | jq .
```
