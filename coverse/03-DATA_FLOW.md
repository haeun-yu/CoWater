# CoVerse Data Flow & Decision Trail

데이터가 각 레이어를 통해 어떻게 흐르고, 운영자가 어떻게 상황을 인식하는지 설명합니다.

---

## 핵심 개념: Decision Trail

**상황 인식의 본질** = **현재 상태(Data) + 판단 근거(Decision Trail)**

```
Entity Layer (무인체 위치, 센서값)
  ↓
Monitoring Role (이상 감지)
  ↓ Decision: "배터리 부족 감지"
  ↓ Reasoning: "센서값 < 임계값"
  ↓
Analysis Role (우선도 결정)
  ↓ Decision: "이 Task의 우선도는 HIGH"
  ↓ Reasoning: "배터리 < 20% AND 현재위치 < 5km"
  ↓
Control Role (실행 결정)
  ↓ Decision: "무인체 A에 복귀 Task 할당"
  ↓ Reasoning: "HIGH 우선도 + 현재 Task 상태 + 시스템 자원"
  ↓
Operation Layer (Task 생성)
```

운영자는 **이 전체 흐름을 보면서** "아, 그래서 이 결정이 내려졌구나"를 이해합니다.

---

## 흐름 1: 이상 감지 → 대응

### 1단계: Entity Layer (실시간 데이터 수집)

```
무인체 A (UUV-001)
├─ location: 37.5°N, 126.8°E, 50m depth
├─ battery: 18% ← 임계값(20%) 이하!
├─ temperature: 12.3°C
└─ timestamp: 2024-05-19T14:30:00Z
```

### 2단계: Monitoring Role (이상 감지)

```
Detection Decision:
{
  id: "decision-20240519-001",
  decisionType: "anomaly_detected",
  madeByRole: "monitoring",
  targetId: "UUV-001",
  
  reasoning: {
    sourceData: {
      measurements: { battery: 18 },
      timestamp: "2024-05-19T14:30:00Z"
    },
    analysisMethod: "rule-based",
    parameters: { threshold: 20 },
    conclusion: "배터리 부족",
    confidence: 0.99
  },
  
  decision: {
    action: "create_alert",
    newValue: { severity: "high" },
    rationale: "18% < 20% threshold"
  }
}
```

### 3단계: Analysis Role (심각도 & 우선도 결정)

```
Analysis Decision:
{
  id: "decision-20240519-002",
  decisionType: "priority_assessment",
  madeByRole: "analysis",
  targetId: "UUV-001",
  
  reasoning: {
    sourceData: {
      measurements: {
        battery: 18,
        location: "37.5°N, 126.8°E, 50m"
      },
      systemMetrics: {
        activeTaskCount: 3,
        nearestBaseSation: 4.2 // km
      },
      timestamp: "2024-05-19T14:30:00Z"
    },
    analysisMethod: "ml-model",
    parameters: {
      model: "priority-scorer-v2",
      factors: [
        "battery_level",
        "distance_to_base",
        "current_task_type",
        "system_load"
      ]
    },
    conclusion: "High priority - 무인체가 반환해야 함",
    confidence: 0.95
  },
  
  decision: {
    action: "escalate_priority",
    newValue: { priority: 1 },
    rationale: "Low battery + Remote position + Available resources"
  }
}
```

### 4단계: Control Role (Task 할당 결정)

```
Control Decision:
{
  id: "decision-20240519-003",
  decisionType: "task_allocation",
  madeByRole: "control",
  targetId: "task-20240519-999",
  
  reasoning: {
    sourceData: {
      entityId: "UUV-001",
      measurements: { battery: 18 },
      currentTask: { type: "monitor", progress: 30 },
      availableCommands: ["return_to_base", "surface", "dock"],
      systemMetrics: { taskQueueLength: 2 }
    },
    analysisMethod: "decision-tree",
    parameters: {
      strategy: "minimize_risk"
    },
    conclusion: "무인체 A는 즉시 반환해야 함",
    confidence: 0.98
  },
  
  decision: {
    action: "abort_current_task_and_assign_return",
    newValue: {
      abortedTaskId: "task-20240519-567",
      newTaskId: "task-20240519-999"
    },
    rationale: "Battery critical + GPS shows 4.2km from base"
  }
}
```

### 5단계: Operation Layer (Task 실행)

```
Task-20240519-999:
{
  id: "task-20240519-999",
  type: "return_to_base",
  assignedEntityId: "UUV-001",
  status: "assigned",
  priority: 1,
  
  command: {
    action: "return_to_base",
    parameters: {
      baseStation: "BASE-STATION-1",
      coordinates: [37.6, 126.9, 0],
      speed: "maximum"
    }
  },
  
  createdAt: "2024-05-19T14:30:15Z",
  assignedAt: "2024-05-19T14:30:20Z"
}
```

---

## 흐름 2: 시스템 모니터링

