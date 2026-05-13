# Event Type Catalog (MEB 이벤트 타입)

**문서 버전**: 1.0  
**목적**: Moth MEB에서 발행되는 모든 이벤트 타입과 구독자를 정의

---

## 1. MEB 채널 구조

### 1.1 단일 채널 설계

모든 이벤트는 **하나의 "agents" MEB 채널**로 통합:

```
MEB 채널: "agents"
  URL: wss://cobot.center:8287/pang/ws/meb?channel=instant&name=agents&source=base&track=base
  
이벤트 분류:
  ├─ event_type: "sys.intent.classified" (System Layer)
  ├─ event_type: "device.healthcheck" (Device Layer)
  └─ ... (총 13가지)
```

### 1.2 라우팅 메커니즘

**Push 방식** (송신자가 수신자 명시):

```json
{
  "event_type": "sys.intent.classified",
  "target_agents": ["MissionPlanner", "PolicyManager"],
  "payload": { ... }
}
```

각 Agent가 MEB를 구독할 때:
1. "agents" 채널 구독
2. 수신한 이벤트의 `target_agents` 필드 확인
3. 자신의 이름이 있으면 처리, 없으면 무시

---

## 2. System Layer 이벤트 (System Agent ↔ System Agent)

System Agent 간의 의사결정 프로세스를 이벤트로 추적.

### 2.1 의도 분류 (RequestHandler → others)

| event_type | 발행자 | 구독자 | 발행 시점 | 페이로드 |
|------------|--------|--------|---------|---------|
| **sys.intent.classified** | RequestHandler | MissionPlanner, PolicyManager, InsightReporter | 사용자 명령 해석 완료 | `{"intent": "MISSION", "goal": "...", "urgency": "high", "extracted_params": {...}}` |

### 2.2 Task 전달 (DeviceBridge → others)

| event_type | 발행자 | 구독자 | 발행 시점 | 페이로드 |
|------------|--------|--------|---------|---------|
| **sys.task.dispatched** | DeviceBridge | SystemSentinel, InsightReporter | Device에 Task 전달 | `{"task_id": "...", "device_id": "...", "action": "...", "timestamp": ...}` |
| **sys.task.result** | DeviceBridge | MissionPlanner, SystemSentinel, InsightReporter | Device로부터 Task 결과 수신 | `{"task_id": "...", "status": "COMPLETED", "result": {...}}` |

### 2.3 이상 징후 (SystemSentinel → others)

| event_type | 발행자 | 구독자 | 발행 시점 | 페이로드 |
|------------|--------|--------|---------|---------|
| **sys.anomaly.detected** | SystemSentinel | PolicyManager, InsightReporter | 규칙/패턴 기반 이상 탐지 | `{"device_id": "...", "anomaly_type": "LOW_BATTERY", "severity": "critical"}` |

### 2.4 정책 결정 (PolicyManager → others)

| event_type | 발행자 | 구독자 | 발행 시점 | 페이로드 |
|------------|--------|--------|---------|---------|
| **sys.policy.decision** | PolicyManager | MissionPlanner, InsightReporter | 정책 매칭 및 대응 결정 | `{"policy_id": "...", "action": "emergency_stop", "target_devices": [...], "auto_execute": true}` |

### 2.5 Mission 상태 변화 (MissionPlanner → others)

| event_type | 발행자 | 구독자 | 발행 시점 | 페이로드 |
|------------|--------|--------|---------|---------|
| **sys.mission.updated** | MissionPlanner | InsightReporter, SystemSentinel | Mission 상태 변화 (PROPOSED, APPROVED, COMPLETED 등) | `{"mission_id": "...", "status": "COMPLETED", "elapsed_time_s": 3600}` |

### 2.6 리포트 생성 (InsightReporter → clients)

| event_type | 발행자 | 구독자 | 발행 시점 | 페이로드 |
|------------|--------|--------|---------|---------|
| **sys.insight.report** | InsightReporter | 클라이언트 (웹 대시보드) | 데이터 분석 리포트 생성 완료 | `{"report_id": "...", "title": "...", "summary": "...", "insights": [...]}` |

---

