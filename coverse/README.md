# 🌐 CoVerse: 상황인식 논리적 데이터 공간

## 📋 개요

**CoVerse**는 운영자의 상황 인식을 위해 데이터를 목적 중심으로 재구성하는 기술입니다.

- 현실 공간을 그대로 복제하는 것이 아니라, **판단에 필요한 데이터만 선별**
- 2D, 3D, Graph, Timeline 등 **다양한 View**로 표현 가능
- **데이터와 시각화는 완전히 분리**
- CoWater는 CoVerse를 해양 무인체 운영에 적용한 인스턴스

---

## 📦 구현 현황

### ✅ Phase 1: Entity Store 메모리 프로토타입
- Entity Layer: 엔티티 실시간 상태 관리
- Operation Layer: Mission, Task, Decision Trail 기록
- System Layer: 시스템 건강도 메트릭
- Temporal Layer: 이벤트 타임라인
- Spatial Layer: 위치 관계 계산

### ✅ Phase 2: REST API + Web Dashboard
- Flask 기반 REST API
- 5개 레이어를 시각화하는 웹 대시보드
- 실시간 업데이트 (5초 간격)

### ✅ Phase 3: Web-based REST API 구현
- FastAPI 기반 `/coverse/*` 엔드포인트 추가
- HTML 기반 5개 레이어별 시각화 페이지 구현
- 3D 홀로그래픽 메인 대시보드 구현
- Demo 데이터 자동 초기화

### 🔄 Phase 4: CoWater 실시간 통합 (다음)
- Moth 데이터 → Entity Layer 실시간 연결
- Detection Agent → Decision Trail 통합
- 실제 운영 데이터와 연결

---

## 🚀 시작하기

### 1️⃣ CoWater 등록 서버 시작

```bash
cd /Users/teamgrit/Documents/CoWater/server/registration
python3 device_registration_server.py --port 8000
```

출력:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
```

### 2️⃣ 정적 웹서버로 HTML 파일 제공

```bash
cd /Users/teamgrit/Documents/CoWater/coverse
python3 -m http.server 5000
```

또는 다른 포트:
```bash
python3 -m http.server 5001
```

### 3️⃣ 브라우저에서 CoVerse 접속

메인 대시보드 (3D 홀로그래픽 뷰):
```
http://localhost:5000/index_3d.html
```

간단한 네비게이션 (각 레이어별 링크):
```
http://localhost:5000/index.html
```

**자동으로 Demo 데이터가 로드됩니다!**
- 4개 엔티티 (UUV-001, UUV-002, GATEWAY, SENSOR)
- 1개 미션 및 태스크

---

## 📚 API Endpoints

모든 API는 **http://localhost:8000/coverse*** 경로에 있습니다.

### Core Snapshot
```
GET /coverse/snapshot
```
전체 CoVerse 데이터 (5개 레이어 + 타임스탬프)

**응답:**
```json
{
  "timestamp": "2026-05-19T10:30:00Z",
  "entityLayer": {...},
  "operationLayer": {...},
  "systemLayer": {...},
  "temporalLayer": {...},
  "spatialLayer": {...}
}
```

### 개별 레이어
```
GET /coverse/entity-layer          # Entity Layer
GET /coverse/operation-layer       # Operation Layer (Mission, Task, Decision)
GET /coverse/system-layer          # System Layer (건강도 메트릭)
GET /coverse/temporal-layer        # Temporal Layer (이벤트)
GET /coverse/spatial-layer         # Spatial Layer (거리 관계)
```

### 테스트
```bash
# 전체 스냅샷
curl http://localhost:8000/coverse/snapshot

# 엔티티만
curl http://localhost:8000/coverse/entity-layer

# 의사결정 기록
curl http://localhost:8000/coverse/operation-layer
```

---

## 📊 5개 레이어 설명

### 1️⃣ Entity Layer (실체 상태)
무인체, 센서 등 관리 대상의 현재 상태
- 위치, 센서값, 배터리, 신호 강도 등
- 실시간 데이터 (초 단위 업데이트)

### 2️⃣ Operation Layer + Decision Trail (판단 근거)
시스템이 내린 모든 결정과 그 근거
- Mission: 상위 목표
- Task: 구체적 작업
- **Decision Trail**: 왜 그런 결정을 했는가

**예시:**
```
Monitoring: "배터리 18% < 임계값 20%"
          ↓
