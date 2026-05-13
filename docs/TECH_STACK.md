# CoWater 기술 스택 (Technology Stack & Communication)

**문서 버전**: v1.0 (설계 기반 - 경량)  
**최종 업데이트**: 2026-05-12  
**목적**: Phase 1에서 필요한 통신 방식과 기술만 정의

---

## 📋 요약

| 항목 | 내용 | 상태 |
|------|------|------|
| **Backend** | FastAPI | ✅ 선택 |
| **Database** | SQLite (또는 PostgreSQL) | ✅ 선택 |
| **Real-time** | Moth WebSocket Pub-Sub | ✅ 이미 운영 중 |
| **Frontend** | 미정 (Phase 2) | 📅 나중 |
| **API** | REST (GraphQL은 Phase 2) | ✅ REST 우선 |

---

# 섹션 1: 통신 방식 (Communication Protocol)

## 📋 통신 방식 요약

| 통신 경로 | 프로토콜 | 용도 | 특징 |
|----------|---------|------|------|
| **Device Agent ↔ System Agent** | A2A Protocol (HTTP) | Task 할당/결과 보고 | 동기식, 요청-응답 |
| **System Agent ↔ Registry** | REST API (HTTP) | 상태 조회/저장 | RESTful 설계 |
| **모든 Agent 간 실시간** | Moth WebSocket Pub-Sub | 텔레메트리, 헬스신호 | 비동기, 양방향 |
| **Web Client** | 향후 (Phase 2) | Dashboard | REST 또는 GraphQL |

---

## 1️⃣ A2A Protocol (Agent-to-Agent) - HTTP 기반

**목적**: Device Agent ↔ System Agent 간 Task 할당 및 결과 보고

**기반**: HTTP/REST  
**방식**: 동기식 (요청 → 응답)  
**데이터 포맷**: JSON

### 주요 엔드포인트
```
POST   /task              # Task 할당
       Payload: { mission_id, task_id, required_action, ... }
       
GET    /health            # 헬스 체크
       Response: { device_id, online, battery, ... }
       
POST   /result            # Task 결과 보고
       Payload: { task_id, status, result_data, ... }
```

### 특징
- Device Agent가 System Agent의 엔드포인트 호출
- Timeout 설정 필요 (오프라인 감지)
- 정책 검증은 System Agent에서 수행

### 향후 확장 (Phase 2+)
- API Gateway 추가 가능 (정책 중앙화)
- 필요시 추가 (현재는 불필요)

---

## 2️⃣ REST API (System Agent ↔ Registry) - HTTP 기반

**목적**: 공용 상태 저장소 접근

**기반**: HTTP/REST (표준)  
**방식**: RESTful 설계  
**데이터 포맷**: JSON

### 주요 엔드포인트
```
GET    /devices              # 디바이스 조회
GET    /missions             # 미션 조회
POST   /missions             # 미션 생성
PUT    /missions/{id}        # 미션 상태 업데이트
GET    /events               # Event 로그
POST   /events               # Event 기록
```

### 특징
- RESTful 설계 (리소스 기반)
- Registry가 Single Source of Truth
- System Agent는 Registry에 모든 상태 저장
- 캐싱 가능 (GET 요청)

---

## 3️⃣ Moth WebSocket Pub-Sub - 실시간 메시징

**목적**: 모든 Agent 간 양방향 실시간 통신

**서버**: `wss://cobot.center:8287` (외부 운영)  
**기반**: WebSocket (표준)  
**방식**: Pub-Sub (비동기)  
**데이터 포맷**: JSON

### 토픽 구조
```
DEVICE_HEALTHCHECK                  # 모든 디바이스 헬스신호
ENV_STATE_CHANGED                  # 환경 상태 변화 이벤트
DEVICE_TELEMETRY_{device_id}_{type} # 특정 디바이스 텔레메트리
a2a.{source_agent}.{target_agent}   # Agent 간 메시지 (선택)
```

### 특징
- 발행-구독 메커니즘 (구독한 토픽만 수신)
- 비동기 (응답 기다리지 않음)
- 실시간 스트리밍에 최적화
- 지속성 미보장 (오프라인 메시지 손실 가능)

---

## 4️⃣ Web Client 통신 (향후 Phase 2)

**현재**: 미정  
**계획**: Frontend 구현시 결정
- Option A: REST API (A2A Protocol 재사용)
- Option B: GraphQL (별도 엔드포인트)

---

## 5️⃣ Device Agent ↔ Device Agent (AgentConnection 기반 물리 통신)

**목적**: Device 간 협력 (중계, 동기화, 데이터 공유 등)

**기반**: AgentConnection.profile (Registry에서 조회)  
**방식**: Registry → 연결 정보 제공 → Device Agent가 물리층 드라이버 선택  
**데이터 포맷**: Device별 (바이너리, JSON 등)

