# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## 프로젝트 개요

**CoWater**: 연안 VTS(선박 교통 서비스) 플랫폼. Moth 서버에서 수신한 선박 위치/상태 정보를 분석하여 실시간 경보를 생성하고, AI 기반 리포트를 작성하는 시스템.

**핵심 특징**:
- 마이크로서비스 아키텍처 (12개 독립 서비스)
- Event-driven Redis pub/sub 파이프라인
- 다중 LLM 백엔드 지원 (Claude, Ollama, vLLM)
- Nginx Agent Gateway로 에이전트 서비스 프록시
- TimescaleDB + PostGIS 시계열/지리공간 데이터 처리
- 분산 배포 지원 (여러 PC에서 마이크로서비스 실행)

---

## 개발 명령어

### 1. 로컬 개발 (단일 호스트)

```bash
cd infra

# ⚠️ 사전 요구사항: 호스트 시스템에서 LLM 서버 실행
# Mac/Windows: ollama serve (또는 Ollama 앱 실행) → 호스트 11434 포트
# Linux: ollama serve → 호스트 11434 포트

# 기본 실행 (호스트 Ollama 사용, localhost만 접근 가능)
docker compose up -d

# 모든 서비스 상태 확인
docker compose ps

# 특정 서비스 로그 보기
docker compose logs -f core

# 서비스별 재빌드
docker compose build core && docker compose up -d core
```

### 2. 네트워크 접근 (원격 호스트에서 연결)

```bash
cd infra

# PostgreSQL/Redis를 원격에서 접근 가능하도록 바인딩
POSTGRES_BIND_ADDR=0.0.0.0 \
REDIS_BIND_ADDR=0.0.0.0 \
CORE_BIND_ADDR=0.0.0.0 \
MOTH_BIND_ADDR=0.0.0.0 \
docker compose up -d

# ⚠️ 주의: 프로덕션 환경에서는 방화벽/VPN 설정 필수!
```

### 3. 시뮬레이터 포함 실행

```bash
cd infra

# 기본 시뮬레이터 (demo 시나리오, 3배속)
SCENARIO=demo docker compose --profile simulation up -d

# 충돌 위험 시나리오
SCENARIO=collision_risk docker compose --profile simulation up -d

# 실시간 시뮬레이션 로그
docker compose logs -f simulator
```

### 4. LLM 백엔드 선택

```bash
cd infra

# Claude API 사용 (권장)
ANTHROPIC_API_KEY=sk-... \
LLM_BACKEND=claude \
docker compose up -d

# Ollama 컨테이너 포함 (Docker-in-Docker LLM)
LLM_BACKEND=ollama docker compose --profile ollama up -d

# vLLM 고성능 서버 포함
LLM_BACKEND=vllm docker compose --profile vllm up -d
```

### 5. 분산 배포 (여러 PC에서 마이크로서비스 실행)

#### PC1 (Database, Redis, Core Backend) 실행

```bash
# .env.local 설정
cat > infra/.env.local <<EOF
POSTGRES_BIND_ADDR=0.0.0.0          # 모든 IP에서 접근 가능
REDIS_BIND_ADDR=0.0.0.0
CORE_BIND_ADDR=0.0.0.0
POSTGRES_PASSWORD=secure_password
REDIS_PASSWORD=secure_password
EOF

cd infra
docker compose up -d postgres redis core moth-bridge agent-gateway
```

#### PC2 (Agent Services) 실행

```bash
# .env.local 설정 (PC1의 IP를 192.168.1.100이라고 가정)
cat > infra/.env.local <<EOF
DATABASE_URL=postgresql+asyncpg://cowater:secure_password@192.168.1.100:5432/cowater
REDIS_URL=redis://:secure_password@192.168.1.100:6379
CORE_API_URL=http://192.168.1.100:7700
CONTROL_AGENTS_UPSTREAM=http://control-agents:8001
DETECTION_AGENTS_UPSTREAM=http://detection-agents:8001
ANALYSIS_AGENTS_UPSTREAM=http://analysis-agents:8001
RESPONSE_AGENTS_UPSTREAM=http://response-agents:8001
REPORT_AGENTS_UPSTREAM=http://report-agents:8001
LEARNING_AGENTS_UPSTREAM=http://learning-agents:8001
SUPERVISION_AGENTS_UPSTREAM=http://supervision-agents:8001
EOF

cd infra
# 에이전트 서비스들 (agent-gateway의 upstream이 같은 네트워크의 컨테이너를 가리킴)
docker compose up -d agent-gateway control-agents response-agents report-agents supervision-agents learning-agents
```

#### PC3 (Frontend) 실행

