# ADR-006: 적응형 자율성 전환 경로

**상태**: Accepted  
**작성일**: 2026-05-12  
**선행 ADR**: ADR-001, ADR-005

---

## 상황

CoWater의 핵심 철학 중 하나는 **계획과 실행의 분리**입니다.

이를 통해:
- **현재**: 사용자 승인 기반 (Manual)
- **미래**: AI 자동 승인 기반 (Autonomous)

로 단계적으로 진화할 수 있습니다.

**문제**:
- "어떻게" 자동화할 것인가?
- 코드를 갈아엎지 않으면서 자동화 수준을 조절하는 방법은?

---

## 결정

**Policy/Rule 설정만으로 단계적 자동화를 구현합니다.**

### 1️⃣ **자동화 수준의 단계**

```
┌─────────────────────────────────────────────────────┐
│                 자동화 수준 (Autonomy Level)         │
├─────────────────────────────────────────────────────┤
│                                                       │
│ Level 0: Manual (지금)                              │
│  Event → Proposal → [사용자 승인] → Mission         │
│                                                       │
│ Level 1: Partial Auto (일부 자동)                  │
│  Event → Proposal → [Rule: CRITICAL만 자동] → M   │
│                                                       │
│ Level 2: Conditional Auto (조건부 자동)            │
│  Event → Proposal → [Rule: Policy 기반] → M        │
│                                                       │
│ Level 3: Full Auto (완전 자동)                      │
│  Event → [Rule: 직접 생성] → Mission               │
│                                                       │
└─────────────────────────────────────────────────────┘
```

---

### 2️⃣ **Rule.action.type으로 단계 제어**

#### **Level 0: Manual (현재 상태)**

```typescript
// 사용자 요청이 들어오면
SYS_INTENT_CLASSIFIED 이벤트 → Proposal 생성 → 사용자 승인 기다림

// Rule 설정
Rule {
  id: "rule-user-recommendation"
  rule_type: "RECOMMENDATION"
  name: "User Request → Proposal"
  
  conditions: [
    { field: "event.type", operator: "EQ", value: "SYS_INTENT_CLASSIFIED" }
  ]
  
  action: {
    type: "CREATE_PROPOSAL"  // ← Proposal 생성만 (Mission X)
  }
  
  enabled: true
  priority: 1
}
```

**동작**:
```
사용자 "A 구역 촬영" 
→ SYS_INTENT_CLASSIFIED 이벤트 
→ Rule: CREATE_PROPOSAL 실행 
→ Proposal-1, Proposal-2 생성 
→ 사용자에게 표시 
→ 사용자 클릭: Proposal-1 선택 
→ Mission 생성 ✅
```

---

#### **Level 1: Partial Auto (Critical만 자동)**

```typescript
// CRITICAL 상황만 사용자 개입 없이 자동 대응
Rule {
  id: "rule-critical-auto-response"
  rule_type: "AUTO_RESPONSE"
  name: "Critical Hazard → Auto Mission"
  
  conditions: [
    { field: "event.type", operator: "EQ", value: "SYS_ANOMALY_DETECTED" },
    { field: "event.data.anomaly_type", operator: "EQ", value: "CRITICAL_HAZARD" },
    { field: "event.severity", operator: "EQ", value: "CRITICAL" }
  ]
  
  action: {
    type: "AUTO_CREATE_MISSION"  // ← Proposal 건너뛰고 Mission 직접 생성
    params: {
      mission_type: "EMERGENCY_RESPONSE"
    }
  }
  
  enabled: true
  priority: 10  // 높은 우선순위
}

// 일반 요청은 여전히 Manual
Rule {
  id: "rule-user-recommendation"
  rule_type: "RECOMMENDATION"
  action: { type: "CREATE_PROPOSAL" }  // ← 여전히 Proposal
  enabled: true
  priority: 1
}
```

**동작**:
```
상황 1: 일반 요청 (SYS_INTENT_CLASSIFIED)
  → CREATE_PROPOSAL 
  → 사용자 승인 필요 ✅

상황 2: 긴급 상황 (SYS_ANOMALY_DETECTED + CRITICAL_HAZARD)
  → AUTO_CREATE_MISSION 
  → 즉시 Mission 생성 (승인 X) ✅
```

---

#### **Level 2: Conditional Auto (정책 기반)**

