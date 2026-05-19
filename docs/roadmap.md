# CoWater 로드맵

**최종 업데이트**: 2026-05-12  
**목적**: 완료된 설계 범위와 앞으로의 구현 우선순위를 한눈에 정리한다.

---

## 현재 상태

- 설계와 아키텍처 문서화는 완료됨
- 핵심 구현은 아직 본격 착수 전 준비 단계
- 로드맵은 `완료`, `단기 구현`, `중기 확장`, `기술 부채`로만 관리함

### 진행 요약

| 구분              | 상태    | 비고                                          |
| ----------------- | ------- | --------------------------------------------- |
| Phase 1 설계      | ✅ 완료 | ADR, 도메인 모델, 시나리오 문서 정리 완료     |
| Phase 2 핵심 구현 | 🚀 예정 | Registry, System Agent, Device Agent, 기본 UI |
| Phase 3 고급 확장 | 📅 예정 | 조건부 미션, 고가용성, 정책 학습              |

---

## 완료

### 설계와 아키텍처

- [ADR-001: CoWater의 핵심 설계 철학](adr/ADR-001-core-design-philosophy.md)
- [ADR-002~006 색인](adr/ADR-000-index.md)
- [설계 원칙](core/principles.md)
- [데이터 스키마](core/schema.md)
- [도메인 모델](core/domain-model.md)

### 운영 시나리오와 프로세스

- [Device 생명주기](scenarios/lifecycle.md)
- [운영 흐름](scenarios/operation.md)
- [예외와 자동 대응](scenarios/exceptions.md)
- [기록과 분석](scenarios/reporting.md)
- [관리와 설정](scenarios/administration.md)

---

## 단기 구현 우선순위

### 1. 공통 인프라

- [ ] `moth_client.py`
  - MEB pub/sub 클라이언트
  - 단일 `agents` 채널 구독/발행
  - 재연결 로직 포함

- [ ] `llm_client.py`
  - Ollama 클라이언트
  - Circuit Breaker, 재시도, timeout
  - JSON 파싱과 유효성 검사

- [ ] `registry_client.py`
  - Registry REST API 클라이언트
  - Device, Mission, Task, Event 조회/생성/업데이트
  - AgentConnection CRUD

- [ ] `base_agent.py`
  - BaseAgent 공통 클래스
  - `init`, `start`, `call_llm`, `publish_event`
  - MEB 구독 패턴
  - 메모리 캐시 기반 상태 관리

- [ ] `config.yaml`
  - 포트, Registry, LLM, Moth 설정

### 2. System Agent 6개 구현

#### RequestHandler

- [ ] Intent 분류 LLM 프롬프트
- [ ] `/agents/{token}/command` 엔드포인트
- [ ] `SYS_INTENT_CLASSIFIED` 발행
- [ ] Fleet 상태 요약 API

#### MissionPlanner

- [ ] 3단계 Proposal 생성: 규칙 기반 + LLM + 검증
- [ ] 여러 대안 생성: 최적 / 빠른 / 안전
- [ ] `SYS_INTENT_CLASSIFIED`, `SYS_TASK_COMPLETED`, `SYS_TASK_FAILED`, `SYS_ANOMALY_DETECTED`, `SYS_POLICY_DECISION` 구독
- [ ] `SYS_MISSION_UPDATED` 발행
- [ ] Mission 생명주기 관리

#### DeviceBridge

- [ ] `POST /message:send` A2A 엔드포인트
- [ ] `task.assign`, `task.result`, `child.register`, `layer.assignment` 처리
- [ ] Device endpoint 관리
- [ ] `SYS_TASK_DISPATCHED`, `SYS_TASK_COMPLETED`, `SYS_TASK_FAILED` 발행

#### PolicyManager

- [ ] Policy 등록과 관리
- [ ] LLM 기반 Policy 매칭
- [ ] `auto_execute` 정책 실행
- [ ] `SYS_INTENT_CLASSIFIED`, `SYS_ANOMALY_DETECTED` 구독
- [ ] `SYS_POLICY_DECISION` 발행

