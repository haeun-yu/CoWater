# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## 개발 명령어

### 전체 스택 실행 (Docker)

```bash
cd infra

# ⚠️ 사전 요구사항: 호스트 시스템에서 Ollama 실행 필요
# Mac/Windows: ollama serve (또는 Ollama 앱 실행)
# Linux: ollama serve

# 핵심 서비스 (postgres, redis, core, moth-bridge, agents, frontend)
# Analysis Service는 호스트의 Ollama에 연결 (host.docker.internal:11434)
docker compose up -d

# 시뮬레이터 포함 실행
SCENARIO=collision_risk docker compose --profile simulation up -d

# Ollama를 Docker 컨테이너에서도 실행하고 싶으면 (선택)
LLM_BACKEND=ollama docker compose --profile ollama up -d
# 최초 실행 시 ollama-init이 모델(qwen2.5:3b)을 자동 pull (~2GB)

# vLLM(고성능 로컬 LLM) 포함 실행 (선택)
LLM_BACKEND=vllm docker compose --profile vllm up -d
# 최초 실행 시 HuggingFace에서 모델 자동 다운로드 (~2GB)

# 기본 실행 (호스트 Ollama 사용)
docker compose up -d

# 서비스별 재빌드
docker compose build core && docker compose up -d core
```

### Python 서비스 로컬 실행

```bash
# 공통 — 각 서비스 디렉토리에서
pip install -r requirements.txt

# core
cd services/core && PYTHONPATH=../.. uvicorn main:app --reload --port 7700

# control-agents (Chat agent for user interactions)
cd services/control-agents && PYTHONPATH=../.. uvicorn main:app --reload --port 7701

# detection-agents (Rule agents: CPA, Anomaly, Zone, Distress)
cd services/detection-agents && PYTHONPATH=../.. uvicorn main:app --reload --port 7704

# analysis-agents (AI analysis agent)
cd services/analysis-agents && PYTHONPATH=../.. uvicorn main:app --reload --port 7705

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

### 데이터 흐름

```
Moth Server (wss://cobot.center:8287)
    ↓ RSSP/WebSocket
[moth-bridge] ParsedReport.to_redis_payload() → Redis pub/sub
                                                 platform.report.{id}
                                                    ↓
                            ┌───────────────────────────────┐
                            │  [core] DB 저장               │
                            │  [detection] Rule 에이전트:   │
                            │    - CPA                      │
                            │    - Anomaly                  │
                            │    - Zone                     │
                            │    - Distress (rule)          │
                            └───────────────────────────────┘
                                      ↓ detect.{agent_id}
                            [analysis] AI 분석 에이전트
                            (Anomaly AI, Distress AI)
                                      ↓ analyze.{agent_id}
                            [response] 경보 생성 에이전트
                                      ↓ respond.{severity}
                    ┌──────────────────────────────────┐
                    │ [report] AI 리포트 생성           │
                    │ [learning] 피드백 기반 학습      │
                    └──────────────────────────────────┘
                                      ↓ report.{id}
                            [core] 리포트 DB 저장
                                  + WS 브로드캐스트
                                      ↓
                            [frontend] WebSocket 수신
```

**Event Pipeline (Redis pub/sub)**:
- `platform.report.{platform_id}`: moth-bridge → core, detection
- `detect.{agent_id}`: detection → analysis
- `analyze.{agent_id}`: analysis → response
- `respond.{severity}`: response → core, report, learning
- `report.{report_id}`: report → core
- `user.{event_type}`: frontend → supervision, learning
- `system.alert_acknowledge`: frontend → learning

**스트림**:
- 위치 스트림: `moth-bridge`의 `/ws/positions` fast path 사용
- 경보 스트림: `core`의 `/ws/alerts` 사용
- 리포트 스트림: `core`의 `/ws/reports` 사용

### 서비스별 역할

| 서비스        | 포트 | 역할                                                                       |
| ------------- | ---- | -------------------------------------------------------------------------- |
| `moth-bridge` | 7703 (host) / 8002 (container) | Moth/RSSP 수신 → `PlatformReport` 정규화 → Redis 발행 + `/ws/positions` relay |
| `core`        | 7700 | REST API, TimescaleDB 저장, WebSocket 허브 (`/ws/platforms`, `/ws/alerts`, `/ws/reports`) |
| `control-agents` | 7701 | Chat 에이전트 (사용자 대화), 제어 명령 API |
| `detection-agents` | 7704 | Rule 에이전트 (CPA, Anomaly, Zone, Distress), `platform.report.*` 구독 |
| `analysis-agents` | 7705 | AI 분석 에이전트 (Anomaly AI, Distress AI), `detect.*` 구독 |
| `response-agents` | 7706 | 경보 생성 에이전트 (Alert Creator), `analyze.*` 구독 |
| `report-agents` | 7709 | AI 리포트 생성 에이전트, `respond.*` 구독 → reports 테이블 저장 |
| `supervision-agents` | 7707 | Supervisor 에이전트, 전체 시스템 상태 모니터링 + heartbeat 추적 |
| `learning-agents` | 7708 | Learning 에이전트, 피드백(`user.*`) 및 응답(`respond.*`) 분석 |
| `simulator`   | —    | YAML 시나리오 기반 AIS 생성, Moth 서버에 퍼블리시                          |
| `frontend`    | 7702 | Next.js 15 해양 관제 대시보드 + 에이전트 제어 UI                          |

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
- **Container**: Docker 컨테이너 = 마이크로서비스 (detection, analysis, response, report, learning, supervision, control)
- **Agent**: Container 내에서 실행되는 개별 logic unit (예: Detection Container에는 CPA, Anomaly, Zone, Distress agents가 포함)

**Event-driven Subscription Pattern**:
```
Detection  → platform.report.* 구독 → CPA/Anomaly/Zone/Distress 규칙 실행 → detect.{agent_id} 발행
Analysis   → detect.* 구독 → AI 분석 에이전트 실행 → analyze.{agent_id} 발행
Response   → analyze.* 구독 → Alert Creator 실행 → respond.{severity} 발행
Report     → respond.* 구독 → AI 리포트 생성 → report.{report_id} 발행
Learning   → respond.*, user.* 구독 → 피드백 학습 → learn.rule_update.* 발행
Supervision → (heartbeat 주기 체크) → health 상태 발행
Control    → agent.command.* 구독 → Chat Agent 실행
```

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
- **Container 그룹핑**: `/agents` 페이지에서 각 서비스별 Container 카드로 표시
- **Agent 상세 보기**: Container 클릭 시 실행 agent 목록 + 발행 이벤트, config 상세 드로어 오픈
- **Environment Variables**: 각 서비스 URL은 `NEXT_PUBLIC_*_URL` 환경변수로 설정 (Docker build time)
