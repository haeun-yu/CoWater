# CoWater

> 국제 해양 표준과 실시간 데이터를 기반으로,
> 해역 전반을 통합 관제하고 안전한 운항과 신속한 의사결정을 지원하는 해양 운영 플랫폼

연안 VTS(Vessel Traffic Service) 수준의 통합 해양 관제 플랫폼입니다.
선박뿐만 아니라 USV, ROV, AUV, 드론, 부이 등 다양한 해양 플랫폼을 단일 인터페이스로 관제하며,
Rule 기반 자동 분석과 Claude AI 기반 지능형 에이전트를 결합해 실시간 위험 감지와 의사결정을 지원합니다.

---

## 주요 기능

| 기능                     | 설명                                                         |
| ------------------------ | ------------------------------------------------------------ |
| **실시간 지도 관제**     | MapLibre + OpenSeaMap 기반 해양 플랫폼 위치·항적 시각화      |
| **CPA/TCPA 충돌 경보**   | 벡터 기반 최근접거리·도달시간 계산, 위험도별 자동 알림       |
| **이상 행동 탐지**       | AIS 타임아웃, 속도 급변, ROT 스파이크 Rule 탐지 + AI 분석    |
| **구역 침입 감지**       | PostGIS 다각형 구역 정의, 레이 캐스팅 실시간 판별            |
| **AI 에이전트**          | Claude 기반 상황 분석·권고, 조난 대응, 사건 리포트 자동 생성 |
| **에이전트 자율성 레벨** | L1(감지·알람) / L2(분석·권고) / L3(자동 실행) 런타임 전환    |
| **훈련 시뮬레이터**      | YAML 시나리오 기반 AIS 데이터 생성, 실제 Moth 서버 연동      |
| **감사 로그**            | PostgreSQL RULE로 보호되는 불변 이벤트 기록                  |
| **음성/텍스트 명령**     | voice/text → intent → 권한 체크 → 실행 → audit 파이프라인   |

---

## 아키텍처

```
[Moth Bridge] ──► [Redis pub/sub] ──► [Core Backend]  ──► [PostgreSQL / TimescaleDB]
  NMEA/AIS                 │              FastAPI              PostGIS, Hypertable
  MAVLink (stub)           │
  ROS (stub)               └──────────► [Agent Runtime]
                                          Rule Agents (CPA, Zone, Anomaly)
[Simulator] ──────────────────────────► AI Agents   (Claude-powered)
  YAML Scenarios                          ↓
                                        [Frontend]
                                          Next.js 15 + MapLibre
```

5개의 독립 서비스가 Redis를 메시지 버스로 느슨하게 연결됩니다.
자세한 설계는 [ARCHITECTURE.md](ARCHITECTURE.md)를 참조하세요.

---

## 음성/텍스트 명령

음성 입력은 별도 특수 경로가 아니라 **일반 명령과 동일한 파이프라인**으로 처리합니다.

```text
voice/text transcript
  -> POST /commands
  -> deterministic intent parse
  -> role/token permission check
  -> execute existing alert/agent action
  -> append-only audit_logs insert
```

지원 예시:

```text
cpa 켜줘
agent level cpa L2
alert resolve <alert-uuid>
```

- `viewer`: dry-run / 파싱 확인 전용
- `operator`: 경보 처리, 수동 agent run
- `admin`: agent enable/disable/level/config/model 등 제어

개발 기본 토큰(운영 환경에서는 반드시 교체):

```text
viewer-dev
operator-dev
admin-dev
```

명령 실행 결과는 `audit_logs`에 `command.received / command.denied / command.executed / command.failed` 이벤트로 기록됩니다.

---

## 서비스 구성

```
CoWater/
├── services/
│   ├── moth-bridge/     # Moth/RSSP WebSocket 수신 → PlatformReport 정규화 → Redis 발행
│   ├── core/            # FastAPI REST API + WebSocket 허브 + TimescaleDB 저장
│   ├── agents/          # Agent Runtime — Rule·AI 에이전트 실행 환경
│   ├── simulator/       # YAML 시나리오 기반 AIS 생성기 (선택 실행)
│   └── frontend/        # Next.js 15 해양 관제 대시보드
├── shared/
│   ├── schemas/         # PlatformReport, Alert 등 서비스 간 공유 타입
│   └── events/          # Redis 채널명 헬퍼
└── infra/
    ├── docker-compose.yml
    └── postgres/        # 스키마 마이그레이션 SQL
```

---

## 빠른 시작

### 사전 요구사항

- Docker 24+ / Docker Compose v2
- Anthropic API Key (AI 에이전트 사용 시)

### 실행

```bash
# 1. 환경 변수 설정
cp services/frontend/.env.local.example services/frontend/.env.local
export ANTHROPIC_API_KEY=sk-ant-...

# 2. 핵심 서비스 실행
cd infra
docker compose up -d

# 3. (선택) 시뮬레이터 실행
docker compose --profile simulation up simulator
```

서비스가 뜨면:

| 서비스        | 주소                       |
| ------------- | -------------------------- |
| Frontend      | http://localhost:7702      |
| Core API      | http://localhost:7700/docs |
| Agent Runtime | http://localhost:7701/docs |
| Position Relay | ws://localhost:7703/ws/positions |
| PostgreSQL    | localhost:5432             |

### 시뮬레이션 시나리오

```bash
# 기본 (선박 5척 순항)
SCENARIO=default docker compose --profile simulation up simulator

# 충돌 위험 (교차 항로 + 기관 정지)
SCENARIO=collision_risk docker compose --profile simulation up simulator

# 조난 대응 (기관 고장 → AIS 유실 → SAR)
SCENARIO=distress_response docker compose --profile simulation up simulator

# 구역 침입 (금지구역 진입 + AIS 침묵)
SCENARIO=zone_intrusion docker compose --profile simulation up simulator
```

