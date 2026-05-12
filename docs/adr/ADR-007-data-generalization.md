# ADR-007: 데이터 구조 일반화 (Data Generalization)

**상태**: Accepted  
**작성일**: 2026-05-12  
**선행 ADR**: ADR-002 (Proposal as Solution Set), ADR-003 (Capability Driven Task Assignment)

---

## 상황 (Context)

CoWater의 데이터 모델이 성장하면서 **스키마 경직성(Schema Rigidity)** 문제가 발생합니다.

### 🔴 현재 문제점

#### 1️⃣ **상태별 시점 컬럼 분산** (State-Specific Timestamps)

```json
// ❌ 기존 (문제)
{
  "status": "COMPLETED | FAILED | CANCELLED",
  "started_at": "timestamp | null",
  "completed_at": "timestamp | null",
  "failed_at": "timestamp | null",
  "cancelled_at": "timestamp | null"
}
```

**문제**:
- 상태 5개당 타임스탬프 4개 → 유지보수 복잡성 증가
- "Task가 언제 시작했는가?" 질문이 불명확 → `started_at`을 추적하지만, 다른 상태로 전이될 때는 추적 불가
- 새로운 상태 추가 시 (예: PAUSED) → 데이터베이스 스키마 변경 필요

#### 2️⃣ **사유 필드 분산** (Reason Field Fragmentation)

```json
// ❌ 기존 (문제)
{
  "status": "COMPLETED | FAILED | CANCELLED | ABORTED",
  "error_message": "string | null",      // FAILED일 때만 의미 있음
  "cancel_reason": "string | null",      // CANCELLED일 때만 의미 있음
  "abort_reason": "string | null"        // ABORTED일 때만 의미 있음
}
```

**문제**:
- "이 Task가 왜 실패했는가?" → 3개 필드 중 어느 것을 봐야 할지 불명확
- 코드에서 상태별로 다른 사유 필드를 읽어야 함 → 로직 분산
- 상태가 추가되면 (예: RETRYING) → 새로운 이유 필드 추가 필요

#### 3️⃣ **다형성 관계 미흡** (Polymorphic Association Gaps)

```json
// ❌ 기존 (문제)
{
  "current_mission_id": "string | null",
  "current_task_id": "string | null"
}
```

**문제**:
- Device가 처리할 수 있는 대상이 증가하면 (예: REPORT, INSPECTION) → 매번 컬럼 추가 필요
- "Device가 지금 뭘 하고 있나?" 질문에 여러 필드를 확인해야 함
- 데이터 정합성: `current_mission_id`와 `current_task_id` 중 둘 다 값이 있는 경우 처리 로직 불명확

---

## 결정 (Decision)

**상태(Status) 및 관계 필드를 다음 3가지 원칙으로 일반화합니다:**

### 1️⃣ **State Normalization** - 상태 필드 통합

```json
// ✅ 변경 (개선)
{
  "status": "READY | IN_PROGRESS | COMPLETED | FAILED | CANCELLED | ABORTED",
  "status_updated_at": "timestamp",      // 마지막 상태 변경 시점 (단 하나)
  "status_reason": "string | null"       // 모든 상태 사유 통합
}
```

**규칙**:
- **`status_updated_at`**: 상태가 전이할 때마다 업데이트 (모든 상태에서 추적 가능)
- **`status_reason`**: 현재 상태에 대한 부연 설명
  - COMPLETED: 완료 결과 요약
  - FAILED: 실패 원인
  - CANCELLED: 취소 사유
  - ABORTED: 거절 사유
  - 상태로 구분 가능하므로, 단일 필드로 통합

**예시**:

```json
// Task 실패 시
{
  "status": "FAILED",
  "status_updated_at": "2026-05-12T14:30:45Z",
  "status_reason": "배터리 부족: 30% 이상 필요 (현재: 15%)"
}

// Task 거절 시
{
  "status": "ABORTED",
  "status_updated_at": "2026-05-12T14:25:10Z",
  "status_reason": "필요한 CAMERA 센서 오류"
}

// Task 취소 시
{
  "status": "CANCELLED",
  "status_updated_at": "2026-05-12T14:20:00Z",
  "status_reason": "사용자 Mission 취소 요청"
}
```

---

### 2️⃣ **Reason Generalization** - 사유 필드 통합

(State Normalization에 포함됨)

**변경 대상**:
- Task: `error_message`, `cancel_reason`, `abort_reason` → `status_reason`
- Mission: `fail_reason`, `cancel_reason` → `status_reason`
- Proposal: `cancel_reason` → `status_reason`

**의도**:
- 상태 변경의 **맥락을 항상 단일 필드에서 찾기**
- "마지막 상태 변경의 사유가 뭐지?" → 항상 `status_reason` 확인

---

### 3️⃣ **Polymorphic Association** - Device의 다형성 관계