## 3. AgentConnection 관련 이벤트

Device 간 통신 가능성을 관리하는 이벤트 (SystemSentinel 발행).

### 3.1 생성 & 활성화

| event_type | 발행자 | 구독자 | 발행 시점 | 페이로드 |
|------------|--------|--------|---------|---------|
| **sys.agent_connection.created** | SystemSentinel | MissionPlanner | 새 AgentConnection 생성 | `{"connection_id": "...", "source_device": "AUV-01", "target_device": "USV-01", "status": "ACTIVE"}` |
| **sys.agent_connection.activated** | SystemSentinel | MissionPlanner | 비활성 연결 → 활성화 | `{"connection_id": "...", "status": "ACTIVE"}` |

### 3.2 상태 변화 & 손실

| event_type | 발행자 | 구독자 | 발행 시점 | 페이로드 |
|------------|--------|--------|---------|---------|
| **sys.agent_connection.deactivated** | SystemSentinel | MissionPlanner | 활성 연결 → 비활성 (일시적) | `{"connection_id": "...", "status": "INACTIVE", "reason": "environment_change"}` |
| **sys.agent_connection.lost** | SystemSentinel | MissionPlanner | 연결 손실 (신호 약함 또는 미응답) | `{"source_device": "AUV-01", "target_device": "USV-01"}` |

### 3.3 삭제

| event_type | 발행자 | 구독자 | 발행 시점 | 페이로드 |
|------------|--------|--------|---------|---------|
| **sys.agent_connection.deleted** | SystemSentinel | MissionPlanner | AgentConnection 삭제 (TTL 만료 또는 수동 삭제) | `{"connection_id": "...", "reason": "stale_ttl"}` |

---

## 4. Device Layer 이벤트 (Device → System)

Device가 발행하는 상태 신호 (MEB를 통해 System에 전파).

### 4.1 Device 건전성

| event_type | 발행자 | 구독자 | 발행 시점 | 페이로드 |
|------------|--------|--------|---------|---------|
| **device.healthcheck** | Device (MEB relay: DeviceBridge) | SystemSentinel, InsightReporter | 주기적 (예: 10초) | `{"device_id": "AUV-01", "status": "ONLINE", "battery_percent": 85, "location": {...}}` |

### 4.2 Device 건전성 신호 (pub 채널)

| event_type | 발행자 | 구독자 | 발행 시점 | 페이로드 |
|------------|--------|--------|---------|---------|
| **device.healthcheck** | Device (pub) | SystemSentinel, InsightReporter | 주기적 (예: 10초) | `{"device_id": "AUV-01", "status": "ONLINE", "battery_percent": 85, "location": {...}, "environment_state": "UNDERWATER"}` |

---

## 5. 이벤트 구독 패턴

### 5.1 각 Agent의 구독 목록

```python
# RequestHandler
subscribe_to_events = []  # 구독 없음, 발행만 함

# DeviceBridge
subscribe_to_events = [
    "sys.task.dispatched",
    "sys.task.result"
]

# MissionPlanner
subscribe_to_events = [
    "sys.intent.classified",
    "sys.task.result",
    "sys.anomaly.detected",
    "sys.policy.decision",
    "sys.agent_connection.created",
    "sys.agent_connection.activated",
    "sys.agent_connection.deactivated",
    "sys.agent_connection.lost"
]

# PolicyManager
subscribe_to_events = [
    "sys.intent.classified",
    "sys.anomaly.detected"
]

# SystemSentinel
subscribe_to_events = [
    "device.healthcheck",
    "sys.task.dispatched"
]

# InsightReporter
subscribe_to_events = [
    "sys.intent.classified",
    "sys.task.dispatched",
    "sys.task.result",
    "sys.anomaly.detected",
    "sys.policy.decision",
    "sys.mission.updated",
    "device.healthcheck"
]
```

### 5.2 MEB 구독 구현 (Python/AsyncIO)

