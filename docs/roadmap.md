# CoWater 로드맵 (Roadmap)

**최종 업데이트**: 2026-05-12  
**상태**: Phase 1 설계 완료 → Phase 2 구현 준비

---

## 📊 진행 상황 요약

```
Phase 1: Design & Architecture     ✅ 2026-05-12 완료
├─ ✅ ADR-001~006 정의
├─ ✅ 5대 설계 철학 확정
├─ ✅ 14개 데이터 모델 정의
├─ ✅ 5개 시나리오 프로세스 문서화
└─ ✅ 설계 원칙 체계화

Phase 2: Core Implementation      🚀 2026-05-12 ~ 2026-08-31
Phase 3: Advanced Features        📅 2026-09-01 이후
```

---

## ✅ 완료 (2026-05-12)

### 핵심 설계 아키텍처

- **[ADR-001: Core Design Philosophy](adr/ADR-001-core-design-philosophy.md)**
  - 5대 핵심 철학 확정
  - Action Abstraction, Decoupling, Inter-Agent Collaboration, Event-Based Traceability, Bridge the Gap
  
- **[ADR-002~006: 아키텍처 결정](adr/ADR-000-index.md)**
  - Proposal as Solution Set
  - Capability-Driven Task Assignment
  - Agent Endpoint Management
  - Event-Triggered Rule Execution
  - Adaptive Autonomy Migration Path

### 데이터 모델 & 도메인

- **[principles.md](core/principles.md)**
  - 5대 철학 상세 설명
  - 10가지 설계 원칙
  - 역할 정의 (User, System Agent, Device Agent, Middle-layer Agent)

- **[schema.md](core/schema.md)**
  - 14개 데이터 모델 정의
  - Device, Proposal, Mission, Task, Event, Alert, Insight, AgentConnection 등

- **[domain-model.md](core/domain-model.md)**
  - 엔티티 간 관계
  - 상태 다이어그램 (UML)
  - AgentConnection 동적 관리 전략

### 시나리오 & 프로세스

- **[lifecycle.md](scenarios/lifecycle.md)**: Device 생명주기 (등록→준비→운영→제거)
- **[operation.md](scenarios/operation.md)**: 사용자 명령 → Proposal → Mission → Task 실행 흐름
- **[exceptions.md](scenarios/exceptions.md)**: 예외 상황 처리 (LOST, OFFLINE, CRITICAL_HAZARD)
- **[reporting.md](scenarios/reporting.md)**: Event 기록, Report 생성, 실패 분석, 피드백 수집
- **[administration.md](scenarios/administration.md)**: 시스템 설정, 정책 관리, 승인 규칙

---

## 🚀 Phase 2: Core Implementation (2026-05-13 ~ 2026-08-31)

### Q2 2026 (2026-05-13 ~ 2026-07-31)

#### 2-1. Backend Core (FastAPI)
- [ ] **Registry Server 구현**
  - Device, Mission, Task 상태 관리
  - Event, Alert, Insight 저장소
  - Transaction 기반 일관성 보장
  - 예상: 3주

- [ ] **System Agent 구현**
  - Proposal 생성 로직 (LLM 기반)
  - Task 할당 알고리즘 (Capability-Driven)
  - Rule Engine (Event 기반 Policy 실행)
  - 예상: 4주

- [ ] **Device Agent Framework**
  - Base Device Agent 클래스
  - Task 수행 판단 로직
  - 로컬 Failsafe 정책
  - Edge-Side Resilience 구현
  - 예상: 3주

- [ ] **A2A 메시징 (Moth 통합)**
  - Agent 간 메시지 전달
  - A2A 로깅
  - 통신 실패 재시도
  - 예상: 2주

#### 2-2. Frontend Core (Next.js)
- [ ] **Proposal 승인 화면**
  - 여러 솔루션 세트 비교
  - 선택, 수정, 거절 UI
  - 예상: 2주

- [ ] **Mission 추적 대시보드**
  - Mission 상태, Step, Task 트리
  - Timeline 표시
  - Device 위치 지도
  - 예상: 3주

- [ ] **Alert & Exception 관리**
  - Alert 목록 및 세부 정보
  - 자동 대응 로그
  - Override UI
  - 예상: 2주

#### 2-3. 통합 테스트
- [ ] **시뮬레이션 Device Agent** (테스트용)
  - USV, AUV, ROV 시뮬레이터
  - 예상: 2주

- [ ] **엔드투엔드 시나리오 테스트**
  - Device 등록 → Proposal → Mission → Task 실행
  - 예상: 2주

### Q3 2026 (2026-08-01 ~ 2026-08-31)

#### 3-1. Phase 1 → Phase 2 전환
- [ ] **자동화 정책 구현**
  - LOW_BATTERY → RETURN_TO_BASE 자동 Mission
  - CRITICAL_HAZARD → EMERGENCY_STOP 자동 Mission
  - 예상: 2주

- [ ] **User Feedback Loop**
  - Feedback 수집 UI
  - Improvement 후보 추적
  - 예상: 1주

