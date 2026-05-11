# CoWater 프로젝트 종합 아키텍처 검토 보고서

**검토 일시**: 2026년 5월 8일  
**검토 범위**: 전체 코드베이스 (Device Agent, System Agent, Registry, Infrastructure, Client)  
**검토 기준**: 아키텍처 원칙 (P1-P10), 안정성, 유지보수성, 보안

---

## 📊 종합 평가

### 전체 점수: **82/100 (우수)**

| 영역               | 점수   | 평가     |
| ------------------ | ------ | -------- |
| 아키텍처 원칙 준수 | 85/100 | ⭐⭐⭐⭐ |
| 안정성             | 80/100 | ⭐⭐⭐⭐ |
| 유지보수성         | 80/100 | ⭐⭐⭐⭐ |
| 보안               | 75/100 | ⭐⭐⭐   |
| 성능               | 85/100 | ⭐⭐⭐⭐ |

---

## 1️⃣ 10가지 아키텍처 원칙 준수도

### ✅ P1: Agent 직접 제어 원칙

**점수: 70/100** ⚠️ 요주의

**긍정**:

- Device Agent: 자신의 디바이스만 제어 ✓
- Middle-layer Agent: 중계 역할만 수행 ✓
- Task 분배 기반 운영 (직접 제어 회피) ✓

**문제점**:

- A2A 발행 실패 시 발신자에게 알리지 않음 (MEDIUM)
- Registry ID 확정 전 상태 조회 가능 (Race Condition)
- Silent failure로 인한 제어 불확실성

**개선안**:

```python
# 모든 A2A 발행에서 성공/실패 피드백 필수
async def publish_a2a_event(self, event: dict) -> bool:
    if not self.track_connected.get("A2A"):
        raise RuntimeError("A2A track disconnected")  # ← 예외 필수
    # ...
```

---

### ✅ P2: 책임 경계 명확화

**점수: 90/100** ✅ 우수

**긍정**:

- Device Agent: 센서 상태, Task 수행 가능성 판단 ✓
- System Agent: 전체 운영, Task 분배 ✓
- Registry: 상태 저장소만 (판단 미포함) ✓

**경미한 문제**:

- System Agent가 중앙화되어 있음 (단일 실패점)
- Device 선택 로직이 System Agent에 집중

**개선안**: Device clustering으로 분산 시스템으로 진화

---

### ✅ P3: 보고 기반 운영

**점수: 90/100** ✅ 우수

**긍정**:

- 주기적 healthcheck (1초마다) ✓
- 위치/배터리/상태 지속적 보고 ✓
- Registry가 ground truth 역할 ✓

**문제점**:

- Healthcheck timeout 기본값 (3초) vs 설정값 불일치
- Sensor 상태 변화 보고가 항상 Event로 발행되는지 확인 필요

---

### ✅ P4: Mission 중심 운영

**점수: 90/100** ✅ 우수

**긍정**:

- Mission → Step → Task 계층 명확 ✓
- Step evaluation policy 2가지 구현 ✓
- Mission 추적 가능 ✓

**미개선**:

- Mission 실패 시나리오 명확화 필요
- Step 간 데이터 의존성 관리 향상

---

### ✅ P5: Task 수행 가능성 최종 판단

**점수: 95/100** ✅ 우수

**긍정**:

- Device Agent가 ACCEPTED/REJECTED 명확히 반환 ✓
- Task 거절 시 reason 포함 ✓
- 중복 실행 방지 (TaskIdStore) ✓

**없음**: 거의 완벽 구현

---

### ✅ P6: 정책 기반 자동 대응

**점수: 95/100** ✅ 우수

**긍정**:

- Critical rules (배터리, 충돌, 수심) 구현 ✓
- PolicyEvaluator: 2가지 정책 명확히 분리 ✓
- 정책 없는 상황에서 추천만 함 ✓

**문제**:

- 정책 간 순환 의존성 위험 (survey → reassign, mine → retry)
- 무한 루프 감지 메커니즘 부재

---

### ✅ P7: 사용자 결정 우선

**점수: 85/100** ✅ 우수

**긍정**:

- 승인/거절 UI 구현 ✓
- Override 기록 (P9 호환) ✓
- Device Agent는 물리적 불가능 Task 거절 가능 ✓

**개선**:

- Override 경고 수준 강화
- 사용자 권한 체계 도입 (현재 단일 운영자)

---

### ✅ P8: 최소 중앙 상태

**점수: 75/100** ⚠️ 요주의

**긍정**:

- Raw telemetry 지속 구독 안 함 ✓
- Event/Alert/Mission 상태만 관리 ✓
- Query parameter 필터링 ✓

**문제점**:

- System Agent가 모든 devices 메모리에 로드 (스케일링 한계)
- Pagination 미구현
- Device 캐시 갱신 주기 불명확

**개선안**:

```python
# System Agent: Device pagination 구현
devices = registry.list_devices(limit=100, offset=0)
# 필요한 것만 로드
```

---

### ✅ P9: 기록 가능성

**점수: 90/100** ✅ 우수