#### SystemSentinel

- [ ] Device 건전성 감시 루프
- [ ] 규칙 기반 이상 탐지: 배터리, Heartbeat, 센서
- [ ] AgentConnection 3단계 필터링: Gateway, 매체, 환경
- [ ] LLM 기반 복합 패턴 분석
- [ ] `DEVICE_HEALTHCHECK`, `ENV_STATE_CHANGED`, `SYS_TASK_DISPATCHED`, `SYS_TASK_COMPLETED`, `SYS_TASK_FAILED` 구독
- [ ] `SYS_ANOMALY_DETECTED`, `SYS_AGENT_CONNECTION_*` 발행

#### InsightReporter

- [ ] Mission, Device, Event 조회
- [ ] LLM 기반 한국어 리포트 생성
- [ ] Registry 실시간 조회 기반 stateless 동작
- [ ] 주요 이벤트 구독

### 3. 통합과 E2E 검증

- [ ] 포트별 응답성 확인: `9110~9114`, `9116`
- [ ] LLM 호출 timeout 처리 확인
- [ ] MEB 이벤트 발행/수신 검증
- [ ] Intent classified → MissionPlanner → Proposal 생성
- [ ] Policy decision → Policy 자동 실행
- [ ] Anomaly detected → Alert + 자동 대응
- [ ] 사용자 명령 → Proposal → Mission → Task → Device 실행 → 결과 보고
- [ ] Device offline, Task timeout, Policy escalation 오류 흐름 검증
- [ ] Multi-hop relay: `Device A → Device B → DeviceBridge`

### 4. 프론트엔드와 시뮬레이션

- [ ] Proposal 승인 화면
  - 여러 솔루션 세트 비교
  - 선택, 수정, 거절 UI

- [ ] Mission 추적 대시보드
  - Mission 상태, Step, Task 트리
  - Timeline 표시
  - Device 위치 지도

- [ ] Alert와 Exception 관리 화면
  - Alert 목록과 세부 정보
  - 자동 대응 로그
  - Override UI

- [ ] 시뮬레이션 Device Agent
  - USV, AUV, ROV 시뮬레이터

- [ ] 엔드투엔드 시나리오 테스트
  - Device 등록 → Proposal → Mission → Task 실행

---

## 중기 확장

### 자동화와 운영 고도화

- [ ] 자동화 정책 구현
  - `SYS_ANOMALY_DETECTED(anomaly_type=LOW_BATTERY)` → `RETURN_TO_BASE`
  - `SYS_ANOMALY_DETECTED(anomaly_type=CRITICAL_HAZARD)` → `EMERGENCY_STOP`

- [ ] 사용자 피드백 루프
  - Feedback 수집 UI
  - Improvement 후보 추적

- [ ] 모니터링과 분석
  - Mission 성공률 추적
  - Task 실패 원인 분석
  - Device 성능 지표

### 성능 최적화

- [ ] LLM 호출 최적화
  - 응답 캐싱
  - 중복 Proposal 생성 호출 감소
  - 프롬프트 템플릿 최적화

- [ ] Registry 조회 최적화
  - 인덱싱 전략
  - Redis 캐싱

- [ ] Mission과 Task 계획 최적화
  - Device 선택 알고리즘 고도화

### 관찰성과 메트릭

- [ ] LLM 성능 메트릭
  - 성공률과 실패율
  - 평균 응답 시간
  - Circuit Breaker 상태
  - 에러 유형별 분류

- [ ] System Agent 메트릭
  - Mission 생성 지연시간
  - Proposal 생성 지연시간
  - Policy 평가 시간
  - 이벤트 처리량

- [ ] 대시보드와 알림
  - Prometheus 메트릭 내보내기
  - Grafana 대시보드
  - 알림 규칙