- [ ] **모니터링 & 분석**
  - Mission 성공률 추적
  - Task 실패 원인 분석
  - Device 성능 지표
  - 예상: 2주

#### 3-2. 성능 최적화
- [ ] **Registry Query 최적화**
  - 인덱싱 전략
  - 캐싱 (Redis)
  - 예상: 1주

- [ ] **Mission/Task 계획 최적화**
  - Device 선택 알고리즘 고도화
  - 예상: 1주

---

## 📅 Phase 3: Advanced Features (2026-09-01 이후)

### Q4 2026

- [ ] **Middle-layer Agent 강화**
  - Relay 기반 미션 관리
  - 예상: 3주

- [ ] **Advanced AgentConnection Types**
  - LEADER_FOLLOWER 협력
  - SHARE_DATA 센서 통합
  - 예상: 2주

- [ ] **Multi-Domain Coordination**
  - USV-AUV-ROV 복합 미션
  - 예상: 3주

### 2027 Q1

- [ ] **AI 기반 정책 학습**
  - Soul.md 기반 Policy 개선
  - 사용자 피드백 기반 추천 고도화
  - 예상: 4주

- [ ] **High Availability & Resilience**
  - Registry 복제
  - Failover 전략
  - 예상: 2주

- [ ] **권한 관리 (ADMIN/OPERATOR/VIEWER)**
  - 역할 기반 접근 제어
  - 감사 로그
  - 예상: 2주

---

## 🎯 마일스톤

| 날짜 | 마일스톤 | 상태 |
|------|---------|------|
| 2026-05-12 | **Design Complete** (ADR 6개, 시나리오 5개) | ✅ |
| 2026-06-30 | **Core Backend MVP** (Registry, System Agent, Device Agent) | 🚀 |
| 2026-07-31 | **Core Frontend MVP** (Proposal, Mission, Alert UI) | 🚀 |
| 2026-08-31 | **Phase 2 완료** (자동화 정책, 모니터링) | 🚀 |
| 2026-09-30 | **Phase 3 시작** (Advanced Features) | 📅 |
| 2027-01-31 | **AI 기반 정책 학습** | 📅 |

---

## 🔧 기술 부채 & 개선

### 높은 우선순위
- [ ] **테스트 커버리지** (목표: 80%)
  - Unit 테스트
  - Integration 테스트
  - E2E 시나리오 테스트

- [ ] **API 문서화** (OpenAPI/Swagger)
  - Registry Server API
  - System Agent API
  - Device Agent API

- [ ] **에러 처리 표준화**
  - 일관된 에러 코드
  - 에러 메시지 가이드라인

- [ ] **로깅 & Observability**
  - 구조화된 로깅
  - 분산 추적 (Tracing)
  - 메트릭 수집 (Prometheus)

### 중간 우선순위
- [ ] **성능 벤치마킹**
  - Mission 생성 지연시간
  - Task 할당 지연시간
  - Registry 조회 성능

- [ ] **배포 자동화**
  - CI/CD 파이프라인
  - 컨테이너화 (Docker)
  - 쿠버네티스 배포

- [ ] **통신 신뢰성**
  - Message Queue (RabbitMQ, Kafka)
  - Retry 정책
  - Dead Letter Queue

### 낮은 우선순위
- [ ] **UI/UX 개선**
  - Dark Mode
  - Mobile Responsive
  - Accessibility

- [ ] **성능 최적화**
  - Frontend 번들 최적화
  - DB 쿼리 최적화
  - Caching 전략

---

## 📚 핵심 문서

### 아키텍처
- [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) - 전체 개요
- [ADR 색인](adr/ADR-000-index.md) - 아키텍처 결정 기록
- [설계 원칙](core/principles.md) - 5대 철학 + 10가지 원칙

### 구현 기준
- [도메인 모델](core/domain-model.md) - 엔티티 관계
- [데이터 스키마](core/schema.md) - 14개 모델 정의

### 운영 프로세스
- [Device Lifecycle](scenarios/lifecycle.md)
- [Operation Workflow](scenarios/operation.md)
- [Exception Handling](scenarios/exceptions.md)
- [Reporting & Analytics](scenarios/reporting.md)
- [Administration](scenarios/administration.md)

---

## 🎓 참고: 현재 구현 상태

현재 (2026-05-12):
- ✅ **설계 아키텍처**: 100% 완료
- 🚀 **Backend 구현**: 준비 단계
- 🚀 **Frontend**: 준비 단계
- 📊 **POC 07**: 실시간 시각화 (Moth 통합) 완료

---

## 📝 피드백 및 개선

로드맵에 대한 피드백:
- 기술 기준 변경 사항은 해당 ADR 또는 설계 원칙 문서 업데이트
- 구현 일정 변경은 마일스톤 재평가 필요
- 새로운 요구사항은 ADR-007+ 추가 검토

---

**다음 단계**: Phase 2 구현 착수 (2026-05-13)