```json
// ❌ 기존 (문제)
{
  "current_mission_id": "string | null",
  "current_task_id": "string | null"
}

// ✅ 변경 (개선)
{
  "target_type": "MISSION | TASK | null",
  "target_id": "string | null"
}
```

**규칙**:
- **`target_type`**: Device가 처리 중인 대상의 타입
  - MISSION: 전체 미션 진행 중
  - TASK: 특정 Task 실행 중
  - null: 유휴 상태
- **`target_id`**: 대상 ID
  - `target_type=TASK`이면 Task ID 저장
  - `target_type=MISSION`이면 Mission ID 저장
  - `target_type=null`이면 ID도 null

**의도**:
- Device가 처리할 수 있는 대상이 증가해도 스키마 변경 불필요
- 예: 향후 INSPECTION, REPORT 같은 대상 추가 가능 → 코드만 변경하면 됨

**예시**:

```json
// Task 실행 중
{
  "target_type": "TASK",
  "target_id": "task-uuid-123"
}

// Mission 진행 중 (여러 Task 처리)
{
  "target_type": "MISSION",
  "target_id": "mission-uuid-456"
}

// 유휴 상태
{
  "target_type": null,
  "target_id": null
}
```

---

## 결과 (Consequences)

### ✅ 이점

#### 1️⃣ **스키마 확장성 향상**
- 새로운 상태 추가 (예: PAUSED, RETRYING) → 코드만 변경, 스키마 변경 X
- Device의 새로운 대상 타입 추가 → 컬럼 추가 없이 처리 가능
- 미래에도 DB 마이그레이션 최소화

#### 2️⃣ **쿼리 및 로직 단순화**
- "마지막 상태 변경 시점": 항상 `status_updated_at` 하나만 확인
- "현재 상태 사유": 항상 `status_reason` 하나만 확인
- "Task의 현재 실행 상태": `status`와 `status_updated_at`으로 충분

#### 3️⃣ **코드 일관성**
- 상태별 다른 필드를 분기 처리할 필요 없음
- 상태 변경 로직이 한 곳에 집중 (status, status_updated_at, status_reason)

#### 4️⃣ **감사 추적(Audit Trail) 개선**
- 모든 상태 변경이 동일한 필드에 기록됨
- 시간 기반 쿼리: `WHERE status_updated_at > timestamp` → 단순화

### ⚠️ 마이그레이션 고려사항

#### 1️⃣ **데이터베이스 마이그레이션** (향후 구현 시)

```sql
-- Mission 테이블 예시
ALTER TABLE missions
ADD COLUMN status_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
ADD COLUMN status_reason TEXT;

-- 기존 데이터 마이그레이션
UPDATE missions
SET status_updated_at = CASE
  WHEN status = 'COMPLETED' THEN completed_at
  WHEN status = 'FAILED' THEN failed_at
  WHEN status = 'CANCELLED' THEN cancelled_at
  ELSE updated_at
END,
status_reason = COALESCE(fail_reason, cancel_reason, 'N/A');

-- 이전 컬럼 제거 (마이그레이션 완료 후)
ALTER TABLE missions
DROP COLUMN started_at,
DROP COLUMN completed_at,
DROP COLUMN failed_at,
DROP COLUMN cancelled_at,
DROP COLUMN fail_reason,
DROP COLUMN cancel_reason;
```

#### 2️⃣ **ORM 쿼리 변경**

```python
# ❌ 기존
task = db.query(Task).filter(Task.completed_at > threshold).first()

# ✅ 변경
task = db.query(Task).filter(
    (Task.status == 'COMPLETED') &
    (Task.status_updated_at > threshold)
).first()
```

#### 3️⃣ **상태별 시점 조회 패턴**

```python
# ❌ 기존: 상태별 다른 필드 사용
if task.status == 'COMPLETED':
    timestamp = task.completed_at
elif task.status == 'FAILED':
    timestamp = task.failed_at

# ✅ 변경: 단일 필드 사용
timestamp = task.status_updated_at  # 상태 무관하게 항상 동일
```

#### 4️⃣ **Proposal의 특수 처리**

Proposal은 **초기 승인 기록(`approved_at`, `approved_by_user_id`)을 별도 유지**합니다:
- `approved_at`: APPROVED 상태로 처음 전이된 시점 (변경 없음)
- `approved_by_user_id`: 누가 승인했는가 (변경 없음)
- `status_updated_at`: 모든 상태 변경 추적 (신규)
- `status_reason`: 취소/거절/재계획 사유 (신규)

이유: 감사(audit) 목적으로 "누가 언제 승인했는가"를 명시적으로 기록해야 함

---

## 참고

- **docs/core/schema.md**: 변경된 스키마 정의 (Proposal, Mission, Task, Device)
- **docs/scenarios/lifecycle.md**: 상태 변이 및 타이밍 (status_updated_at 기반 업데이트)
- **ADR-002**: Proposal as Solution Set
- **ADR-003**: Capability Driven Task Assignment
