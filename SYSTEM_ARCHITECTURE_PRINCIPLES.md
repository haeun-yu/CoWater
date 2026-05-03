# CoWater 시스템 아키텍처 원칙 및 규칙

**버전**: 1.2  
**최초 작성**: 2026-04-29  
**최종 수정**: 2026-05-03  
**변경 이력**:
- v1.1 (2026-04-30): Heartbeat 단일 공통 스트림으로 정리, A2A 전송 방식 정정 (Moth → HTTP), DEVICE_TYPES enum 추가, Safety-Critical 예외 규칙 추가, 하위→상위 이벤트 발행 케이스 추가, 표준 HTTP 클라이언트(`urllib.request`) 명시  
- v1.2 (2026-05-03): 계층 통신 규칙 개선(중간계층 없을 때 직접 통신 허용, 같은 계층 A2A 허용), 알림 전달 방식 polling→push(A2A) 변경, Heartbeat 주기 1초/3초 타임아웃으로 변경, Alert/Event 도메인 분리, System Layer 책임 확장(사용자 지시 의사결정·완료 알림·보고서·상태관리), Middle Layer 하위 에이전트 상태 인지 추가, 기뢰 탐지 시나리오 의사결정 플로우 개선  

**목적**: 시스템의 핵심 목적, 설계 원칙, 구현 규칙을 정의하여 팀원과 AI Agent가 일관된 방식으로 개발할 수 있도록 함

---

## 목차