```python
class BaseAgent:
    async def subscribe_to_meb(self):
        """MEB 이벤트 구독"""
        await self.moth_client.subscribe(
            channel="agents",
            callback=self.on_meb_event
        )
    
    async def on_meb_event(self, event_type: str, payload: dict, 
                           target_agents: list[str]):
        """MEB 이벤트 수신"""
        # 1. target_agents 확인
        if self.agent_name not in target_agents:
            return  # 다른 Agent 대상 이벤트는 무시
        
        # 2. 이벤트 타입별 핸들러 호출
        handler = getattr(self, f"on_{event_type}", None)
        if handler:
            await handler(payload)
```

---

## 6. 이벤트 발행 패턴

### 6.1 MEB 발행 구현

```python
class BaseAgent:
    async def publish_event(self, event_type: str, payload: dict, 
                           target_agents: list[str]):
        """MEB에 이벤트 발행"""
        event = {
            "event_type": event_type,
            "target_agents": target_agents,
            "payload": payload,
            "timestamp": int(time.time() * 1000),  # Unix timestamp (ms)
            "source_agent": self.agent_name
        }
        
        await self.moth_client.publish(
            channel="agents",
            message=event
        )
```

### 6.2 예시: MissionPlanner가 Task 결과 수신 후 Mission 업데이트

```python
class MissionPlanner(BaseAgent):
    async def on_sys_task_result(self, payload: dict):
        """sys.task.result 이벤트 수신"""
        task_id = payload["task_id"]
        status = payload["status"]
        
        # Mission 상태 업데이트
        mission = await self.registry.get_mission_by_task(task_id)
        mission.status = "COMPLETED" if status == "COMPLETED" else "FAILED"
        await self.registry.update_mission(mission)
        
        # 다른 Agent에 알림
        await self.publish_event(
            event_type="sys.mission.updated",
            payload={
                "mission_id": mission.id,
                "status": mission.status,
                "elapsed_time_s": (time.time() - mission.start_time)
            },
            target_agents=["InsightReporter", "SystemSentinel"]
        )
```

---

## 7. 이벤트 흐름 다이어그램

### 7.1 사용자 명령 → Mission 실행

```
사용자 명령 (RequestHandler:9116)
    │
    ├─ MEB: sys.intent.classified
    │  target_agents: [MissionPlanner, PolicyManager]
    │
    ▼
MissionPlanner
    │
    ├─ MEB: sys.mission.updated (PROPOSED)
    │
    └─ (사용자 승인)
        │
        ├─ Registry: Task 생성
        │
        ├─ MEB: sys.task.dispatched
        │  target_agents: [SystemSentinel]
        │
        ├─ A2A: POST Device:9201/message:send (task.assign)
        │
        └─ Device 실행 (비동기)
            │
            └─ A2A: POST DeviceBridge:9110/message:send (task.result)
                │
                └─ MEB: sys.task.result
                   target_agents: [MissionPlanner, SystemSentinel]
                    │
                    └─ MissionPlanner: Mission 상태 업데이트
                        │
                        └─ MEB: sys.mission.updated (COMPLETED)
```

### 7.2 이상 징후 → 자동 대응

```
SystemSentinel (감시 루프)
    │
    ├─ 규칙: battery < 20% 감지
    │
    └─ MEB: sys.anomaly.detected
       target_agents: [PolicyManager]
           │
           ├─ PolicyManager: Policy 매칭
           │
           ├─ MEB: sys.policy.decision
           │  target_agents: [MissionPlanner]
           │
           └─ MissionPlanner: Emergency Mission 생성
               │
               └─ Device에 응급 Task 할당
```

---

## 8. 확장성 고려사항

### 8.1 신규 이벤트 타입 추가

새로운 이벤트를 추가할 때:
1. 이벤트 타입명 정의 (`sys.` 또는 `device.` 접두사)
2. 페이로드 스키마 정의
3. 구독 Agent 결정
4. 핸들러 메서드 구현

### 8.2 버전 관리

이벤트 구조 변경 시:
```json
{
  "event_type": "sys.task.result",
  "version": "1.0",  // 스키마 버전
  "payload": { ... }
}
```

---

**관련 문서**:
- [A2A Protocol](./a2a-protocol.md)
- [Port Mapping](./ports.md)
- [System Agent 설계](../SYSTEM_AGENT_DESIGN.md)