```bash
# .env.local 설정 (PC1의 IP를 192.168.1.100이라고 가정)
cat > services/frontend/.env.local <<EOF
NEXT_PUBLIC_API_URL=http://192.168.1.100:7700
NEXT_PUBLIC_WS_URL=ws://192.168.1.100:7700
NEXT_PUBLIC_AGENTS_URL=http://192.168.1.100:7701
NEXT_PUBLIC_POSITION_WS_URL=ws://192.168.1.100:7703
EOF

cd services/frontend
npm run dev  # http://localhost:7702
```

### 6. Python 서비스 로컬 실행 (개발 모드, 자동 리로드)

```bash
# 사전 요구사항
pip install -r requirements.txt

# core
cd services/core && PYTHONPATH=../.. uvicorn main:app --reload --port 7700

# control-agents (Chat agent for user interactions)
cd services/control-agents && PYTHONPATH=../.. uvicorn main:app --reload --port 7701

# response-agents (Response agent: Alert Creator)
cd services/response-agents && PYTHONPATH=../.. uvicorn main:app --reload --port 7706

# supervision-agents (Supervisor agent)
cd services/supervision-agents && PYTHONPATH=../.. uvicorn main:app --reload --port 7707

# learning-agents (Learning agent)
cd services/learning-agents && PYTHONPATH=../.. uvicorn main:app --reload --port 7708

# report-agents (Report agent: AI Report Generation)
cd services/report-agents && PYTHONPATH=../.. uvicorn main:app --reload --port 7709

# moth-bridge
cd services/moth-bridge && python main.py

# simulator
cd services/simulator && SCENARIO=default python main.py
```

### 7. 인증 정보 관리

```bash
# 프로덕션 배포 시 필수 설정 (.env.prod)
POSTGRES_PASSWORD=생성된_강력한_비밀번호
REDIS_PASSWORD=생성된_강력한_비밀번호
ANTHROPIC_API_KEY=sk-...
OLLAMA_URL=http://llm-server-ip:11434  # 원격 Ollama인 경우
```

### Frontend

```bash
cd services/frontend
cp .env.local.example .env.local  # 최초 1회
npm install
npm run dev      # http://localhost:7702
npm run build
npm run lint
```

---

## 아키텍처

### 데이터 흐름 (Event Pipeline)

```
Moth Server (wss://cobot.center:8287)
    ↓ RSSP/WebSocket
[moth-bridge] (PC1)
  ParsedReport.to_redis_payload() 
    → Redis pub/sub: platform.report.{platform_id}
                                      ↓
          ┌─────────────────────────────────────────┐
          │ [core] DB 저장 (platform_reports)       │ PC1
          │ WebSocket 브로드캐스트                  │
          └─────────────────────────────────────────┘
                          ↓
          ┌─────────────────────────────────────────┐
          │ [detection-agents] ✅ 활성              │ PC2 (192.168.0.108:7704)
          │ Rule: CPA, Anomaly, Zone, Distress     │
          │ → detect.{agent_id} 발행               │
          └─────────────────────────────────────────┘
                          ↓
          ┌─────────────────────────────────────────┐
          │ [analysis-agents] ✅ 활성               │ PC2 (192.168.0.108:7705)
          │ AI 분석: Anomaly AI, Distress AI        │
          │ → analyze.{agent_id} 발행              │
          └─────────────────────────────────────────┘
                          ↓
          ┌─────────────────────────────────────────┐
          │ [response-agents] ✅ 활성               │ PC1
          │ Rule: Alert Creator                     │
          │ → respond.{severity} 발행              │
          └─────────────────────────────────────────┘
                        ↓
        ┌───────────────────────────────────┐
        │ [report-agents] AI 리포트 생성   │ PC1
        │ [learning-agents] 피드백 학습    │ PC1
        └───────────────────────────────────┘
                        ↓
        [core] reports 테이블 저장 (PC1)
            + WebSocket 브로드캐스트
                        ↓
        [frontend] WebSocket 수신 (PC1 - 대시보드)
```

**현재 완전한 Event Pipeline**: detection과 analysis가 활성화되어 모든 단계의 처리가 작동합니다.

**Event Pipeline (Redis pub/sub)**:
- `platform.report.{platform_id}`: moth-bridge → core, detection
- `detect.{agent_id}`: detection → analysis
- `analyze.{agent_id}`: analysis → response
- `respond.{severity}`: response → core, report, learning
- `report.{report_id}`: report → core
- `user.{event_type}`: frontend → supervision, learning
- `system.alert_acknowledge`: frontend → learning

**주의**: Redis 서버(PC1)는 모든 에이전트가 접근 가능하도록 `REDIS_BIND_ADDR=0.0.0.0`으로 설정

### 분산 배포 아키텍처 (Flexible Distributed Deployment)

**핵심 원칙**: 서비스 개수와 배포 위치는 **환경변수로 동적 결정** → 고정된 PC 구조 없음

