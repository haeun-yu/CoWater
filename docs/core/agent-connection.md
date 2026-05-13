# AgentConnection Specification (Device 간 통신 관리)

**문서 버전**: 1.0  
**목적**: Device 간 통신 가능성을 관리하는 AgentConnection의 3단계 필터링, CRUD, soft-delete 기반 활성 관리

---

## 1. AgentConnection 정의

Device A에서 Device B로 통신 가능한지를 판단하는 **연결 객체**입니다.

```python
class AgentConnection:
    id: str                          # 고유 ID
    source_device_id: str            # 송신자 Device
    target_device_id: str            # 수신자 Device

    primary_medium: str              # 주 통신 매체 (WIRED, ACOUSTIC, ...)
    active_mediums: list[str]        # 사용 가능한 모든 매체

    gateway_agent_id: str            # 송신자의 gateway (relay용)
    environment_state: str           # "SURFACE", "UNDERWATER"

    deleted_at: datetime | null      # null = 활성, 값 있음 = 소프트 삭제
    
    created_at: datetime
    updated_at: datetime
```

---

## 2. 3단계 필터링 로직

AgentConnection 생성 시 SystemSentinel이 다음 3단계 검증을 수행합니다.

### Stage 1: Gateway 검증

**목적**: 통신 가능한 Gateway를 통해서만 연결

```python
def check_gateway(source: Device, target: Device) -> bool:
    """동일 Gateway를 사용하는가?"""
    
    # 규칙 1: 동일 Gateway를 가진 경우
    if source.gateway_agent_id == target.gateway_agent_id:
        return True
    
    # 규칙 2: 계층 관계 (Parent → Child)
    # source가 target의 parent gateway인 경우
    if source.device_id == target.gateway_agent_id:
        return True
    
    return False
```

**의의**: 같은 Gateway를 통해서만 신뢰할 수 있는 경로 확보

### Stage 2: 매체 교집합 확인

**목적**: 양쪽 Device 모두 지원하는 통신 매체 찾기

```python
MEDIUM_PRIORITY = {
    "Wired": 1,       # 최고 우선순위
    "RF": 2,
    "Acoustic": 3,
    "Satellite": 4,
    "Inertial": 5     # 최저 우선순위 (추정 항법)
}

def calculate_compatible_mediums(source: Device, target: Device) -> list[str]:
    """양쪽이 모두 지원하는 매체 목록"""
    compatible = set(source.available_mediums) & set(target.available_mediums)
    
    if not compatible:
        return []  # 호환 가능한 매체 없음
    
    # 우선순위 정렬
    return sorted(compatible, 
                  key=lambda m: MEDIUM_PRIORITY.get(m, 999))

def select_primary_medium(compatible_mediums: list[str]) -> str:
    """최고 우선순위 매체 선택"""
    return min(compatible_mediums, 
               key=lambda m: MEDIUM_PRIORITY.get(m, 999))
```

**예시**:
- Source (USV): RF, Satellite, Acoustic
- Target (AUV): Acoustic, Inertial
- **결과**: Acoustic만 호환 → primary_medium = "Acoustic"

### Stage 3: 환경별 필터링

**목적**: 현재 환경 상태에서 연결이 활성 가능한가?

```python
def check_environment_feasibility(source: Device, target: Device, 
                                   primary_medium: str) -> bool:
    """환경 제약 검증"""
    source_env = source.environment_state  # SURFACE, UNDERWATER
    target_env = target.environment_state
    
    # 규칙 1: 같은 환경 내에서는 항상 가능
    if source_env == target_env:
        return True
    
    # 규칙 2: 환경 교차 시 매체 확인
    # SURFACE → UNDERWATER (또는 역방향): Acoustic 또는 Wired만 가능
    if (source_env == "SURFACE" and target_env == "UNDERWATER") or \
       (source_env == "UNDERWATER" and target_env == "SURFACE"):
        return primary_medium in ["Acoustic", "Wired"]
    
    return False
```

**상태 전환 규칙**:
```
SURFACE:
  - depth > 5.0m     → UNDERWATER

UNDERWATER:
  - depth ≤ 0m       → SURFACE
```

---

## 3. CRUD 구현

SystemSentinel이 AgentConnection의 전체 생명주기를 관리합니다.

### 3.1 생성 (Create)

**발동 지점**: Device healthcheck 수신 시 새 Device 감지

```python
async def on_device_detected(device: Device):
    """새 Device 감지 → 모든 기존 Device와의 연결 검토"""
    
    existing_devices = await self.registry.get_devices()
    
    for other_device in existing_devices:
        if other_device.device_id == device.device_id:
            continue
        
        # 양방향 연결 검토
        for (source, target) in [(device, other_device), 
                                  (other_device, device)]:
            
            # 3단계 필터링
            if not check_gateway(source, target):
                continue
            
            compatible_mediums = calculate_compatible_mediums(source, target)
            if not compatible_mediums:
                continue
            
            primary_medium = select_primary_medium(compatible_mediums)
            
            if not check_environment_feasibility(source, target, primary_medium):
                continue
            
            # ✅ AgentConnection 생성
            conn = AgentConnection(
                source_device_id=source.device_id,
                target_device_id=target.device_id,
                primary_medium=primary_medium,
                active_mediums=compatible_mediums,
                gateway_agent_id=source.gateway_agent_id,
                environment_state=source.environment_state
            )
            
            await self.registry.post_agent_connection(conn)
            await self.publish_event(
                event_type="SYS_AGENT_CONNECTION_CREATED",
                payload={"connection_id": conn.id},
                target_agents=["MissionPlanner"]
            )
```

**MEB 이벤트**: `SYS_AGENT_CONNECTION_CREATED`

