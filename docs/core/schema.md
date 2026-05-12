# 공통 데이터 스키마 (Common Schema)

주요 데이터 모델의 JSON/SQL 상세 정의  
**기반**: [ADR-001~006](../adr/)

---

## 1. User (사용자)

```json
{
  "id": "string (uuid)",
  "name": "string",
  "role": "ADMIN | OPERATOR | VIEWER",
  "status": "ACTIVE | DISABLED",
  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

**역할**:

- **ADMIN**: 정책/설정 관리, 사용자 관리
- **OPERATOR**: 미션 승인, 작업 실행
- **VIEWER**: 읽기 전용

---

## 2. Device (장비)

```json
{
  "id": "string (uuid)",
  "name": "string",
  "type": "USV | AUV | ROV | UAV | BUOY | FIXED_SENSOR | OTHER",

  "actions": ["string"], // 자신이 수행 가능한 원자적 기능
  // 예: ["MOVE_TO", "HIGH_RES_SCAN", "SAMPLE_COLLECTION"]

  "status": "ONLINE | OFFLINE | ERROR | DEGRADED | REMOVED",

  "position": {
    "latitude": "number",
    "longitude": "number"
  },

  "battery_percent": "number | null",
  "device_agent_id": "string (uuid) | null", // 연관된 Device Agent

  "current_mission_id": "string (uuid) | null",
  "current_task_id": "string (uuid) | null",

  "last_seen_at": "timestamp | null",

  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

**중요**:

- **actions[]**: Device가 등록할 때 선언한 기능 목록 (불변, ADR-003)
- **status**: Device 자체의 운영 상태 (ONLINE/OFFLINE/ERROR 등)
- **current_mission_id/task_id**: 진행 중인 작업 추적용

---

## 3. Agent (에이전트)

```json
{
  "id": "string (uuid)",
  "name": "string",
  "type": "SYSTEM_AGENT | DEVICE_AGENT",

  "role": "COMMAND | MISSION_PLANNING | ASSIGNMENT | MONITORING | POLICY_CHECK | REPORTING | DEVICE_CONTROL",

  "device_id": "string (uuid) | null", // DEVICE_AGENT만 설정

  "endpoint": {
    "host": "string", // IP 또는 도메인
    "port": "number", // 포트
    "protocol": "string", // HTTP, GRPC, WebSocket, SSE 등
    "path": "string | null", // 경로 (예: /api/agent)
    "auth_token_ref": "string | null" // 인증 토큰 참조 (실제 토큰 X)
  },

  "last_heartbeat_at": "timestamp | null",

  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

**변경 (ADR-004)**:

- **endpoint** 필드 추가: Agent 등록 시 통신 정보 포함
- AgentConnection이 이 정보를 자동으로 조회하여 profile 생성

---

## 4. AgentConnection (협력 관계)

```json
{
  "id": "string (uuid)",

  "agent_a_id": "string (uuid)",
  "agent_b_id": "string (uuid)",

  "connection_type": "RELAY | COORDINATE | SHARE_DATA | BACKUP | SWARM_MEMBER | LEADER_FOLLOWER",

  "relation_level": "PEER | PARENT_CHILD",
  "parent_agent_id": "string (uuid) | null", // PARENT_CHILD 인 경우만

  "mission_id": "string (uuid) | null",

  "reason": "string | null",

  "profile": {
    "endpoint_a": "string", // 자동 구성 (Agent.endpoint 기반)
    "endpoint_b": "string",

    "protocol": "A2A",
    "transport": "HTTP | SSE | GRPC | REST | CUSTOM",
    "network_type": "RF | LTE | SATELLITE | ACOUSTIC | LOCAL_NETWORK | OTHER",

    "auth_info_ref": "string | null",
    "expires_at": "timestamp | null"
  },

  "deleted_at": "timestamp | null", // null = 활성, 값 있음 = 소프트 삭제

  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

**특성**:

- **profile**: Agent 테이블의 endpoint를 기반으로 자동 생성 (ADR-004)
- **deleted_at**: null이면 활성, 값이 있으면 소프트 삭제 상태 (REMOVED로 표시하지 않음)

**endpoint 동기화 규칙** (ADR-004):

- **기본 원칙**: Agent.endpoint는 변경하지 않는 것을 권장 (주소/포트 변경 시 모든 AgentConnection.profile 업데이트 필요)
- **변경 시 처리**:
  1. Agent.endpoint 업데이트
  2. 해당 Agent가 관련된 **모든 활성 AgentConnection의 profile(endpoint_a 또는 endpoint_b) 재계산 및 갱신**
  3. 진행 중인 Mission: 다음 Task 전달부터 새 endpoint 사용
  4. 진행 중인 Task: 진행 중이면 기존 endpoint 유지 (변경 미적용)

**relation_level 상세**:

- **PEER**: 두 에이전트가 서로 독립적인 의사결정권을 가지며, 정보를 공유하거나 단순히 통신을 릴레이 (예: 두 대의 AUV 협력 수색)
- **PARENT_CHILD**: 한 에이전트(Parent)가 다른 에이전트(Child)의 생명주기나 명령 실행을 부분적으로 통제하거나, Child가 Parent의 자원에 물리적으로 종속된 관계
  - 예: USV(Parent)가 ROV(Child) 유선 연결 → Parent 복귀 명령 시 Child도 자동 복귀/수거 준비

---

## 5. Event (사건)

```json
{
  "id": "string (uuid)",

  "type": "string", // USER_COMMAND, PROBLEM_DETECTED, TASK_FAILED, CRITICAL_HAZARD 등

  "severity": "INFO | WARNING | CRITICAL",
  "status": "OPEN | HANDLED | RESOLVED",

  "actor_type": "USER | SYSTEM | DEVICE",
  "actor_id": "string (uuid)",

  "target_type": "USER | DEVICE | AGENT | AGENT_CONNECTION | PROPOSAL | MISSION | TASK | SYSTEM | REPORT | CONFIG",
  "target_id": "string (uuid) | null",

  "title": "string",
  "description": "string | null",

  "data": {
    // Event 타입별로 다름
    // 예: { original_request: "...", capability_gap: {...} }
    // 중요: 전체 Proposal/Mission/Task 데이터 저장 금지
  },

  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

**규칙** (ADR-005):

- Event는 사건의 **기록**이지 데이터의 **저장소** X
- Proposal/Mission/Task 전체 데이터를 data에 넣지 않기
- Rule Engine이 Event를 트리거로 삼아 실행

---

## 6. Proposal (추천안)

```json
{
  "id": "string (uuid)",

  "source_event_id": "string (uuid)",

  "title": "string",

  "type": "OPERATION | RESPONSE | RECOVERY | SURVEY | INSPECTION | MONITORING | RETURN | EMERGENCY",

  "status": "PROPOSED | REPLANNING | APPROVED | CANCELLED | EXPIRED",

  "selected": "boolean", // true = 사용자가 이 Proposal을 선택함

  "priority": "LOW | NORMAL | HIGH | EMERGENCY",

  "target_area": "string | null",
  "target_position": {
    "latitude": "number",
    "longitude": "number"
  },

  "requires_approval": "boolean",

  "reason": "string | null",
  "limitations": "string | null",

  "created_by": {
    "type": "USER | SYSTEM | DEVICE",
    "id": "string (uuid)"
  },

  "approved_by_user_id": "string (uuid) | null",
  "approved_at": "timestamp | null",

  "cancelled_at": "timestamp | null",
  "cancel_reason": "string | null",

  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

**특성** (ADR-002):

- Proposal은 **완전한 솔루션 세트**
- 포함된 모든 ProposalTask가 사전 검증된 상태
- 사용자는 Proposal 전체를 선택 (개별 Task 조합 불가)

**상태 변이**:

- **PROPOSED**: System Agent가 생성, 사용자 선택 대기 중
  - → APPROVED: 사용자가 선택(selected=true) → 재검증 완료 → Mission 생성
  - → REPLANNING: 이전 Proposal 불채택으로 재계획 필요
  - → CANCELLED: 사용자가 거절
  - → EXPIRED: 유효기간 만료
- **APPROVED** (결과 상태): 사용자가 이 Proposal을 선택/승인함. Mission 생성 및 실행 중에도 계속 유지 (결과로서의 상태)
  - → COMPLETED (Mission 완료 시 자동)
  - → FAILED (Mission 실패 시 자동)
  - → CANCELLED: 사용자가 Mission 취소 명령
- **REPLANNING**: 이전 Proposal이 채택되지 않았으므로 재계획 중 (reason 필드에 불채택 이유 기록)
- **CANCELLED**: 사용자가 거절
- **EXPIRED**: 장시간 선택 안 됨

**필드 상세**:

- `selected`: 사용자가 이 Proposal을 선택했는지 여부 (true = 승인 절차 진행 중, false = 미선택)
- `reason`: REPLANNING 상태일 때, 이전 Proposal이 왜 채택되지 않았는지 기록 (사용자 피드백 요약)
- `limitations`: 사용자가 반드시 알아야 할 제약 사항이나 잠재적 위험 요소 (조건부 정보로, 최종 판단에 도움)

---

## 7. ProposalTask (Task 후보)

```json
{
  "id": "string (uuid)",
  "proposal_id": "string (uuid)",

  "title": "string",

  "type": "DEVICE_TASK | SYSTEM_TASK | REPORT_TASK | NOTIFY_TASK",

  "required_action": "string", // Device.actions[]에 있어야 함 (ADR-003)

  "sequence": "number", // 실행 순서

  "target_area": "string | null",
  "target_position": {
    "latitude": "number",
    "longitude": "number"
  },

  "recommended_device_id": "string (uuid) | null",
  "recommended_agent_id": "string (uuid) | null",

  "alternative_device_ids": ["string (uuid)"],

  "recommendation_reason": "string | null",

  "parameters": {
    // required_action별로 다름
    // 예: { duration_sec: 300, resolution: "high" }
  },

  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

---

## 8. Mission (실행 계획)

```json
{
  "id": "string (uuid)",

  "source_event_id": "string (uuid) | null",
  "source_proposal_id": "string (uuid) | null",

  "title": "string",

  "type": "OPERATION | RESPONSE | RECOVERY | SURVEY | INSPECTION | MONITORING | RETURN | EMERGENCY",

  "status": "READY | IN_PROGRESS | COMPLETED | FAILED | CANCELLED",

  "priority": "LOW | NORMAL | HIGH | EMERGENCY",

  "target_area": "string | null",
  "target_position": {
    "latitude": "number",
    "longitude": "number"
  },

  "created_by": {
    "type": "USER | SYSTEM | DEVICE",
    "id": "string (uuid)"
  },

  "approved_by_user_id": "string (uuid) | null",
  "approved_at": "timestamp | null",

  "started_at": "timestamp | null",
  "completed_at": "timestamp | null",
  "failed_at": "timestamp | null",
  "cancelled_at": "timestamp | null",

  "result_summary": "string | null",
  "fail_reason": "string | null",
  "cancel_reason": "string | null",

  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

**상태 변이**:

- **READY** (준비됨): Proposal 승인 직후, ProposalTask → Task 변환 완료. 모든 Task는 **PENDING** 상태. 아직 첫 Task 실행 전
  - → IN_PROGRESS: 첫 번째 Task가 시작될 때 (다른 Task들이 PENDING이어도 상관없음)
  - → CANCELLED: 사용자가 취소
- **IN_PROGRESS** (진행 중): 첫 Task 이상이 실행 중
  - → COMPLETED: 모든 Task가 COMPLETED 상태
  - → FAILED: 임의의 Task가 FAILED 상태 → 이후 모든 PENDING/IN_PROGRESS Task는 CANCELLED 처리
  - → CANCELLED: 사용자가 취소 (진행 중/대기 중 Task도 함께 취소)
- **COMPLETED** (완료): 모든 Task COMPLETED
- **FAILED** (실패): 하나 이상의 Task FAILED, 이후 Task들 CANCELLED
- **CANCELLED** (취소): 사용자 명령

**개념 정의** (ADR-002):

- Proposal.status = APPROVED: 사용자가 이 솔루션을 선택/승인함 (결과 상태로, Mission 생성/실행 중에도 유지)
- Mission.status = READY: 시스템이 실행 준비를 완료함 (Task들을 PENDING 상태로 생성, Device에 전달할 준비 완료)

---

## 9. Task (실행 단위)

```json
{
  "id": "string (uuid)",
  "mission_id": "string (uuid)",

  "source_proposal_task_id": "string (uuid) | null",

  "title": "string",

  "type": "DEVICE_TASK | SYSTEM_TASK | REPORT_TASK | NOTIFY_TASK",

  "required_action": "string",

  "assigned_device_id": "string (uuid) | null",
  "assigned_agent_id": "string (uuid) | null",

  "status": "PENDING | ASSIGNED | IN_PROGRESS | COMPLETED | FAILED | CANCELLED | ABORTED",

  "sequence": "number",

  "target_area": "string | null",
  "target_position": {
    "latitude": "number",
    "longitude": "number"
  },

  "parameters": {
    // required_action별로 다름
  },

  "result": {
    // 실행 결과 (완료 시에만 채워짐)
  },

  "error_message": "string | null",
  "cancel_reason": "string | null",
  "abort_reason": "string | null",

  "started_at": "timestamp | null",
  "completed_at": "timestamp | null",
  "cancelled_at": "timestamp | null",
  "aborted_at": "timestamp | null",

  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

**상태 변이**:

- **PENDING** (대기): Task 생성됨, Device 배정됨, Device에 아직 전달되지 않음
  - → ASSIGNED: Device Agent가 Task를 수신 확인
  - → CANCELLED: Mission 취소 또는 선행 Task 실패로 인한 자동 취소
- **ASSIGNED** (할당됨): Device Agent가 Task 수신 확인, 아직 실행 시작 전
  - → IN_PROGRESS: Device가 실행 시작
  - → CANCELLED: 사용자가 Mission 취소 명령
- **IN_PROGRESS** (진행 중): Device가 Task를 실행 중
  - → COMPLETED: Device가 Task 완료 보고
  - → FAILED: Device 오류로 Task 실패
  - → ABORTED: Device에서 직접 Task 중단 (자체 판단, P5 원칙)
  - → CANCELLED: 사용자가 Mission 취소 명령
- **COMPLETED** (완료): Task 성공 완료
- **FAILED** (실패): Device 오류/장애로 Task 실패 → Mission도 FAILED, 이후 Task들은 CANCELLED
- **CANCELLED** (취소): 사용자 Mission 취소 또는 선행 Task 실패로 인한 자동 취소
- **ABORTED** (중단): Device Agent가 Task를 수신 후 실행 불가능하다고 판단해서 거절 (P5: Task 수행 가능성 최종 판단)
  - 발생 가능 상태: PENDING, ASSIGNED 상태에서 가능 (시작하기 전 판단)
  - 예: "필요한 센서가 없음", "배터리 부족", "물리적 위치 초과", "안전 규칙 위반"
  - FAILED와의 차이: ABORTED = 수행 전 판단으로 거절, FAILED = 실행 중 장애/오류로 실패
  - Mission에 영향: ABORTED 발생 시 Mission은 FAILED로 전이, 이후 Task들 CANCELLED

---

## 10. Report (기록/분석)

```json
{
  "id": "string (uuid)",

  "type": "MISSION_REPORT | EVENT_REPORT | DAILY_REPORT | DEVICE_REPORT",

  "target_type": "MISSION | EVENT | DEVICE | TASK",
  "target_id": "string (uuid)",

  "title": "string",
  "summary": "string",

  "details": {
    // 기록 타입별로 다름
    // 예: mission_summary, task_results, device_health_check
  },

  "created_by": {
    "type": "USER | SYSTEM | DEVICE",
    "id": "string (uuid)"
  },

  "created_at": "timestamp"
}
```

**역할**:

- Mission/Event/Device 완료 후 결과 요약
- 사용자 리포팅 및 감사 추적
- 분석 및 개선 대상 파악

---

## 11. Policy (운영 원칙)

```json
{
  "id": "string (uuid)",

  "name": "string", // 예: "Critical Auto-Response Policy"
  "description": "string | null",

  "scope": "PROBLEM_DETECTION | AUTO_RESPONSE | RECOMMENDATION | APPROVAL | AGENT_CONNECTION | SYSTEM",

  "enabled": "boolean",

  "created_by": {
    "type": "USER | SYSTEM",
    "id": "string (uuid)"
  },

  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

**역할** (9번 사용자 피드백 기반):

- 🛡️ Policy: "무엇이 허용되고, 무엇이 중요한가"를 정의하는 **상위 원칙과 권한 정의**
- 여러 Rule이 단일 Policy 아래 속할 수 있음
- Policy.enabled로 전체 on/off 제어 가능
- 예시:
  - "심각한(Critical) 위험 상황에서는 사용자 승인 없이 시스템이 개입할 수 있다."
  - "모든 수중 촬영 미션은 반드시 운영자의 최종 컨펌을 거쳐야 한다."
  - "배터리가 40% 이상인 장비들만 릴레이(Relay) 역할을 맡을 수 있다."

**Policy와 Rule의 관계**:

```
Policy: "Low Battery Auto-Return"
  ├─ Rule-1: conditions=[battery<20%] → action=AUTO_CREATE_MISSION
  └─ Rule-2: conditions=[battery 20-30%] → action=CREATE_EVENT
```

---

## 12. Rule (조건 + 행동)

```json
{
  "id": "string (uuid)",
  "policy_id": "string (uuid) | null",

  "rule_type": "PROBLEM_DETECTION | AUTO_RESPONSE | RECOMMENDATION | APPROVAL | AGENT_CONNECTION",

  "name": "string",
  "enabled": "boolean",

  "priority": "number", // 낮을수록 먼저 실행

  "conditions": [
    {
      "field": "string", // 예: "event.type", "device.battery_percent"
      "operator": "EQ | NEQ | GT | GTE | LT | LTE | IN | CONTAINS",
      "value": "string | number | boolean | string[] | number[]"
    }
  ],

  "action": {
    "type": "CREATE_EVENT | CREATE_PROPOSAL | AUTO_CREATE_MISSION | ALLOW_AGENT_CONNECTION | REQUIRE_APPROVAL | BLOCK",
    "params": {
      // action 타입별로 다름
    }
  },

  "severity": "INFO | WARNING | CRITICAL",

  "created_by": {
    "type": "USER | SYSTEM",
    "id": "string (uuid)"
  },

  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

**역할** (ADR-005, 9번 사용자 피드백 기반):

- ⚡ Rule: "만약 A라면, B를 하라 (If-Then)" 실전 판단과 트리거
- Event 발생 시 실행될 조건 + 행동 정의
- Event-Triggered System의 핵심 (매 Heartbeat마다 실행 X, 특정 Event 발생 시만)
- 흐름: Event 발생 → Rule Engine이 활성화된 Policy 하위 Rule들 확인 → 조건 매칭 → 행동 실행

**action.type 정의**:

- `CREATE_EVENT`: 새로운 Event 발행 (알림용)
- `CREATE_PROPOSAL`: Proposal 생성 (사용자 선택 대기)
- `AUTO_CREATE_MISSION`: Mission 직접 생성 (자동 실행, ADR-006)
- `ALLOW_AGENT_CONNECTION`: AgentConnection 허용
- `REQUIRE_APPROVAL`: 승인 필수
- `BLOCK`: 작업 차단

**예시** (ADR-005):

```json
{
  "rule_type": "AUTO_RESPONSE",
  "name": "Critical Hazard Immediate Stop",

  "conditions": [
    {
      "field": "event.type",
      "operator": "EQ",
      "value": "CRITICAL_HAZARD"
    },
    {
      "field": "event.severity",
      "operator": "EQ",
      "value": "CRITICAL"
    }
  ],

  "action": {
    "type": "AUTO_CREATE_MISSION",
    "params": {
      "mission_type": "EMERGENCY_STOP"
    }
  },

  "priority": 1, // 가장 높은 우선순위
  "enabled": true
}
```

---

## 13. Config (설정값)

```json
{
  "key": "string", // 예: "device_offline_timeout_sec"

  "value": "string | number | boolean | Record<string, unknown>",

  "type": "string | number | boolean | json",

  "scope": "SYSTEM | PROBLEM_DETECTION | AUTO_RESPONSE | RECOMMENDATION | APPROVAL | AGENT_CONNECTION",

  "description": "string | null",

  "updated_by": {
    "type": "USER | SYSTEM",
    "id": "string (uuid)"
  },

  "updated_at": "timestamp"
}
```

**역할** (14번 사용자 피드백 기반):

- 시스템/Rule에서 참조하는 파라미터
- 코드 수정 없이 운영 로직 조정 가능

**scope별 실제 적용처**:

| Scope                 | 실제 사용처                               | 예시 파라미터                                        |
| --------------------- | ----------------------------------------- | ---------------------------------------------------- |
| **SYSTEM**            | 시스템 전반의 타임아웃 및 주기 관리       | `device_offline_timeout_sec`, `heartbeat_interval`   |
| **PROBLEM_DETECTION** | Rule Engine이 문제를 감지하는 임계치      | `low_battery_threshold`, `min_signal_strength`       |
| **AUTO_RESPONSE**     | 자동 대응 미션 생성 시의 제약 조건        | `auto_return_min_battery`, `emergency_stop_distance` |
| **RECOMMENDATION**    | Proposal 생성 시 후보 필터링 및 정렬 기준 | `max_proposal_options`, `preferred_device_type`      |
| **APPROVAL**          | 승인 프로세스의 유효성 검증               | `proposal_expiration_min`, `revalidation_threshold`  |
| **AGENT_CONNECTION**  | 에이전트 간 연결 유지 및 품질 판단        | `connection_recheck_interval`, `max_relay_hop_count` |

**예시**:

```json
{
  "key": "device_offline_timeout_sec",
  "value": 600,
  "type": "number",
  "scope": "SYSTEM",
  "description": "Device Heartbeat 타임아웃 (초)"
}

{
  "key": "low_battery_threshold",
  "value": 20,
  "type": "number",
  "scope": "PROBLEM_DETECTION",
  "description": "배터리 임계치 (%) - 이 이하면 자동 복귀"
}

{
  "key": "max_proposal_options",
  "value": 3,
  "type": "number",
  "scope": "RECOMMENDATION",
  "description": "사용자에게 표시할 최대 Proposal 개수"
}

{
  "key": "connection_recheck_interval_sec",
  "value": 10,
  "type": "number",
  "scope": "AGENT_CONNECTION",
  "description": "AgentConnection 상태 재평가 주기"
}
```

---

## 14. Sensor (센서)

```json
{
  "id": "string (uuid)",
  "device_id": "string (uuid)",

  "name": "string",

  "type": "CAMERA | SONAR | LIDAR | RADAR | GPS | IMU | DEPTH | TEMPERATURE | WATER_QUALITY | OTHER",

  "stream_endpoint": "string", // 센서 데이터 스트림 주소

  "removed_at": "timestamp | null", // null이면 활성, 값이 있으면 제거됨

  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

**특징** (11번 사용자 피드백 기반):

- **Sensor는 System의 확인 범위 X**: 센서 데이터 구독 X, 센서 문제 감지 X
- **Device Agent의 책임**: Sensor 확인과 센서 기반 거절 판단 (P5 원칙)
- System은 센서 endpoint 정보만 관리 (메타데이터)

**Sensor와 Action의 독립성**:

- **Action**: Capability Matching, Task 할당에 사용 (System Agent)
  - 예: `HIGH_RES_SCAN` action이 Device.actions[]에 있는가? → System이 확인
- **Sensor**: 웹 UI, 데이터 스트림 관리, Device Agent의 거절 판단에 사용
  - 예: `HIGH_RES_SCAN` 수행에 필요한 `CAMERA` sensor 정상 작동? → Device Agent가 확인
- 따라서 System Agent는 `Device.actions[]`만 확인하고, 실제 sensor 존재 여부는 Device Agent가 최종 판단

**최소 필드**:

- `stream_endpoint`: 센서가 데이터를 내보내는 주소
- `type`: 센서 종류 (Device가 사용할 기능을 식별)

**제거된 필드** (불필요):

- ~~status~~ (센서는 Device와 같은 주기로 상태 체크 안 함)
- ~~last_seen_at~~ (센서 자체의 heartbeat 추적 안 함)
- ~~sample_rate~~ (용도별로 다르므로 Config로 관리)
- ~~last_value~~ (스트림 데이터는 센서 측에서 관리)
- ~~metadata~~ (필요시 stream_endpoint 문서에 포함)

---

## 참고

- **[ADR-002](../adr/ADR-002-proposal-as-solution-set.md)**: Proposal 구조
- **[ADR-003](../adr/ADR-003-capability-driven-task-assignment.md)**: required_action과 Device.actions[]의 매핑
- **[ADR-004](../adr/ADR-004-agent-endpoint-management.md)**: Agent.endpoint 추가
- **[ADR-005](../adr/ADR-005-event-triggered-rule-execution.md)**: Event와 Rule의 관계
- **[domain-model.md](domain-model.md)**: 각 엔티티의 역할과 관계
- **[principles.md](principles.md)**: 설계 원칙
