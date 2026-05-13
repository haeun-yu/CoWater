# ADR-004: Agent Endpoint Management

**상태**: Accepted  
**작성일**: 2026-05-12  
**선행 ADR**: ADR-001

---

## 상황 (Context)

AgentConnection을 통해 Device Agent 간 협력(RELAY, COORDINATE 등)을 구성하려면, **각 Agent가 어떻게 통신하는가**에 대한 정보가 필요합니다.

**문제**:
- AgentConnection.profile에 `endpoint_a`, `endpoint_b`가 있지만
- Device나 Agent 스키마에 endpoint 정보가 저장되지 않음
- AgentConnection 생성할 때 endpoint를 어떻게 얻을지 불명확

---

## 결정 (Decision)

**Agent 등록 API의 Request Body에 endpoint 정보를 포함하고, Agent 테이블에 저장합니다.**

### 1️⃣ **Agent 스키마 확장**

```typescript
Agent {
  id: string
  name: string
  type: "SYSTEM_AGENT" | "DEVICE_AGENT"
  device_id?: string
  
  // ← 추가된 필드
  endpoint?: {
    host: string           // IP 또는 도메인
    port: number          // 포트
    protocol: string      // HTTP, GRPC, WebSocket 등
    path?: string         // 경로 (예: /api/agent)
    auth_token_ref?: string   // 인증 토큰 참조
  }
  
  last_heartbeat_at?: string
  created_at: string
  updated_at: string
}
```

---

### 2️⃣ **Device Agent 초기화 & 등록 흐름**

Device Agent 시작 시 자동으로 수행되는 흐름:

```mermaid
graph TD
    A["Device Agent 시작<br/>(설정파일 로드)"] -->|device_id, capabilities| B{"IdentityStore<br/>확인"}
    B -->|캐시 있음<br/>(재기동)| C["기존 agent_id<br/>endpoint 사용"]
    B -->|캐시 없음<br/>(첫 실행)| D["1️⃣ Device 등록"]
    D -->|POST /devices/register| E["Registry<br/>(Device 저장)"]
    E -->|device_id, endpoint| F["2️⃣ Agent 등록"]
    F -->|POST /agents/register| G["Registry<br/>(Agent + endpoint 저장)"]
    G -->|agent_id 반환| H["3️⃣ IdentityStore 저장<br/>(.data/identity/{device_id}.json)"]
    C -->|4️⃣ Heartbeat 시작| I["System과<br/>A2A 통신"]
    H -->|4️⃣ Heartbeat 시작| I
```

### **Step 1: Device 등록** (캐시 없을 때만)

```json
POST /api/devices/register
{
  "device_id": "rov-1",
  "device_type": "ROV",
  "device_ip": "192.168.50.1",
  "device_port": 9001
}

Response:
{
  "device_id": "rov-1",
  "device_type": "ROV",
  "endpoint": {
    "host": "192.168.50.1",
    "port": 9001,
    "protocol": "HTTP"
  },
  "stream_endpoints": [
    {
      "type": "sensor_stream",
      "url": "ws://192.168.1.100:8002/stream/rov-1"
    }
  ],
  "created_at": "2026-05-13T10:30:45.123Z"
}
```

### **Step 2: Agent 등록** (Device 등록 후)

Device 등록에서 반환된 endpoint 정보를 사용하여 Agent를 등록합니다:

```json
POST /api/agents/register
{
  "name": "Agent_rov-1",
  "type": "DEVICE_AGENT",
  "role": "DEVICE_BRIDGE",
  "device_id": "rov-1",
  "endpoint": {
    "host": "192.168.50.1",
    "port": 9001,
    "protocol": "HTTP",
    "path": "/agent"
  },
  "capabilities": ["WIRED", "RF"],
  "gateway_agent_id": null
}

Response:
{
  "agent_id": "agent-rov-1-uuid",
  "device_id": "rov-1",
  "type": "DEVICE_AGENT",
  "role": "DEVICE_BRIDGE",
  "endpoint": {
    "host": "192.168.50.1",
    "port": 9001,
    "protocol": "HTTP",
    "path": "/agent"
  },
  "created_at": "2026-05-13T10:30:45.123Z"
}
```