### 3.2 삭제 (Delete) - Soft Delete

| 상황 | 작업 | 타입 |
|------|------|------|
| 환경 조건 불만족 (환경 변화) | deleted_at 설정 (소프트 삭제) | 일시적 |
| Device 제거 또는 TTL 만료 | deleted_at 설정 (소프트 삭제) | 영구 |

`deleted_at IS NULL` 이면서 환경/신호 조건이 나쁜 경우는 삭제되지 않은 비정상 운영 상태로 간주합니다. 이 경우 AgentConnection 레코드는 유지하고, 판단/알림은 `SystemSentinel`이 Event/Alert로 처리합니다.

**Soft Delete 메커니즘**:
```python
async def delete_connection(conn_id: str):
    """AgentConnection 소프트 삭제"""
    conn = await self.registry.get_agent_connection(conn_id)
    conn.deleted_at = datetime.utcnow()
    await self.registry.put_agent_connection(conn_id, conn)
    
    await self.publish_event(
        event_type="SYS_AGENT_CONNECTION_DELETED",
        payload={"connection_id": conn_id, "reason": "environment_change|stale_ttl"},
        target_agents=["MissionPlanner"]
    )
```

**MEB 이벤트**: `SYS_AGENT_CONNECTION_DELETED`

---

## 4. 상태 관리

### 4.1 Registry 저장소 (System Agent 중심)

**Location**: Registry REST API `/agent-connections`

**Endpoints**:
```
POST   /agent-connections              # 생성
GET    /agent-connections              # 목록 조회
GET    /agent-connections/{id}         # 단일 조회
PUT    /agent-connections/{id}         # 업데이트
DELETE /agent-connections/{id}         # 삭제
GET    /devices/{id}/connections       # Device별 연결 조회
```

**담당**: SystemSentinel

### 4.2 Device Agent 로컬 캐시 (이벤트 기반 + 주기적 동기화)

**전략**: 
1. **Event-driven 즉시 업데이트** (100ms 반응)
2. **Periodic sync fallback** (MEB 손실 대비)

```python
class DeviceAgent:
    async def on_agent_connection_event(self, event_type: str, payload: dict):
        """AgentConnection 변경 이벤트 → 즉시 캐시 갱신"""
        if event_type == "SYS_AGENT_CONNECTION_CREATED":
            self.local_connections_cache[payload["connection_id"]] = payload
        elif event_type == "SYS_AGENT_CONNECTION_DELETED":
            self.local_connections_cache.pop(payload["connection_id"], None)
    
    async def periodic_sync_connections(self):
        """주기적 폴백 (매 5분)"""
        while True:
            connections = await self.registry.get_agent_connections_for_device(
                self.device_id
            )
            self.local_connections_cache = {conn.id: conn for conn in connections}
            await asyncio.sleep(300)
```

---

## 5. MEB 이벤트

AgentConnection 관련 MEB 이벤트 (총 4가지):

| event_type | 발행자 | 구독자 | 발행 시점 |
|-----------|--------|--------|---------|
| **SYS_AGENT_CONNECTION_CREATED** | SystemSentinel | MissionPlanner | 새 AgentConnection 생성 |
| **SYS_AGENT_CONNECTION_DELETED** | SystemSentinel | MissionPlanner | AgentConnection 소프트 삭제 (환경 변화, TTL 만료 등) |

---

## 6. 통합 워크플로우 예시

### Device 진입 → 연결 생성 → Task 할당

```
Device A (USV) 시작
    ↓
DEVICE_HEALTHCHECK MEB 발행
    ↓
SystemSentinel 수신
    ├─ 3단계 필터링 수행
    ├─ Device B (AUV)와의 연결 검토
    │  └─ Gateway ✓, 매체 (Acoustic) ✓, 환경 (SURFACE-UNDERWATER) ✓
    │
    └─ AgentConnection 생성
        └─ MEB: SYS_AGENT_CONNECTION_CREATED
           target_agents: [MissionPlanner]
            ↓
            MissionPlanner
            └─ 이제 Device A → Device B로 Task 할당 가능
                (또는 relay 경로 계산)
```

### Device 수중 진입 → 환경 상태 변화 → 연결 재평가

```
Device (USV) 수심 변화 감지
    ↓
depth > 5.0m (수중 진입)
    ↓
environment_state: SURFACE → UNDERWATER 변경
    ↓
DEVICE_HEALTHCHECK 발행 (meb pub 채널)
    └─ {"device_id": "USV-01", "environment_state": "UNDERWATER", ...}
    ↓
SystemSentinel 수신 (healthcheck에서 environment_state 변화 감지)
    ├─ 모든 AgentConnection 재검증
    │  └─ (예) USV-ROV 연결: 환경 교차 → Acoustic만 가능?
    │
    └─ 조건 불만족 시 deleted_at 설정
        └─ MEB: SYS_AGENT_CONNECTION_DELETED
```

---

## 7. Device-to-Device 통신 흐름

AgentConnection이 생성되어 있고 deleted_at이 null일 때, Device A는 Device B로 직접 A2A 통신 가능:

```
Device A (9201)
    │
    └─ AgentConnection 조회
        │
        └─ primary_medium 확인 (Acoustic)
            │
            └─ A2A HTTP POST Device B:9202/message:send
                └─ message_type: task.result (relay)
                    │
                    └─ Device B 수신 후 처리 또는 다음 Device로 relay
```

자세한 내용: [Communication Driver Strategy](communication-driver.md)

---

**관련 문서**:
- [Communication Driver](communication-driver.md)
- [Event Types](event-types.md)
- [Port Mapping](ports.md)
- [System Architecture](../SYSTEM_ARCHITECTURE.md)