병렬로 진행되는 시스템 건강도 모니터링:

### System Layer (실시간 모니터링)

```
SystemMetrics:
{
  timestamp: "2024-05-19T14:30:00Z",
  
  components: {
    "analysis-agent": {
      status: "healthy",
      metrics: {
        latency: 45, // ms
        errorRate: 0.002
      }
    },
    "control-agent": {
      status: "degraded",
      metrics: {
        latency: 320, // ms (높음!)
        cpuUsage: 85 // (높음!)
      },
      alerts: [{
        severity: "warning",
        message: "Control Agent latency high"
      }]
    },
    "message-broker": {
      status: "healthy",
      throughput: 1250 // msgs/sec
    }
  },
  
  overall: {
    operationalLoad: 0.72,
    activeTaskCount: 12,
    failureRate: 0.001
  }
}
```

이것도 Decision Trail로 기록:

```
System Decision:
{
  id: "decision-20240519-0XX",
  decisionType: "system_alert",
  madeByRole: "system_monitoring",
  targetId: "control-agent",
  
  reasoning: {
    sourceData: {
      metrics: {
        latency: 320,
        cpuUsage: 85
      }
    },
    analysisMethod: "threshold-check",
    conclusion: "Control Agent is struggling"
  },
  
  decision: {
    action: "notify_operator",
    rationale: "Latency increased by 300% in 5 minutes"
  }
}
```

---

## 흐름 3: 시간 흐름 기록 (Temporal Layer)

위의 모든 결정과 변화가 이벤트로 기록됨:

```typescript
events: [
  {
    id: "event-1",
    type: "entity_status_change",
    timestamp: "2024-05-19T14:30:00Z",
    sourceId: "UUV-001",
    event: {
      category: "battery_warning",
      description: "Battery dropped below 20%",
      stateChange: { before: 22, after: 18 },
      data: { threshold: 20 }
    },
    severity: "warning"
  },
  {
    id: "event-2",
    type: "decision_made",
    timestamp: "2024-05-19T14:30:01Z",
    sourceId: "decision-20240519-001",
    event: {
      category: "anomaly_detection",
      description: "Monitoring role detected anomaly"
    }
  },
  {
    id: "event-3",
    type: "task_status_change",
    timestamp: "2024-05-19T14:30:15Z",
    sourceId: "task-20240519-999",
    event: {
      category: "task_created",
      description: "Return task created for UUV-001"
    }
  },
  // ... 계속
]
```

---

## 운영자의 상황 인식

### 화면에 보이는 것

**Layer 1: 현재 상태 (Entity Layer)**
```
무인체 A (UUV-001)
- 위치: 37.5°N, 126.8°E, 50m depth
- 배터리: 18% ⚠️
- 온도: 12.3°C
- 상태: Return to Base (Task-999)
```

**Layer 2: 작업 상황 (Operation Layer)**
```
현재 Task (ID: task-20240519-999)
- 타입: Return to Base
- 상태: In Progress (진행률 5%)
- 우선도: 1 (최높음)
- 근거: [배터리 부족] → [높은 우선도] → [반환 명령]
```

**Layer 3: 판단 과정 (Decision Trail)**
```
왜 이 결정이 내려졌나:

1️⃣ 센서 값 18% < 임계값 20%
   → Monitoring: "배터리 부족"

2️⃣ 18% + 4.2km 거리 + System Load 72%
   → Analysis: "Priority = 1 (최높음)"

3️⃣ Priority 1 + Current Task Progress 5% + 배터리 위험
   → Control: "현재 Task 중단, 반환 Task 할당"
```

**Layer 4: 시스템 상태 (System Layer)**
```
✅ Analysis Agent: Healthy
⚠️ Control Agent: High Latency (320ms)
✅ Message Broker: Normal (1250 msgs/sec)

Overall: 72% load, 12 active tasks
```

**Layer 5: 시간 흐름 (Temporal Layer)**
```
Timeline:
14:30:00 - Battery 22% → 18%
14:30:01 - Anomaly detected
14:30:05 - Priority escalated
14:30:15 - Return task created
14:30:20 - Task assigned to UUV-001
14:31:00 - UUV-001 heading to base
```

---

## Decision Trail의 중요성

운영자가 **"왜 이렇게 됐는가"를 이해**할 때:

1. **신뢰**: 시스템의 결정이 합리적인지 검증 가능
2. **개입**: 필요시 판단의 어느 단계에서든 개입 가능
3. **학습**: 패턴을 분석해서 시스템 개선
4. **감시**: 이상한 판단이 있으면 즉시 발견

---

## 다음 단계

1. ✅ 범용 CoVerse 설계
2. ✅ Data Schema 정의
3. ✅ Data Flow & Decision Trail 분석
4. 🏗️ `04-COWATER_MAPPING.md`: CoWater에 어떻게 적용할지
5. 💻 구현 시작