Analysis: "우선도 HIGH (원격지 + 낮은 배터리)"
          ↓
Control: "복귀 Task 할당"
```

### 3️⃣ System Layer (시스템 건강도)
시스템 자체의 상태와 성능
- Agent 상태, CPU/메모리, 처리량
- 지연 시간, 에러율, 알람

### 4️⃣ Temporal Layer (시간 흐름)
시스템의 모든 이벤트를 시간 순서대로 기록
- Entity 상태 변화
- Task 상태 변화
- 판단 기록
- 시스템 알람

### 5️⃣ Spatial Layer (공간 관계)
엔티티들 간의 위치 관계
- 각 엔티티 위치 (위도, 경도, 깊이)
- 거리 계산 (Haversine)
- 클러스터링 (선택사항)

---

## 📁 파일 구조

```
coverse/
├── README.md (이 파일)
├── index.html                    # 간단한 네비게이션 (5개 레이어 링크)
├── index_3d.html                 # 메인 3D 홀로그래픽 대시보드
├── test_coverse_store.py         # 메모리 저장소 테스트 스크립트
└── layers/
    ├── 01_entity_layer.html      # 실시간 엔티티 상태 시각화
    ├── 02_operation_layer.html   # 미션/태스크/Decision Trail
    ├── 03_system_layer.html      # 시스템 건강도 모니터링
    ├── 04_temporal_layer.html    # 이벤트 타임라인
    └── 05_spatial_layer.html     # 거리 행렬 및 네트워크 토폴로지

server/shared/storage/
├── coverse_store.py              # 5-레이어 데이터 저장소 (메모리)
└── (다른 저장소 모듈)

server/registration/src/
├── api.py                        # FastAPI 메인 (CoVerse 엔드포인트 추가)
└── (다른 API 엔드포인트)
```

---

## 🔗 다음 단계

### Phase 4: CoWater 실시간 통합
1. **Moth Bridge** → Entity Layer 실시간 연결 (WebSocket)
2. **Detection Agent** → Decision Trail 실시간 통합
3. **Analysis/Control Agent** → Decision Trail 통합
4. 실제 Device/Mission 데이터 피드

### Phase 5: 고급 기능
1. **Leaflet/Mapbox** 통합 (실제 지도 기반)
2. **WebSocket** 실시간 데이터 스트리밍
3. **엔티티 클릭** → 상세 정보 모달
4. **Decision 분석** → 의사결정 대시보드

### Phase 6: 선택적 기능
1. VR/3D 모델 뷰
2. 모바일 반응형 레이아웃
3. 사용자별 커스텀 뷰 (Part Streaming)
4. 실시간 알람 및 안내

---

## 💡 Key Insights

### Decision Trail의 중요성
**상황 인식 = 현재 상태 + 판단 근거**

운영자가 "왜 이렇게 됐는가"를 이해할 때:
- 시스템의 신뢰성 향상
- 필요시 개입 가능
- 패턴 학습 가능
- 이상 판단 감지 가능

### Data와 Viz의 분리
같은 CoVerse 데이터를 다양한 관점으로 표현:
- 실시간 모니터링: 지도/3D 뷰
- 시간 분석: 타임라인
- 시스템 진단: 대시보드
- 리포트: 요약 문서

---

## 🧪 테스트

### 단위 테스트
```bash
python coverse/test_coverse_store.py
```

### API 테스트 (curl)
```bash
# 전체 스냅샷
curl http://localhost:5000/api/coverse/snapshot

# 엔티티 조회
curl http://localhost:5000/api/entities

# 결정 조회
curl http://localhost:5000/api/decisions
```

---

## 📖 관련 문서

- `01-COVERSE_DESIGN.md`: 범용 CoVerse 설계
- `02-DATA_SCHEMA.md`: TypeScript 스키마 정의
- `03-DATA_FLOW.md`: Decision Trail 상세 흐름
- `04-COWATER_MAPPING.md`: CoWater 통합 계획

---

## 📝 License

CoWater Project

---

**만든이:** Claude (AI)  
**최종 업데이트:** 2026-05-19
