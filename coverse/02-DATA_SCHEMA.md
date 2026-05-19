# CoVerse Data Schema

각 레이어의 구체적인 데이터 구조를 TypeScript 형태로 정의합니다.

---

## 1. Entity Layer

시스템이 관리하는 실체의 현재 상태.

```typescript
interface Entity {
  // 기본 정보
  id: string;
  type: "device" | "sensor" | "component" | string;
  name: string;
  
  // 현재 상태
  status: "active" | "idle" | "error" | "disconnected" | string;
  
  // 실시간 측정값
  measurements: {
    [key: string]: {
      value: number | string | boolean;
      unit?: string;
      timestamp: ISO8601String;
    };
  };
  
  // 연결 상태
  connectivity: {
    isConnected: boolean;
    lastHeartbeat: ISO8601String;
    signalStrength?: number; // 0-100
    latency?: number; // ms
  };
  
  // 메타데이터
  metadata?: {
    [key: string]: any;
  };
  
  // 업데이트 시점
  updatedAt: ISO8601String;
}

// 예시: 무인체
interface UUV extends Entity {
  type: "device";
  measurements: {
    location: { value: { lat: number; lon: number; depth: number }; timestamp: ISO8601String };
    battery: { value: number; unit: "%"; timestamp: ISO8601String };
    temperature: { value: number; unit: "°C"; timestamp: ISO8601String };
    salinity: { value: number; unit: "PSU"; timestamp: ISO8601String };
  };
}
```

---

## 2. Operation Layer

### 2-1. Mission

상위 수준의 목표 및 진행 상황.

```typescript
interface Mission {
  // 기본 정보
  id: string;
  type: "surveillance" | "patrol" | "recovery" | string;
  description: string;
  
  // 상태 관리
  status: "planned" | "assigned" | "in_progress" | "completed" | "failed" | "cancelled";
  
  // 우선도
  priority: 1 | 2 | 3 | 4 | 5; // 1: highest, 5: lowest
  
  // 시간 정보
  createdAt: ISO8601String;
  estimatedCompletionTime: ISO8601String;
  actualCompletionTime?: ISO8601String;
  
  // 구성 Task 목록
  taskIds: string[];
  
  // 성과
  result?: {
    success: boolean;
    reason?: string;
    completedAt: ISO8601String;
  };
  
  // 메타데이터
  metadata?: {
    [key: string]: any;
  };
}
```

### 2-2. Task

구체적인 작업 단위.

```typescript
interface Task {
  // 기본 정보
  id: string;
  parentMissionId: string;
  type: "move" | "sample" | "monitor" | "return" | string;
  
  // 할당 정보
  assignedEntityId: string;
  
  // 상태
  status: "requested" | "assigned" | "in_progress" | "completed" | "failed" | "aborted";
  
  // 우선도
  priority: 1 | 2 | 3 | 4 | 5;
  
  // 실행 명령
  command: {
    action: string;
    parameters: {
      [key: string]: any;
    };
  };
  
  // 진행 상황
  progress: {
    percentageComplete: number; // 0-100
    stage?: string;
    estimatedTimeRemaining?: number; // seconds
  };
  
  // 시간 정보
  createdAt: ISO8601String;
  assignedAt?: ISO8601String;
  startedAt?: ISO8601String;
  completedAt?: ISO8601String;
  
  // 결과
  result?: {
    success: boolean;
    reason?: string;
    output?: {
      [key: string]: any;
    };
  };
  
  // 메타데이터
  metadata?: {
    [key: string]: any;
  };
}
```

### 2-3. Decision Trail

각 판단의 근거와 과정.

```typescript
interface Decision {
  // 기본 정보
  id: string;
  decisionType: "allocation" | "priority_adjustment" | "termination" | "escalation" | string;
  
  // 판단 주체
  madeByRole: "analysis" | "control" | "monitoring" | "learning" | string;
  madeAt: ISO8601String;
  
  // 판단 대상
  targetType: "task" | "mission" | "entity";
  targetId: string;
  
  // 판단 근거 (왜 이런 결정을 했는가)
  reasoning: {
    // 1. 기반 데이터
    sourceData: {
      entityId?: string;
      measurements?: {
        [key: string]: any;
      };
      systemMetrics?: {
        [key: string]: any;
      };
      timestamp: ISO8601String;
    };
    
    // 2. 분석 로직
    analysisMethod: string; // "rule-based", "ml-model", "manual", etc.
    parameters?: {
      [key: string]: any;
    };
    
    // 3. 결론
    conclusion: string;
    confidence: number; // 0-1
  };
  
  // 판단 결과
  decision: {
    action: string;
    newValue?: any;
    rationale: string;
  };
  
  // 메타데이터
  metadata?: {
    [key: string]: any;
  };
}
```

---

## 3. System Layer

시스템 컴포넌트의 건강도와 성능.

