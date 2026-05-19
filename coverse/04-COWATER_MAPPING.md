# CoWater: CoVerse 인스턴스화 계획

CoVerse의 범용 설계를 CoWater의 구체적 아키텍처에 어떻게 적용할지 정의합니다.

---

## 개요

| CoVerse (범용) | CoWater (해양 무인체) |
|---|---|
| Entity | UUV (무인체), Sensor, Gateway |
| Entity Layer | Moth 텔레메트리 + 센서 데이터 |
| Monitoring Role | Detection Agent |
| Analysis Role | Analysis Agent |
| Control Role | Control Agent |
| System Monitoring Role | Supervision Agent |
| Operation Layer | Mission/Task DB + Redis |
| Decision Trail | 새로 구축해야 함 |
| Temporal Layer | 기존 Event Log DB |
| Spatial Layer | 위치 데이터 계산 레이어 |

---

## 데이터 흐름 (CoWater 구현)

### Phase 1: Entity Layer 구축

**현재 상태**: Moth에서 텔레메트리 데이터가 들어옴

**필요한 작업**:

1. **데이터 수집 (Moth Bridge)**
   ```python
   # 현재: Moth 메시지 → 각 Agent에 분산
   # 변경: Moth 메시지 → Entity Layer (중앙 저장소)
   
   class EntityStore:
       async def update_entity(self, entity_id: str, data: dict):
           # PostgreSQL에 저장
           # 또는 Redis에 캐시
           await db.execute(...)
   ```

2. **Entity 모델 정의**
   ```typescript
   // CoWater의 구체적 Entity 타입
   type CoWaterEntity = UUV | SensorGateway | BaseStation;
   
   interface UUV extends Entity {
     type: "device";
     deviceType: "AUV" | "ROV" | "AROV";
     measurements: {
       location: GNSSData;
       battery: BatteryStatus;
       depth: DepthData;
       temperature: WaterTemperature;
       salinity: SalinityData;
     };
   }
   ```

---

### Phase 2: Operation Layer 구축

**현재 상태**: Mission-Planner가 Proposal 생성, 각 Agent가 처리

**필요한 작업**:

1. **Mission/Task 저장소 통합**
   ```python
   # 기존: Mission DB + Redis 메시지
   # 변경: 이 둘을 CoVerse Operation Layer로 통합
   
   class OperationStore:
       async def create_mission(self, mission: Mission):
           # PostgreSQL에 저장
           await db.save(mission)
           # Decision Trail과 함께 기록
           await self.create_decision_entry(...)
   ```

2. **Decision Trail 저장소 신규 구축**
   ```python
   class DecisionTrail:
       async def record_decision(self, decision: Decision):
           # 각 에이전트의 판단을 기록
           # 예: Detection이 이상 감지했을 때
           #      Analysis가 우선도 결정했을 때
           #      Control이 Task 할당했을 때
           await db.save(decision)
           await redis.publish("decision_made", decision)
   ```

3. **Agent 판단 과정 기록**
   
   **Detection Agent**:
   ```python
   # 이상 감지 → Decision Trail 기록
   async def detect_anomaly(self, entity_id: str, data: dict):
       if data['battery'] < THRESHOLD:
           decision = Decision(
               decisionType="anomaly_detected",
               madeByRole="monitoring",
               reasoning={
                   "sourceData": data,
                   "analysisMethod": "rule-based",
                   "conclusion": "Battery low"
               },
               decision={
                   "action": "create_alert",
                   "rationale": f"{data['battery']}% < {THRESHOLD}%"
               }
           )
           await decision_store.record(decision)
   ```
   
   **Analysis Agent**:
   ```python
   # 우선도 결정 → Decision Trail 기록
   async def analyze(self, detection_result: dict):
       # ML 모델로 우선도 결정
       priority = self.priority_model.predict(
           battery=detection_result['battery'],
           location=detection_result['location'],
           system_load=system_metrics['load']
       )
       
       decision = Decision(
           decisionType="priority_assessment",
           madeByRole="analysis",
           reasoning={
               "sourceData": detection_result,
               "analysisMethod": "ml-model",
               "parameters": {"model": "priority-scorer-v2"},
               "conclusion": f"Priority = {priority}",
               "confidence": 0.95
           },
           decision={
               "action": "set_priority",
               "newValue": priority,
               "rationale": f"Low battery + Remote position"
           }
       )
       await decision_store.record(decision)
   ```
   
   **Control Agent**:
   ```python
   # Task 할당 → Decision Trail 기록
   async def allocate_task(self, priority: int, entity_id: str):
       task = Task(
           type="return_to_base",
           assignedEntityId=entity_id,
           priority=priority,
           status="assigned"
       )
       
       decision = Decision(
           decisionType="task_allocation",
           madeByRole="control",
           reasoning={
               "sourceData": {
                   "entityId": entity_id,
                   "priority": priority,
                   "availableResources": self.get_resources()
               },
               "analysisMethod": "decision-tree",
               "conclusion": "Allocate return task"
           },
           decision={
               "action": "create_and_assign_task",
               "newValue": task.id,
               "rationale": "High priority + Low battery"
           }
       )
       
       await task_store.save(task)
       await decision_store.record(decision)
       await redis.publish("task_assigned", task)
   ```

