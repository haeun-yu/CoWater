# 공통 데이터 스키마

주요 데이터 모델의 JSON/SQL 상세 정의  
**기반**: [ADR-001~006](../adr/)

**표기 규칙**:

- 본 문서는 각 엔티티의 **정본 canonical 필드**를 `id` 기준으로 설명합니다.
- 현재 Registry/API 구현은 점진적 전환을 위해 `event_id`, `proposal_id`, `mission_id`, `task_id` 같은 **별칭 필드**를 함께 반환할 수 있습니다.
- Device 응답은 외부 식별자인 `id`(UUID)와 별도로 내부 라우팅용 `registry_id`(numeric)를 포함할 수 있습니다. 외부 참조는 `id`를 기준으로 사용합니다.

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

## 2. Device (장비 - H/W 스펙)

```json
{
  "id": "string (uuid)",
  "name": "string",
  "type": "USV | AUV | ROV | OTHER",

  "actions": ["string"], // 자신이 수행 가능한 원자적 기능
  // 예: ["MOVE_TO", "HIGH_RES_SCAN", "SAMPLE_COLLECTION"]

  "status": "ONLINE | OFFLINE | ERROR | DEGRADED | REMOVED",

  "position": {
    "latitude": "number",
    "longitude": "number"
  },

  // ← 추가: 물리적 통신 인터페이스 (H/W)
  "physical_interfaces": [
    {
      "type": "WIRED | ACOUSTIC | RF | INTERNET",
      "hardware": "string", // "Ethernet", "Acoustic Modem", "LTE Module" 등
      "specs": "string | null" // "2.4GHz WiFi", "300m range" 등
    }
  ],

  "battery_percent": "number | null",
  "device_agent_id": "string (uuid) | null", // 연관된 Device Agent

  "target_type": "MISSION | TASK | null", // 현재 처리 중인 대상
  "target_id": "string (uuid) | null", // 대상의 ID

  "last_seen_at": "timestamp | null",

  "deleted_at": "timestamp | null",

  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

**운영 확장 필드**:

- 현재 Device Registry 응답은 운영/라우팅 동기화를 위해 `connected`, `connectivity_status`, `main_video_track_name`, `server`, `agent`, `tracks`, `action_catalog`를 함께 포함합니다.
- 현재 Device Registry 응답은 위치/라우팅 추적을 위해 `device_type`, `layer`, `connectivity`, `latitude`, `longitude`, `last_battery_percent`, `last_battery_update`, `parent_id`, `last_location_update`를 함께 포함합니다.
- 현재 Device Registry 응답은 Moth/A2A 연계를 위해 `healthcheck_topic`, `healthcheck_endpoint`, `telemetry_topics`를 함께 포함합니다.
- 현재 Device Registry 응답은 수중 운용 상태를 위해 `is_submerged`, `submerged_at`, `surfaced_at`, `force_parent_routing`를 함께 포함합니다.

**중요**:

- **actions[]**: Device가 등록할 때 선언한 기능 목록 (불변, ADR-003)
- **status**: Device 자체의 운영 상태 (ONLINE/OFFLINE/ERROR 등)
- **physical_interfaces[]**: Device가 물리적으로 가진 통신 모듈 (H/W 사양, 불변)
  - 예: ROV는 [WIRED], AUV는 [ACOUSTIC, INTERNET, RF]
- **target_type/target_id**: 진행 중인 작업 추적용 (다형성 관계)

---

## 3. Agent (에이전트 - 통신 인터페이스)

```json
{
  "id": "string (uuid)",
  "name": "string",
  "type": "SYSTEM_AGENT | DEVICE_AGENT",

  "role": "REQUEST_HANDLER | DEVICE_BRIDGE | MISSION_PLANNER | POLICY_MANAGER | SYSTEM_SENTINEL | INSIGHT_REPORTER | DEVICE_CONTROL",

  "device_id": "string (uuid) | null", // DEVICE_AGENT만 설정

  "endpoint": {
    "host": "string", // IP 또는 도메인
    "port": "number", // 포트
    "protocol": "string", // HTTP, GRPC, WebSocket, SSE 등
    "path": "string | null", // 경로 (예: /api/agent)
    "auth_token_ref": "string | null" // 인증 토큰 참조 (실제 토큰 X)
  },

  // ← 추가: 물리적 통신 능력 (I/F - Interface)
  "capabilities": ["WIRED", "ACOUSTIC", "RF", "INTERNET"], // 지원 가능한 매체 (Device.physical_interfaces와 동기화)
  
  // ← 추가: 물리적 종속성 (Gateway Pattern)
  "gateway_agent_id": "string (uuid) | null", // 부모 Agent (ROV의 경우 USV 참조)
  
  // ← 추가: 환경 상태 (실시간 변경)
  "environment_state": "SURFACE | UNDERWATER", // 현재 물리적 위치
  
  // ← 추가: 현재 활성 매체 (반드시 capabilities의 부분집합, 실시간 업데이트)
  "active_mediums": ["WIRED", "RF"], // 지금 사용 가능한 매체 (AUV 수중 진입 시 ["ACOUSTIC"]으로 변경)

  "last_heartbeat_at": "timestamp | null",

  "deleted_at": "timestamp | null",

  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

**역할별 에이전트 정의 (ADR-008 참고)**:

| 역할 | Agent 이름 | 책임 | DB 권한 |
|------|----------|------|--------|
| REQUEST_HANDLER | RequestHandler | 사용자 요청 해석 & 경로 결정 | Read-only |
| DEVICE_BRIDGE | DeviceBridge | 장비 통신, 상태 동기화 | Device, Sensor |
| MISSION_PLANNER | MissionPlanner | 미션/태스크 계획, 실행 추적 | Mission, Task, Proposal |
| POLICY_MANAGER | PolicyManager | 정책/규칙 관리, 자동 대응 | Policy, Rule, Config |
| SYSTEM_SENTINEL | SystemSentinel | 이상 감시, Alert/Event 생성 | Alert, Event |
| INSIGHT_REPORTER | InsightReporter | 데이터 조회, 리포트 생성 | Read-only |
| DEVICE_CONTROL | Device Agent | 개별 디바이스 제어 | Device 상태 |

**변경 (ADR-004 + ADR-008)**:

- **role** 필드: 6개의 전문 에이전트 역할로 업데이트 (ADR-008 참고)
  - 각 역할은 명확한 책임 영역과 DB 소유권을 가짐
- **endpoint** 필드: Agent 등록 시 통신 정보 포함 (기존)
- **capabilities[]**: Device의 physical_interfaces와 동기화 (등록 시 고정)
  - ROV: ["WIRED"] (유선만)
  - AUV: ["ACOUSTIC", "RF", "INTERNET"] (수중/수상 모두)
- **gateway_agent_id**: 물리적으로 종속된 Agent 참조
  - ROV가 USV에 케이블로 연결 → ROV.gateway_agent_id = USV의 agent_id
- **environment_state**: Agent의 현재 물리적 위치 (실시간 변경)
  - SURFACE: 수상 (모든 매체 사용 가능)
  - UNDERWATER: 수중 (ACOUSTIC만 사용 가능)
- **active_mediums[]**: 현재 사용 가능한 매체 (∈ capabilities)
  - AUV 수상: ["RF", "INTERNET", "ACOUSTIC"]
  - AUV 수중: ["ACOUSTIC"] (자동 전환)

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
    "transport": "HTTP | REST | GRPC | CUSTOM",
    
    // ← 추가: 물리 계층 추상화
    "network_type": "WIRED | ACOUSTIC | RF | SATELLITE | INERTIAL",
    "signal_strength": "number | null", // % (0-100)
    "latency_ms": "number | null", // 지연시간 (밀리초)
    "bandwidth_mbps": "number | null", // 대역폭 (Mbps)

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
  - **network_type**: Device Agent가 물리 계층 드라이버를 선택하기 위한 정보
    - `WIRED`: 유선 (Ethernet, USB) → HTTP, REST 드라이버
    - `ACOUSTIC`: 음파 (수중 통신) → Acoustic Modem 드라이버
    - `RF`: 무선 (WiFi, RF) → RF 모듈 드라이버
    - `SATELLITE`: 위성 → Satellite 모듈 드라이버
    - `INERTIAL`: 관성 항법 (위치 추정) → Inertial 드라이버
  - **signal_strength, latency_ms, bandwidth_mbps**: 협력 판단 시 참고값 (Policy Rule 실행)
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

  "type": "string", // SYS_INTENT_CLASSIFIED, SYS_TASK_COMPLETED, SYS_TASK_FAILED, SYS_ANOMALY_DETECTED, SYS_MISSION_UPDATED, SYS_MISSION_COMPLETED, DEVICE_HEALTHCHECK, ENV_STATE_CHANGED 등

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
    // 예: SYS_ANOMALY_DETECTED -> { anomaly_type: "LOW_BATTERY", ... }
    // 예: SYS_TASK_FAILED -> { status: "FAILED", error_type: "...", ... }
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
- `SYS_ANOMALY_DETECTED`는 `data.anomaly_type`으로 세부 이상 종류를 구분

---

## 6. Proposal (추천안)

```json
{
  "id": "string (uuid)",

  "type": "MISSION | SYSTEM_CONTROL",

  "title": "string",

  "status": "PROPOSED | APPROVED | CANCELLED | EXPIRED",

  "selected": "boolean",

  "priority": "LOW | NORMAL | HIGH | EMERGENCY",

  "requires_approval": "boolean",

  "reason": "string | null",
  "limitations": "string | null",

  "category_data": {
    // 타입별로 다른 구조 (아래 참고)
  },

  "created_by": {
    "type": "USER | SYSTEM | DEVICE",
    "id": "string (uuid)"
  },

  "approved_by_user_id": "string (uuid) | null",
  "approved_at": "timestamp | null",

  "status_updated_at": "timestamp",
  "status_reason": "string | null",

  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

**타입별 category_data 구조**:

### MISSION
```json
{
  "source_event_id": "string (uuid)",
  "target_area": "string | null",
  "target_position": {
    "latitude": "number",
    "longitude": "number"
  }
}
```

### SYSTEM_CONTROL
```json
{
  "action": "restart | stop | emergency_stop | config_reload | ...",
  "target_system": "string (어떤 시스템을 제어할지)",
  "source_event_id": "string (uuid) | null"
}
```

**특성** (ADR-002):

- Proposal은 **사용자 승인이 필요한 모든 제안**의 통합 엔티티
- type에 따라 category_data 구조가 다름
- 각 타입별로 필요한 필드만 채움 (null 허용)

**상태 변이**:

- **PROPOSED**: System Agent가 생성, 사용자 선택 대기 중
  - → APPROVED: 사용자가 선택(selected=true) → 재검증 완료 → 실행
  - → CANCELLED: 사용자가 거절
  - → EXPIRED: 유효기간 만료
- **APPROVED** (고정 상태): 사용자가 이 Proposal을 선택/승인함

**필드 상세**:

- `selected`: 사용자가 이 Proposal을 선택했는지 여부
- `reason`: Proposal 재생성 또는 거절 사유
- `limitations`: 사용자가 반드시 알아야 할 제약 사항
- `category_data`: type별로 필요한 도메인 데이터 (동적 필드)

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

  "status": "READY | IN_PROGRESS | COMPLETED | FAILED | CANCELLED | EXPIRED",

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
  "approval_id": "string (uuid) | null",

  "status_updated_at": "timestamp",
  "status_reason": "string | null",

  "result_summary": "string | null",

  "steps": [
    {
      "step_id": "string",
      "step_type": "string",
      "evaluation_policy": "string",
      "depends_on": ["string"],
      "tasks": ["Task 실행 정의"]
    }
  ],

  "timeline": [
    {
      "timestamp": "timestamp",
      "type": "string",
      "message": "string",
      "data": {}
    }
  ],

  "final_result": {
    "status": "string",
    "reason": "string | null",
    "summary": "string | null"
  },

  "metadata": {
    "dispatch_state": {
      "steps": ["Dispatch 상태"],
      "execution_results": ["실행 결과 집계"]
    }
  },

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
- **FAILED** (실패): 하나 이상의 Task FAILED, 이후 Task들 CANCELLED (status_reason에 실패 사유 기록)
- **EXPIRED** (만료): 승인 이후 유효 시간이 지나 자동 종료된 상태

**구현 메모**:

- Mission은 문서상의 핵심 상태 엔티티이면서, 현재 구현에서는 실행 orchestration을 위한 `steps`, `timeline`, `final_result`, `metadata.dispatch_state`를 함께 보관합니다.
- `logs`, `device_execution_results` 같은 중복 실행 기록 필드는 정본 Mission 스키마에서 제외합니다.
- **CANCELLED** (취소): 사용자 명령 (status_reason에 취소 사유 기록)

**개념 정의** (ADR-002):

- Proposal.status = APPROVED: 사용자가 이 솔루션을 선택/승인함 (결과 상태로, Mission 생성/실행 중에도 유지)
- Mission.status = READY: 시스템이 실행 준비를 완료함 (Task들을 PENDING 상태로 생성, Device에 전달할 준비 완료)
- Mission.status_updated_at: 마지막 상태 변경 시점 (READY→IN_PROGRESS, IN_PROGRESS→COMPLETED 등)

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

  "status_updated_at": "timestamp",
  "status_reason": "string | null",

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
  - → ABORTED: Device Agent가 Task 실행 불가능 판단 (P5 원칙)
- **IN_PROGRESS** (진행 중): Device가 Task를 실행 중
  - → COMPLETED: Device가 Task 완료 보고
  - → FAILED: Device 오류로 Task 실패
  - → CANCELLED: 사용자가 Mission 취소 명령
- **COMPLETED** (완료): Task 성공 완료
- **FAILED** (실패): Device 오류/장애로 Task 실패 → Mission도 FAILED, 이후 Task들은 CANCELLED (status_reason에 오류 사유 기록)
- **CANCELLED** (취소): 사용자 Mission 취소 또는 선행 Task 실패로 인한 자동 취소 (status_reason에 취소 사유 기록)
- **ABORTED** (중단): Device Agent가 Task를 수신 후 실행 불가능하다고 판단해서 거절 (P5: Task 수행 가능성 최종 판단)
  - 발생 가능 상태: PENDING, ASSIGNED 상태에서 가능 (시작하기 전 판단)
  - 예: "필요한 센서가 없음", "배터리 부족", "물리적 위치 초과", "안전 규칙 위반"
  - FAILED와의 차이: ABORTED = 수행 전 판단으로 거절, FAILED = 실행 중 장애/오류로 실패
  - Mission에 영향: ABORTED 발생 시 Mission은 FAILED로 전이, 이후 Task들 CANCELLED (status_reason에 거절 사유 기록)

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
    // 예: mission_summary, task_execution_summary, device_health_snapshot
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
  ├─ Rule-1: conditions=[battery<10%] → action=AUTO_CREATE_MISSION
  └─ Rule-2: conditions=[battery 10-30%] → action=CREATE_EVENT
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
      "value": "SYS_ANOMALY_DETECTED"
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

## 13a. Policy (정책 - 고수준)

```json
{
  "id": "string (uuid)",
  "name": "string",
  "description": "string | null",
  
  "enabled": "boolean",
  "priority": "number",  // 1(높음) ~ 100(낮음)
  
  "scope": "SYSTEM | DEVICE_TYPE | DEVICE_ID",
  "target_device_type": "USV | AUV | ROV | null",  // scope=DEVICE_TYPE인 경우
  "target_device_id": "string (uuid) | null",      // scope=DEVICE_ID인 경우
  
  "rules": ["string (uuid)"],  // 포함된 Rule 목록
  
  "created_by": {
    "type": "USER | SYSTEM",
    "id": "string (uuid)"
  },
  
  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

**특성** (`docs/implementation/system-agent.md` 참고):

- **scope**: Policy 적용 범위
  - `SYSTEM`: 모든 Device에 적용
  - `DEVICE_TYPE`: 특정 Device 타입에만 적용 (예: AUV만)
  - `DEVICE_ID`: 특정 Device 하나에만 적용
- **rules[]**: 이 Policy가 포함하는 Rule ID 목록
  - Rule은 Policy와는 독립적으로 존재 가능 (여러 Policy에서 재사용 가능)
- **priority**: 여러 Policy가 동시에 트리거될 때 실행 순서

---

## 13b. Rule (규칙 - 저수준, Event 기반)

```json
{
  "id": "string (uuid)",
  "policy_id": "string (uuid) | null",  // 소속 Policy (optional)
  
  "name": "string",
  "description": "string | null",
  "enabled": "boolean",
  "priority": "number",  // 1(높음) ~ 100(낮음), Policy 내 실행 순서
  
  "trigger": {
    "event_type": "string"  // DEVICE_HEALTHCHECK, SYS_TASK_DISPATCHED, SYS_ALERT 등
  },
  
  "condition": "string",  // SQL WHERE 스타일
  // 예: "device.battery < 30 AND device.status = 'ONLINE'"
  // 연산자: ==, !=, <, >, <=, >=, IN, BETWEEN, LIKE
  // 피연산자: device.*, task.*, system.*
  
  "action": {
    "type": "ALERT | AUTO_TASK | DEVICE_STATE_CHANGE | POLICY_EXECUTE | NOTIFY",
    
    // type=ALERT
    "severity": "INFO | WARNING | CRITICAL",
    "message": "string",  // 템플릿 변수 가능: {{ device.battery }}
    
    // type=AUTO_TASK
    "task_title": "string",
    "required_action": "string",
    "parameters": {},
    "timeout_sec": "number",
    "auto_create_mission": "boolean",
    
    // type=DEVICE_STATE_CHANGE
    "target_device_id": "string (uuid)",
    "new_status": "OFFLINE | DEGRADED | REMOVED",
    
    // type=POLICY_EXECUTE
    "target_policy_id": "string (uuid)",
    
    // type=NOTIFY
    "channels": ["slack", "email", "sms"],
    "recipients": ["email@example.com"]
  },
  
  "created_by": {
    "type": "USER | SYSTEM",
    "id": "string (uuid)"
  },
  
  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

**특성** (`docs/implementation/rule-engine.md` 참고):

- **trigger**: Rule을 발동하는 Event 타입
  - 예: `DEVICE_HEALTHCHECK` (Device Heartbeat), `SYS_TASK_DISPATCHED` (Task 할당)
- **condition**: 실행 조건 (SQL WHERE 스타일)
  - 조건이 없으면 (null/empty) trigger만 일치해도 실행
  - 조건이 있으면 AND/OR로 복합 조건 가능
- **action**: 조건 일치 시 실행할 동작
  - **ALERT**: 경고 메시지 발행 (severity 수준 다름)
  - **AUTO_TASK**: 자동으로 새 Task 생성 (Mission 생성 옵션)
  - **DEVICE_STATE_CHANGE**: Device 상태 강제 변경 (OFFLINE 처리 등)
  - **POLICY_EXECUTE**: 다른 Policy 실행 (연쇄 실행)
  - **NOTIFY**: 사용자 알림 (Slack, Email, SMS)
- **priority**: 같은 Event에 여러 Rule이 매칭될 때 실행 순서
  - 숫자가 작을수록 먼저 실행

**action.message의 템플릿 변수**:

```
{{ device.device_id }}      # Device ID
{{ device.battery_percent }} # 배터리 %
{{ device.status }}          # Device 상태
{{ task.task_id }}           # Task ID
{{ task.required_action }}   # Task 액션
{{ system.time }}            # 현재 시간
```

**Rule 평가 흐름** (`docs/implementation/rule-engine.md` 참고):

```
Event 발생
  ↓
PolicyManager.handle_event(event)
  ↓
RuleEngine.process_event(event)
  ↓
trigger 일치하는 모든 Rule 찾기
  ↓
각 Rule의 condition 평가
  ↓
조건 일치 Rule을 priority 순서로 정렬
  ↓
각 Rule의 action 실행
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

  "deleted_at": "timestamp | null", // null이면 활성, 값이 있으면 제거됨

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

## 14. Agent Card (.well-known/agent-card.json)

**정의**: 에이전트의 메타데이터 및 통신 정보를 담은 JSON 파일

**경로**: `/.well-known/agent-card.json`

**목적**:
- 에이전트 자동 발견 (Agent Discovery)
- 통신 가능 메서드 명시 (JSON-RPC)
- 에이전트의 역할, 능력, 엔드포인트 정보 제공
- 외부 클라이언트와의 A2A 호환성

**포맷**:

```json
{
  "version": "v0.3.0",
  
  "name": "string",
  "type": "DEVICE_AGENT | SYSTEM_AGENT",
  
  "role": "DEVICE_CONTROL | REQUEST_HANDLER | DEVICE_BRIDGE | MISSION_PLANNER | POLICY_MANAGER | SYSTEM_SENTINEL | INSIGHT_REPORTER",
  
  "endpoint": {
    "host": "string",
    "port": "number",
    "protocol": "HTTP",
    "path": "string"
  },
  
  "capabilities": ["string"],  // 지원 능력 (예: ["scan_area", "remove_mine"])
  
  "supported_methods": [
    "message/send",
    "tasks/get",
    "tasks/cancel"
  ],
  
  "supported_message_types": [
    "task.assign",
    "task.result",
    "event.report",
    "mission.result",
    "child.register",
    "layer.assignment"
  ],
  
  "authentication": {
    "type": "none | token | oauth2",
    "details": "object | null"
  },
  
  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

**필드 설명**:

| 필드 | 설명 |
|------|------|
| **version** | A2A 프로토콜 버전 (Google A2A v0.3.0 기준) |
| **name** | 에이전트 이름 |
| **type** | 에이전트 타입 (Device vs System) |
| **role** | 에이전트의 구체적 역할 |
| **endpoint** | HTTP 통신 주소 (host, port, path) |
| **capabilities** | 지원 능력 목록 (Device Agent의 경우 actions[]) |
| **supported_methods** | JSON-RPC 메서드 목록 |
| **supported_message_types** | A2A 메시지 타입 목록 |
| **authentication** | 인증 방식 (향후 확장) |

**예시 (Device Agent)**:

```json
{
  "version": "v0.3.0",
  "name": "AUV-01 Agent",
  "type": "DEVICE_AGENT",
  "role": "DEVICE_CONTROL",
  "endpoint": {
    "host": "127.0.0.1",
    "port": 9201,
    "protocol": "HTTP",
    "path": "/message:send"
  },
  "capabilities": ["scan_area", "remove_mine", "return_to_base"],
  "supported_methods": ["message/send"],
  "supported_message_types": [
    "task.assign",
    "task.result",
    "event.report",
    "mission.result"
  ],
  "authentication": {
    "type": "token",
    "details": null
  },
  "created_at": "2026-05-15T10:00:00Z",
  "updated_at": "2026-05-15T10:00:00Z"
}
```

**예시 (System Agent - DeviceBridge)**:

```json
{
  "version": "v0.3.0",
  "name": "DeviceBridge Agent",
  "type": "SYSTEM_AGENT",
  "role": "DEVICE_BRIDGE",
  "endpoint": {
    "host": "127.0.0.1",
    "port": 9110,
    "protocol": "HTTP",
    "path": "/message:send"
  },
  "capabilities": ["task.assign", "task.result.aggregate", "event.logging"],
  "supported_methods": ["message/send"],
  "supported_message_types": [
    "task.assign",
    "task.result",
    "event.report",
    "mission.result",
    "child.register",
    "layer.assignment"
  ],
  "authentication": {
    "type": "none",
    "details": null
  },
  "created_at": "2026-05-15T10:00:00Z",
  "updated_at": "2026-05-15T10:00:00Z"
}
```

---

## 15. Event (시스템 사건 기록)

```json
{
  "id": "string (uuid)",
  
  "event_type": "string",
  // 예: USER_COMMAND_RECEIVED, SYS_ANOMALY_DETECTED, SYSTEM_ALERT, etc
  
  "context_id": "string (uuid)",
  // 이 Event가 속한 흐름의 ID (같은 사용자 명령, 같은 이상징후, 같은 task 등)
  // AgentLog와 함께 조회하여 전체 흐름 추적
  
  "actor_type": "SYSTEM | DEVICE | USER",
  "actor_id": "string (uuid) | null",
  
  "target_type": "MISSION | TASK | DEVICE | AGENT | SYSTEM",
  "target_id": "string (uuid) | null",
  
  "severity": "INFO | WARNING | CRITICAL",
  
  "data": {
    // Event 타입별로 다름
    // 예: { command: "...", user_id: "...", reason: "..." }
  },
  
  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

**특징**:

- **event_type**: 무슨 일이 일어났는가 (USER_COMMAND_RECEIVED, SYS_ANOMALY_DETECTED 등)
- **context_id**: 이 Event와 관련된 "흐름"의 ID
  - 같은 context_id를 가진 Event들은 같은 사건의 일부
  - 예: 사용자 명령 하나 → Event 1개, AgentLog 여러 개
- **actor_type/actor_id**: 누가 이 Event를 발행했는가
- **target_type/target_id**: 이 Event가 무엇에 대한 것인가
- **data**: Event 타입별 상세 정보 (JSON, 어떤 필드든 가능)

**설계 원칙**:

- Event는 "**무엇이 일어났는가**"만 기록 (간결함)
- Agent의 상세 판단/행동은 AgentLog에 기록
- Event 하나가 여러 AgentLog를 가질 수 있음 (같은 context_id)

---

## 16. AgentLog (Agent 실행 기록)

```json
{
  "id": "string (uuid)",
  
  "context_id": "string (uuid)",
  // Event.context_id와 동일 (같은 흐름에 속함)
  
  "event_id": "string (uuid) | null",
  // 이 로그가 직접 기록한 Event (없을 수도 있음)
  
  "agent_id": "string (uuid)",
  "agent_role": "REQUEST_HANDLER | DEVICE_BRIDGE | MISSION_PLANNER | POLICY_MANAGER | SYSTEM_SENTINEL | INSIGHT_REPORTER",
  
  "action": "string",
  // Agent가 수행한 행동 (예: "classify_intent", "call_mission_planner", "generate_proposal")
  
  "input": {
    // Agent가 받은 입력 데이터
  },
  
  "output": {
    // Agent가 생성한 출력 데이터
  },
  
  "reasoning": {
    // Agent의 판단 과정 (왜 이 선택을 했는가)
    // 예: { confidence: 0.95, llm_reasoning: "...", keywords_matched: [...] }
  },
  
  "status": "SUCCESS | FAILED | TIMEOUT",
  
  "duration_ms": "number | null",
  // 이 행동이 걸린 시간
  
  "error": "string | null",
  // 실패한 경우 에러 메시지
  
  "created_at": "timestamp"
}
```

**특징**:

- **context_id**: Event와 같은 흐름의 ID를 공유
  - `AgentLog.context_id = Event.context_id`로 조회 → 전체 흐름 추적
- **action**: Agent가 뭘 했는가 (의도 분류, A2A 호출, proposal 생성 등)
- **input/output**: 상세 데이터 (JSON, 크기 제약 없음)
- **reasoning**: Agent의 의사결정 과정 (LLM 이유, 신뢰도, 선택 사항 등)
- **status**: 성공/실패/타임아웃
- **duration_ms**: 성능 모니터링용

**조회 예시**:

```python
# 사용자 명령 흐름의 모든 내용 조회
events = registry_client.list_events(
    filters={"context_id": "ctx-123"}
)
logs = registry_client.list_agent_logs(
    filters={"context_id": "ctx-123"}
)

# RequestHandler의 의도 분류 과정 상세 조회
classify_log = registry_client.list_agent_logs(
    filters={
        "context_id": "ctx-123",
        "agent_role": "REQUEST_HANDLER",
        "action": "classify_intent"
    }
)
print(classify_log[0]["reasoning"])  # LLM의 판단 이유
```

---

## 참고

- **[ADR-002](../adr/ADR-002-proposal-as-solution-set.md)**: Proposal 구조
- **[ADR-003](../adr/ADR-003-capability-driven-task-assignment.md)**: required_action과 Device.actions[]의 매핑
- **[ADR-004](../adr/ADR-004-agent-endpoint-management.md)**: Agent.endpoint 추가
- **[ADR-005](../adr/ADR-005-event-triggered-rule-execution.md)**: Event와 Rule의 관계
- **[domain-model.md](domain-model.md)**: 각 엔티티의 역할과 관계
- **[principles.md](principles.md)**: 설계 원칙