```
┌────────────────────────────────────────────────────────────────┐
│ 호스트 A, B, C, ... (개수 제한 없음)                           │
│                                                                │
│ 각 호스트는 docker-compose.yml로 서비스 선택적 실행:          │
│ - docker compose up -d postgres redis core               │
│ - docker compose up -d detection-agents analysis-agents  │
│ - docker compose up -d control-agents response-agents    │
│ - docker compose up -d frontend                          │
│ - 등등... 자유로운 조합                                  │
│                                                                │
│ .env.local로 모든 서비스 연결:                               │
│ - DATABASE_URL=postgresql://...@HOST_A:5432              │
│ - REDIS_URL=redis://:pass@HOST_A:6379                    │
│ - DETECTION_AGENTS_UPSTREAM=http://HOST_B:7704          │
│ - ANALYSIS_AGENTS_UPSTREAM=http://HOST_B:7705           │
│ - 등등... (각 서비스별 upstream)                         │
│                                                                │
│ agent-gateway (Nginx 프록시):                            │
│ ├─ :7701 → CONTROL_AGENTS_UPSTREAM (기본: localhost)   │
│ ├─ :7704 → DETECTION_AGENTS_UPSTREAM (기본: localhost)  │
│ ├─ :7705 → ANALYSIS_AGENTS_UPSTREAM (기본: localhost)   │
│ ├─ :7706 → RESPONSE_AGENTS_UPSTREAM (기본: localhost)   │
│ ├─ :7707 → SUPERVISION_AGENTS_UPSTREAM (기본: localhost)│
│ ├─ :7708 → LEARNING_AGENTS_UPSTREAM (기본: localhost)   │
│ └─ :7709 → REPORT_AGENTS_UPSTREAM (기본: localhost)    │
└────────────────────────────────────────────────────────────────┘
```

**환경변수 기반 설정 (docker-compose.yml에서 기본값 정의)**:

```bash
# 데이터 바인딩 (어느 호스트에서든 접근 가능하려면 0.0.0.0)
POSTGRES_BIND_ADDR=0.0.0.0      # 기본: 127.0.0.1
REDIS_BIND_ADDR=0.0.0.0         # 기본: 127.0.0.1
CORE_BIND_ADDR=0.0.0.0          # 기본: 127.0.0.1
MOTH_BIND_ADDR=0.0.0.0          # 기본: 127.0.0.1

# 원격 서비스 연결 (호스트명 또는 IP)
DATABASE_URL=postgresql://cowater:${POSTGRES_PASSWORD}@HOST_A:5432/cowater
REDIS_URL=redis://:${REDIS_PASSWORD}@HOST_A:6379

# Agent Gateway upstream (로컬/원격 모두 가능)
CONTROL_AGENTS_UPSTREAM=http://HOST_B:7701      # 또는 http://control-agents:8001
DETECTION_AGENTS_UPSTREAM=http://HOST_C:7704    # 또는 http://detection-agents:8001
ANALYSIS_AGENTS_UPSTREAM=http://HOST_C:7705     # 또는 http://analysis-agents:8001
RESPONSE_AGENTS_UPSTREAM=http://HOST_A:7706     # 또는 http://response-agents:8001
REPORT_AGENTS_UPSTREAM=http://HOST_A:7709       # 또는 http://report-agents:8001
SUPERVISION_AGENTS_UPSTREAM=http://HOST_A:7707  # 또는 http://supervision-agents:8001
LEARNING_AGENTS_UPSTREAM=http://HOST_A:7708     # 또는 http://learning-agents:8001
```

**배포 유연성 예시**:

**예1: 단일 호스트** (개발 환경)
```bash
# .env
POSTGRES_BIND_ADDR=127.0.0.1
REDIS_BIND_ADDR=127.0.0.1
# 모든 UPSTREAM은 기본값 (localhost)
docker compose up -d
```

**예2: 2대 호스트** (중소 배포)
```bash
# 호스트 A (.env)
POSTGRES_BIND_ADDR=0.0.0.0
REDIS_BIND_ADDR=0.0.0.0
CORE_BIND_ADDR=0.0.0.0
# 모든 UPSTREAM은 기본값 (localhost)
docker compose up -d postgres redis core moth-bridge agent-gateway control-agents response-agents report-agents supervision-agents learning-agents frontend

# 호스트 B (.env)
DATABASE_URL=postgresql://cowater:pass@HOST_A_IP:5432/cowater
REDIS_URL=redis://:pass@HOST_A_IP:6379
DETECTION_AGENTS_UPSTREAM=http://detection-agents:8001
ANALYSIS_AGENTS_UPSTREAM=http://analysis-agents:8001
docker compose up -d detection-agents analysis-agents
# agent-gateway는 HOST_B를 가리키도록 HOST_A의 .env 수정
```

**예3: 5대 호스트** (대규모 배포)
```
호스트 A: postgres, redis, core, moth-bridge
호스트 B: agent-gateway, control-agents, response-agents
호스트 C: detection-agents, analysis-agents, report-agents
호스트 D: supervision-agents, learning-agents
호스트 E: frontend
# 각 호스트의 .env로 위치 지정
```