### **Step 3: IdentityStore에 저장** (로컬 캐싱)

등록 응답 데이터를 로컬 JSON 파일에 저장합니다:

`.data/identity/rov-1.json`:
```json
{
  "device_id": "rov-1",
  "device_type": "ROV",
  "layer": "lower",
  "device_endpoint": {
    "host": "192.168.50.1",
    "port": 9001,
    "protocol": "HTTP"
  },
  
  "agent_id": "agent-rov-1-uuid",
  "agent_type": "DEVICE_AGENT",
  "agent_role": "DEVICE_BRIDGE",
  "agent_endpoint": "http://192.168.50.1:9001/agent",
  "capabilities": ["WIRED", "RF"],
  "gateway_agent_id": "agent-usv-1-uuid",
  "parent_id": 2,
  
  "sensors": [
    {
      "name": "front-camera",
      "type": "VIDEO",
      "endpoint": "ws://192.168.1.100:8002/stream/rov-1/front-camera"
    },
    {
      "name": "manipulator-cam",
      "type": "VIDEO",
      "endpoint": "ws://192.168.1.100:8002/stream/rov-1/manipulator-cam"
    }
  ],
  "telemetry_topics": [
    {
      "track_type": "VIDEO",
      "track_name": "front-camera",
      "topic": "device.telemetry.rov-1.VIDEO"
    },
    {
      "track_type": "VIDEO",
      "track_name": "manipulator-cam",
      "topic": "device.telemetry.rov-1.VIDEO"
    }
  ],
  
  "healthcheck_topic": "agents",
  "healthcheck_endpoint": "/healthcheck/rov-1",
  
  "is_submerged": true,
  "environment_state": "UNDERWATER",
  "active_mediums": ["WIRED"],
  "force_parent_routing": true,
  
  "registered_at": "2026-05-13T10:30:45.123Z"
}
```

### **캐시 재사용** (재기동 시)

Device Agent 재기동 시:
1. 설정파일(`device-config.yaml`) 로드 → device_id 확인
2. IdentityStore 확인 → `.data/identity/{device_id}.json` 존재?
3. 있으면: 파일에서 agent_id, endpoint 로드 → 바로 heartbeat 송신
4. 없으면: 위의 Step 1~3 수행

**이점**:
- ✅ 재기동 시 System Agent와의 재협상 불필요
- ✅ 네트워크 단절 중에도 agent_id/endpoint 유지
- ✅ 기존 AgentConnection 재활용 가능

---

### 3️⃣ **AgentConnection 자동 구성**

AgentConnection이 필요할 때(RELAY, COORDINATE 등), 시스템이 등록된 endpoint 정보를 자동으로 조회합니다.

```typescript
// AgentConnection 생성 시
AgentConnection {
  id: "conn-relay-1"
  agent_a_id: "agent-rov-1"      // ROV Agent
  agent_b_id: "agent-usv-1"      // USV Agent
  connection_type: "RELAY"
  
  profile?: {
    // ← 자동으로 채워짐
    endpoint_a: "http://192.168.1.100:8080/agent",  // Agent-A의 endpoint에서 조회
    endpoint_b: "http://192.168.1.50:8080/agent",   // Agent-B의 endpoint에서 조회
    
    protocol: "A2A"
    transport: "HTTP"
    network_type: "LOCAL_NETWORK"
    expires_at: "2026-06-12T10:00:00Z"
  }
  
  created_at: string
  updated_at: string
}
```