```typescript
interface SystemMetrics {
  // 시간 정보
  timestamp: ISO8601String;
  
  // 컴포넌트 상태
  components: {
    [componentName: string]: {
      status: "healthy" | "degraded" | "error" | "offline";
      lastHealthCheck: ISO8601String;
      
      // 성능 지표
      metrics: {
        cpuUsage?: number; // 0-100
        memoryUsage?: number; // 0-100
        diskUsage?: number; // 0-100
        latency?: number; // ms
        errorRate?: number; // 0-1
        throughput?: number; // requests/sec
      };
      
      // 알람
      alerts?: Array<{
        severity: "info" | "warning" | "critical";
        message: string;
        timestamp: ISO8601String;
      }>;
    };
  };
  
  // 전체 시스템 메트릭
  overall: {
    operationalLoad: number; // 0-1 (현재 얼마나 바쁜가)
    taskQueueLength: number;
    activeTaskCount: number;
    failureRate: number; // 0-1
  };
  
  // 이상 감지
  anomalies?: Array<{
    type: string;
    severity: "info" | "warning" | "critical";
    description: string;
    timestamp: ISO8601String;
  }>;
}
```

---

## 4. Temporal Layer

이벤트와 상태 변화의 기록.

```typescript
interface Event {
  // 기본 정보
  id: string;
  type: "entity_status_change" | "task_status_change" | "decision_made" | "system_alert" | string;
  
  // 시간 정보
  timestamp: ISO8601String;
  
  // 발생 주체
  sourceType: "entity" | "task" | "mission" | "system" | "user";
  sourceId: string;
  
  // 이벤트 내용
  event: {
    category: string;
    description: string;
    
    // 상태 변화 (있으면)
    stateChange?: {
      before: any;
      after: any;
      reason?: string;
    };
    
    // 데이터 (있으면)
    data?: {
      [key: string]: any;
    };
  };
  
  // 심각도 (필요시)
  severity?: "info" | "warning" | "critical";
  
  // 추적 정보
  correlatedEventIds?: string[]; // 관련된 다른 이벤트
}

// Timeline: 이벤트들을 시간 순서대로 정렬
interface Timeline {
  events: Event[];
  timeRange: {
    from: ISO8601String;
    to: ISO8601String;
  };
  totalCount: number;
}

// History: 특정 엔티티/Task/Mission의 히스토리
interface History {
  targetId: string;
  targetType: "entity" | "task" | "mission";
  
  events: Event[];
  
  // 요약
  summary: {
    totalEvents: number;
    timeSpan: {
      from: ISO8601String;
      to: ISO8601String;
    };
    keyMilestones: string[];
  };
}
```

---

## 5. Spatial Layer

엔티티 간의 공간적 관계.

```typescript
interface SpatialRelationship {
  // 기본 정보
  timestamp: ISO8601String;
  
  // 엔티티 위치 정보
  entities: {
    [entityId: string]: {
      position: {
        latitude: number;
        longitude: number;
        altitude?: number; // 또는 depth (음수)
      };
      velocity?: {
        speed: number; // m/s
        heading: number; // 0-360 degrees
      };
    };
  };
  
  // 엔티티 간 거리/근접성
  distances: {
    [entityIdPair: string]: { // "entityA-entityB"
      distance: number; // meters
      closingRate?: number; // m/s (음수면 멀어지는 중)
    };
  };
  
  // 클러스터링 정보 (선택사항)
  clusters?: Array<{
    clusterID: string;
    entityIds: string[];
    centroid: {
      latitude: number;
      longitude: number;
    };
    radius: number; // meters
    density: number; // entities per km²
  }>;
  
  // 계층 관계 (선택사항)
  hierarchy?: {
    parentId?: string;
    childrenIds?: string[];
  };
}
```

---

## 타입 정의 (공통)

```typescript
type ISO8601String = string; // e.g., "2024-05-19T14:30:00Z"

interface CoVerseSnapshot {
  timestamp: ISO8601String;
  
  // 각 레이어의 현재 상태
  entityLayer: {
    entities: Entity[];
  };
  
  operationLayer: {
    missions: Mission[];
    tasks: Task[];
    decisions: Decision[];
  };
  
  systemLayer: {
    metrics: SystemMetrics;
  };
  
  temporalLayer: {
    recentEvents: Event[]; // 최근 N개 이벤트
    timeline: Timeline;
  };
  
  spatialLayer: {
    relationships: SpatialRelationship;
  };
}
```

---

## 다음 단계

1. ✅ CoVerse 범용 설계 완료
2. ✅ Data Schema 정의 완료
3. 📊 `03-DATA_FLOW.md`: Decision Trail과 데이터 흐름의 상세 분석
4. 🏗️ `04-COWATER_MAPPING.md`: CoWater에 어떻게 적용할지
5. 💻 구현 시작