**분산 배포 핵심 원칙**:
1. **Stateless**: 각 에이전트는 상태를 가지지 않음 → 어느 호스트든 가능
2. **환경변수**: DATABASE_URL, REDIS_URL, 모든 UPSTREAM으로 연결 위치 지정
3. **Redis는 한 곳**: Pub/Sub 중앙화 필수 (다중화하려면 Redis Sentinel/Cluster)
4. **Postgres도 한 곳**: TimescaleDB 데이터 중앙화 필수
5. **agent-gateway**: 모든 에이전트를 프록시 → 클라이언트는 단일 진입점

**스트림**:
- 위치 스트림: `moth-bridge`의 `/ws/positions` fast path 사용
- 경보 스트림: `core`의 `/ws/alerts` 사용
- 리포트 스트림: `core`의 `/ws/reports` 사용

### 서비스별 역할

| 서비스        | 포트 (컨테이너) | 외부 포트 | 상태 | 역할                                                                       |
| ------------- | ---- | ---- | ---- | -------------------------------------------------------------------------- |
| **인프라**    |      |      |      |
| `postgres`    | 5432 | 5432 (POSTGRES_BIND_ADDR) | ✅ 활성 | TimescaleDB + PostGIS, 시계열/지리공간 데이터 저장 |
| `redis`       | 6379 | 6379 (REDIS_BIND_ADDR) | ✅ 활성 | Pub/Sub 이벤트 버스, 실시간 메시징 (모든 에이전트가 구독) |
| **API & 게이트웨이** |      |      |      |
| `core`        | 8000 | 7700 (CORE_BIND_ADDR) | ✅ 활성 | REST API, TimescaleDB 저장, WebSocket 허브 (`/ws/platforms`, `/ws/alerts`, `/ws/reports`) |
| `agent-gateway` | 80 | 7701-7709 | ✅ 활성 | Nginx 리버스 프록시, 모든 에이전트 upstream 매핑 (환경변수 기반) |
| `moth-bridge` | 8002 | 7703 (MOTH_BIND_ADDR) | ✅ 활성 | Moth/RSSP 수신 → `PlatformReport` 정규화 → Redis 발행 + `/ws/positions` relay |
| **에이전트 (Agent Container)** |      |      |      |
| `control-agents` | 8001 | 7701 (via gateway) | ✅ 활성 | Chat 에이전트 (사용자 대화), 제어 명령 API, LLM 기반 |
| `detection-agents` | 8001 | 7704 (via gateway) | ✅ 활성 | Rule 에이전트 (CPA, Anomaly, Zone, Distress), `platform.report.*` 구독 |
| `analysis-agents` | 8001 | 7705 (via gateway) | ✅ 활성 | AI 분석 에이전트 (Anomaly AI, Distress AI), `detect.*` 구독, LLM 기반 |
| `response-agents` | 8001 | 7706 (via gateway) | ✅ 활성 | 경보 생성 에이전트 (Alert Creator), `analyze.*` 구독 |
| `report-agents` | 8001 | 7709 (via gateway) | ✅ 활성 | AI 리포트 생성 에이전트, `respond.*` 구독 → reports 테이블 저장, LLM 기반 |
| `supervision-agents` | 8001 | 7707 (via gateway) | ✅ 활성 | Supervisor 에이전트, 전체 시스템 상태 모니터링 + heartbeat 추적 |
| `learning-agents` | 8001 | 7708 (via gateway) | ✅ 활성 | Learning 에이전트, 피드백(`user.*`) 및 응답(`respond.*`) 분석 |
| **보조**      |      |      |      |
| `simulator`   | — | — | ✅ 선택 | YAML 시나리오 기반 AIS 생성, Moth 서버에 퍼블리시 (profile: simulation) |
| `frontend`    | 7702 | 7702 | ✅ 활성 | Next.js 15 해양 관제 대시보드 + 에이전트 제어 UI |

**배포 위치는 환경변수로 결정**:
- 각 서비스는 어느 호스트에든 배포 가능
- `DATABASE_URL`, `REDIS_URL`로 원격 데이터 접근
- `*_AGENTS_UPSTREAM`으로 agent-gateway에서 에이전트 위치 지정
- 같은 docker 네트워크면 `localhost:8001`, 원격이면 `호스트명:7XXX`

### 공유 타입 및 유틸 (`shared/`)

**PlatformReport** (`shared/schemas/report.py`):
- Redis 직렬화 기준이 되는 **단일 정의**
- `moth-bridge` → `ParsedReport.to_redis_payload()` (flat dict)
- 각 Container → `PlatformReport.from_dict()` 역직렬화

