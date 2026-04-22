# PoC 05: Detection Agents

## 목표

Telemetry/Sensor stream을 도메인 탐지 이벤트로 변환합니다.

## 범위

포함:

- Sonar contact 기반 기뢰 탐지
- 네트워크 성능 저하 탐지 후보
- 위치/상태 기반 간단 anomaly 탐지 후보
- Agent-local cooldown/dedup 개념

제외:

- LLM 분석
- Alert 생성
- UI

## 입력

```text
telemetry.*
sensor.*
```

## 출력

```text
detect.mine.{deviceId}
detect.network.{deviceId}
detect.anomaly.{deviceId}
```

## 성공 기준

- Agent는 필요한 stream만 구독합니다.
- Detection event는 필요한 경우 `flow_id`, `causation_id`를 포함합니다.
- 중복 탐지는 설정 가능한 cooldown window 안에서 억제됩니다.

## 실행

```bash
cd pocs/05-detection-agents
python3 src/detect.py --input sample-events/sonar-contact.json --threshold 0.4 --format table
```

출력은 `detect.mine.{deviceId}` 도메인 이벤트입니다.
JSONL이 필요하면 `--format jsonl`을 사용합니다.