```typescript
// 특정 Policy에 따라 자동화
Rule {
  id: "rule-low-battery-response"
  rule_type: "AUTO_RESPONSE"
  name: "Low Battery Detected → Return to Base"
  
  conditions: [
    { field: "event.type", operator: "EQ", value: "SYS_ANOMALY_DETECTED" },
    { field: "event.data.anomaly_type", operator: "EQ", value: "LOW_BATTERY" },
    { field: "device.battery_percent", operator: "LT", value: 20 }
  ]
  
  action: {
    type: "AUTO_CREATE_MISSION"
    params: {
      mission_type: "RETURN",
      reason: "Low battery auto-return"
    }
  }
  
  enabled: true
  priority: 5
}
```

**동작**:
```
Heartbeat: battery = 18%
→ SYS_ANOMALY_DETECTED 이벤트 (`anomaly_type=LOW_BATTERY`) 
→ Rule 조건 매칭 
→ AUTO_CREATE_MISSION 
→ RETURN Mission 직접 생성 ✅
```

---

#### **Level 3: Full Auto (완전 자동)**

```typescript
// Proposal 단계 완전 제거, Event에서 직접 Mission 생성
Rule {
  id: "rule-routine-operation"
  rule_type: "OPERATION"
  name: "Routine Operation → Direct Mission"
  
  conditions: [
    { field: "event.type", operator: "IN", value: ["OPERATION_TRIGGERED"] },
    { field: "policy.auto_approval", operator: "EQ", value: true }
  ]
  
  action: {
    type: "AUTO_CREATE_MISSION"
    params: { ... }
  }
  
  enabled: true
  priority: 1
}
```

**동작**:
```
OPERATION_TRIGGERED 이벤트
→ AUTO_CREATE_MISSION (Proposal 건너뜀)
→ 즉시 Mission 생성
→ 전혀 사용자 개입 없음 ✅
```

---

### 3️⃣ **마이그레이션 경로 (시간에 따른 전환)**

```
┌──────────────────────────────────────────────────────────────┐
│              CoWater 자동화 진화 타이믄라인                    │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│ Phase 1 (현재): Level 0 - Manual                            │
│ ├─ 모든 작업 사용자 승인 필수                                │
│ ├─ System Agent: Proposal 생성                              │
│ └─ 신뢰성 검증 단계                                          │
│                                                               │
│ Phase 2 (Q3 2026): Level 1 - Partial Auto                  │
│ ├─ CRITICAL 상황만 자동 응답 (Rule 추가)                     │
│ ├─ 저배터리, 충돌 위험 등 자동 대응                         │
│ ├─ enable/disable로 opt-in 가능                             │
│ └─ Rule 검증 단계                                            │
│                                                               │
│ Phase 3 (Q4 2026): Level 2 - Conditional Auto              │
│ ├─ 더 많은 Policy 기반 자동화 (새 Rule 추가)                 │
│ ├─ 사용자 선호도 학습 시작                                  │
│ └─ 자동화 신뢰도 향상 단계                                   │
│                                                               │
│ Phase 4 (2027): Level 3 - Full Auto                        │
│ ├─ Proposal 단계 선택 사항화 (필요시만 표시)                │
│ ├─ 대부분의 작업 자동 실행                                  │
│ └─ 사용자는 예외/수정만 개입                                 │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

### 4️⃣ **코드 변경 없이 구현**

```typescript
// 핵심: 스키마와 로직은 고정, 설정만 변경

// 1. Rule 추가 (코드 수정 X, DB에만 insert)
INSERT INTO rules (rule_type, action_type, conditions, enabled)
VALUES ('AUTO_RESPONSE', 'AUTO_CREATE_MISSION', {...}, true)

// 2. 기존 CREATE_PROPOSAL Rule은 그대로
// (disable만 할 수도 있음)

// 3. Rule Engine은 동일하게 작동
// action.type == "AUTO_CREATE_MISSION"이면 Mission 생성
// action.type == "CREATE_PROPOSAL"이면 Proposal 생성

// → 코드 수정 없음, Rule 추가만으로 자동화 수준 상향
```

---

## 결과

### ✅ 이점
- **점진적 전환**: 한 번에 완전 자동화로 가지 않고 단계적 진화
- **롤백 가능**: Rule.enabled = false로 이전 단계로 복귀 가능
- **코드 안정성**: 핵심 로직은 건드리지 않음 (Rule 추가만)
- **사용자 신뢰**: 초기는 수동, 점차 자동으로 전환하며 신뢰 구축

### ⚠️ 제약
- **Rule 관리 복잡도**: 자동화 수준이 높아질수록 Rule 관리 필요
- **정책 결정 필요**: 어느 시점부터 자동화할지는 비즈니스 결정

---

## 참고

- **ADR-001**: Core Design Philosophy (Decoupling Planning/Execution)
- **ADR-005**: Event-Triggered Rule Execution
- **docs/roadmap.md**: 향후 자동화 계획
