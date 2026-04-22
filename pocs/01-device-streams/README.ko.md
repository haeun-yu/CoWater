# PoC 01: Device Streams

## 목표

하나의 해양 디바이스가 여러 독립 스트림을 동시에 발행할 수 있고, parent-child 디바이스 구조를 중앙 Core 없이 표현할 수 있는지 검증합니다.

## 범위

포함:

- Control USV, AUV, ROV 샘플 디바이스
- 위치, 상태, 소나, 작업, 네트워크, 이벤트 스트림
- `packages/schemas`의 공유 schema 사용
- 다운스트림 PoC가 사용할 JSONL 출력

제외:

- 프로토콜 파싱
- Redis/NATS 전송
- Core 저장
- UI 렌더링
- Detection/Response Agent

## 실행

```bash
cd pocs/01-device-streams
python3 src/simulator.py --ticks 5 --format table
```

fixture 파일 생성:

```bash
python3 src/simulator.py --ticks 10 --output out/device-streams.jsonl
```

Docker로 실행하면 기본적으로 table 형식이 logs에 출력됩니다.

```bash
docker compose up
```

## 성공 기준

- 각 디바이스가 둘 이상의 stream을 발행합니다.
- stream subject가 서로 분리됩니다.
- parent-child 관계는 subject가 아니라 envelope metadata에 남습니다.
- 다른 PoC가 이 PoC 내부 구현을 import하지 않고 출력 파일만 사용할 수 있습니다.
