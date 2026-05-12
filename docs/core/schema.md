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
  
  "actions": ["string"],  // 자신이 수행 가능한 원자적 기능
                          // 예: ["MOVE_TO", "HIGH_RES_SCAN", "SAMPLE_COLLECTION"]
  
  "status": "ONLINE | OFFLINE | ERROR | DEGRADED | REMOVED",
  
  "position": {
    "latitude": "number",
    "longitude": "number"
  },
  
  "battery_percent": "number | null",
  "device_agent_id": "string (uuid) | null",  // 연관된 Device Agent
  
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
  
  "device_id": "string (uuid) | null",  // DEVICE_AGENT만 설정
  
  "endpoint": {
    "host": "string",        // IP 또는 도메인
    "port": "number",        // 포트
    "protocol": "string",    // HTTP, GRPC, WebSocket, SSE 등
    "path": "string | null", // 경로 (예: /api/agent)
    "auth_token_ref": "string | null"  // 인증 토큰 참조 (실제 토큰 X)
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
  "parent_agent_id": "string (uuid) | null",  // PARENT_CHILD 인 경우만
  
  "status": "CANDIDATE | ACTIVE | DEGRADED | INACTIVE | EXPIRED | REMOVED",
  
  "mission_id": "string (uuid) | null",
  
  "reason": "string | null",
  
  "profile": {
    "endpoint_a": "string",  // 자동 구성 (Agent.endpoint 기반)
    "endpoint_b": "string",
    
    "protocol": "A2A",
    "transport": "HTTP | SSE | GRPC | REST | CUSTOM",
    "network_type": "RF | LTE | SATELLITE | ACOUSTIC | LOCAL_NETWORK | OTHER",
    
    "auth_info_ref": "string | null",
    "expires_at": "timestamp | null"
  },
  
  "expires_at": "timestamp | null",
  
  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

**특성**:
- **profile**: Agent 테이블의 endpoint를 기반으로 자동 생성 (ADR-004)
- **status**: ACTIVE일 때만 통신 가능

---

## 5. Event (사건)

```json
{
  "id": "string (uuid)",
  
  "type": "string",  // USER_COMMAND, PROBLEM_DETECTED, TASK_FAILED, CRITICAL_HAZARD 등
  
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
  
  "priority": "LOW | NORMAL | HIGH | EMERGENCY",
  
  "target_area": "string | null",
  "target_position": {
    "latitude": "number",
    "longitude": "number"
  },
  
  "requires_approval": "boolean",
  
  "selected": "boolean",  // 사용자가 선택했으면 true (ADR-002)
  
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

---

## 7. ProposalTask (Task 후보)

```json
{
  "id": "string (uuid)",
  "proposal_id": "string (uuid)",
  
  "title": "string",
  
  "type": "DEVICE_TASK | SYSTEM_TASK | REPORT_TASK | NOTIFY_TASK",
  
  "required_action": "string",  // Device.actions[]에 있어야 함 (ADR-003)
  
  "sequence": "number",  // 실행 순서
  
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
  "cancelled_at": "timestamp | null",
  
  "result_summary": "string | null",
  "fail_reason": "string | null",
  "cancel_reason": "string | null",
  
  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

**상태 변이** (ADR-002):
- APPROVED (승인됨) → IN_PROGRESS (진행 중) → COMPLETED/FAILED/CANCELLED

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
  
  "status": "PENDING | ASSIGNED | IN_PROGRESS | COMPLETED | FAILED | CANCELLED",
  
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
  
  "started_at": "timestamp | null",
  "completed_at": "timestamp | null",
  "cancelled_at": "timestamp | null",
  
  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

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
  
  "name": "string",  // 예: "Critical Auto-Response Policy"
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

**역할**:
- 시스템의 운영 원칙 정의 (개념 수준)
- 여러 Rule이 단일 Policy 아래 속할 수 있음
- Policy.enabled로 전체 on/off 제어 가능

**예시**:
```
Policy: "Low Battery Auto-Return"
  ├─ Rule-1: "Battery < 20% → RETURN_TO_BASE"
  └─ Rule-2: "Battery 20-30% → Alert"
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
  
  "priority": "number",  // 낮을수록 먼저 실행
  
  "conditions": [
    {
      "field": "string",  // 예: "event.type", "device.battery_percent"
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

**역할** (ADR-005):
- Event 발생 시 실행될 조건 + 행동 정의
- Event-Triggered System의 핵심

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
  
  "priority": 1,  // 가장 높은 우선순위
  "enabled": true
}
```

---

## 13. Config (설정값)

```json
{
  "key": "string",  // 예: "device_offline_timeout_sec"
  
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

**역할**:
- 시스템/Rule에서 참조하는 파라미터
- 코드 수정 없이 운영 로직 조정 가능

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
  "key": "min_battery_percent_for_task",
  "value": 30,
  "type": "number",
  "scope": "PROBLEM_DETECTION",
  "description": "작업 할당 최소 배터리 %"
}

{
  "key": "max_proposal_options",
  "value": 3,
  "type": "number",
  "scope": "RECOMMENDATION",
  "description": "사용자에게 표시할 최대 Proposal 개수"
}

{
  "key": "agent_connection_recheck_interval_sec",
  "value": 10,
  "type": "number",
  "scope": "AGENT_CONNECTION",
  "description": "AgentConnection 상태 재평가 주기"
}
```

---

## 3. Sensor (센서)

```json
{
  "id": "string (uuid)",
  "device_id": "string (uuid)",
  
  "name": "string",
  
  "type": "CAMERA | SONAR | LIDAR | RADAR | GPS | IMU | DEPTH | TEMPERATURE | WATER_QUALITY | OTHER",
  
  "stream_endpoint": "string",  // 센서 데이터 스트림 주소
  
  "removed_at": "timestamp | null",  // null이면 활성, 값이 있으면 제거됨
  
  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

**특징**:
- System은 센서 데이터를 직접 구독하지 않음
- 센서 문제를 별도로 감지하지 않음
- endpoint 정보만 관리 (센서 가용성 메타데이터)

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
