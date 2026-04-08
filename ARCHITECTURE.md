# CoWater — Maritime Operations Platform
## System Architecture Design

> 국제 해양 표준과 실시간 데이터를 기반으로,
> 해역 전반을 통합 관제하고 안전한 운항과 신속한 의사결정을 지원하는 해양 운영 플랫폼

---

## 목차

1. [플랫폼 개요](#1-플랫폼-개요)
2. [핵심 설계 원칙](#2-핵심-설계-원칙)
3. [시스템 경계 및 서비스 구성](#3-시스템-경계-및-서비스-구성)
4. [데이터 흐름](#4-데이터-흐름)
5. [도메인 모델](#5-도메인-모델)
6. [서비스별 상세 설계](#6-서비스별-상세-설계)
   - [6.1 Moth Bridge](#61-moth-bridge)
   - [6.2 Core Backend](#62-core-backend)
   - [6.3 Agent Runtime](#63-agent-runtime)
   - [6.4 Simulator](#64-simulator)
   - [6.5 Frontend](#65-frontend)
7. [인프라 및 메시지 버스](#7-인프라-및-메시지-버스)
8. [API 설계 개요](#8-api-설계-개요)
9. [기술 스택](#9-기술-스택)
10. [레포지토리 구조](#10-레포지토리-구조)
11. [개발 단계](#11-개발-단계)

---

## 1. 플랫폼 개요

### 운영 범위

**연안 광역 관제 (Coastal VTS)** — 연안 해역에서의 선박 교통 서비스 수준의 통합 관제

### 관제 대상

단순 선박(Vessel)에 국한하지 않고 다양한 해양 플랫폼을 통합 관제한다.

| 유형 | 설명 | 주요 데이터 소스 |
|------|------|------------------|
| Vessel | 일반 선박 (화물, 여객, 어선 등) | AIS/NMEA |
| USV | Unmanned Surface Vehicle | MAVLink, ROS |
| ROV | Remotely Operated Vehicle | ROS, Custom |
| AUV | Autonomous Underwater Vehicle | ROS, MAVLink |
| Drone | 해양 감시 드론 | MAVLink |
| Buoy | 계류 센서 부이 | Custom, NMEA |

### 핵심 기능

1. CPA/TCPA 계산 및 충돌 경보
2. 이상 행동 탐지 (속도 이상, AIS 위조 의심, 표류)
3. 규정 준수 모니터링 (금지구역, 지정 항로)
4. 항로 분석 및 밀집도
5. 교통 흐름 관리 및 항로 최적화
6. 조난 신호 수신 및 대응
7. 실시간 항행 정보 제공
8. 알림 및 경보 시스템
9. 의사결정 지원 (AI)
10. 재생 및 훈련 시뮬레이션
11. 리포팅 및 통계
12. 감사 및 기록 관리

---

## 2. 핵심 설계 원칙

### 프로토콜 불가지론 (Protocol Agnostic)

내부 시스템은 항상 정규화된 `PlatformReport` 포맷만 소비한다.
프로토콜 변환 책임은 **Moth Bridge의 Protocol Adapter**에 격리된다.
새로운 프로토콜 추가 시 어댑터 하나만 추가하면 된다.

### 플랫폼 추상화 (Platform Abstraction)

`Vessel`은 `Platform`의 한 유형이다.
모든 비즈니스 로직은 `Platform` 인터페이스 기준으로 작성되어,
ROV/USV/드론이 추가되어도 핵심 로직 변경이 없다.

### 에이전트 아키텍처 (Agent-First Backend)

백엔드의 모든 분석 모듈은 독립적인 **Agent**로 동작한다.
각 Agent는 개별 토글(활성화/비활성화), 레벨 설정(L1~L3), 상태 모니터링이 가능하다.
Rule 기반 Agent와 AI Agent가 동일한 인터페이스를 공유한다.

### 서비스 독립성

5개 서비스(Moth Bridge, Core Backend, Agent Runtime, Simulator, Frontend)는
각각 독립적으로 배포 및 실행 가능하다.
서비스 간 통신은 **Redis pub/sub** 이벤트 버스와 **REST/WebSocket**으로만 한다.

---

## 3. 시스템 경계 및 서비스 구성

```
외부 세계 (실선박 / 시뮬레이터 / 무인 플랫폼)
│
│  AIS/NMEA    ROS Topics    MAVLink    Custom Binary
│
▼
┌──────────────────────────────────────────────────────────┐
│                  MOTH BRIDGE SERVICE                     │
│                                                          │
│  Moth Server 구독  wss://cobot.center:8287              │
│  채널별 Protocol Adapter (플러그인)                      │
│                                                          │
│  ┌───────────┐ ┌─────────┐ ┌──────────┐ ┌───────────┐  │
│  │ AIS/NMEA  │ │   ROS   │ │ MAVLink  │ │  Custom   │  │
│  │ Adapter   │ │ Adapter │ │ Adapter  │ │  Adapter  │  │
│  └───────────┘ └─────────┘ └──────────┘ └───────────┘  │
│                     ↓ 정규화                             │
│              PlatformReport (내부 공통 포맷)             │
└────────────────────────┬─────────────────────────────────┘
                         │ Redis: platform.report.*
┌────────────────────────▼─────────────────────────────────┐
│                  CORE BACKEND SERVICE                    │
│                                                          │
│  Platform Registry  Track Store  Zone Registry          │
│  REST API           WebSocket    Audit Log              │
│                                                          │
│  (비즈니스 로직 없음 — 데이터 허브 역할)                │
└───────────┬──────────────────────┬───────────────────────┘
            │ Redis Events         │ REST / WebSocket
┌───────────▼───────┐    ┌─────────▼────────────────────────┐
│     FRONTEND      │    │        AGENT RUNTIME SERVICE     │
│                   │    │                                  │
│  MapLibre GL 해도 │    │  Agent Registry + Toggle API     │
│  실시간 선박 오버 │    │  Health Monitor                  │
│  Alert Panel      │    │                                  │
│  Replay Player    │    │  Rule Agents       AI Agents     │
│  Agent 제어 패널  │    │  ┌──────────┐     ┌───────────┐  │
│  Report View      │    │  │ CPA/TCPA │     │ Anomaly   │  │
└───────────────────┘    │  ├──────────┤     ├───────────┤  │
                         │  │ Zone Mon │     │ Route Opt │  │
                         │  ├──────────┤     ├───────────┤  │
                         │  │Compliance│     │ Distress  │  │
                         │  ├──────────┤     ├───────────┤  │
                         │  │ Traffic  │     │ Report Gen│  │
                         │  └──────────┘     └───────────┘  │
                         └──────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│                  SIMULATOR SERVICE                       │
│  (개발/훈련용 독립 실행 환경)                            │
│                                                          │
│  Vessel Physics Engine    Weather Generator             │
│  Scenario Controller      Time Control                  │
│  → Moth Bridge에 퍼블리시 (실선박과 동일 경로 사용)     │
└──────────────────────────────────────────────────────────┘
```

---

## 4. 데이터 흐름

### 실시간 위치 데이터 흐름

```
[선박/플랫폼]
  → AIS/NMEA 송출
  → Moth Server (wss://cobot.center:8287) 채널에 퍼블리시
  → Moth Bridge가 해당 채널 구독
  → Protocol Adapter 적용 → PlatformReport 생성
  → Redis "platform.report.{platform_id}" 퍼블리시
  → Core Backend 구독 → PostgreSQL/TimescaleDB 저장
  → Agent Runtime 구독 → 각 Agent에 이벤트 전달
  → WebSocket → Frontend 실시간 업데이트
```

### 알람 흐름

```
[Agent] 이상 탐지
  → Alert 생성 → Redis "alert.created.{level}"
  → Core Backend 구독 → PostgreSQL 저장
  → WebSocket → Frontend 알람 패널
  → (L3 Agent) 자동 대응 액션 실행
```

### 재생(Replay) 흐름

```
[Frontend] 재생 요청 (시작시각, 종료시각)
  → Core Backend REST API
  → TimescaleDB 시계열 쿼리
  → WebSocket 스트리밍 (재생 속도 적용)
  → Frontend 해도 애니메이션
```

---

## 5. 도메인 모델

### Platform (플랫폼)

```python
class Platform:
    platform_id:    str                     # 고유 식별자 (MMSI 또는 UUID)
    platform_type:  Literal[
                      "vessel", "rov",
                      "usv", "auv",
                      "drone", "buoy"
                    ]
    name:           str
    flag:           str | None              # 국적 (선박의 경우)
    dimensions:     PlatformDimensions | None
    data_source:    str                     # Moth 채널명 or 직접 연결 식별자
    source_protocol: Literal["ais", "ros", "mavlink", "nmea", "custom"]
    capabilities:   list[str]              # ["position", "depth", "camera", "arm"]
    metadata:       dict                   # 프로토콜별 추가 정보
```

### PlatformReport (위치/상태 보고 — 내부 공통 포맷)

```python
class PlatformReport:
    platform_id:    str
    timestamp:      datetime
    # 위치
    position:       GeoPoint              # lat, lon
    depth_m:        float | None          # ROV/AUV 수심
    altitude_m:     float | None          # 드론 고도
    # 운동
    sog:            float | None          # Speed Over Ground (knots)
    cog:            float | None          # Course Over Ground (degrees)
    heading:        float | None          # True Heading (degrees)
    rot:            float | None          # Rate of Turn
    # 상태
    nav_status:     str | None            # AIS Nav Status (0-15)
    # 원본 보존 (정책 기반)
    source_protocol: str
    raw_payload:    bytes | None
```

### Zone (구역)

```python
class Zone:
    zone_id:    str
    name:       str
    zone_type:  Literal[
                  "fairway",          # 지정 항로
                  "restricted",       # 제한구역
                  "prohibited",       # 금지구역
                  "anchorage",        # 앵커리지
                  "tss",              # 분리통항방식
                  "precautionary"     # 주의구역
                ]
    geometry:   GeoJSON Polygon / MultiPolygon
    rules:      list[ZoneRule]        # 속도 제한, 진입 제한 등
```

### Alert (경보)

```python
class Alert:
    alert_id:       str
    alert_type:     Literal[
                      "cpa", "zone_intrusion", "anomaly",
                      "ais_off", "distress", "compliance"
                    ]
    severity:       Literal["info", "warning", "critical"]
    status:         Literal["new", "acknowledged", "resolved"]
    platforms:      list[str]         # 관련 플랫폼 ID
    generated_by:   str               # Agent ID
    message:        str
    recommendation: str | None        # AI Agent의 경우 권고 포함
    timestamp:      datetime
    resolved_at:    datetime | None
```

### Incident (사건)

```python
class Incident:
    incident_id:   str
    incident_type: str
    alerts:        list[str]          # 연관 Alert ID
    platforms:     list[str]
    timeline:      list[IncidentEvent]
    resolved:      bool
    report:        str | None         # AI 생성 보고서
```

### Scenario (훈련 시나리오)

```python
class Scenario:
    scenario_id:    str
    name:           str
    description:    str
    duration_s:     int
    platforms:      list[SimPlatformConfig]   # 초기 위치, 속도, 목적지
    events:         list[ScenarioEvent]       # 특정 시각에 발생할 이벤트
    weather:        WeatherConfig
```

---

## 6. 서비스별 상세 설계

### 6.1 Moth Bridge

**역할**: 외부 데이터 소스를 구독하여 내부 표준 포맷으로 변환

**Moth Server 연결 정보**
- Endpoint: `wss://cobot.center:8287`
- Protocol: RSSP over WebSocket (`/pang/ws/sub`)
- 채널 구독 시: `channel=<type>&name=<name>&track=<track>&mode=single`

**Protocol Adapter 인터페이스**

```python
class ProtocolAdapter(ABC):
    mime_types: list[str]             # 처리 가능한 MIME types

    @abstractmethod
    def parse(self, raw: bytes, mime: str) -> PlatformReport:
        ...
```

**기본 제공 어댑터**

| Adapter | 처리 MIME | 설명 |
|---------|-----------|------|
| `NMEAAdapter` | `application/nmea` | NMEA 0183 AIS 문장 파싱 |
| `AISSentenceAdapter` | `text/plain` | Raw AIS 문장 |
| `MAVLinkAdapter` | `application/mavlink` | MAVLink v2 메시지 |
| `ROSAdapter` | `application/json` | ROS topic JSON 직렬화 |
| `CustomAdapter` | `application/octet-stream` | 사용자 정의 이진 포맷 |

**채널 설정 (config.yaml)**

```yaml
channels:
  - name: "ais-coastal"
    moth_channel: instant
    moth_name: "cowater-ais-stream"
    track: "data"
    adapter: NMEAAdapter
    platform_type: vessel

  - name: "usv-001"
    moth_channel: static
    moth_name: "usv-alpha"
    track: "telemetry"
    adapter: MAVLinkAdapter
    platform_type: usv

  - name: "rov-survey"
    moth_channel: instant
    moth_name: "rov-survey-01"
    track: "ros"
    adapter: ROSAdapter
    platform_type: rov
```

---

### 6.2 Core Backend

**역할**: 데이터 허브. 저장, 조회, 실시간 스트리밍. 비즈니스 로직 없음.

**모듈 구성**

| 모듈 | 역할 |
|------|------|
| `platform_registry` | Platform CRUD, 상태 관리 |
| `track_store` | PlatformReport 시계열 저장 및 조회 |
| `zone_registry` | Zone CRUD, 지형 데이터 관리 |
| `alert_store` | Alert/Incident 저장 및 조회 |
| `audit_log` | 불변 이벤트 로그 |
| `ws_hub` | WebSocket 연결 관리 및 브로드캐스트 |
| `replay_engine` | 시계열 데이터 재생 스트리밍 |

**데이터베이스 구성**

```
PostgreSQL + PostGIS
├── platforms           (플랫폼 레지스트리)
├── zones               (구역 — PostGIS Geometry)
├── alerts              (경보 이력)
├── incidents           (사건 이력)
└── audit_logs          (불변 감사 로그)

TimescaleDB (PostgreSQL Extension)
└── platform_reports    (위치 보고 시계열 — Hypertable)
    └── 파티션: platform_id, 7일 단위

Redis
├── platform:state:{id}     (최신 상태 캐시, TTL 60s)
├── platform.report.*       (위치 보고 이벤트 스트림)
├── alert.created.*         (알람 이벤트 스트림)
└── agent.command.*         (Agent 제어 명령)
```

---

### 6.3 Agent Runtime

**역할**: 분석 에이전트 실행 환경. Agent 등록, 토글, 헬스 모니터링.

**Agent 인터페이스**

```python
class Agent(ABC):
    agent_id:    str
    name:        str
    description: str
    agent_type:  Literal["rule", "ai"]
    level:       Literal["L1", "L2", "L3"]
    enabled:     bool
    config:      dict

    # L1: 감지 → 알람
    # L2: 감지 → 설명과 함께 권고
    # L3: 감지 → 규칙 충족 시 자동 실행

    @abstractmethod
    async def on_platform_report(self, report: PlatformReport): ...

    @abstractmethod
    async def on_alert(self, alert: Alert): ...

    async def health_check(self) -> AgentHealth: ...
```

**기본 Agent 목록**

| Agent | 유형 | 기본 레벨 | 설명 |
|-------|------|-----------|------|
| `CPAAgent` | Rule | L1 | CPA/TCPA 계산, 충돌 위험 경보 |
| `ZoneMonitorAgent` | Rule | L1 | 금지구역/제한구역 침입 감지 |
| `ComplianceAgent` | Rule | L1 | 항로 이탈, 규정 위반 판단 |
| `TrafficFlowAgent` | Rule | L1 | 밀집도 분석, 혼잡 구간 식별 |
| `AnomalyAgent` | AI | L2 | 이상 행동 탐지 + 원인 설명 (Claude) |
| `RouteOptAgent` | AI | L2 | 기상 기반 항로 권고 (Claude) |
| `DistressAgent` | AI | L3 | 조난 신호 수신 + 자동 통보 |
| `ReportAgent` | AI | L2 | 사건 보고서 자동 생성 (Claude) |
| `DecisionSupportAgent` | AI | L2 | 상황 기반 의사결정 보조 (Claude) |

**Agent 제어 API**

```
GET    /agents                    # 전체 Agent 목록 및 상태
GET    /agents/{id}               # Agent 상세 + 헬스
PATCH  /agents/{id}/enable        # 활성화
PATCH  /agents/{id}/disable       # 비활성화
PATCH  /agents/{id}/level         # 자율성 레벨 변경 (L1/L2/L3)
PATCH  /agents/{id}/config        # Agent 설정 변경
GET    /agents/{id}/logs          # Agent 실행 로그
```

**에이전트 자율성 레벨**

```
L1 — Monitor & Alert
  감지 → Alert 생성 → 운영자에게 전달
  예: CPA 임계값 이하 접근 → "충돌 위험" 경보

L2 — Recommend & Explain
  감지 → 원인 분석 → 권고사항 포함한 Alert 생성
  예: "충돌 위험, 우현 15도 변침 권장 (COLREGS Rule 15 기준)"

L3 — Auto-act
  감지 → 사전 정의된 운영 규칙 확인 → 자동 실행
  예: 조난 신호 수신 → 해경/SAR 기관 자동 통보 + 주변 선박 알림
  (L3 전환은 명시적 운영자 승인 필요)
```

---

### 6.4 Simulator

**역할**: 독립 실행 가능한 해양 플랫폼 시뮬레이터 (개발/훈련용)

**모드**

| 모드 | 설명 |
|------|------|
| `data-gen` | AIS 스트림만 생성하여 Moth에 퍼블리시 |
| `scenario` | YAML 시나리오 실행 (이벤트 주입 포함) |
| `replay` | 과거 실제 데이터 재생 |
| `training` | 시간 제어(일시정지/배속), 교관 개입 가능 |

**선박 물리 모델**

```
- 초기 위치, 목적지 설정
- 선박 유형별 최대 속도, 선회율 적용
- Waypoint 기반 자율 항법
- 기상(풍향/풍속, 해류) 영향 적용
- AIS Nav Status 자동 전환 (항행 중 / 정박 / 묘박 등)
```

**시나리오 이벤트 유형**

```yaml
events:
  - at: 300          # 시나리오 시작 후 300초
    type: engine_stop
    platform: vessel-03
    duration: 120

  - at: 600
    type: ais_silence
    platform: vessel-07

  - at: 900
    type: distress_signal
    platform: vessel-02
    position: [126.9, 35.1]
```

**출력**: Moth Server에 AIS/NMEA MIME으로 퍼블리시 → 실제 데이터와 동일한 파이프라인 통과

---

### 6.5 Frontend

**역할**: 실시간 해양 관제 웹 인터페이스

**명령 인터페이스**

```text
voice or typed command
  -> Core /commands
  -> deterministic parser (allowlist)
  -> role check (viewer/operator/admin)
  -> existing Core alert action or Agent Runtime control endpoint
  -> immutable audit_logs append
```

- voice는 transcript만 저장하고 raw audio는 저장하지 않는다.
- executor는 요청 body가 아니라 Bearer token 매핑으로 결정한다.
- 명령 성공/거부/실패를 모두 `audit_logs`에 남긴다.
- 프론트엔드의 음성 입력은 Web Speech API를 사용하지만 실행 경로는 텍스트 명령과 동일하다.

**주요 화면**

| 화면 | 설명 |
|------|------|
| 관제 지도 | MapLibre GL 기반 실시간 플랫폼 오버레이 |
| 알람 패널 | 실시간 경보 목록, 인지/처리 |
| 플랫폼 상세 | 선택 플랫폼 정보, 항적, 이력 |
| 재생 플레이어 | 시간 범위 선택, 배속 재생 |
| Agent 제어판 | Agent 목록, 토글, 레벨 설정 |
| 보고서 뷰어 | AI 생성 사건 보고서 |
| 통계 대시보드 | 교통량, 이벤트 통계 |

**해도 데이터**

- 기본: OpenSeaMap 타일 (즉시 사용 가능)
- 확장: S-57 ENC (Electronic Navigational Chart) 렌더링 (추후)

---

## 7. 인프라 및 메시지 버스

### Docker Compose 서비스 구성

```yaml
services:
  postgres:     # PostgreSQL 15 + PostGIS + TimescaleDB
  redis:        # Redis 7 (메시지 버스 + 캐시)
  core:         # Core Backend (FastAPI)
  moth-bridge:  # Moth Bridge (Python)
  agents:       # Agent Runtime (Python)
  simulator:    # Simulator (Python, 선택적 실행)
  frontend:     # Next.js
```

### Redis 이벤트 채널 정의

| 채널 패턴 | 발행자 | 구독자 | 내용 |
|-----------|--------|--------|------|
| `platform.report.*` | Moth Bridge | Core, Agents | PlatformReport JSON |
| `platform.status.changed` | Core | Frontend WS | 플랫폼 상태 변경 |
| `alert.created.{level}` | Agents | Core, Frontend | Alert 생성 |
| `alert.updated.{id}` | Core | Frontend | Alert 상태 변경 |
| `agent.command.{id}` | Core API | Agent Runtime | Agent 제어 명령 |
| `agent.health.{id}` | Agent Runtime | Core | Agent 헬스 리포트 |

### Command Ingress

운영자 명령 ingress는 `Core /commands` 하나로 통일한다.

- 입력: voice transcript 또는 typed text
- 파싱: allowlist 기반 deterministic intent parser
- 권한: `viewer` / `operator` / `admin` Bearer token
- 실행: 기존 alert action 또는 agent runtime 제어 API 재사용
- 감사: `command.received`, `command.denied`, `command.executed`, `command.failed`

---

## 8. API 설계 개요

### Core Backend REST API

```
# 플랫폼
GET    /platforms                        # 전체 플랫폼 목록 (현재 상태)
GET    /platforms/{id}                   # 플랫폼 상세
GET    /platforms/{id}/track             # 항적 조회 (?from=&to=&interval=)
GET    /platforms/{id}/reports           # 위치 보고 시계열

# 구역
GET    /zones                            # 구역 목록
POST   /zones                            # 구역 등록
PUT    /zones/{id}                       # 구역 수정
DELETE /zones/{id}                       # 구역 삭제

# 경보
GET    /alerts                           # 경보 목록 (?status=&level=&platform=)
GET    /alerts/{id}                      # 경보 상세
PATCH  /alerts/{id}/acknowledge          # 인지 처리
PATCH  /alerts/{id}/resolve              # 처리 완료
POST   /alerts/{id}/action               # workflow action 실행

# 명령
POST   /commands                         # voice/text command 실행 및 audit

# 사건
GET    /incidents                        # 사건 목록
GET    /incidents/{id}                   # 사건 상세 + 보고서

# 재생
POST   /replay/sessions                  # 재생 세션 생성
GET    /replay/sessions/{id}/stream      # WebSocket 재생 스트리밍

# WebSocket 실시간
WS     /ws/positions                     # moth-bridge fast path 위치 스트림
WS     /ws/alerts                        # 실시간 경보
WS     /ws/platforms                     # core canonical 플랫폼 상태
WS     /ws/replay/{session_id}           # 재생 스트림
```

---

## 9. 기술 스택

| 레이어 | 기술 | 선택 이유 |
|--------|------|-----------|
| **Moth Bridge** | Python 3.12 + asyncio + websockets | 비동기 다중 채널 구독 |
| **Core Backend** | FastAPI + Uvicorn | 고성능 비동기 API, WebSocket 지원 |
| **Agent Runtime** | Python 3.12 + asyncio | Anthropic SDK 네이티브 지원 |
| **AI Agents** | Anthropic Claude SDK | claude-haiku-4-5-20251001 |
| **Simulator** | Python 3.12 + pyais | AIS 표준 인코딩 |
| **DB (공간)** | PostgreSQL 15 + PostGIS | Zone 지형 쿼리 |
| **DB (시계열)** | TimescaleDB | 위치 데이터 시계열 최적화 |
| **캐시/이벤트** | Redis 7 | pub/sub + 실시간 상태 캐시 |
| **Frontend** | Next.js 15 + TypeScript | React 기반 SSR/SSG |
| **해도** | MapLibre GL JS | 오픈소스 벡터 타일 렌더링 |
| **UI** | Tailwind CSS + shadcn/ui | 빠른 UI 구성 |
| **상태관리** | Zustand | 경량 클라이언트 상태 |
| **인프라** | Docker Compose | 로컬 통합 실행 |

---

## 10. 레포지토리 구조

```
cowater/
├── services/
│   ├── core/                   # Core Backend
│   │   ├── api/                # FastAPI 라우터
│   │   │   ├── platforms.py
│   │   │   ├── zones.py
│   │   │   ├── alerts.py
│   │   │   ├── replay.py
│   │   │   └── ws.py
│   │   ├── models/             # SQLAlchemy 모델
│   │   ├── services/           # 비즈니스 서비스
│   │   │   ├── track_store.py
│   │   │   ├── zone_service.py
│   │   │   └── replay_engine.py
│   │   ├── db.py
│   │   ├── redis_client.py
│   │   └── main.py
│   │
│   ├── moth-bridge/            # Moth Bridge
│   │   ├── adapters/           # Protocol Adapters
│   │   │   ├── base.py
│   │   │   ├── nmea.py
│   │   │   ├── mavlink.py
│   │   │   ├── ros.py
│   │   │   └── custom.py
│   │   ├── moth_client.py      # RSSP WebSocket 클라이언트
│   │   ├── config.yaml         # 채널-어댑터 매핑
│   │   └── main.py
│   │
│   ├── agents/                 # Agent Runtime
│   │   ├── base.py             # Agent 기본 클래스
│   │   ├── registry.py         # Agent 등록 및 토글
│   │   ├── rule/               # Rule 기반 Agents
│   │   │   ├── cpa_agent.py
│   │   │   ├── zone_monitor.py
│   │   │   ├── compliance.py
│   │   │   └── traffic_flow.py
│   │   ├── ai/                 # AI Agents
│   │   │   ├── anomaly.py
│   │   │   ├── route_opt.py
│   │   │   ├── distress.py
│   │   │   ├── report_gen.py
│   │   │   └── decision_support.py
│   │   └── main.py
│   │
│   ├── simulator/              # 훈련 시뮬레이터
│   │   ├── core/
│   │   │   ├── vessel.py       # 선박 물리 모델
│   │   │   ├── weather.py      # 기상 생성기
│   │   │   └── ais_encoder.py  # NMEA 인코더
│   │   ├── scenarios/          # YAML 시나리오 파일
│   │   │   ├── collision_risk.yaml
│   │   │   ├── distress_response.yaml
│   │   │   └── zone_intrusion.yaml
│   │   ├── moth_publisher.py   # Moth 퍼블리셔
│   │   └── main.py
│   │
│   └── frontend/               # Next.js 관제 UI
│       ├── src/
│       │   ├── app/            # Next.js App Router
│       │   ├── components/
│       │   │   ├── map/        # 해도 컴포넌트
│       │   │   ├── alerts/     # 경보 패널
│       │   │   ├── platforms/  # 플랫폼 상세
│       │   │   ├── replay/     # 재생 플레이어
│       │   │   └── agents/     # Agent 제어판
│       │   └── stores/         # Zustand stores
│       └── package.json
│
├── shared/
│   ├── schemas/                # 공통 데이터 타입 (Python dataclass + JSON Schema)
│   │   ├── platform.py
│   │   ├── report.py
│   │   ├── alert.py
│   │   └── events.py
│   └── events/                 # Redis 이벤트 채널 상수
│       └── channels.py
│
├── infra/
│   ├── docker-compose.yml
│   ├── docker-compose.dev.yml
│   └── postgres/
│       ├── 01_extensions.sql   # PostGIS, TimescaleDB
│       ├── 02_schema.sql
│       └── 03_seed.sql         # 테스트용 Zone 데이터
│
├── docs/
│   └── architecture/
│       └── diagrams/
│
├── ARCHITECTURE.md             # 이 문서
└── 핵심기능.md
```

---

## 11. 개발 단계

### Phase 1 — 기반 (인프라 + 데이터 파이프라인)
1. `infra/` — Docker Compose 구성 (PostgreSQL/PostGIS/TimescaleDB + Redis)
2. `shared/schemas/` — 공통 타입 정의 (PlatformReport, Alert, Event)
3. `services/core/` — 기초 API 서버 (Platform CRUD, Track 저장, WebSocket)
4. `services/moth-bridge/` — Moth 연결 + NMEAAdapter (AIS 수신)

### Phase 2 — 시뮬레이션
5. `services/simulator/` — 가상 선박 생성 → Moth 퍼블리시
6. End-to-End 검증: 시뮬레이터 → Moth → Bridge → Core → WebSocket

### Phase 3 — 분석 엔진
7. `services/agents/` — Agent Runtime + CPAAgent + ZoneMonitorAgent
8. 경보 파이프라인: Agent → Redis → Core → WebSocket

### Phase 4 — 시각화
9. `services/frontend/` — 해도 + 실시간 선박 오버레이
10. Alert Panel, Platform 상세, Agent 제어판

### Phase 5 — 지능화
11. AI Agents (AnomalyAgent, ReportAgent, DecisionSupportAgent)
12. 재생 플레이어, 훈련 시나리오 시스템

### Phase 6 — 확장
13. MAVLink/ROS 어댑터 추가
14. S-57 해도 렌더링
15. 고급 통계 대시보드

---

*last updated: 2026-03-30*