**Event** (`shared/events.py`):
- `detect.*`, `analyze.*`, `respond.*`, `report.*` 채널의 표준 이벤트 포맷
- `Event.from_json()` / `Event.to_json()` 메서드로 Redis 직렬화

**LLM Client** (`shared/llm_client.py`):
- 추상 `LLMClient` ABC: `generate()`, `chat()` 메서드
- 구현체: `ClaudeClient`, `OllamaClient`, `VllmClient`, `FallbackClient`
- `make_llm_client(settings)` 팩토리로 `LLM_BACKEND` 환경변수 기반 선택
- Analysis, Report 서비스 모두 동일한 클라이언트 사용

**Build Context**:
- 각 Container Dockerfile은 build context가 repo root(`..`)
- `PYTHONPATH=/app` 으로 shared 패키지를 참조

### Redis 채널 규칙

| 패턴                             | 발행자      | 구독자                           |
| -------------------------------- | ----------- | -------------------------------- |
| `platform.report.{platform_id}`  | moth-bridge | core, detection                  |
| `detect.{agent_id}`              | detection   | analysis                         |
| `analyze.{agent_id}`             | analysis    | response                         |
| `respond.{severity}`             | response    | core, report, learning           |
| `report.{report_id}`             | report      | core                             |
| `user.{event_type}`              | frontend    | supervision, learning            |
| `system.alert_acknowledge`       | frontend    | learning                         |
| `agent.command.{agent_id}`       | (예약)      | control                          |
| `platform:state:{platform_id}`   | moth-bridge | (키-값 캐시, TTL 60s)            |
| `learn.rule_update.{agent_id}`   | learning    | detection, analysis, response    |

### Container vs Agent 구조

**Container (서비스 단위)** vs **Agent (실행 단위)**의 구분:
- **Container**: Docker 컨테이너 = 마이크로서비스 (control, response, report, learning, supervision, detection❌, analysis❌)
- **Agent**: Container 내에서 실행되는 개별 logic unit (예: Detection Container에는 CPA, Anomaly, Zone, Distress agents가 포함—단, 현재 비활성)

**Event-driven Subscription Pattern (현재 상태)**:
```
┌─────────────────────────────────────────────────────────┐
│ Moth Server                                             │
└────────────────┬────────────────────────────────────────┘
                 ↓
         [moth-bridge] (PC1)
            ↓ platform.report.*
     ┌──────┴──────┐
     ↓             ↓
  [core]    [detection-agents] (PC2)
  (PC1)         ↓ detect.*
              [analysis-agents] (PC2)
                   ↓ analyze.*
              [response-agents] (PC1)
                   ↓ respond.{severity}
              ┌────┴───────┐
              ↓            ↓
         [core]  [report-agents] (PC1)
        (alerts)      ↓ report.*
                  [core] (reports)
                   ↓ WebSocket
              [frontend] (PC1)

User Interaction
    ↓
[frontend]
    ↓ user.*, system.alert_acknowledge
    ├─ [supervision-agents] (PC1)
    └─ [learning-agents] (PC1)
        ↓ learn.rule_update.*
        └─ [detection/response agents]
```

**현재**: 전체 Event Pipeline이 완전히 작동합니다!

**Agent 실행 패턴**:
- **Rule Agent** (Detection, Response): 동기 실행 (`await`)
- **AI Agent** (Analysis, Report): 비동기 백그라운드 (`asyncio.create_task()`)
  - LLM 호출 시간이 길어도 다음 이벤트 처리를 블로킹하지 않음
  - `ai/llm_client.py`의 `make_llm_client(settings)` 로 Claude/Ollama 선택
  - `LLM_BACKEND=ollama` 환경변수로 로컬 모델 전환 가능

### Core Backend 주요 패턴

- ORM 모델의 `metadata` 컬럼은 SQLAlchemy 예약어 충돌로 `metadata_`로 정의됨. `PlatformResponse.from_model()`에서 `m.metadata_`를 명시적으로 참조해야 한다.
- `platform_reports` 테이블은 TimescaleDB Hypertable. `platform_id`로 4 파티션.
- `zones` 테이블은 PostGIS geometry. 읽기 시 `geoalchemy2.shape.to_shape().geojson`으로 변환.

### 데이터베이스 스키마 (New in Report/Learning Services)

**reports** 테이블 (Report Service):
```sql
CREATE TABLE reports (
  id UUID PRIMARY KEY,
  flow_id UUID NOT NULL,              -- 원본 보고서(platform_report)의 flow_id 추적
  alert_ids UUID[] NOT NULL,          -- 해당 리포트를 생성한 경보들
  report_type VARCHAR,                -- 'summary' | 'detailed' | 'incident'
  content TEXT NOT NULL,              -- AI 생성 리포트 본문
  ai_model VARCHAR,                   -- 사용한 LLM 모델명
  created_at TIMESTAMP DEFAULT NOW(),
  metadata_ JSONB                     -- 생성 파라미터, 처리 결과 등
);
```