---

## 에이전트

Agent Runtime은 런타임에 개별 에이전트를 토글·레벨 변경할 수 있습니다.

```bash
# 에이전트 목록
GET  http://localhost:7701/agents

# 에이전트 활성화 / 비활성화
PATCH http://localhost:7701/agents/{agent_id}/enable
PATCH http://localhost:7701/agents/{agent_id}/disable

# 자율성 레벨 변경 (L1 / L2 / L3)
PATCH http://localhost:7701/agents/{agent_id}/level
Body: {"level": "L2"}
```

| 에이전트         | 유형 | 설명                                    |
| ---------------- | ---- | --------------------------------------- |
| `cpa-agent`      | Rule | 선박 간 CPA/TCPA 충돌 위험 계산         |
| `zone-monitor`   | Rule | 구역 침입·이탈 감지                     |
| `anomaly-rule`   | Rule | AIS 타임아웃, 속도·ROT 이상             |
| `anomaly-ai`     | AI   | Rule 탐지 결과 Claude 심층 분석 및 권고 |
| `distress-agent` | AI   | 조난 상황 판단 및 대응                  |
| `report-agent`   | AI   | 사건 종합 리포트 자동 생성              |

---

## 기술 스택

| 영역        | 기술                                                      |
| ----------- | --------------------------------------------------------- |
| Backend     | Python 3.12, FastAPI, SQLAlchemy 2 (async)                |
| Database    | TimescaleDB (time-series), PostGIS (공간 데이터)          |
| Message Bus | Redis pub/sub                                             |
| AI          | Anthropic Claude (claude-haiku-4-5-20251001)             |
| Frontend    | Next.js 15 (App Router), TypeScript, Zustand, MapLibre GL |
| 지도        | OpenStreetMap + OpenSeaMap                                |
| 인프라      | Docker Compose                                            |

---

## 환경 변수

기본 로컬 포트는 7700번대로 통일합니다.

Core, Agent Runtime, Moth Bridge는 Docker Compose에서 환경 변수를 직접 주입합니다. 로컬 실행 시에는 셸 환경 변수로 지정하거나 별도 `.env` 파일을 직접 만들어 사용할 수 있습니다.

### Core (환경 변수)

| 변수           | 기본값                     | 설명                    |
| -------------- | -------------------------- | ----------------------- |
| `DATABASE_URL` | `postgresql+asyncpg://...` | TimescaleDB 연결 문자열 |
| `REDIS_URL`    | `redis://localhost:6379`   | Redis 주소              |
| `AGENTS_API_URL` | `http://localhost:7701`  | Core가 Agent Runtime 제어 시 사용하는 내부 URL |
| `COMMAND_TOKENS_JSON` | 개발용 기본 토큰 내장 | voice/text command용 Bearer 토큰 매핑(JSON) |

### Agent Runtime (환경 변수)

| 변수                | 기본값                   | 설명                 |
| ------------------- | ------------------------ | -------------------- |
| `REDIS_URL`         | `redis://localhost:6379` | Redis 주소           |
| `CORE_API_URL`      | `http://localhost:7700`  | Core Backend URL     |
| `COMMAND_TOKENS_JSON` | 개발용 기본 토큰 내장 | mutating agent API 보호용 Bearer 토큰 매핑(JSON) |
| `ANTHROPIC_API_KEY` | —                        | Claude API 키 (필수) |
| `CLAUDE_MODEL`      | `claude-haiku-4-5-20251001` | 사용할 Claude 모델 |
| `OLLAMA_THINK`      | `false`                  | Ollama reasoning/think 모드 사용 여부 |

### Frontend (`services/frontend/.env.local`)

| 변수                     | 기본값                  | 설명           |
| ------------------------ | ----------------------- | -------------- |
| `NEXT_PUBLIC_API_URL`    | `http://localhost:7700` | Core REST API  |
| `NEXT_PUBLIC_WS_URL`     | `ws://localhost:7700`   | Core WebSocket 허브 |
| `NEXT_PUBLIC_AGENTS_URL` | `http://localhost:7701` | Agent Runtime  |
| `NEXT_PUBLIC_POSITION_WS_URL` | `ws://localhost:7703` | Moth-bridge 위치 relay |

### Moth Bridge (환경 변수)

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `RAW_PAYLOAD_MODE` | `cache` | `off`, `cache`, `db` 중 선택 |
| `RAW_PAYLOAD_PROTOCOLS` | `ais,ros,mavlink,nmea` | raw payload 보존 대상 프로토콜 목록 |
| `RAW_PAYLOAD_MAX_BYTES` | `4096` | 저장할 raw payload 최대 바이트 수 |
| `RAW_PAYLOAD_TTL_SEC` | `86400` | `cache` 모드일 때 Redis 보존 시간(초) |

### 실시간 스트림 경로

- 위치 업데이트: `moth-bridge`의 `ws://localhost:7703/ws/positions`
- 경보 업데이트: `core`의 `ws://localhost:7700/ws/alerts`
- Docker 내부에서는 moth-bridge relay가 `8002` 포트에서 listen하고, 호스트에는 `7703`으로 노출됩니다.

### Raw payload 보존 정책

- 기본값은 `cache` 모드입니다.
- `cache` 모드: Redis에 TTL을 두고 짧게 보존합니다.
- `db` 모드: core가 `platform_reports.raw_payload`에 저장합니다.
- `off` 모드: raw payload를 저장하지 않습니다.
- 운영 환경에서는 `cache`를 권장하고, 장기 보관이 꼭 필요할 때만 `db`로 전환하세요.
