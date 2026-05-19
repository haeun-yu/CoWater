"""
CoVerse Data Storage (Memory-based Prototype)

5개 레이어를 메모리에 저장하는 간단한 구현.
- Entity Layer
- Operation Layer (Mission, Task, Decision)
- System Layer
- Temporal Layer
- Spatial Layer
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
import math
from dataclasses import dataclass, asdict, field
from enum import Enum


# ============================================================================
# 1. Entity Layer
# ============================================================================

class EntityStatus(str, Enum):
    ACTIVE = "active"
    IDLE = "idle"
    ERROR = "error"
    DISCONNECTED = "disconnected"


@dataclass
class Measurement:
    """단일 측정값"""
    value: Any
    unit: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class Connectivity:
    """연결 상태"""
    is_connected: bool
    last_heartbeat: str
    signal_strength: Optional[int] = None  # 0-100
    latency: Optional[int] = None  # ms


@dataclass
class Entity:
    """시스템이 관리하는 실체"""
    id: str
    type: str  # "device", "sensor", "component", etc.
    name: str
    status: EntityStatus = EntityStatus.ACTIVE
    measurements: Dict[str, Measurement] = field(default_factory=dict)
    connectivity: Optional[Connectivity] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ============================================================================
# 2. Operation Layer
# ============================================================================

class MissionStatus(str, Enum):
    PLANNED = "planned"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskStatus(str, Enum):
    REQUESTED = "requested"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


@dataclass
class Mission:
    """상위 수준의 목표"""
    id: str
    type: str
    description: str
    status: MissionStatus = MissionStatus.PLANNED
    priority: int = 3  # 1: highest, 5: lowest
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    estimated_completion_time: Optional[str] = None
    actual_completion_time: Optional[str] = None
    task_ids: List[str] = field(default_factory=list)
    result: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Task:
    """구체적인 작업 단위"""
    id: str
    parent_mission_id: str
    type: str
    assigned_entity_id: str
    status: TaskStatus = TaskStatus.REQUESTED
    priority: int = 3
    command: Dict[str, Any] = field(default_factory=dict)
    progress_percentage: int = 0
    progress_stage: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    assigned_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class DecisionType(str, Enum):
    ALLOCATION = "allocation"
    PRIORITY_ADJUSTMENT = "priority_adjustment"
    TERMINATION = "termination"
    ESCALATION = "escalation"
    ANOMALY_DETECTED = "anomaly_detected"
    TASK_ALLOCATION = "task_allocation"
    SYSTEM_ALERT = "system_alert"


@dataclass
class DecisionReasoning:
    """판단의 근거"""
    source_data: Dict[str, Any]
    analysis_method: str
    parameters: Optional[Dict[str, Any]] = None
    conclusion: str = ""
    confidence: float = 0.5


@dataclass
class Decision:
    """각 판단의 기록"""
    id: str
    decision_type: DecisionType
    made_by_role: str  # "analysis", "control", "monitoring", etc.
    made_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    target_type: str = "task"  # "task", "mission", "entity"
    target_id: str = ""
    reasoning: Optional[DecisionReasoning] = None
    decision: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# 3. System Layer
# ============================================================================

@dataclass
class ComponentMetrics:
    """컴포넌트별 메트릭"""
    status: str  # "healthy", "degraded", "error", "offline"
    last_health_check: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    alerts: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class SystemMetrics:
    """시스템 전체 메트릭"""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    components: Dict[str, ComponentMetrics] = field(default_factory=dict)
    operational_load: float = 0.0  # 0-1
    task_queue_length: int = 0
    active_task_count: int = 0
    failure_rate: float = 0.0
    anomalies: List[Dict[str, Any]] = field(default_factory=list)


# ============================================================================
# 4. Temporal Layer
# ============================================================================

class EventType(str, Enum):
    ENTITY_STATUS_CHANGE = "entity_status_change"
    TASK_STATUS_CHANGE = "task_status_change"
    DECISION_MADE = "decision_made"
    SYSTEM_ALERT = "system_alert"


@dataclass
class Event:
    """시스템의 이벤트 기록"""
    id: str
    type: EventType
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source_type: str = "entity"  # "entity", "task", "mission", "system"
    source_id: str = ""
    category: str = ""
    description: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    severity: Optional[str] = None  # "info", "warning", "critical"
    correlated_event_ids: List[str] = field(default_factory=list)


# ============================================================================
# 5. Spatial Layer
# ============================================================================

@dataclass
class Position:
    """위치 정보"""
    latitude: float
    longitude: float
    altitude: Optional[float] = None  # 또는 depth (음수)


@dataclass
class SpatialRelationship:
    """공간적 관계"""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    entities: Dict[str, Position] = field(default_factory=dict)  # entity_id -> position
    distances: Dict[str, float] = field(default_factory=dict)  # "id1-id2" -> distance
    clusters: List[Dict[str, Any]] = field(default_factory=list)


# ============================================================================
# CoVerse Store (메모리 기반)
# ============================================================================

class CoVerseStore:
    """모든 레이어를 관리하는 통합 저장소"""

    def __init__(self):
        # Entity Layer
        self.entities: Dict[str, Entity] = {}

        # Operation Layer
        self.missions: Dict[str, Mission] = {}
        self.tasks: Dict[str, Task] = {}
        self.decisions: List[Decision] = []

        # System Layer
        self.system_metrics: Optional[SystemMetrics] = None

        # Temporal Layer
        self.events: List[Event] = []

        # Spatial Layer
        self.spatial_data: Optional[SpatialRelationship] = None

    # ========================================================================
    # Entity Layer Operations
    # ========================================================================

    def add_or_update_entity(self, entity: Entity) -> Entity:
        """엔티티 추가 또는 업데이트"""
        entity.updated_at = datetime.now(timezone.utc).isoformat()
        self.entities[entity.id] = entity

        # 이벤트 기록
        if entity.id not in self.entities:
            event_type = EventType.ENTITY_STATUS_CHANGE
        event = Event(
            id=str(uuid.uuid4()),
            type=EventType.ENTITY_STATUS_CHANGE,
            source_type="entity",
            source_id=entity.id,
            category="entity_updated",
            description=f"Entity {entity.name} updated",
            data={"status": entity.status.value}
        )
        self.events.append(event)

        return entity

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """엔티티 조회"""
        return self.entities.get(entity_id)

    def get_all_entities(self) -> List[Entity]:
        """모든 엔티티 조회"""
        return list(self.entities.values())

    # ========================================================================
    # Operation Layer Operations
    # ========================================================================

    def create_mission(self, mission: Mission) -> Mission:
        """미션 생성"""
        if not mission.id:
            mission.id = str(uuid.uuid4())
        self.missions[mission.id] = mission

        # 이벤트 기록
        event = Event(
            id=str(uuid.uuid4()),
            type=EventType.TASK_STATUS_CHANGE,
            source_type="mission",
            source_id=mission.id,
            category="mission_created",
            description=f"Mission {mission.type} created",
            data={"priority": mission.priority}
        )
        self.events.append(event)

        return mission

    def get_mission(self, mission_id: str) -> Optional[Mission]:
        """미션 조회"""
        return self.missions.get(mission_id)

    def get_all_missions(self) -> List[Mission]:
        """모든 미션 조회"""
        return list(self.missions.values())

    def create_task(self, task: Task) -> Task:
        """태스크 생성"""
        if not task.id:
            task.id = str(uuid.uuid4())
        self.tasks[task.id] = task

        # 미션에 태스크 추가
        if task.parent_mission_id in self.missions:
            self.missions[task.parent_mission_id].task_ids.append(task.id)

        # 이벤트 기록
        event = Event(
            id=str(uuid.uuid4()),
            type=EventType.TASK_STATUS_CHANGE,
            source_type="task",
            source_id=task.id,
            category="task_created",
            description=f"Task {task.type} created for {task.assigned_entity_id}",
            data={"priority": task.priority}
        )
        self.events.append(event)

        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        """태스크 조회"""
        return self.tasks.get(task_id)

    def get_all_tasks(self) -> List[Task]:
        """모든 태스크 조회"""
        return list(self.tasks.values())

    def update_task_status(self, task_id: str, status: TaskStatus) -> Optional[Task]:
        """태스크 상태 업데이트"""
        task = self.tasks.get(task_id)
        if not task:
            return None

        task.status = status

        # 이벤트 기록
        event = Event(
            id=str(uuid.uuid4()),
            type=EventType.TASK_STATUS_CHANGE,
            source_type="task",
            source_id=task.id,
            category="task_status_changed",
            description=f"Task status changed to {status.value}",
            data={"status": status.value}
        )
        self.events.append(event)

        return task

    def record_decision(self, decision: Decision) -> Decision:
        """판단 기록"""
        if not decision.id:
            decision.id = str(uuid.uuid4())
        self.decisions.append(decision)

        # 이벤트 기록
        event = Event(
            id=str(uuid.uuid4()),
            type=EventType.DECISION_MADE,
            source_type="system",
            source_id=decision.id,
            category="decision_made",
            description=f"Decision {decision.decision_type.value} made by {decision.made_by_role}",
            data={
                "decision_type": decision.decision_type.value,
                "target_id": decision.target_id,
                "confidence": decision.reasoning.confidence if decision.reasoning else 0
            }
        )
        self.events.append(event)

        return decision

    def get_decisions_for_target(self, target_id: str) -> List[Decision]:
        """특정 대상의 모든 판단 조회"""
        return [d for d in self.decisions if d.target_id == target_id]

    # ========================================================================
    # System Layer Operations
    # ========================================================================

    def set_system_metrics(self, metrics: SystemMetrics) -> SystemMetrics:
        """시스템 메트릭 저장"""
        self.system_metrics = metrics
        return metrics

    def get_system_metrics(self) -> Optional[SystemMetrics]:
        """시스템 메트릭 조회"""
        return self.system_metrics

    # ========================================================================
    # Temporal Layer Operations
    # ========================================================================

    def add_event(self, event: Event) -> Event:
        """이벤트 추가"""
        if not event.id:
            event.id = str(uuid.uuid4())
        self.events.append(event)
        return event

    def get_all_events(self) -> List[Event]:
        """모든 이벤트 조회"""
        return self.events

    def get_events_for_source(self, source_id: str) -> List[Event]:
        """특정 소스의 이벤트 조회"""
        return [e for e in self.events if e.source_id == source_id]

    def get_recent_events(self, count: int = 10) -> List[Event]:
        """최근 이벤트 조회"""
        return self.events[-count:] if self.events else []

    # ========================================================================
    # Spatial Layer Operations
    # ========================================================================

    def compute_spatial_relationships(self) -> SpatialRelationship:
        """공간적 관계 계산"""
        spatial = SpatialRelationship()

        # 각 엔티티의 위치 정보 추출
        for entity_id, entity in self.entities.items():
            if "location" in entity.measurements:
                loc_data = entity.measurements["location"].value
                if isinstance(loc_data, dict):
                    spatial.entities[entity_id] = Position(
                        latitude=loc_data.get("lat", 0),
                        longitude=loc_data.get("lon", 0),
                        altitude=loc_data.get("altitude") or loc_data.get("depth")
                    )

        # 엔티티 간 거리 계산
        entity_ids = list(spatial.entities.keys())
        for i, id1 in enumerate(entity_ids):
            for id2 in entity_ids[i+1:]:
                distance = self._haversine_distance(
                    spatial.entities[id1],
                    spatial.entities[id2]
                )
                spatial.distances[f"{id1}-{id2}"] = distance

        self.spatial_data = spatial
        return spatial

    def get_spatial_relationships(self) -> Optional[SpatialRelationship]:
        """공간적 관계 조회"""
        if not self.spatial_data:
            return self.compute_spatial_relationships()
        return self.spatial_data

    # ========================================================================
    # Helper Methods
    # ========================================================================

    @staticmethod
    def _haversine_distance(pos1: Position, pos2: Position) -> float:
        """두 위치 간의 거리 계산 (미터)"""
        R = 6371000  # 지구 반지름 (미터)

        lat1_rad = math.radians(pos1.latitude)
        lat2_rad = math.radians(pos2.latitude)
        delta_lat = math.radians(pos2.latitude - pos1.latitude)
        delta_lon = math.radians(pos2.longitude - pos1.longitude)

        a = math.sin(delta_lat / 2) ** 2 + \
            math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c

    def get_coverse_snapshot(self) -> Dict[str, Any]:
        """전체 CoVerse 스냅샷 조회"""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "entityLayer": {
                "entities": [asdict(e) for e in self.entities.values()]
            },
            "operationLayer": {
                "missions": [asdict(m) for m in self.missions.values()],
                "tasks": [asdict(t) for t in self.tasks.values()],
                "decisions": [asdict(d) for d in self.decisions[-10:]],  # 최근 10개
            },
            "systemLayer": asdict(self.system_metrics) if self.system_metrics else None,
            "temporalLayer": {
                "recentEvents": [asdict(e) for e in self.get_recent_events(20)],
            },
            "spatialLayer": asdict(self.spatial_data) if self.spatial_data else None,
        }


# 전역 인스턴스
_coverse_store: Optional[CoVerseStore] = None


def _initialize_demo_data(store: CoVerseStore) -> None:
    """Demo 데이터로 저장소 초기화"""
    # Entity 생성
    entities_data = [
        {
            "id": "UUV-001", "name": "AUV Alpha", "type": "device",
            "measurements": {
                "location": Measurement({"lat": 37.5, "lon": 126.8, "depth": 50}, "degrees/meters"),
                "battery": Measurement(85, "%"),
                "temperature": Measurement(12.3, "°C"),
            },
            "connectivity": Connectivity(True, datetime.now(timezone.utc).isoformat(), 92),
        },
        {
            "id": "UUV-002", "name": "AUV Beta", "type": "device",
            "measurements": {
                "location": Measurement({"lat": 37.52, "lon": 126.85, "depth": 30}, "degrees/meters"),
                "battery": Measurement(18, "%"),
            },
            "connectivity": Connectivity(True, datetime.now(timezone.utc).isoformat(), 45),
        },
        {
            "id": "GATEWAY-001", "name": "Base Station", "type": "device",
            "measurements": {
                "location": Measurement({"lat": 37.48, "lon": 126.75, "depth": 0}, "degrees/meters"),
                "battery": Measurement(100, "%"),
            },
            "connectivity": Connectivity(True, datetime.now(timezone.utc).isoformat(), 100),
        },
        {
            "id": "SENSOR-001", "name": "Water Sensor", "type": "sensor",
            "measurements": {
                "location": Measurement({"lat": 37.54, "lon": 126.88, "depth": 100}, "degrees/meters"),
                "temperature": Measurement(11.5, "°C"),
            },
            "connectivity": Connectivity(True, datetime.now(timezone.utc).isoformat(), 78),
        },
    ]

    for entity_data in entities_data:
        entity = Entity(
            id=entity_data["id"],
            type=entity_data["type"],
            name=entity_data["name"],
            measurements=entity_data["measurements"],
            connectivity=entity_data["connectivity"],
        )
        store.add_or_update_entity(entity)

    # Mission 생성
    mission = Mission(
        id="MISSION-001",
        type="surveillance",
        description="해역 모니터링",
        status=MissionStatus.IN_PROGRESS,
        priority=2,
    )
    store.create_mission(mission)

    # Task 생성
    task = Task(
        id="TASK-001",
        parent_mission_id="MISSION-001",
        type="return_to_base",
        assigned_entity_id="UUV-002",
        status=TaskStatus.IN_PROGRESS,
        priority=1,
        command={"action": "return_to_base"},
    )
    store.create_task(task)

    # System Metrics 생성
    store.system_metrics = SystemMetrics(
        operational_load=0.72,
        task_queue_length=5,
        active_task_count=3,
        failure_rate=0.001,
    )


def get_coverse_store() -> CoVerseStore:
    """CoVerse Store 싱글톤 조회 (첫 액세스 시 demo 데이터로 초기화)"""
    global _coverse_store
    if _coverse_store is None:
        _coverse_store = CoVerseStore()
        # 첫 액세스 시 demo 데이터로 초기화
        _initialize_demo_data(_coverse_store)
    return _coverse_store