---

### Phase 3: System Layer 통합

**현재 상태**: Supervision Agent가 모니터링

**필요한 작업**:

1. **System Metrics 저장소**
   ```python
   class SystemMetricsStore:
       async def record_metrics(self, metrics: SystemMetrics):
           # 각 Agent의 상태 저장
           await redis.set(f"system:metrics:{timestamp}", metrics)
           await db.save(metrics)  # 히스토리 유지
   ```

2. **Supervision Agent 수정**
   ```python
   # 기존: 각 Agent 모니터링만 함
   # 변경: System Metrics를 정규적으로 수집 & 저장
   
   async def monitor_system(self):
       metrics = SystemMetrics(
           timestamp=utc_now(),
           components={
               "analysis-agent": {...},
               "control-agent": {...},
               "detection-agent": {...},
               "database": {...},
               "redis": {...}
           }
       )
       await system_metrics_store.record(metrics)
   ```

---

### Phase 4: Temporal Layer 통합

**현재 상태**: Event Log가 각 에이전트마다 따로 기록

**필요한 작업**:

1. **중앙화된 Event Log**
   ```python
   class TemporalStore:
       async def record_event(self, event: Event):
           # 모든 이벤트를 중앙화된 DB에 저장
           await db.save(event)
           
           # 특정 엔티티/Task의 히스토리 추적
           await redis.lpush(f"history:{event.sourceId}", event.id)
   ```

2. **이벤트 발행 정규화**
   ```python
   # 모든 상태 변화가 이벤트로 발행되도록
   # Entity 상태 변화 → Event
   # Task 상태 변화 → Event
   # Decision 기록 → Event
   # System Alert → Event
   ```

---

### Phase 5: Spatial Layer 구축

**현재 상태**: 위치 데이터는 Entity Layer에만 있음

**필요한 작업**:

1. **공간 관계 계산**
   ```python
   class SpatialAnalyzer:
       async def compute_spatial_relationships(self):
           # Entity Layer에서 위치 정보 추출
           entities = await entity_store.get_all_entities()
           
           # 거리 계산
           distances = {}
           for i, e1 in enumerate(entities):
               for e2 in entities[i+1:]:
                   distance = self.haversine(e1.location, e2.location)
                   distances[f"{e1.id}-{e2.id}"] = distance
           
           # 클러스터링 (선택사항)
           clusters = self.compute_clusters(entities)
           
           # 저장
           spatial_data = SpatialRelationship(
               timestamp=utc_now(),
               entities={e.id: e.position for e in entities},
               distances=distances,
               clusters=clusters
           )
           await spatial_store.save(spatial_data)
   ```

---

## CoWater 수정 사항 정리

### 새로 추가해야 할 컴포넌트

| 컴포넌트 | 용도 | 위치 |
|---|---|---|
| Entity Store | Entity Layer 중앙 저장소 | Core API 또는 별도 서비스 |
| Decision Store | Decision Trail 저장소 | PostgreSQL + Redis |
| System Metrics Collector | System Layer 정기 수집 | Supervision Agent 내부 또는 별도 |
| Temporal Aggregator | Event 중앙화 | Core API 또는 별도 서비스 |
| Spatial Analyzer | Spatial Layer 계산 | Core API 또는 별도 서비스 |

### 기존 컴포넌트 수정

| 컴포넌트 | 수정 사항 |
|---|---|
| Moth Bridge | Entity Store에 데이터 저장 |
| Detection Agent | Decision Trail 기록 추가 |
| Analysis Agent | Decision Trail 기록 추가 |
| Control Agent | Decision Trail 기록 추가 |
| Supervision Agent | System Metrics 수집 로직 추가 |
| Event System | 중앙화된 Temporal Store로 통합 |

---

## 구현 타임라인

### Phase 1: 기반 구조 (1주)
- [ ] Entity Store 설계 및 구축
- [ ] PostgreSQL 테이블 설계
- [ ] Moth Bridge → Entity Store 연결

### Phase 2: Decision Trail (2주)
- [ ] Decision Store 설계 및 구축
- [ ] Detection → Decision Trail 통합
- [ ] Analysis → Decision Trail 통합
- [ ] Control → Decision Trail 통합

### Phase 3: System & Temporal (1주)
- [ ] System Metrics Collector 구축
- [ ] Temporal Aggregator 구축
- [ ] Event 정규화

### Phase 4: Spatial (1주)
- [ ] Spatial Analyzer 구축
- [ ] 거리 및 클러스터링 계산

### Phase 5: View 구현 (2주)
- [ ] 첫 번째 View 구현 (2D 지도 또는 3D)
- [ ] 모든 5개 레이어 시각화

---

## 다음 단계

1. ✅ 범용 CoVerse 설계
2. ✅ Data Schema
3. ✅ Data Flow & Decision Trail
4. ✅ CoWater 매핑 계획
5. 💻 **구현 시작** (Entity Store부터)
