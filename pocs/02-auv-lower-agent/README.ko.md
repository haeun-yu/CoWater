# POC 02 - AUV Lower Agent

## 개요

AUV Lower Agent는 수중 탐사와 sonar 기반 탐지를 수행하는 lower-layer 에이전트다. Event를 상위로 보고할 수 있으며, heartbeat와 telemetry를 발행한다.

## 기본 정보

- 포트: `9112`
- Registry 기본 주소: `http://127.0.0.1:8280`
- heartbeat: `1초` 주기
- 주요 heartbeat 필드: `latitude`, `longitude`, `battery_percent`

## 실행

```bash
cd /Users/teamgrit/Documents/CoWater/pocs/02-auv-lower-agent
python3 device_agent.py
```

고정 식별자로 실행:

```bash
COWATER_INSTANCE_ID=auv-001 python3 device_agent.py
```

## 주요 기능

- 수중 이동과 심도 제어 수행
- sonar 기반 수중 탐색과 스캔 수행
- 음향 통신 기반 상태 보고
- heartbeat 및 telemetry 발행

## Capability 기준

스킬:

- `underwater_navigation`
- `depth_control`
- `sonar_scanning`
- `acoustic_communication`
- `mission_execution`

도구:

- `depth_sensor`
- `pressure_monitor`
- `acoustic_modem`
- `sonar_scanner`
- `battery_monitor`
- `thruster_control`
- `safety_validator`

주요 액션:

- `dive_to_depth`
- `hold_depth`
- `surface`
- `follow_route`
- `scan_area`
- `abort_mission`
- `emergency_ascent`

## 주요 엔드포인트

- `GET /health`
- `GET /state`
- `GET /manifest`
- `POST /message:send`

## 점검 예시

```bash
curl http://127.0.0.1:9112/health | jq .
curl http://127.0.0.1:9112/state | jq '.last_telemetry | {depth, latitude, longitude, battery_percent}'
curl http://127.0.0.1:9112/manifest | jq .
```