**learning_parameters** 테이블 (Learning Service):
```sql
CREATE TABLE learning_parameters (
  id UUID PRIMARY KEY,
  agent_id VARCHAR NOT NULL,          -- 대상 에이전트
  parameter_name VARCHAR NOT NULL,    -- 파라미터명 (e.g., "threshold", "confidence")
  current_value JSONB NOT NULL,       -- 현재 값
  updated_at TIMESTAMP DEFAULT NOW(),
  updated_by VARCHAR,                 -- 업데이트 주체 ('learning-agent', 'user')
  reason TEXT                         -- 변경 사유
);
```

**learning_insights** 테이블 (Learning Service):
```sql
CREATE TABLE learning_insights (
  id UUID PRIMARY KEY,
  agent_id VARCHAR NOT NULL,
  insight_type VARCHAR,               -- 'false_positive_rate' | 'performance_trend' | 'threshold_recommendation'
  insight_data JSONB NOT NULL,        -- FP율, 권장 값 등
  confidence FLOAT,                   -- 0.0 ~ 1.0
  status VARCHAR,                     -- 'proposed' | 'implemented' | 'rejected'
  created_at TIMESTAMP DEFAULT NOW(),
  implemented_at TIMESTAMP,
  metadata_ JSONB
);
```

### Protocol Adapter 확장

새 프로토콜 추가 시 `services/moth-bridge/adapters/` 에 `ProtocolAdapter` 서브클래스 작성 후 `config.yaml`에 채널 추가. 현재 활성: `NMEAAdapter`. 스텁: `MAVLinkAdapter`, `ROSAdapter`.

### Agent Gateway (Nginx) 구성

**목적**: 분산된 에이전트 서비스들을 단일 진입점(7701-7709)으로 통합

