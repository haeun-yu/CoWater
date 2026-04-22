# PoC 02: Bridge Normalizer

## 목표

원시 프로토콜 payload를 공유 `DeviceStreamMessage` 계약으로 변환합니다.

## 범위

포함:

- NMEA, MAVLink, ROS JSON, custom JSON을 위한 adapter 경계
- 원시 입력 fixture
- 정규화된 stream 출력 fixture

제외:

- 실제 디바이스 연결
- 이벤트 버스 전송
- Detection Agent
- UI

## 입력

```text
raw protocol payload
```

## 출력

```text
DeviceStreamMessage JSON
```

## 실행

ROS NavSat JSON 정규화:

```bash
cd pocs/02-bridge-normalizer
python3 src/normalizer.py --protocol ros-navsat --input sample-data/raw-ros-navsat.json --format summary
```

decoded AIS fixture 정규화:

```bash
python3 src/normalizer.py --protocol nmea-ais --input sample-data/decoded-ais.json
```

Docker로 실행하면 변환 요약이 logs에 출력됩니다.

```bash
docker compose up
```

## 성공 기준

- 모든 adapter가 같은 공유 schema 형태를 반환합니다.
- 지원하지 않는 프로토콜 payload는 명시적으로 실패합니다.
- 하나의 원시 payload가 여러 stream message를 만들 수 있습니다.