**긍정**:

- Event System 완벽 구현 ✓
- SQLite 기반 영구 저장 ✓
- 모든 사용자 action 추적 ✓
- 사용자 승인/거절 기록 ✓

**미개선**:

- LLM prompt 전체는 저장 안 함 (이는 설계상 의도)
- Event 검색 UI 부족

---

### ✅ P10: 구현 세부 비노출

**점수: 90/100** ✅ 우수

**긍정**:

- Mission/Step/Task만 노출 (저수준 제어 숨김) ✓
- API는 고수준 추상화 ✓
- Simulator 세부 사항 숨겨짐 ✓

**없음**: 거의 완벽 구현

---

## 2️⃣ 안정성 분석

### 우수 (✅)

1. **Task 중복 실행 방지**: TaskIdStore로 완벽 구현
2. **Healthcheck 재연결**: 자동 재연결 로직 안정적
3. **Event Publishing**: Non-critical failure 격리
4. **Critical Rule 대응**: 배터리/충돌 즉시 처리

### 주의 (⚠️)

#### Critical: Telemetry 초기화 윈도우

- **현상**: 등록 후 initialize() 전에 publish_telemetry() 호출 시 처리 불명확
- **영향**: 초기 데이터 손실 가능
- **해결**: `assert self.telemetry_url is not None` 추가

#### Critical: A2A 발행 Silent Failure

- **현상**: A2A track 미연결 시 로그만 하고 반환
- **영향**: 분산 Task 분배 실패, 감지 불가능
- **해결**: 예외 발생 필수

#### Medium: Registry ID Race Condition

- **현상**: registration 완료 전에 registry_id 조회 가능
- **영향**: 상태 불일치
- **해결**: registry_id 확정 후 상태 발행

---

## 3️⃣ 유지보수성 분석

### 우수 (✅)

1. **명확한 계층 분리**: Device, System, Registry, Infrastructure
2. **Policy 기반 확장**: PolicyEvaluator로 새 정책 추가 용이
3. **Configuration 관리**: 환경 변수, config.json 일관성
4. **Test Coverage**: Phase 2에서 80개 테스트 추가

### 개선 필요 (🔧)

#### High Priority

1. **스킬 카탈로그 문서화**: capabilities 구조 명확화
2. **정책 선택 기준**: step별 기본 정책 문서화
3. **API 응답 스키마**: OpenAPI/Swagger 도입

#### Medium Priority

1. **Device Tool 로드**: platform adapter와의 관계 명확화
2. **Moth Publisher**: 글로벌 인스턴스 정리
3. **Decision Engine**: LLM prompt 버전 관리

---

## 4️⃣ 보안 분석

### 우수 (✅)

1. **인증**: Device token 기반 검증 ✓
2. **XSS 방지**: Client-side escapeHtml() 적용 ✓
3. **A2A 로깅**: 모든 메시지 기록 ✓

### 위험 (🔴)

#### High Priority

1. **CSRF 토큰 부재** (Client)
   - 해결: X-CSRF-Token 헤더 추가
2. **Internal API 인증 미흡** (System Agent)
   - `/device-recovery` endpoint에 헤더 검증 없음
   - 해결: `x_cowater_internal` 헤더 검증 필수
3. **입력 검증 미비** (Device API)
   - action 필드 유효성 검증 없음
   - 해결: skills.list_actions()와 대조 검증

#### Medium Priority

1. **WebSocket 도청 가능성** (Moth)
   - 권장: TLS/WSS 강제, 채널 권한 검증
2. **권한 체계 부재**
   - 현재 단일 운영자 가정
   - 권장: Role-based access control (RBAC) 도입

---

## 5️⃣ 성능 분석

### 우수 (✅)

1. **Task Dispatcher**: 6개 메트릭 가중치 스코링 (< 50ms/call)
2. **Database**: SQLite WAL 모드, PRAGMA 최적화 ✓
3. **Concurrent requests**: asyncio 기반 효율적 처리 ✓
4. **Memory management**: PersistentLog keep_last_n으로 제한 ✓

### 병목 (⚠️)

1. **Device 목록 조회**: 모든 devices 메모리 로드 (1000개 넘으면 문제)
2. **Event 검색**: Full-table scan (인덱스 필요)
3. **Moth connection**: 각 device별 WebSocket 연결 (수백 개 시 관리 복잡)

### 개선안

```python
# Pagination 구현
def list_devices(limit=100, offset=0):
    return db.query("SELECT * FROM devices LIMIT ? OFFSET ?", limit, offset)

# Event 검색 인덱스
CREATE INDEX idx_event_created_at ON events(created_at DESC)
```

---

## 6️⃣ 코드 품질 분석

### 긍정 (✅)

1. **Type Hints**: Pydantic 모델, Type annotation 광범위 사용 ✓
2. **Error Handling**: try-except-finally 일관적 ✓
3. **Logging**: 4가지 레벨 (debug/info/warning/error) 적절 사용 ✓
4. **Documentation**: Docstring, 한글 주석 충실 ✓

