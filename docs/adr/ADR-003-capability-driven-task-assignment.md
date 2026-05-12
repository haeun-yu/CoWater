# ADR-003: Capability-Driven Task Assignment

**상태**: Accepted  
**작성일**: 2026-05-12  
**선행 ADR**: ADR-001

---

## 상황 (Context)

사용자: "A 구역 바닥면을 **고해상도로** 촬영해줘"

**문제**:
- System Agent가 "ROV는 고해상도 촬영이 없으니 대신 저해상도를 쓰자" 식으로 추측해서 제시하면 안 됨
- 또는 가능하지 않은 작업을 억지로 Task로 만들어서 Device에 할당하면 실행 실패 가능성 높음

**핵심 질문**:
> "시스템은 어떻게 '가능' vs '불가능'을 판단하는가?"

---

## 결정 (Decision)

**System Agent는 '계획가(Planner)'이지 '창조주'가 아닙니다.**

### 1️⃣ **Device의 자기 선언 (Self-Declaration)**

각 Device Agent가 시스템에 등록할 때, **자신이 수행 가능한 원자적 기능(Atomic Actions) 목록**을 보냅니다.

```typescript
Device {
  id: "rov-1"
  type: "ROV"
  actions: [
    "MOVE_TO",           // 위치 이동
    "HIGH_RES_SCAN",     // 고해상도 스캔 (카메라)
    "SONAR_SCAN",        // 소나 스캔
    "SAMPLE_COLLECTION", // 샘플 채취
    "RETURN_TO_BASE"     // 복귀
  ]
  
  // 이 목록에 없는 것은 절대 할당 불가
}

Device {
  id: "usv-1"
  type: "USV"
  actions: [
    "MOVE_TO",
    "SURFACE_SCAN",      // 표면 스캔만 가능
    "WATER_QUALITY_CHECK"
  ]
}
```

**중요 규칙**: 
> System은 **`Device.actions[]`에 없는 `required_action`을 해당 Device에게 절대 할당할 수 없습니다.**

---

### 2️⃣ **작업 추천의 역량 대조 (Capability Matching)**

사용자 요청 → System Agent의 판단 흐름:

```
1️⃣ 의도 해석 (Intent Parsing)
   "A 구역 바닥면을 고해상도로 촬영해줘"
   → required_action: ["MOVE_TO", "HIGH_RES_SCAN"]

2️⃣ 역량 대조 (Capability Matching)
   현재 가용 Device들을 전수 조사:
   
   ROV-1: actions = [MOVE_TO, HIGH_RES_SCAN, ...]
          ✅ MOVE_TO 있음
          ✅ HIGH_RES_SCAN 있음
          → 합격
   
   USV-1: actions = [MOVE_TO, SURFACE_SCAN, ...]
          ✅ MOVE_TO 있음
          ❌ HIGH_RES_SCAN 없음 (SURFACE_SCAN만 있음)
          → 탈락

3️⃣ 물리적 제약 확인 (Constraint Check)
   ROV-1이 HIGH_RES_SCAN을 가졌지만:
   ❌ 현재 OFFLINE
   ❌ 배터리 < 30%
   ❌ 이미 다른 Mission 진행 중
   → 불가능

4️⃣ 최종 판단
   조건을 만족하는 Device가 없음
   → Proposal을 생성하지 않음
   → USER_COMMAND_FAILED 이벤트 생성
   → 사용자에게 명확한 이유 제시
```

---

### 3️⃣ **명시적 거절 (Fail-Fast)**

요청을 수행할 수 없으면, **억지로 제시하지 않습니다.**

```typescript
// ❌ 나쁜 예 (System이 추측)
"USV로 저해상도 촬영으로 대체해드릴게요" 
→ 사용자 기대와 다름, 나중에 불만족

// ✅ 좋은 예 (System이 명시적 거절)
"고해상도 촬영을 위해서는 다음이 필요합니다:
 - HIGH_RES_SCAN 기능이 있는 Device
 - 현재 가용 Device: 없음
 - 이유: ROV-1은 오프라인, USV는 저해상도 스캔만 가능
 
 [대안]
 1. ROV-1이 온라인 될 때까지 대기
 2. 저해상도 촬영으로 변경
 3. 다른 Device 추가 등록"
```

**이벤트 생성**:
```typescript
Event {
  type: "USER_COMMAND_FAILED"
  target_type: "SYSTEM"
  actor_type: "USER"
  severity: "INFO"
  data: {
    original_request: "A 구역 바닥면을 고해상도로 촬영해줘",
    reason: "HIGH_RES_SCAN 기능이 없거나 현재 불가능한 Device들만 존재",
    required_actions: ["MOVE_TO", "HIGH_RES_SCAN"],
    capability_gap: {
      missing_action: "HIGH_RES_SCAN",
      available_devices: "ROV-1(오프라인), USV-1(기능 없음)"
    }
  }
}
```

---

### 4️⃣ **논리적 체인 검증 (Logical Chain Validation)**

단순히 "Action이 있나?" 뿐만 아니라, **판단 근거**까지 검증합니다.

**예시**: "수질을 파악하고 더러우면 청소를 시작해"

```
필요한 논리 체인:
Detection (수질 파악) → Decision (오염 판단) → Action (청소)

System Agent 검증:
1. Detection: WATER_QUALITY_SCAN 액션 필요
   → 가능한 Device 있나? → 없음
   ❌ 이 시점에서 종료
   
2. 청소 Device (CLEANING_ACTION)는 아무리 많아도
   "오염 판단"을 할 수 없으므로 미션 불가능

최종 응답:
"수질 파악을 위한 센서나 기능을 보유한 장치가 없습니다.
 따라서 요청하신 '수질 기반 청소 작업'을 계획할 수 없습니다.
 
 필요: WATER_QUALITY_SCAN 기능이 있는 Device 추가"
```

---

## 결과 (Consequences)

### ✅ 이점
- **신뢰성**: Device가 제공하지 않은 기능은 절대 요청하지 않음
- **실패 감소**: "할 수 없다"는 것을 미리 알려주어 Task 실패 사전 차단
- **사용자 피드백**: "어떤 Device가 필요한가"를 명확히 알려주어 시스템 개선 방향 제시
- **명확한 책임**: System Agent는 Fact 기반만 판단 (추측 X)

### ⚠️ 제약
- **Device.actions 관리 중요**: 잘못 선언하면 역능 불일치 (따라서 Device 등록 검증 강화 필요)
- **Proposal 생성 불가 경우 증가**: 요청을 수행할 Device가 없으면 Proposal 제시 불가

---

## 참고

- **ADR-001**: Core Design Philosophy
- **ADR-002**: Proposal as Solution Set
- **docs/core/schema.md**: Device.actions 정의
- **docs/scenarios/operation.md**: 2-3. 작업 추천안 생성