### 고급 기능

- [ ] Conditional Mission
  - 자연어 기반 조건부 명령
  - Task 결과 기반 다음 Task 자동 실행
  - PolicyManager Rule + Task chaining

- [ ] 해역 표준/별칭 관리 기능
  - 표준 해역 집합과 좌표 범위 등록/수정
  - `울릉도 근해` 같은 별칭을 표준 해역으로 매핑
  - Agent Skill 또는 전용 운영 도구로 해역 정보 변경 이력 관리

- [ ] Middle-layer Agent 강화
  - Relay 기반 미션 관리

- [ ] Advanced AgentConnection Types
  - `LEADER_FOLLOWER`
  - `SHARE_DATA`

- [ ] Multi-Domain Coordination
  - USV, AUV, ROV 복합 미션

- [ ] AI 기반 정책 학습
  - 사용자 피드백 기반 추천 고도화

- [ ] High Availability와 Resilience
  - Registry 복제
  - Failover 전략

- [ ] 권한 관리
  - `ADMIN`, `OPERATOR`, `VIEWER`
  - 역할 기반 접근 제어
  - 감사 로그

---

## 기술 부채와 운영 개선

### 높은 우선순위

- [ ] 테스트 커버리지 확대
  - Unit 테스트
  - Integration 테스트
  - E2E 시나리오 테스트

- [ ] API 문서화
  - Registry Server API
  - System Agent API
  - Device Agent API

- [ ] 에러 처리 표준화
  - 일관된 에러 코드
  - 에러 메시지 가이드라인

- [ ] 로깅과 Observability
  - 구조화된 로깅
  - 분산 추적
  - Prometheus 메트릭 수집

### 중간 우선순위

- [ ] 성능 벤치마킹
  - Mission 생성 지연시간
  - Task 할당 지연시간
  - Registry 조회 성능

- [ ] 배포 자동화
  - CI/CD 파이프라인
  - Docker 컨테이너화
  - Kubernetes 배포

- [ ] 통신 신뢰성
  - Message Queue
  - Retry 정책
  - Dead Letter Queue

### 낮은 우선순위

- [ ] UI/UX 개선
  - Dark Mode
  - Mobile Responsive
  - Accessibility

- [ ] 추가 성능 최적화
  - Frontend 번들 최적화
  - DB 쿼리 최적화
  - Caching 전략

---

## 마일스톤

| 날짜       | 마일스톤               | 상태 |
| ---------- | ---------------------- | ---- |
| 2026-05-12 | 설계 완료              | ✅   |
| 2026-06-30 | Core Backend MVP       | 🚀   |
| 2026-07-31 | Core Frontend MVP      | 🚀   |
| 2026-08-31 | Phase 2 완료           | 🚀   |
| 2026-09-30 | Phase 3 시작           | 📅   |
| 2027-01-31 | AI 기반 정책 학습 시작 | 📅   |

---

## 참고 문서

### 아키텍처

- [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md)
- [ADR 색인](adr/ADR-000-index.md)
- [설계 원칙](core/principles.md)

### 구현 기준

- [도메인 모델](core/domain-model.md)
- [데이터 스키마](core/schema.md)

### 운영 프로세스

- [Device Lifecycle](scenarios/lifecycle.md)
- [Operation Workflow](scenarios/operation.md)
- [Exception Handling](scenarios/exceptions.md)
- [Reporting & Analytics](scenarios/reporting.md)
- [Administration](scenarios/administration.md)

---

## 유지 규칙

- 완료 항목은 `완료` 섹션으로만 이동한다.
- 아직 시작하지 않은 일은 `단기 구현 우선순위`, `중기 확장`, `기술 부채` 중 하나에만 둔다.
- 같은 작업을 일정 섹션과 기술 부채 섹션에 중복으로 쓰지 않는다.
- 구현 기준이 바뀌면 로드맵보다 ADR과 설계 문서를 먼저 갱신한다.
