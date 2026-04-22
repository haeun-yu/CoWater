# PoC 03: Event Bus Contract

## 목표

장기 transport를 선택하기 전에 subject naming, QoS 정책, latest/durable 동작을 검증합니다.

## 범위

포함:

- Subject taxonomy
- Stream policy 파일
- Redis/NATS 후보 구현을 검토할 수 있는 contract
- Contract 테스트용 replay

제외:

- 디바이스 프로토콜 파싱
- UI
- 장기 저장소

## 성공 기준

- `telemetry.*`, `sensor.*` stream이 `detect.*` event와 섞이지 않습니다.
- `latest` stream은 device별 최신값으로 대체될 수 있습니다.
- `durable` event는 재생 가능해야 합니다.
- consumer는 필요한 subject만 구독합니다.

## 실행

PoC 01에서 stream fixture를 생성하고 contract bus로 재생합니다.

```bash
python3 ../01-device-streams/src/simulator.py --ticks 3 --output out/device-streams.jsonl
python3 src/bus_contract.py --input out/device-streams.jsonl --format table
```

예상 동작:

- `telemetry.position`은 `latest_keys`에 나타납니다.
- `telemetry.status`, `telemetry.network`, `telemetry.task`, `sensor.sonar`는 non-durable traffic으로 집계됩니다.

Docker로 실행하면 stream policy table이 logs에 출력됩니다.