**자동 구성 로직 (3단계 필터링)**:
```typescript
function createAgentConnection(
  agent_a_id: string,
  agent_b_id: string,
  connection_type: string
) {
  const agent_a = getAgent(agent_a_id)
  const agent_b = getAgent(agent_b_id)
  
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // Step 1: 물리적 종속성 확인 (Gateway Check)
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  
  // ROV가 USV에 물리적으로 연결되어 있는가?
  if (agent_a.gateway_agent_id) {
    // agent_a는 부모(gateway)를 통해서만 통신 가능
    // agent_b는 반드시 gateway_agent_id와 일치해야 함
    if (agent_b.id !== agent_a.gateway_agent_id) {
      throw new Error(
        `Agent A (${agent_a.id}) has gateway ${agent_a.gateway_agent_id}, ` +
        `but trying to connect to ${agent_b.id}`
      )
    }
    // Fixed Routing: agent_a → gateway만 가능
    const gatewayConnection = {
      agent_a_id: agent_a.id,
      agent_b_id: agent_a.gateway_agent_id,
      connection_type: "GATEWAY",  // 특수 타입
      profile: {
        endpoint_a: buildEndpoint(agent_a.endpoint),
        endpoint_b: buildEndpoint(agent_b.endpoint),
        protocol: "A2A",
        transport: "HTTP",  // 부모 통신은 항상 HTTP
        network_type: "wired",  // Gateway는 항상 유선
      }
    }
    return saveAgentConnection(gatewayConnection)
  }
  
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // Step 2: 매체 교집합 확인 (Medium Matching)
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  
  // agent_a와 agent_b가 공통으로 지원하는 매체는?
  const commonMedias = agent_a.capabilities.filter(
    m => agent_b.capabilities.includes(m)
  )
  
  if (commonMedias.length === 0) {
    throw new Error(
      `No common media between ${agent_a.id} (${agent_a.capabilities}) ` +
      `and ${agent_b.id} (${agent_b.capabilities})`
    )
  }
  
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // Step 3: 환경별 가용성 필터 (Environmental Filter)
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  
  // 현재 환경에서 실제로 사용 가능한 매체는?
  const availableMedias = commonMedias.filter(media => {
    // 수중인 경우 acoustic만 가능
    if (agent_a.environment_state === "submerged" && media !== "acoustic") {
      return false
    }
    if (agent_b.environment_state === "submerged" && media !== "acoustic") {
      return false
    }
    // 둘 다 active_mediums에 포함되어야 함
    return agent_a.active_mediums.includes(media) &&
           agent_b.active_mediums.includes(media)
  })
  
  if (availableMedias.length === 0) {
    throw new Error(
      `No available media in current environment ` +
      `(A: ${agent_a.environment_state}, ${agent_a.active_mediums}; ` +
      `B: ${agent_b.environment_state}, ${agent_b.active_mediums})`
    )
  }
  
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // 최종: AgentConnection 생성
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  
  // 우선순위: wired > rf/internet > acoustic
  const selectedMedia = selectByPriority(availableMedias)
  
  const connection = {
    agent_a_id,
    agent_b_id,
    connection_type,
    profile: {
      endpoint_a: buildEndpoint(agent_a.endpoint),
      endpoint_b: buildEndpoint(agent_b.endpoint),
      protocol: "A2A",
      transport: detectTransport(selectedMedia),
      network_type: selectedMedia,
      active_mediums: availableMedias,  // 후보 매체들
      expires_at: calculateExpiry()
    }
  }
  
  return saveAgentConnection(connection)
}

// 우선순위 선택: wired > rf/internet > acoustic
function selectByPriority(medias: string[]): string {
  const priority = { "wired": 1, "rf": 2, "internet": 2, "acoustic": 3 }
  return medias.sort((a, b) => priority[a] - priority[b])[0]
}
```

---

### 4️⃣ **Endpoint 변경 시 처리 규칙**