### 흐름
```
1. Device Agent A
   └─ REST로 Registry 요청
      "Device B와 협력하려면 연결 정보 줄래?"
      
2. Registry (AgentConnection 저장소)
   └─ AgentConnection.profile 응답:
      {
        "device_id": "ROV-1",
        "endpoint": "192.168.1.50:9111",
        "network_type": "acoustic",
        "transport": "acoustic_modem",
        "latency_ms": 500,
        "signal_strength": 85
      }
      
3. Device Agent A
   └─ profile.network_type에 맞는 드라이버 선택
   └─ profile.endpoint로 Device B와 물리 통신 시작
```

### 지원 네트워크 타입

| Type | 용도 | 특징 | 드라이버 |
|------|------|------|---------|
| **wired** | 유선 (Ethernet, USB) | 낮은 지연, 높은 대역폭 | HTTP, Serial |
| **acoustic** | 음파 (수중) | 높은 지연(초~분), 낮은 대역폭 | Acoustic Modem 드라이버 |
| **rf** | 무선 (WiFi, RF) | 중간 지연, 신호 감쇠 | RF 모듈 드라이버 |
| **satellite** | 위성 | 매우 높은 지연(초), 제한 대역폭 | Satellite 모듈 드라이버 |

### 특징
- **Registry가 중앙 집중식 연결 관리** (모든 Device 간 협력 정보 보유)
- **Device Agent가 자율적으로 드라이버 선택** (물리층 추상화)
- **새로운 네트워크 타입 추가 용이** (profile 확장, 코드 변경 없음)

---

## 6️⃣ Device ↔ Physical Device (내부)

**책임**: Device Agent가 각자 구현  
**방식**: Serial, Modbus, MQTT 등 (Device 타입별)  
**System Agent는 관여 안 함**

---

## 📊 통신 흐름 (Task 할당 예시)

```
1. System Agent (Policy 검증)
   └─ A2A Protocol (HTTP)로 Task 할당
      ↓
2. Device Agent (ROV-1)
   └─ Task 수락
   └─ Moth (WebSocket)로 진행 상황 실시간 발행
      ↓
3. System Agent
   └─ Moth 구독으로 모니터링
   └─ REST API로 Registry에 상태 업데이트
      ↓
4. Device Agent
   └─ Task 완료
   └─ A2A Protocol (HTTP)로 결과 보고
      ↓
5. System Agent
   └─ REST API로 Registry에 최종 상태 저장
```

---

# 섹션 2: 기술 스택 (Technology Stack)

## 0️⃣ 물리 통신 매체 관리 (Physical Media Management)

### 매체별 우선순위 및 특성

| 매체 | 우선순위 | 환경 | 대역폭 | 지연 | 사용 사례 | 자세히 |
|-----|---------|------|--------|------|---------|--------|
| **Wired** | 1순위 | - | 매우 높음 | 극저 | ROV 테더, 충전 스테이션 | [ADR-009](../adr/ADR-009-physical-communication-routing.md) |
| **RF/Internet** | 2순위 | Surface | 높음 | 저 | 수상 AUV/USV | [ADR-009](../adr/ADR-009-physical-communication-routing.md) |
| **Acoustic** | 3순위 | Submerged | 낮음 | 높음 | 수중 AUV, 음파 통신 | [ADR-009](../adr/ADR-009-physical-communication-routing.md) |

### 동적 선택 로직

System Agent가 AgentConnection 생성 시:
1. **Gateway 확인** (ROV의 부모는 USV)
2. **매체 교집합** (둘 다 지원하는 매체만)
3. **환경별 필터** (수중 = acoustic만, 수면 = 전부)
4. **우선순위 선택** (Wired > RF > Acoustic)

---

## 1️⃣ Backend Framework

### 선택: **FastAPI**

**이유**:
- 빠름 (Python 중 가장 빠른 프레임워크)
- 간단함 (코드 작성 쉬움)
- 자동 문서화 (API 테스트 편함)
- 비동기 지원 (여러 요청 동시 처리)

**다른 선택지**:
- Flask: 더 가볍지만 기능 적음
- Django: 더 많지만 무거움 (오버킬)

---

## 2️⃣ Database

### 선택: **SQLite (Phase 1) → PostgreSQL (필요시)**

**Phase 1 (지금): SQLite**

**이유**:
- 파일 1개만 필요 (설정 없음)
- 개발/테스트 편함
- 단일 Registry 서버일 때 충분

**언제 PostgreSQL로 바꿀까?**
- 여러 Registry 서버 필요할 때
- 동시 쓰기 많을 때
- 대규모 데이터 저장할 때

**Phase 2+**: 필요하면 마이그레이션

---

## 3️⃣ Real-time Messaging

### 확정: **Moth WebSocket Pub-Sub**

**상태**: ✅ 이미 운영 중 (외부 서버)  
**서버**: `wss://cobot.center:8287`