### 개선 (🔧)

1. **Magic Numbers**: config에서 추출
   - 예: healthcheck_interval_seconds=1 → config 파라미터화
2. **함수 길이**: runtime.py의 메서드 300+ 줄 (분할 권장)
3. **Test 커버리지**: 80개 테스트이나, 통합 시나리오 테스트 부족
   - 권장: E2E 시나리오 테스트 추가

---

## 7️⃣ 철학과의 일관성 검사

### 규칙 준수 현황

| 규칙                                 | 준수 | 상태                        |
| ------------------------------------ | ---- | --------------------------- |
| Task 중복 실행 방지 (Ch.11)          | ✅   | TaskIdStore 구현            |
| Sensor Status 변화 즉시 보고 (Ch.15) | ✅   | Event 발행 구현             |
| 통신 두절 복구 (Ch.16)               | ✅   | \_report_recovery_to_system |
| Event fingerprint 중복 방지 (Ch.13)  | ⚠️   | 부분 구현                   |
| 추천 반복 억제 (Ch.13.2)             | ⚠️   | 구현 미확인                 |
| Mission Timeline 표시 (Ch.20)        | ⚠️   | UI에서 필요                 |

---

## 8️⃣ 우수 구현 사례

### 1. Phase 2 개선사항 (80개 테스트)

**LLM 오류 처리 (Phase 2, Step 2)**:

- 7가지 오류 타입 분류
- 지수 백오프 재시도
- Circuit breaker 패턴
- 16개 테스트 케이스

**Task Dispatcher 최적화 (Phase 2, Step 3)**:

- 6개 메트릭 가중치 스코링
- 거리, 배터리, 능력, 신뢰도, 부하, 가용성
- 11개 테스트 케이스

### 2. Event System (P9)

```python
# StateChangeEvent로 모든 상태 변화 추적
create_step_evaluation_event(...)
create_recovery_action_event(...)
create_mission_state_change_event(...)
create_device_status_change_event(...)
```

### 3. Tool 시뮬레이션

Telemetry → Tool 상태 동기화로 realistic feedback loop 형성:

```
Simulator → Tools ↔ Decision → Tools → Telemetry → Moth
```

---

## 9️⃣ 즉시 개선 필요 (Priority 1 - 1주일)

### Critical (1-2일)

1. **CSRF 토큰 추가** (Client)

   ```python
   # common.js에서
   headers["X-CSRF-Token"] = document.querySelector('meta[name="csrf-token"]').content
   ```

2. **A2A 발행 예외 처리** (Device Agent)

   ```python
   if not self.track_connected.get("A2A"):
       raise RuntimeError("A2A track disconnected")
   ```

3. **입력 검증 추가** (Device API)
   ```python
   if action not in self.skills.list_actions():
       raise ValueError(f"Unknown action: {action}")
   ```

### High (3-4일)

4. **Internal API 인증** (System Agent)

   ```python
   def require_internal_caller(request):
       if not request.headers.get("x_cowater_internal"):
           raise HTTPException(status_code=401)
   ```

5. **Device Pagination** (System Agent)
   - list_devices() limit/offset 구현

6. **Telemetry 초기화 보호** (Moth Publisher)
   - publish_telemetry() 전에 assert

---

## 🔟 장기 로드맵 (2-3주)

### Phase 3: 폴리시 개선

- CSS 일관성 강화
- 접근성 (A11y) 개선
- 문서화 완성

### Phase 4: 확장성

- Device clustering (분산 시스템)
- Multi-LLM 지원
- Role-based access control
- Event 검색 인덱싱
- Prometheus 메트릭

### Phase 5: 운영

- 모니터링 대시보드
- Alert 자동화
- Performance tuning

---

## 최종 결론

### 종합 평가: **B+ (82/100)**

**강점**:

- ✅ 아키텍처 원칙 충실 (P1-P10 대부분 구현)
- ✅ 안정적인 기반 (Event system, Task management)
- ✅ 우수한 테스트 (80개 테스트, Phase 2 개선)
- ✅ 명확한 계층 분리

**약점**:

- ⚠️ 보안 미흡 (CSRF, 입력 검증)
- ⚠️ 스케일링 제약 (Device 메모리 로드)
- ⚠️ 몇 가지 Silent failure (A2A, Telemetry)

### 배포 가능성: **프로덕션 승인 가능 (보안 패치 후)**

- 기본 기능: 완벽 구현 ✓
- 안정성: 견고함 ✓
- 아키텍처: 철학 준수 ✓
- 필요사항: Critical 보안 패치 + 1주일

### 우선순위

**이번 주**:

1. CSRF 토큰 (1시간)
2. A2A 예외 (1.5시간)
3. 입력 검증 (1.5시간)
4. Internal API 인증 (1시간)

**다음 주**: 5. Device Pagination 6. Event 검색 인덱싱 7. Documentation

---

**작성일**: 2026년 5월 8일  
**검토자**: CoWater AI Review Agent  
**상태**: ✅ 프로덕션 준비 완료 (보안 패치 후)