```typescript
// Agent endpoint 변경 (권장하지 않음 - 모든 Connection에 영향)
PUT /api/agents/{agent_id}
{
  "endpoint": {
    "host": "192.168.1.101",  // 새로운 IP
    "port": 8080
  }
}

// 변경 처리 단계:
// Step 1: 해당 Agent이 참여한 모든 활성 AgentConnection 찾기
SELECT * FROM agent_connections 
WHERE (agent_a_id = '{agent_id}' OR agent_b_id = '{agent_id}')
  AND deleted_at IS NULL

// Step 2: 각 Connection의 profile 재계산 (endpoint 갱신)
AgentConnection {
  agent_a_id: "agent-rov-1",
  agent_b_id: "agent-usv-1",
  profile: {
    endpoint_a: "http://192.168.1.101:8080/agent",  // ← 새로운 IP로 갱신
    endpoint_b: "http://192.168.1.50:8080/agent"    // ← 그대로
  }
}

// Step 3: Task 전달 시점별 처리
// - 아직 배정되지 않은 Task: 새 endpoint 사용
// - 진행 중인 Task: 기존 endpoint 유지 (Task 완료까지)
// - 다음 Task부터: 새 endpoint 사용
```

**⚠️ 주의사항**:
- endpoint 변경은 **진행 중인 Task에 영향을 줄 수 있으므로** 가능한 한 **변경하지 않기**를 권장
- 변경이 불가피하면 진행 중인 Mission이 완료된 후 변경할 것

---

### 5️⃣ **Device Agent ↔ Device Agent 물리 통신 (AgentConnection.profile 활용)**

AgentConnection이 생성되면, Device Agent A는 Registry에서 AgentConnection을 조회하여 Device Agent B와 물리 통신을 시작합니다.

**흐름**:

```
1. Device Agent A (USV)
   └─ Registry에 요청: "Device B (ROV)와의 협력 정보 줄래?"
      GET /api/agent-connections?agent_a_id=agent-usv-1&agent_b_id=agent-rov-1
   
2. Registry
   └─ AgentConnection 응답:
      {
        "connection_type": "RELAY",
        "profile": {
          "endpoint_b": "192.168.1.50:9111",
          "network_type": "acoustic",
          "signal_strength": 85,
          "latency_ms": 500,
          "bandwidth_mbps": 0.5
        }
      }
   
3. Device Agent A
   └─ profile.network_type = "acoustic"
   └─ AcousticModemDriver 선택
   └─ profile.endpoint_b로 음파 통신 시작
   
4. Device Agent A → Device Agent B
   └─ 음파 신호로 명령 전송 (RELAY, COORDINATE 등)
```

**각 network_type별 드라이버 선택**:

```typescript
function getTransportDriver(profile) {
  switch (profile.network_type) {
    case "wired":
      return new HTTPDriver(profile.endpoint_b)
    case "acoustic":
      return new AcousticModemDriver(profile.endpoint_b)
    case "rf":
      return new RFModuleDriver(profile.endpoint_b)
    case "satellite":
      return new SatelliteDriver(profile.endpoint_b)
    default:
      throw new Error(`Unsupported network type: ${profile.network_type}`)
  }
}
```

**신호 강도, 지연시간 기반 Policy 실행**:

```
Rule: "signal_strength < 30% → RELAY 중단, 기본 임무로 복귀"
Rule: "latency_ms > 2000ms → COORDINATE 불가, SHARE_DATA만 허용"
```

이러한 profile 정보는 System Agent의 Policy/Rule Engine이 협력 관계 판단에 활용합니다.

---

## 결과 (Consequences)

### ✅ 이점
- **자동화**: AgentConnection 생성 시 endpoint 자동 조회 (수동 입력 X)
- **유연성**: Agent endpoint 변경 시 관련 AgentConnection도 자동 갱신
- **신뢰성**: 등록된 endpoint로만 통신 시도 (임의 통신 차단)

### ⚠️ 제약
- **등록 필수**: Agent는 반드시 endpoint와 함께 등록되어야 함
- **변경 추적**: endpoint 변경 시 이전 연결 재평가 필요

---

## 참고

- **docs/core/schema.md**: Agent, AgentConnection 스키마
- **docs/scenarios/lifecycle.md**: 1-1. Device Agent 등록