**특징**:
- 모든 Agent이 동시에 정보 공유
- 실시간 텔레메트리 스트림
- 오프라인 복구 시 재동기화

**선택 여지 없음** (기존 인프라 활용)

---

## 4️⃣ Frontend (Phase 2)

**선택**: **Next.js**

**이유**:
- React 기반 (배우기 쉽고, 생태계 크다)
- SSR 지원 (성능, SEO)
- API Route 내장 (System Agent 연결 간단)
- TypeScript 표준 (타입 안정성)
- 모던 (2025년 기준)

**주요 라이브러리**:
- React 18+ (UI)
- TypeScript (타입 안정성)
- Tailwind CSS (스타일링) - 선택
- Socket.io 또는 websocket (Moth 연결)
- Axios 또는 Fetch (REST API)

**구성**:
```
/app
  /api          # API Route (System Agent 중간 계층)
  /dashboard    # 메인 대시보드
  /proposals    # Proposal 승인 화면
  /missions     # Mission 추적
  /devices      # Device 상태 관리
```

---

## 5️⃣ Frontend API (Phase 2)

**선택**: **REST API** (Phase 2) → GraphQL (Phase 3, 선택)

**Phase 2 (REST)**:
- System Agent의 기존 REST API 재사용
- Next.js API Route에서 프록시 (선택사항)
- 간단함, 빠른 구현

**Phase 3 (GraphQL, 선택사항)**:
- 복잡한 쿼리 필요시 마이그레이션
- Strawberry GraphQL (Python, System Agent)
- Apollo Client (JavaScript, Next.js)

---

## 6️⃣ 의도적으로 제외한 것

| 기술 | 이유 | 필요 시점 |
|------|------|---------|
| **Cache (Redis)** | 아직 필요 없음 | Phase 3 (성능 병목시) |
| **ORM** | 아직 필요 없음 | 데이터 복잡도 증가시 |
| **Docker/K8s** | 개발 복잡도 증가 | 배포 자동화 필요시 |
| **Message Queue** | Moth가 이미 커버 | 특수한 경우 |

---

## 📦 최소 요구사항

**개발**:
- Python 3.10+
- FastAPI + uvicorn
- SQLite (내장)

**런타임**:
- Python 3.10+
- 필요한 패키지 (requirements.txt)
- 인터넷 (Moth 서버)

---

## 🚀 Phase별 기술 스택

```
Phase 1 (지금):
├─ Backend: FastAPI ✅
├─ Database: SQLite ✅
├─ Real-time: Moth ✅
└─ Frontend: ❌ (아직 필요 없음)

Phase 2 (Frontend 구현):
├─ Backend: FastAPI (유지)
├─ Database: SQLite (유지) 또는 PostgreSQL (필요시)
├─ Real-time: Moth (유지)
├─ Frontend: Next.js ✅
├─ Frontend 라이브러리: React 18+, TypeScript, Tailwind CSS
└─ API: REST (System Agent 기존 API 재사용)

Phase 3 (확장, 선택사항):
├─ 기존 기술 유지
├─ API: GraphQL 추가 (복잡한 쿼리 필요시)
├─ Cache: Redis (성능 최적화)
├─ ORM: SQLAlchemy (데이터 복잡도 증가시)
└─ Container: Docker/K8s (배포 자동화)
```

---

## ✅ 기술 선택 원칙

**언제 기술을 바꾸나?**
1. 명확한 성능 병목 (실제 측정)
2. 운영 복잡도 증가
3. 팀의 필요성

**절대 안 하는 것**:
- ❌ 예상으로 바꾸기 (측정 먼저)
- ❌ "더 좋은 기술"로 바꾸기
- ❌ 아직 필요 없는데 미리 추가

---

## 📝 최종 정리

| 항목 | 선택 | 이유 | 변경 시점 |
|------|------|------|---------|
| **Backend** | FastAPI | 빠르고 간단함 | 성능 병목시 (드물 예상) |
| **Database** | SQLite → PostgreSQL | 단일 서버 → 분산 | 확장 필요시 (Phase 3+) |
| **Real-time** | Moth | 기존 인프라 | 변경 불필요 |
| **Frontend** | Next.js | React 기반, SSR, 모던 | Phase 2 시작 |
| **Frontend 라이브러리** | React 18+, TypeScript, Tailwind | 표준 스택 | Phase 2 시작 |
| **Frontend API** | REST (Phase 2) → GraphQL (Phase 3) | 간단 → 복잡 진화 | Phase 3 (선택) |

---

## 참고

- [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) - 전체 아키텍처
- [COMMUNICATION_PROTOCOL.md](COMMUNICATION_PROTOCOL.md) - 상세 통신 방식 (향후 추가 가능)
- [roadmap.md](roadmap.md) - 구현 계획
