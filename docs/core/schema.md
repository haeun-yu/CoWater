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

  "type": "string", // SYS_INTENT_CLASSIFIED, SYS_TASK_RESULT, SYS_ANOMALY_DETECTED, SYS_MISSION_UPDATED, DEVICE_HEALTHCHECK, ENV_STATE_CHANGED 등

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
    // 예: SYS_TASK_RESULT -> { status: "FAILED", error_type: "...", ... }
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

  "status_updated_at": "timestamp",
  "status_reason": "string | null",

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
- **APPROVED** (고정 상태): 사용자가 이 Proposal을 선택/승인함. Proposal은 승인 시점까지만 추적하며, 이후에는 상태를 변경하지 않음
  - **참고**: Mission의 최종 결과(COMPLETED/FAILED/CANCELLED)는 Proposal.status에 반영되지 않음. 실행 결과는 Mission.status만 추적
- **REPLANNING**: 이전 Proposal이 채택되지 않았으므로 재계획 중 (status_reason 필드에 불채택 이유 기록)
- **CANCELLED**: 사용자가 거절 (status_reason에 거절 사유 기록)
- **EXPIRED**: 장시간 선택 안 됨

**필드 상세**:

- `selected`: 사용자가 이 Proposal을 선택했는지 여부 (true = 승인 절차 진행 중, false = 미선택)
- `reason`: REPLANNING 상태일 때, 이전 Proposal이 왜 채택되지 않았는지 기록 (사용자 피드백 요약)
- `limitations`: 사용자가 반드시 알아야 할 제약 사항이나 잠재적 위험 요소 (조건부 정보로, 최종 판단에 도움)
- `status_updated_at`: 마지막으로 상태가 변경된 시점 (모든 상태 전이 추적)
- `status_reason`: 현재 상태에 대한 사유 또는 설명 (취소/거절/재계획 사유 기록)
- `approved_at`: APPROVED 상태로 처음 전이된 시점 (초기 승인 기록)

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

  "status_updated_at": "timestamp",
  "status_reason": "string | null",

  "result_summary": "string | null",

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

## 참고

- **[ADR-002](../adr/ADR-002-proposal-as-solution-set.md)**: Proposal 구조
- **[ADR-003](../adr/ADR-003-capability-driven-task-assignment.md)**: required_action과 Device.actions[]의 매핑
- **[ADR-004](../adr/ADR-004-agent-endpoint-management.md)**: Agent.endpoint 추가
- **[ADR-005](../adr/ADR-005-event-triggered-rule-execution.md)**: Event와 Rule의 관계
- **[domain-model.md](domain-model.md)**: 각 엔티티의 역할과 관계
- **[principles.md](principles.md)**: 설계 원칙