1. [시스템의 비전 및 목적](#시스템의-비전-및-목적)
2. [핵심 설계 원칙](#핵심-설계-원칙)
3. [아키텍처 규칙](#아키텍처-규칙)
4. [계층별 책임](#계층별-책임)
5. [통신 및 메시징 규칙](#통신-및-메시징-규칙)
6. [상태 관리 원칙](#상태-관리-원칙)
7. [에러 처리 및 복원력](#에러-처리-및-복원력)
8. [개발 가이드라인](#개발-가이드라인)
9. [의사결정 플로우](#의사결정-플로우)
10. [코드 리뷰 체크리스트](#코드-리뷰-체크리스트)

---

## 시스템의 비전 및 목적

### 🎯 전체 비전

**CoWater**: 해양 무인 시스템(AUV, ROV, USV 등)의 자율적 협력 운영을 위한 멀티레이어 분산 에이전트 플랫폼

### 🎯 핵심 목적

1. **자율성**: 각 로봇이 자신의 역할을 독립적으로 수행
2. **협력**: 상위 지시를 받아 다른 로봇들과 협력
3. **강건성**: 개별 로봇 장애가 전체 시스템을 마비시키지 않음
4. **확장성**: 새로운 로봇 추가 시 기존 시스템 수정 최소화
5. **실시간성**: 중요한 메시지(경고, 명령)의 빠른 전달
6. **추적성**: 모든 의사결정과 행동의 기록

### 🎯 사용 사례 (예시: 기뢰 탐지 및 제거)

```
1. 센서 (외부 시스템) → 기뢰 탐지 Event 발행 → System Supervisor (A2A)
2. System Supervisor → Event 저장 및 탐지 위치 기록
3. System Supervisor → 위치 기반 근접 디바이스 분석 및 작업 디바이스 선정
   ├─ AUV: 정확한 위치 확인 임무 할당
   └─ ROV: 기뢰 제거 임무 할당
4. System Supervisor → 중간 계층(Control Ship) 존재 여부 판단
   ├─ If Yes → Control Ship (A2A): 작업 목록 전달
   │           └─ Control Ship → AUV/ROV (A2A): 개별 임무 지시
   └─ If No  → AUV/ROV 에 직접 A2A 전달
5. AUV, ROV → 임무 실행 → 결과를 A2A로 상위에 보고
6. System Supervisor → 모든 임무 완료 확인 → Alert(완료) 발행 + 보고서 생성/저장
```

---

## 핵심 설계 원칙

### 1️⃣ 계층화 (Layering)

**원칙**: 시스템은 3개의 명확한 계층으로 구성되며, 계층 간 통신은 정해진 프로토콜만 사용

```
┌─────────────────────────────────────────┐
│   System Layer (POC 06)                 │
│   - System Supervisor Agent             │
│   - 전체 시스템 모니터링 및 의사결정    │
└─────────────┬───────────────────────────┘
              │ A2A Message (task.assign)
              ↓
┌─────────────────────────────────────────┐
│   Middle Layer (POC 04, 05)             │
│   - Control Ship, USV Middle Agents     │
│   - 하위 디바이스 조율 및 중계          │
└─────────────┬───────────────────────────┘
              │ A2A Message (command)
              ↓
┌─────────────────────────────────────────┐
│   Lower Layer (POC 01, 02, 03)          │
│   - USV, AUV, ROV Lower Agents          │
│   - 실제 작업 수행                      │
└─────────────────────────────────────────┘
```

**규칙**:

- 하위 계층이 상위 계층으로 직접 메시지 보내면 안 됨 (항상 중간 계층을 거쳐야 함)
- 상위 계층이 하위 계층을 건너뛰어 직접 명령하면 안 됨
- **예외**: 중간 계층이 존재하지 않을 경우, 상위↔하위 간 직접 A2A 통신 허용
- 각 계층은 자신의 책임만 담당

### 2️⃣ 자율성과 의존성 최소화

**원칙**: 각 에이전트는 최대한 독립적으로 동작하되, 필요한 정보는 Registry나 Moth를 통해 획득

**규칙**:

- 에이전트는 다른 에이전트의 내부 상태를 직접 조회하면 안 됨
- 모든 공유 정보는 Registry 또는 Moth pub-sub을 통해서만 접근
- "필요한 정보를 얻기 위해 A 에이전트가 B 에이전트를 기다려야 하는" 상황 금지

**예외 — 하위 에이전트가 상위에 이벤트를 전달해야 하는 경우**:

하위 에이전트가 자체 센서로 중요 이벤트를 감지했을 때는 상위로 이벤트를 올려야 한다. 이 경우 **A2A 메시지**를 통해 상위(또는 중간 계층)에 직접 전달한다. Registry에 poll 방식으로 올리는 것이 아니라, System Agent가 이벤트를 먼저 수신(push)받는 구조를 따른다.

```
AUV가 기뢰 감지
    ↓ (Registry polling 방식 ❌)
    ↓ A2A → Middle Agent (중간 계층 있을 경우)  ✅
              └─ A2A → System Supervisor
    ↓ A2A → System Supervisor (중간 계층 없을 경우)  ✅
        { message_type: "event.report", event_type: "mine_detection", severity: "critical", location: {...} }
```

> Registry가 하위 서버에 직접 접근하는 구조는 허용되지 않는다. Registry는 수동적 저장소 역할만 담당한다.

**허용되는 상위 참조**:
- Registry에서 자신의 `parent_id`나 부모 에이전트의 엔드포인트 조회 → ✅ (공개 정보)
- 부모 에이전트의 `/state` 직접 조회 → ❌

### 3️⃣ 명확한 책임 경계 (Single Responsibility)

**원칙**: 각 에이전트는 하나의 명확한 책임을 가짐

| 에이전트                   | 책임                                        |
| -------------------------- | ------------------------------------------- |
| Registry (POC 00)          | 디바이스 등록, 위치 관리, 하트비트 수신 처리 |
| System Supervisor (POC 06) | 이벤트/알림 수신, 최고 수준 의사결정, 미션 할당, 디바이스·Agent 상태관리 |
| Control Ship (POC 05)      | 하위 디바이스 조율, A2A 라우팅, 하위 에이전트 상태 인지 |
| AUV/ROV/USV (POC 01-03)    | 할당받은 임무 실행                          |

**규칙**:

- "하나의 에이전트가 여러 책임을 가져야 하는" 상황은 아키텍처 문제
- 새 기능 추가 시 기존 에이전트 책임에 벗어나면 새 에이전트 추가 검토

### 4️⃣ 명시적 메시징 (Explicit Messaging)

**원칙**: 모든 의도적 상호작용은 명시적 메시지(하트비트, A2A, 명령어)로 표현되어야 함

**규칙**:

- 암묵적 상태 공유 금지 (예: "파일을 몰래 수정하면 다른 에이전트가 읽을 거야")
- 모든 중요한 메시지는 로깅되어야 함
- Moth를 통해 발행된 메시지는 외부에서 추적 가능해야 함

### 5️⃣ 약속된 인터페이스 (Contract-Based)

**원칙**: 에이전트 간 상호작용은 명확히 약속된 메시지 형식으로만 가능

**규칙**:

- A2A 메시지 형식 변경 시 모든 수신자에게 영향 → 반드시 호환성 유지 또는 버전 관리
- API 응답 형식은 문서화되어야 하고, 변경 시 마이그레이션 계획 필요
- "암묵적 이해"에 의존하는 인터페이스 금지

---

## 아키텍처 규칙

### 디바이스 타입 Enum (공식 정의)

실제 Registry 서버(`src/core/models.py`)에 정의된 공식 값. 에이전트 등록, heartbeat, A2A 메시지 모두 이 값을 사용한다.

```python
DEVICE_TYPES = Literal["USV", "AUV", "ROV", "CONTROL_SHIP", "SYSTEM"]
LAYERS      = Literal["lower", "middle", "system"]
```

| DEVICE_TYPE | 계층 | 설명 |
|---|---|---|
| `USV` | lower | 무인 수상 로봇 |
| `AUV` | lower | 자율 수중 로봇 |
| `ROV` | lower | 원격 수중 로봇 |
| `CONTROL_SHIP` | middle | 지휘함 (하위 디바이스 조율) |
| `SYSTEM` | system | System Supervisor |

> ⚠️ 소문자 사용 금지. Registry API는 대문자만 허용하며, 소문자로 보내면 유효성 검사 오류 발생.

---

### 포트 할당 규칙

```
8280      Device Registry Server (POC 00)
9010      AUV Lower Agent (POC 02)
9011      ROV Lower Agent (POC 03)
9012      USV Lower Agent (POC 01)
9014      USV Middle Agent (POC 04)
9015      Control Ship Middle Agent (POC 05)
9116      System Supervisor Agent (POC 06)
```

**규칙**:

- 각 POC는 기본 포트를 가짐
- 포트 충돌 시 config.json에서 변경 (코드 수정 금지)
- 다중 인스턴스 실행 시 포트 번호가 중복되면 안 됨

### 메시지 라우팅 규칙

```
System Supervisor (9116)
    ↓ [A2A]
Control Ship (9015)
    ├─ [A2A] → AUV (9010)
    ├─ [A2A] → ROV (9011)
    └─ [A2A] → USV (9012)
```

**규칙**:

- 상위 → 하위: A2A 메시지 사용 (중간 계층 경유, 없으면 직접)
- 하위 → 상위: A2A 메시지 사용 (중간 계층 경유, 없으면 직접)
- 같은 계층: 필요 시 A2A로 직접 통신 가능 (상위가 양측에 A2A 주소를 전달한 경우 등)

### 데이터 흐름 규칙

**Moth pub-sub 채널**:

- `device.heartbeat`: 모든 디바이스와 시스템의 주기적 상태 스냅샷(생존, 위치, 배터리)
- `system.a2a`: 에이전트 간 A2A 메시지 (대시보드 시각화용)
- `device.telemetry`: 센서 데이터 스트림
- `system.event`: 발생한 이벤트 스트림 (기뢰 감지 등 실제 문제 도메인)
- `system.alert`: 이벤트에 의해 생성된 알림 스트림

> 모든 **에이전트 간 이벤트 통신은 A2A**, 모든 **데이터 스트림(센서·상태·로그)은 Moth**를 사용한다.

**Registry**:

- 읽기: 모든 에이전트가 자유롭게 접근 가능
- 쓰기: 자신의 정보만 업데이트 가능 (다른 디바이스 정보 수정 불가)

---

## 계층별 책임

### System Layer (POC 06)

**책임**:

1. 하위 에이전트 또는 외부 시스템으로부터 A2A로 **이벤트/알림 수신** (push 방식)
2. 각 이벤트·알림에 대한 **의사결정** (DecisionEngine)
3. **사용자의 자연어 지시에 대한 의사결정** — 현재 자원이나 상황으로 불가능한 작업은 사용자에게 명확히 알림, 진행 중인 작업도 사용자에게 알릴 수 있어야 함
4. 적절한 middle-layer 에이전트(또는 중간 계층이 없으면 lower-layer)에 A2A 메시지 전송
5. 모든 작업이 완료되면 **완료 알림(Alert) 발행** + **보고서 생성 및 저장**
6. 의사결정 이력 저장
7. **디바이스 및 Agent 상태관리** — Registry heartbeat 데이터 수신, offline 감지, 비정상 상태 감지, 재할당 판단

**할 수 없는 것**:

- ❌ 중간 계층이 존재함에도 하위 에이전트에 직접 명령 (중간 계층 있는 경우)
- ❌ Registry에 저장된 다른 디바이스의 정보 수정
- ❌ 다른 System Supervisor와 통신 (구조상 1개만 존재)

**주요 인터페이스**:

```
POST http://localhost:9116/message:send    # 외부로부터 A2A 이벤트/알림 수신
POST http://target:9015/message:send       # Control Ship에 A2A 전송
POST http://target:9010/message:send       # 중간 계층 없을 때 lower에 직접 A2A 전송
GET  http://localhost:8280/devices         # 디바이스 목록 및 상태 조회
```

### Middle Layer (POC 04, 05)

**책임**:

1. System Supervisor로부터 받은 A2A 메시지 처리
2. 받은 명령을 하위 에이전트들에게 분배
3. **하위 에이전트들의 상태 인지** — heartbeat 수신 또는 Registry 조회를 통해 하위 에이전트의 생존 여부·위치·배터리·임무 상태를 파악
4. A2A를 통해 작업 결과 및 이벤트를 System Supervisor에게 보고

**일반적으로 할 수 없는 것**:

- ❌ 독립적인 의사결정 (시스템 명령이 없이 자체 판단으로 명령 발송)
- ❌ System Supervisor를 건너뛰고 직접 Registry 알림 생성

**Safety-Critical 예외** (즉각 조치가 필요한 경우):

상위 에이전트의 지시를 기다릴 수 없는 상황에서는 Middle Layer도 독립 판단이 허용된다.

| 상황 | 허용 조치 | 이유 |
|---|---|---|
| 자식 디바이스 배터리 < 10% | 즉시 귀환 명령 | 손실 방지 |
| 자식 디바이스와 통신 두절 (30초) | 마지막 알려진 위치로 복구 명령 | 장애 격리 |
| 충돌 위험 감지 | 즉시 비상정지 | 물리적 안전 |

조치 이후에는 반드시 **A2A로 System Supervisor에게 이벤트를 보고**하여 상위가 인지하도록 한다.

**주요 인터페이스**:

```
POST http://localhost:9015/message:send    # 외부(System/Lower)로부터 A2A 수신
POST http://target:9010/message:send       # Lower agent에 A2A 전송
POST http://localhost:9116/message:send    # System Supervisor에 A2A 보고
GET  http://localhost:8280/devices         # 하위 디바이스 상태 조회
```

### Lower Layer (POC 01, 02, 03)

**책임**:

1. Middle layer로부터 받은 명령 실행
2. 주기적으로 heartbeat 발행 (10초)
3. 센서 데이터를 telemetry로 발행
4. 작업 결과를 상위에 보고

**일반적으로 할 수 없는 것**:

- ❌ 상위 계층의 지시 없이 독립적으로 행동
- ❌ 다른 lower agent와 직접 통신

**Safety-Critical 예외**:

| 상황 | 허용 조치 |
|---|---|
| 자신의 배터리 < 5% | 자체 판단으로 귀환 시작 |
| 장애물 충돌 임박 | 자체 판단으로 비상정지 |
| 중요 이벤트(기뢰 감지 등) 감지 | A2A로 중간 계층(또는 System Supervisor)에 즉시 보고 |

> 단, 이러한 자율 판단 이후에는 반드시 A2A 또는 heartbeat를 통해 상위에 상황을 알려야 한다.

**주요 인터페이스**:

```
POST http://localhost:9010/message:send    # A2A 수신 (상위 또는 같은 계층으로부터)
POST http://localhost:9015/message:send    # A2A로 중간 계층에 이벤트 보고
POST http://localhost:9116/message:send    # A2A로 System Supervisor에 직접 보고 (중간 계층 없을 때)
Moth: device.heartbeat 채널에 발행         # 1초 주기 상태 발행
```

---

## 통신 및 메시징 규칙

### Heartbeat 메시지

**목적**: 주기적으로 "나는 살아있고 정상 작동 중"을 알림

**발행 주기**: 1초  
**타임아웃**: 3초 (3회 heartbeat 미수신 시 offline 판단)  
**복구**: heartbeat가 다시 수신되면 즉시 online으로 전환

#### 단일 공통 스트림 (실제 구현 기준)

각 디바이스와 시스템은 heartbeat를 **하나의 공통 스트림**에 발행한다:

| 채널 | 예시 | 목적 |
|---|---|---|
| `device.heartbeat` | `device.heartbeat` | **공통 채널** — Registry(POC 00)가 구독하여 전체 디바이스 상태 추적 및 위치/배터리 갱신 |

> 공통 스트림에는 `device_id`, `status`, `latitude`/`longitude`, `battery_percent` 같은 최소 상태가 함께 포함된다. Registry는 이 하나의 스트림만 보고 생존 여부와 최신 위치를 갱신한다.

**메시지 형식**:

```json
{
  "device_id": "auv-001",
  "agent_id": "agent-uuid",
  "timestamp": "2026-04-29T10:30:00Z",
  "latitude": 37.003,
  "longitude": 129.425,
  "altitude": -25,
  "battery": 85,
  "heading": 45,
  "speed": 1.5
}
```

**위치/배터리가 heartbeat에서 빠졌을 때 사이드 이펙트**:

Registry는 heartbeat을 수신할 때 `latitude`/`longitude`와 `battery_percent`가 있으면 디바이스 상태를 업데이트한다. 이 값들이 없으면:
1. Registry의 위치 정보가 이전 값 그대로 유지 (stale)
2. 대시보드/다른 에이전트가 Registry 조회 시 **오래된 위치** 반환
3. 기뢰 탐지 등 위치 기반 의사결정 시 **잘못된 좌표로 미션 할당** 가능
4. GPS와 별도로 `device.telemetry.{id}.gps` 채널로 위치를 발행하더라도 Registry 업데이트는 발생하지 않음 (telemetry는 Registry가 구독하지 않음)
5. 배터리 값이 누락되면 배터리 기반 안전 판단이 stale 상태를 그대로 사용할 수 있음

**규칙**:

- 모든 에이전트는 **1초마다** heartbeat 발행 의무
- 3초 이상 heartbeat 미수신 시 Registry가 자동으로 오프라인 처리
- heartbeat가 다시 수신되면 즉시 online 상태로 복구
- GPS 데이터가 있을 경우 반드시 heartbeat에 포함 (위치 정확성 유지)

### A2A (Agent-to-Agent) 메시지

**목적**: 에이전트 간 명령/이벤트 전달

**전송 방식**: Moth 채널이 아닌 **HTTP POST 직접 호출** (실제 구현 기준)

```
POST http://{target_endpoint}/message:send
```

> Moth의 `system.a2a` 채널은 대시보드 시각화용 발행에만 사용될 수 있으며, 실제 명령 전달은 각 에이전트의 HTTP 엔드포인트를 직접 호출한다. target_endpoint는 Registry의 `agent.endpoint` 필드에서 획득.

**메시지 형식**:

```json
{
  "jsonrpc": "2.0",
  "method": "message/send",
  "id": "uuid",
  "params": {
    "message": {
      "role": "user",
      "parts": [
        {
          "type": "data",
          "data": {
            "message_type": "task.assign",
            "action": "survey_depth",
            "params": {
              "mission_type": "mine_clearance",
              "location": { "lat": 37.003, "lon": 129.425 }
            },
            "reason": "System supervisor decision"
          }
        }
      ]
    },
    "taskId": "uuid",
    "metadata": {}
  }
}
```

**규칙**:

- `message_type`: task.assign, layer.assignment 등으로 명확히 구분
- `action`: 수신자가 수행할 구체적 행동
- `reason`: 왜 이 명령을 내렸는지 설명 (감시 및 분석용)
- 모든 A2A 메시지는 로깅되어야 함

### Telemetry 메시지

**목적**: 센서 데이터를 실시간으로 발행

**채널**: `device.telemetry`

**메시지 형식**:

```json
{
  "device_id": "auv-001",
  "timestamp": "2026-04-29T10:30:00Z",
  "sensor_type": "sonar",
  "data": {
    "frequency": 200,
    "range": 500,
    "target_detected": true,
    "target_distance": 150
  }
}
```

**규칙**:

- sensor_type로 센서 종류 명시
- 센서별로 다른 데이터 구조 가능
- 민감한 정보 제거 (보안)

### Alert / Event 도메인 분리

**원칙**: Alert와 Event는 별개의 도메인으로 분리하여 관리한다.

| 도메인  | 설명                                               | 예시                                             |
| ------- | -------------------------------------------------- | ------------------------------------------------ |
| `Event` | 실제로 발생한 문제 또는 상황에 대한 도메인         | 기뢰 감지, 배터리 부족, 통신 두절                |
| `Alert` | Event에 의해 생성된 알림 — 의사결정을 위한 신호     | "기뢰 탐지 알림", "배터리 부족 알림"             |

- Event는 실제 발생 사실(fact)을 기록하고 상위로 A2A 전달
- Alert는 Event를 기반으로 System Supervisor가 생성하는 의사결정 트리거
- Alert 없이도 Event는 독립적으로 저장/이력화 가능

**이벤트 메시지 예시**:

```json
{
  "message_type": "event.report",
  "event_type": "mine_detection",
  "severity": "critical",
  "location": { "lat": 37.003, "lon": 129.425 },
  "detected_by": "auv-001",
  "timestamp": "2026-05-03T10:30:00Z"
}
```

---

## 상태 관리 원칙

### 단일 진실 공급원 (Single Source of Truth)

**원칙**: 각 정보의 "진실"은 정확히 한 곳에만 존재

| 정보                  | 진실의 출처                               |
| --------------------- | ----------------------------------------- |
| 디바이스 위치         | Registry (heartbeat로 업데이트)           |
| 디바이스 연결 상태    | Registry (heartbeat timeout — 3초)        |
| 현재 활성화된 임무    | 해당 에이전트의 state                     |
| 이벤트 (발생한 사실)  | System Supervisor (A2A 수신 후 저장)      |
| 알림 (Alert)          | System Supervisor (이벤트 기반으로 생성)  |
| 에이전트 간 통신 이력 | Moth pub-sub + 각 에이전트의 inbox/outbox |

**규칙**:

- 한 정보가 여러 곳에 동시에 존재하면, 동기화 로직 필수
- 동기화 필요한 경우, 명확한 "master" 지정
- 충돌 시 해결 방법 명시

### 상태의 일관성 (Consistency)

**규칙**:

- A가 B에게 명령을 보내면, 두 곳 모두 그 명령의 기록을 유지
- Registry의 디바이스 정보와 실제 디바이스 상태가 다르면, Registry 신뢰 (다음 heartbeat 까지 기다림)
- 중간에 통신 끊김이 발생해도 데이터 손실 없이 복구 가능해야 함

---

## 에러 처리 및 복원력

### 장애 분류 및 대응

| 장애 유형             | 원인                    | 대응                                      |
| --------------------- | ----------------------- | ----------------------------------------- |
| **Heartbeat Timeout** | 에이전트 다운           | 3초 미수신 시 자동 오프라인 처리, 자식 재할당 |
| **Network Error**     | Moth/Registry 연결 끊김 | 자동 재연결 (5초 주기)                    |
| **Message Loss**      | 전송 중 에러            | 재전송 (발신자가 책임)                    |
| **Deadlock**          | 순환 대기               | 타임아웃 설정 (A→B 메시지 응답 30초 대기) |

### 복원력 원칙 (Resilience)

**원칙**: 한 에이전트의 장애가 전체 시스템을 마비시키면 안 됨

**규칙**:

1. **타임아웃**: 모든 외부 호출은 타임아웃 설정 필수

   ```python
   urllib.request.urlopen(req, timeout=5)  # 5초 이상 걸리면 에러
   ```

2. **재연결**: 연결 끊김 시 자동으로 재연결 (지수 백오프)

   ```python
   # 1차 실패: 1초 후 재시도
   # 2차 실패: 2초 후 재시도
   # 3차 실패: 4초 후 재시도
   # ... (최대 30초)
   ```

3. **로깅**: 모든 에러는 로깅되어야 함

   ```python
   logger.error(f"Failed to send A2A to {target}: {e}")
   ```

4. **Graceful Degradation**: 선택적 기능 실패는 핵심 기능을 막으면 안 됨
   - 예: LLM 분석 실패 → 규칙 기반 decision으로 폴백

---

## 개발 가이드라인

### 코드 작성 원칙

#### 1. 명확한 책임 (SRP)

```python
# ❌ 나쁜 예: 여러 책임을 혼합
class ControlShip:
    def handle_a2a_message(self, msg):
        # A2A 처리
        # + Moth 발행
        # + Registry 업데이트
        # + 자식 에이전트 관리
        pass

# ✅ 좋은 예: 각각 분리
class ControlShip:
    def handle_a2a_message(self, msg):
        # A2A 처리만 담당
        pass

    def publish_heartbeat(self):
        # Moth 발행은 별도
        pass

    def update_registry(self):
        # Registry 업데이트는 별도
        pass
```

#### 2. 명시적 에러 처리

```python
# ❌ 나쁜 예: 에러 무시
try:
    response = urllib.request.urlopen(req)
except:
    pass  # 에러 무시

# ✅ 좋은 예: 에러 처리 및 로깅
try:
    response = urllib.request.urlopen(req, timeout=5)
except urllib.error.HTTPError as e:
    logger.error(f"HTTP error: {e.code}")
    raise  # 또는 적절한 폴백
except Exception as e:
    logger.error(f"Network error: {e}")
    await self._retry_with_backoff()
```

#### 3. 로깅 규칙

```python
# 형식: [Component] Level: Message
logger.info("[ControlShip] A2A message received from System Supervisor")
logger.warning("[AUV] Battery low: 15%")
logger.error("[ROV] Failed to connect to parent: connection timeout")
```

#### 4. HTTP 클라이언트 표준

```python
# ✅ 표준: urllib.request (표준 라이브러리, 외부 의존성 없음)
import urllib.request
import json

req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
with urllib.request.urlopen(req, timeout=5) as resp:
    result = json.loads(resp.read().decode())

# ⚠️ 예외: LLM 클라이언트 호출 시에만 httpx 허용 (비동기 필요)
import httpx  # llm_client.py 내부에서만 사용
```

#### 5. 설정 vs 코드

```python
# ❌ 나쁜 예: 포트가 코드에 하드코딩
app = create_app()
app.run(host="127.0.0.1", port=9015)

# ✅ 좋은 예: config에서 읽음
config = load_config("config.json")
app = create_app(config)
app.run(host=config["server"]["host"], port=config["server"]["port"])
```

### 동작 검증 규칙

> 여기서 테스트는 unit test가 아닌 **실제 동작(end-to-end) 테스트**를 의미한다. 각 에이전트는 실제 서버로 띄웠을 때 다음을 보장해야 한다.

**필수 검증 항목**:

- `GET /health` → 200 OK 응답
- Moth 연결 없어도 단독 실행 가능 (graceful degradation)
- Registry 연결 없어도 기본 동작 유지 (연결 실패 시 재시도, 서비스 중단 금지)
- 1초 주기 heartbeat가 실제로 발행되는지 확인 (`tail -f logs/device.log | grep Heartbeat`)

**동작 테스트 방법**:

```bash
# 1. 에이전트 실행
python device_agent.py

# 2. 헬스체크
curl http://localhost:{port}/health | jq .

# 3. 상태 확인
curl http://localhost:{port}/state | jq .

# 4. Moth 메시지 실시간 확인
tail -f logs/device.log | grep "Heartbeat\|A2A\|Telemetry"
```

---

### 버전 관리 규칙

#### API 변경 시

1. **구버전 지원**: 최소 1 메이저 버전까지는 구 형식 지원
2. **마이그레이션 경로**: 변경 전에 마이그레이션 가이드 문서화
3. **Deprecation Warning**: 변경 예정을 미리 공지

#### 메시지 형식 변경 시

```python
# 변경 전: 새 필드 추가 (하위호환성 유지)
{
  "message_type": "task.assign",
  "action": "survey_depth",
  "params": {...},
  # 새 필드 (선택)
  "priority": "high"
}

# 변경 후: 구 필드 제거 (1 버전 후)
{
  "message_type": "task.assign",
  "action": "survey_depth",
  "params": {...},
  "priority": "high"  # 이제 필수
}
```

---

## 의사결정 플로우

### 기뢰 탐지 시나리오 의사결정

```
입력: A2A로 mine_detection 이벤트 수신 (System Supervisor)
      └─ event_type: "mine_detection"
      └─ severity: "critical"
      └─ location: {lat, lon}  ← 탐지 위치 저장

↓ System Supervisor의 event 처리

사전 작업: 위치 기반 디바이스 분석
├─ 탐지 위치 저장
├─ 위치에 가까운 디바이스 목록 조회 (Registry)
├─ 각 디바이스의 상태/가용성 확인
└─ 작업 할당 디바이스 선정
   ├─ AUV: 정확한 위치 확인 임무
   └─ ROV: 기뢰 제거 임무

의사결정 1: 중간 계층(Control Ship)이 존재하는가?
├─ If Yes → Control Ship에 작업 목록 A2A 전달
│           └─ Control Ship → 각 디바이스에 A2A 전달
└─ If No  → 각 디바이스에 직접 A2A 전달

의사결정 2: 해당 디바이스가 응답 가능 상태인가?
├─ If Yes → A2A 메시지 전송
└─ If No  → 대안 디바이스 탐색 또는 사용자에게 불가 알림

결과: A2A 메시지 발송 및 로깅
완료: 모든 임무 완료 시 → Alert(완료) 발행 + 보고서 생성 저장
```

### 의사결정 권한 매트릭스

| 의사결정                                | System Supervisor | Control Ship | Lower Agent      |
| --------------------------------------- | ----------------- | ------------ | ---------------- |
| 어느 Control Ship에 할당?               | ✅                | ❌           | ❌               |
| Control Ship이 어느 Lower Agent에 할당? | ❌                | ✅           | ❌               |
| 구체적인 실행 방법?                     | ❌                | ❌           | ✅               |
| 임무 포기 결정?                         | ✅                | ✅ (부분)    | ✅ (자신의 임무) |

---

## 코드 리뷰 체크리스트

새로운 코드를 추가할 때 다음을 확인하세요:

### 아키텍처 규칙

- [ ] 계층 구조를 위반하지 않는가? (하위가 상위를 호출하지 않는가?)
- [ ] 책임 경계가 명확한가?
- [ ] 외부 에이전트의 내부 상태를 직접 조회하지 않는가?

### 통신 규칙

- [ ] 모든 메시지가 명시적으로 정의되어 있는가?
- [ ] A2A 메시지에 `reason` 필드가 있는가?
- [ ] Moth pub-sub 채널을 올바르게 사용하는가?

### 상태 관리

- [ ] 정보의 "진실의 공급원"이 명확한가?
- [ ] 필요한 경우 동기화 로직이 있는가?
- [ ] 상태 충돌 시 해결 방법이 명시되어 있는가?

### 에러 처리

- [ ] 모든 외부 호출에 타임아웃이 있는가?
- [ ] 연결 실패 시 재시도 로직이 있는가?
- [ ] 에러 발생 시 로깅이 되는가?
- [ ] 폴백 전략이 있는가?

### 코드 품질

- [ ] 함수/메서드가 하나의 책임만 가지는가?
- [ ] 로깅이 충분한가? (의사결정 시점마다)
- [ ] 설정 파일에서 읽을 수 있는가? (하드코딩 없음)
- [ ] 문서화가 되어 있는가? (특히 인터페이스)

### 호환성

- [ ] 기존 메시지 형식과 호환성이 유지되는가?
- [ ] API 변경이 필요한가? 그렇다면 마이그레이션 가이드가 있는가?
- [ ] 다른 에이전트의 코드도 함께 수정해야 하는가?

---

## 추가 원칙

### "모르면 물어보라"

- 의사결정이 불명확하면 코드를 짜지 말고 먼저 물어보기
- 이 문서에 없는 내용은 팀 또는 AI와 상의

### "변경의 최소 영향"

- 기존 기능 수정 시 다른 곳에 미치는 영향 검토
- 가능하면 기존 코드를 건드리지 말고 새 코드 추가
- "A를 수정하면 B도 수정해야 하는" 상황 = 설계 문제

### "투명성 극대화"

- 모든 의사결정을 로깅하기
- 외부 의존성은 명시적으로 표시하기
- 암묵적 가정 없이 명시적으로 표현하기

---

## 예제: 올바른 구현

### ❌ 잘못된 구현

```python
# Control Ship이 AUV의 상태를 직접 조회
class ControlShip:
    def get_auv_status(self):
        response = requests.get("http://localhost:9010/state")
        return response.json()

    def make_decision(self):
        auv_status = self.get_auv_status()
        if auv_status['battery'] < 20:
            # AUV에 직접 명령 전송 (System Supervisor 우회)
            self.send_command_to_auv("return_to_base")
```

**문제점**:

1. Control Ship이 AUV의 내부 상태를 직접 조회
2. System Supervisor의 권한을 침범
3. 에러 처리가 없음 (AUV가 다운되면?)

### ✅ 올바른 구현

```python
# Registry에서 공개 정보만 조회, 명령은 System Supervisor 기다림
class ControlShip(Agent):
    def handle_a2a_message(self, msg):
        """System Supervisor로부터 온 A2A 메시지 처리"""
        logger.info(f"[ControlShip] A2A received: {msg.get('action')}")

        if msg.get("action") == "deploy_auv":
            self.deploy_auv(msg.get("params"))

    def deploy_auv(self, params):
        """AUV 배치 임무"""
        try:
            # AUV에 A2A 메시지 전송
            target_endpoint = self.get_child_endpoint("auv-001")
            a2a_msg = {
                "message_type": "task.assign",
                "action": "survey_depth",
                "params": params,
                "reason": "Deployed by Control Ship per System Supervisor order"
            }
            self.send_a2a(target_endpoint, a2a_msg, timeout=5)
            logger.info(f"[ControlShip] AUV deploy message sent")
        except Exception as e:
            logger.error(f"[ControlShip] Failed to deploy AUV: {e}")
            # System Supervisor에 실패 보고 (heartbeat + inbox)
            self.report_failure("auv_deployment_failed", str(e))

    def get_child_endpoint(self, child_id):
        """Registry에서 공개 정보 조회"""
        try:
            # 표준: urllib.request 사용 (외부 라이브러리 불필요)
            req = urllib.request.Request(
                "http://localhost:8280/devices",
                headers={"Accept": "application/json"},
                method="GET"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                devices = json.loads(resp.read().decode())
            for device in devices:
                if device.get("id") == child_id:
                    return device.get("agent", {}).get("endpoint")
            raise RuntimeError(f"Device {child_id} not found")
        except Exception as e:
            logger.error(f"[ControlShip] Failed to get device endpoint: {e}")
            raise
```

**좋은 점**:

1. A2A 메시지로만 통신
2. Registry에서 공개 정보만 조회
3. 에러 처리 및 로깅
4. System Supervisor의 의사결정 존중
5. 모든 액션이 명시적

---

**마지막으로**: 이 문서는 살아있는 문서입니다.
새로운 패턴이 발견되거나 원칙이 더 필요하면 업데이트하세요!
