# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## 개발 명령어

### 전체 스택 실행 (Docker)

```bash
cd infra

# 핵심 서비스 (postgres, redis, core, moth-bridge, agents, frontend)
docker compose up -d

# 시뮬레이터 포함 실행
SCENARIO=collision_risk docker compose --profile simulation up -d

# Ollama(로컬 LLM) 포함 실행
LLM_BACKEND=ollama docker compose --profile ollama up -d
# 최초 실행 시 ollama-init이 모델(qwen2.5:3b)을 자동 pull (~2GB)

# 전체 실행
LLM_BACKEND=ollama SCENARIO=demo docker compose --profile ollama --profile simulation up -d


# 서비스별 재빌드
docker compose build core && docker compose up -d core
```

### Python 서비스 로컬 실행

```bash
# 공통 — 각 서비스 디렉토리에서
pip install -r requirements.txt

# core
cd services/core && uvicorn main:app --reload --port 8000

# agents
cd services/agents && PYTHONPATH=../.. uvicorn main:app --reload --port 8001

# moth-bridge
cd services/moth-bridge && python main.py

# simulator
cd services/simulator && SCENARIO=default python main.py
```

### Frontend

```bash
cd services/frontend
cp .env.local.example .env.local  # 최초 1회
npm install
npm run dev      # http://localhost:3000
npm run build
npm run lint
```

---

## 아키텍처

### 데이터 흐름

```
Moth Server (wss://cobot.center:8287)
    ↓ RSSP/WebSocket
[moth-bridge]  ─── ParsedReport.to_redis_payload() ──►  Redis pub/sub
                                                          platform.report.{id}
                                                               ↓
                                              ┌─────────────────────────────┐
                                              │  [core]        [agents]     │
                                              │  DB 저장        Rule 에이전트│
                                              │  WS 브로드캐스트 AI 에이전트 │
                                              └─────────────────────────────┘
                                                      ↓ alert.created.{severity}
                                              [core] DB 저장 + WS 브로드캐스트
                                                      ↓
                                              [frontend] WebSocket 수신
```

### 서비스별 역할

| 서비스        | 포트 | 역할                                                                       |
| ------------- | ---- | -------------------------------------------------------------------------- |
| `moth-bridge` | —    | Moth/RSSP 수신 → `PlatformReport` 정규화 → Redis 발행                      |
| `core`        | 7700 | REST API, TimescaleDB 저장, WebSocket 허브 (`/ws/platforms`, `/ws/alerts`) |
| `agents`      | 7701 | Rule/AI 에이전트 실행환경, 에이전트 제어 API                               |
| `simulator`   | —    | YAML 시나리오 기반 AIS 생성, Moth 서버에 퍼블리시                          |
| `frontend`    | 7702 | Next.js 15 해양 관제 대시보드                                              |

### 공유 타입 (`shared/`)

`shared/schemas/report.py`의 `PlatformReport`가 Redis 직렬화 기준이 되는 **단일 정의**다.

- `moth-bridge` → `ParsedReport.to_redis_payload()` (flat dict)
- `agents` → `PlatformReport.from_dict()` 역직렬화
- `agents` Dockerfile은 build context가 repo root(`..`)이며, `PYTHONPATH=/app`으로 shared 패키지를 참조한다.

### Redis 채널 규칙

| 패턴                            | 발행자      | 구독자                |
| ------------------------------- | ----------- | --------------------- |
| `platform.report.{platform_id}` | moth-bridge | core, agents          |
| `alert.created.{severity}`      | agents      | core, agents          |
| `agent.command.{agent_id}`      | (예약)      | agents                |
| `platform:state:{platform_id}`  | moth-bridge | (키-값 캐시, TTL 60s) |

### Agent Runtime 구조

에이전트는 `services/agents/base.py`의 `Agent` ABC를 상속한다.

```
on_platform_report(PlatformReport)   # 위치 보고 수신 시
on_alert(dict)                       # 다른 에이전트의 경보 수신 시
emit_alert(AlertPayload)             # Redis에 경보 발행
level: L1 | L2 | L3                 # 자율성 레벨
```

`_dispatch_report()`에서 Rule 에이전트는 직렬 `await`, AI 에이전트는 `asyncio.create_task()`로 백그라운드 실행한다 (Claude/Ollama 호출이 다음 보고 처리를 블로킹하지 않도록).

AI 에이전트는 `ai/llm_client.py`의 `make_llm_client(settings)`를 통해 Claude 또는 Ollama를 선택한다. `LLM_BACKEND=ollama` 설정만으로 로컬 모델 전환 가능.

### Core Backend 주요 패턴

- ORM 모델의 `metadata` 컬럼은 SQLAlchemy 예약어 충돌로 `metadata_`로 정의됨. `PlatformResponse.from_model()`에서 `m.metadata_`를 명시적으로 참조해야 한다.
- `platform_reports` 테이블은 TimescaleDB Hypertable. `platform_id`로 4 파티션.
- `zones` 테이블은 PostGIS geometry. 읽기 시 `geoalchemy2.shape.to_shape().geojson`으로 변환.

### Protocol Adapter 확장

새 프로토콜 추가 시 `services/moth-bridge/adapters/` 에 `ProtocolAdapter` 서브클래스 작성 후 `config.yaml`에 채널 추가. 현재 활성: `NMEAAdapter`. 스텁: `MAVLinkAdapter`, `ROSAdapter`.

### Frontend 상태 관리

- Zustand 스토어: `platformStore`(위치 상태), `alertStore`(경보), `agentStore`(에이전트 목록)
- WebSocket: `useWebSocket` 훅이 `/ws/platforms`, `/ws/alerts` 두 연결 유지 (20초 ping, 3초 재연결)
- 지도: MapLibre GL + MapLibre 마커. `mapLoaded` state로 스타일 로드 완료 후 마커 동기화 보장.

---

## 핵심 설계 제약

- **AI 에이전트 무한루프 방지**: `on_alert()`에서 반드시 `alert.get("generated_by") == self.agent_id` 조기 반환 체크.
- **Track 쿼리 정렬**: `ORDER BY time DESC LIMIT N` 서브쿼리로 최신 N개를 가져온 뒤, 외부 쿼리에서 `ORDER BY time ASC`로 재정렬 (항적 렌더링 방향 보장).
- **`audit_logs` 테이블**: PostgreSQL RULE로 UPDATE/DELETE 차단. 코드에서 절대 수정 시도 금지.
- **시뮬레이터는 실제 Moth 서버에 연결**: `MOTH_SERVER_URL=wss://cobot.center:8287`. 프로덕션 채널에 충돌하지 않는 시나리오 데이터를 사용할 것.
