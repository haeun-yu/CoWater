# PoC 04: Realtime Dashboard

## 목표

기존 frontend에 의존하지 않는 작은 관제 UI로 디바이스, stream, alert를 시각화합니다.

## 범위

포함:

- Mock API
- 실시간에 가까운 polling feed
- 디바이스 목록
- 지도 placeholder
- Stream 상태 패널
- Alert 패널

제외:

- 기존 CoWater UI 전체 이전
- 인증
- 운영용 지도 레이어

## 성공 기준

- mock stream feed가 UI를 실시간으로 갱신합니다.
- 위치, 상태, 네트워크, 작업, alert view가 시각적으로 분리됩니다.
- `01-device-streams` fixture를 기반으로 확장할 수 있습니다.

## 실행

```bash
cd pocs/04-realtime-dashboard
python3 src/server.py --port 8744
```

브라우저에서 `http://127.0.0.1:8744`를 엽니다.

Docker:

```bash
docker compose up
```