**작동 원리**:
1. `agent-gateway` 컨테이너는 Nginx 리버스 프록시
2. 환경변수로 각 에이전트 서비스의 upstream 지정:
   - `CONTROL_AGENTS_UPSTREAM`: control-agents 위치 (기본: http://control-agents:8001)
   - `DETECTION_AGENTS_UPSTREAM`: detection-agents 위치 (기본: http://detection-agents:8001)
   - `ANALYSIS_AGENTS_UPSTREAM`: analysis-agents 위치 (기본: http://analysis-agents:8001)
   - `RESPONSE_AGENTS_UPSTREAM`: response-agents 위치 (기본: http://response-agents:8001)
   - `REPORT_AGENTS_UPSTREAM`: report-agents 위치 (기본: http://report-agents:8001)
   - `LEARNING_AGENTS_UPSTREAM`: learning-agents 위치 (기본: http://learning-agents:8001)
   - `SUPERVISION_AGENTS_UPSTREAM`: supervision-agents 위치 (기본: http://supervision-agents:8001)

**분산 배포 시 설정**:
```bash
# PC2에서 실행할 때, 모든 upstream이 localhost:8001을 가리킴
# (같은 docker-compose 네트워크 내에서 컨테이너명으로 해석)
docker compose up -d agent-gateway control-agents response-agents ...

# 각 에이전트는 내부적으로 :8001에서 수신
# agent-gateway가 :7701-7709로 리버스 프록시
```

**포트 매핑**:
- 7701 → control-agents:8001 (/control)
- 7704 → detection-agents:8001 (/detection)
- 7705 → analysis-agents:8001 (/analysis)
- 7706 → response-agents:8001 (/response)
- 7707 → supervision-agents:8001 (/supervision)
- 7708 → learning-agents:8001 (/learning)
- 7709 → report-agents:8001 (/report)

### Frontend 상태 관리 및 API

**Zustand 스토어**:
- `platformStore`: 위치 상태 (MMSI, 위도/경도, 항속 등)
- `alertStore`: 경보 목록 (severity, 생성 시간, 상태)
- `agentStore`: 에이전트 목록 + 상태 (health status, config)

**WebSocket 연결**:
- `useWebSocket` 훅: `moth-bridge /ws/positions`와 `core /ws/alerts` 두 연결 유지
- 추가: `core /ws/reports` (새 리포트 실시간 수신)

**지도**:
- MapLibre GL + MapLibre 마커
- `mapLoaded` state로 스타일 로드 완료 후 마커 동기화 보장

**Service API URLs** (`lib/publicUrl.ts`):
```typescript
getDetectionApiUrl()      // NEXT_PUBLIC_DETECTION_URL → :7704
getAnalysisApiUrl()       // NEXT_PUBLIC_ANALYSIS_URL  → :7705
getResponseApiUrl()       // NEXT_PUBLIC_RESPONSE_URL  → :7706
getReportApiUrl()         // NEXT_PUBLIC_REPORT_URL    → :7709
getLearningApiUrl()       // NEXT_PUBLIC_LEARNING_URL  → :7708
getSupervisionApiUrl()    // NEXT_PUBLIC_SUPERVISION_URL → :7707
```

**Agents Page API Pattern**:
```
GET /health              (각 Container 상태 확인)
GET /agents             (Container 내 agent 목록 + 상태)
  - Detection: CPA, Anomaly, Zone, Distress (rule)
  - Analysis: Anomaly AI, Distress AI (ai)
  - Response: Alert Creator (rule)
  - Report: AI Report Agent (ai)
  - Control: Chat Agent (ai)
  - Learning: Learning Agent (rule+ai)
  - Supervision: Supervisor (system)
```

**Reports Page API Pattern**:
```
GET /reports                    (보고서 목록, 페이지네이션)
GET /reports/{report_id}        (보고서 상세 조회)
```

---

## 핵심 설계 제약

### Event Pipeline
- **Event 채널 계층화**: `platform.report.*` → `detect.*` → `analyze.*` → `respond.*` → `report.*`
  - 각 Container는 **정확히 한 단계의 입력 채널**만 구독
  - 순환 구독 금지 (Detection은 detect.* 발행하지 않음, Analysis는 analyze.* 발행하지 않음)
- **Event 발행 순서**: 각 Container는 처리 완료 후 다음 단계 채널에만 발행
- **Learn Update 채널**: `learn.rule_update.{agent_id}`는 Learning Agent만 발행, 각 Container는 구독하되 반영은 신중하게

### AI 에이전트 실행
- **백그라운드 실행**: AI 에이전트(`asyncio.create_task()`)는 LLM 호출이 다음 이벤트를 블로킹하지 않도록 함
- **Fallback 처리**: LLM 호출 실패 시 template-based response 반환 (신뢰도 낮게 표시)
- **Timeout 설정**: 모든 LLM 호출은 명시적 timeout 지정 (연쇄 시간초과 방지)

### 데이터 무결성
- **Track 쿼리 정렬**: `ORDER BY time DESC LIMIT N` 서브쿼리로 최신 N개를 가져온 뒤, 외부 쿼리에서 `ORDER BY time ASC`로 재정렬 (항적 렌더링 방향 보장)
- **`audit_logs` 테이블**: PostgreSQL RULE로 UPDATE/DELETE 차단. 코드에서 절대 수정 시도 금지
- **Flow ID 추적**: 각 리포트는 원본 platform_report의 flow_id 기록 (감시자 감사 추적)

### 시뮬레이터
- **실제 Moth 서버 연결**: `MOTH_SERVER_URL=wss://cobot.center:8287`. 프로덕션 채널에 충돌하지 않는 시나리오 데이터만 사용할 것.

### Frontend

#### 기술 스택
- **Framework**: Next.js 15, React 19
- **State Management**: Zustand (store per domain)
- **Styling**: Tailwind CSS + CSS custom properties (dark/light mode)
- **Map**: MapLibre GL (open-source, no API key required)
- **Real-time**: WebSocket (`/ws/platforms`, `/ws/alerts`, `/ws/reports`)
- **Type Safety**: TypeScript, strict mode

#### Zustand 스토어
| Store | 역할 |
|-------|------|
| `platformStore` | 플랫폼 위치 (MMSI, lat/lon, SOG, COG), 선택 상태 |
| `alertStore` | 경보 목록 (severity, status, timestamps) |
| `agentStore` | 에이전트 상태 및 설정 |
| `zoneStore` | 관제 구역 지역 데이터 (PostGIS geometry) |
| `systemStore` | 시스템 상태 (streams, notifications) |
| `authStore` | 사용자 역할 및 권한 (viewer/operator/admin) |
| `eventStore` | 탐지/분석/응답 이벤트 흐름 |
| `themeStore` | 다크/라이트 모드 (localStorage 영속) |
| `mapLayerStore` | 지도 레이어 가시성 (seamark, zones, platforms, trails, navAids) |

#### UX/UI 개선사항 (Phase 1-10)

**Phase 1: 디자인 시스템**
- CSS 변수: `--bg-primary`, `--bg-secondary`, `--text-primary`, `--text-secondary` 등 16개
- 애니메이션: `slide-in-from-top`, `fade-in`, `pulse-slow`, `count-update` (Tailwind 확장)
- 다크/라이트 모드: HTML `data-theme` 속성으로 실시간 전환, localStorage 영속

**Phase 2: 시각화 컴포넌트**
- `LiveDot`: 실시간 상태 표시 (animated pulse)
- `SparkLine`: SVG 미니 라인차트 (의존성 없음)
- `DonutRing`: SVG 도넛 링 차트 (심각도 분포)
- `SeverityBar`: 가로 스택바 (critical/warning/info 비율)
- `TimelineList`: 날짜 그룹핑 타임라인 (오늘/어제 구분선)
- `ThemeToggle`: 다크/라이트 모드 토글
- `KeyboardShortcutHint`: 단축키 오버레이 (? 키 트리거)

**Phase 3: NavBar 강화**
- `ThemeToggle` (compact mode)
- `KeyboardShortcutHint` 모달
- `LiveDot` 실시간 연결 상태
- 알림 뱃지 pulse 애니메이션 (`animate-pulse-slow`)

**Phase 4: 대시보드 (/) 개선**
- Sticky KPI 바: 4개 핵심 지표 + SeverityBar
- 이벤트 흐름 SparkLine (탐지→분석→응답)
- 3칼럼 레이아웃 (플랫폼/지도/경보) 유지

**Phase 5: 경보 페이지 (/alerts) 개선**
- DonutRing 심각도 분포 표시
- SeverityBar 건수 비율
- TimelineList 기반 경보 시간선 (타입별 정렬)

**Phase 6: 플랫폼 페이지 (/platforms) 개선**
- 타입별 분포 표시 (vessel/usv/rov/auv/drone/buoy)
- 테이블/카드 뷰 토글 (FilterChip)
- 카드뷰: grid-cols-2 md:grid-cols-3 lg:grid-cols-4

**Phase 7: 에이전트 페이지 (/agents) 개선**
- ContainerCard 헬스 상태 글로우 (emerald/amber/red)
- LiveDot 각 파이프라인 단계에 표시
- StatusBadge로 에이전트 상태 시각화

**Phase 8: 리포트 페이지 (/reports) 개선**
- 기간 필터 (오늘/7일/30일)
- TimelineList 기반 리포트 타임라인
- 리포트 타입별 컬러 코딩

**Phase 9: 지도 레이어 컨트롤**
- `mapLayerStore`: 레이어 가시성 상태 관리
- `LayerControlPanel`: FAB 버튼 + 슬라이드 아웃 패널
  - 기본 레이어 토글 (seamark, zones, platforms, trails, navAids)
  - 플랫폼 타입 필터 (chip buttons)
  - 구역 타입 필터 (color-coded toggles)
  - 항적 길이 슬라이더 (10-200 points)
  - 초기화 버튼
- 플랫폼 마커 visiblePlatformTypes 기반 필터링
- Trail 렌더링 showTrails 상태 존중

**Phase 10: 상수 통합**
- `lib/constants.ts`: 전역 상수 중복 제거
  - ALERT_SEVERITY_LABEL, ALERT_TYPE_LABEL, ALERT_STATUS_LABEL
  - PLATFORM_TYPE_ICON, PLATFORM_TYPE_LABEL, PLATFORM_TYPE_COLOR
  - NAV_STATUS_LABEL, NAV_STATUS_BADGE_STYLE
  - REPORT_TYPE_LABEL, REPORT_TYPE_COLOR, ROLE_ORDER

#### 키보드 단축키 (`useKeyboard` hook)
| 키 | 동작 |
|----|------|
| `?` | 단축키 오버레이 열기 |
| `⌘K` / `Ctrl+K` | 빠른 플랫폼 검색 |
| `↑↓` | 목록 항목 탐색 |
| `Enter` | 항목 확인 |
| `A` | 경보 확인 (Acknowledge) |
| `Esc` | 패널/드로어 닫기 |
| `1~5` | 페이지 빠른 이동 (1=Home, 2=Platforms, 3=Alerts, 4=Agents, 5=Reports) |

#### 환경 변수
```
# Frontend development
NEXT_PUBLIC_CORE_URL=http://localhost:7700
NEXT_PUBLIC_DETECTION_URL=http://localhost:7704
NEXT_PUBLIC_ANALYSIS_URL=http://localhost:7705
NEXT_PUBLIC_RESPONSE_URL=http://localhost:7706
NEXT_PUBLIC_REPORT_URL=http://localhost:7709
NEXT_PUBLIC_LEARNING_URL=http://localhost:7708
NEXT_PUBLIC_SUPERVISION_URL=http://localhost:7707
```

#### 페이지별 특징
- `/` (대시보드): 전체 현황 + 실시간 이벤트 흐름
- `/platforms`: 선박/드론 목록 + 위치 필터
- `/alerts`: 경보 타임라인 + 상세 분석
- `/agents`: 에이전트 파이프라인 상태
- `/reports`: AI 리포트 조회 + 기간 필터
- `/zones`: 관제 구역 지도 표시

---

## Frontend 의존성 추가사항 (2026-04-16)
- maplibre-gl: ^3.0.0 (지도 렌더링)
- zustand: ^4.0.0 (상태 관리)
- date-fns: ^3.0.0 (날짜 포맷팅)
- 추가 의존성 없이 구현한 컴포넌트:
  - SparkLine, DonutRing: Pure SVG (recharts/chart.js 없음)
  - TimelineList: Vanilla React (react-beautiful-dnd 없음)
  - ThemeToggle: CSS custom properties 기반
