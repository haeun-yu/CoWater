#!/usr/bin/env python3
"""
CoVerse Store 테스트 스크립트

Entity Store, Decision Trail, 공간 관계를 테스트합니다.
"""

import sys
from pathlib import Path

# CoWater 모듈 import
sys.path.insert(0, str(Path(__file__).parent.parent / "server"))
from shared.storage.coverse_store import (
    get_coverse_store,
    Entity, EntityStatus, Measurement, Connectivity,
    Mission, MissionStatus, Task, TaskStatus,
    Decision, DecisionType, DecisionReasoning,
    SystemMetrics, ComponentMetrics,
    Event, EventType,
    Position, SpatialRelationship
)
from datetime import datetime, timezone
import json


def test_entity_layer():
    """Entity Layer 테스트"""
    print("\n" + "="*70)
    print("TEST 1: Entity Layer")
    print("="*70)

    store = get_coverse_store()

    # 무인체 1 생성
    uuv1 = Entity(
        id="UUV-001",
        type="device",
        name="AUV Alpha",
        status=EntityStatus.ACTIVE,
        measurements={
            "location": Measurement(
                value={"lat": 37.5, "lon": 126.8, "depth": 50},
                unit="degrees/meters"
            ),
            "battery": Measurement(
                value=85,
                unit="%"
            ),
            "temperature": Measurement(
                value=12.3,
                unit="°C"
            ),
        },
        connectivity=Connectivity(
            is_connected=True,
            last_heartbeat=datetime.now(timezone.utc).isoformat(),
            signal_strength=92
        )
    )
    store.add_or_update_entity(uuv1)
    print(f"✅ Created: {uuv1.name}")

    # 무인체 2 생성
    uuv2 = Entity(
        id="UUV-002",
        type="device",
        name="AUV Beta",
        status=EntityStatus.ACTIVE,
        measurements={
            "location": Measurement(
                value={"lat": 37.52, "lon": 126.85, "depth": 30},
                unit="degrees/meters"
            ),
            "battery": Measurement(
                value=18,  # 낮은 배터리
                unit="%"
            ),
        },
        connectivity=Connectivity(
            is_connected=True,
            last_heartbeat=datetime.now(timezone.utc).isoformat(),
            signal_strength=45  # 신호 약함
        )
    )
    store.add_or_update_entity(uuv2)
    print(f"✅ Created: {uuv2.name}")

    # 전체 엔티티 조회
    entities = store.get_all_entities()
    print(f"\n📊 Total entities: {len(entities)}")
    for entity in entities:
        print(f"  - {entity.name} ({entity.id}): {entity.status.value}")
        for key, measurement in entity.measurements.items():
            print(f"    • {key}: {measurement.value} {measurement.unit or ''}")


def test_operation_layer():
    """Operation Layer 테스트 (Mission, Task, Decision)"""
    print("\n" + "="*70)
    print("TEST 2: Operation Layer (Mission → Task → Decision)")
    print("="*70)

    store = get_coverse_store()

    # 1. Mission 생성
    mission = Mission(
        id="MISSION-001",
        type="surveillance",
        description="해역 모니터링",
        status=MissionStatus.PLANNED,
        priority=2
    )
    store.create_mission(mission)
    print(f"✅ Mission created: {mission.description}")

    # 2. Detection: 배터리 부족 감지
    detection_decision = Decision(
        id="",
        decision_type=DecisionType.ANOMALY_DETECTED,
        made_by_role="monitoring",
        target_type="entity",
        target_id="UUV-002",
        reasoning=DecisionReasoning(
            source_data={"battery": 18, "threshold": 20},
            analysis_method="rule-based",
            conclusion="배터리 부족 감지",
            confidence=0.99
        ),
        decision={
            "action": "create_alert",
            "severity": "high",
            "rationale": "18% < 20% threshold"
        }
    )
    store.record_decision(detection_decision)
    print(f"✅ Decision (Monitoring): {detection_decision.reasoning.conclusion}")

    # 3. Analysis: 우선도 결정
    analysis_decision = Decision(
        id="",
        decision_type=DecisionType.PRIORITY_ADJUSTMENT,
        made_by_role="analysis",
        target_type="task",
        target_id="",  # 아직 Task가 없음
        reasoning=DecisionReasoning(
            source_data={
                "battery": 18,
                "distance_to_base": 4.2,
                "system_load": 0.72
            },
            analysis_method="ml-model",
            parameters={"model": "priority-scorer-v2"},
            conclusion="높은 우선도 필요",
            confidence=0.95
        ),
        decision={
            "action": "escalate_priority",
            "newValue": 1,
            "rationale": "Low battery + Remote position + System load"
        }
    )
    store.record_decision(analysis_decision)
    print(f"✅ Decision (Analysis): {analysis_decision.reasoning.conclusion}")

    # 4. Task 생성 (Control 판단)
    task = Task(
        id="",
        parent_mission_id="MISSION-001",
        type="return_to_base",
        assigned_entity_id="UUV-002",
        status=TaskStatus.ASSIGNED,
        priority=1,  # 최고 우선도
        command={
            "action": "return_to_base",
            "parameters": {
                "baseStation": "BASE-1",
                "coordinates": [37.6, 126.9, 0],
                "speed": "maximum"
            }
        }
    )
    created_task = store.create_task(task)
    print(f"✅ Task created: {created_task.type} for UUV-002")

    # 5. Control 판단 기록
    control_decision = Decision(
        id="",
        decision_type=DecisionType.TASK_ALLOCATION,
        made_by_role="control",
        target_type="task",
        target_id=created_task.id,
        reasoning=DecisionReasoning(
            source_data={
                "entity_id": "UUV-002",
                "battery": 18,
                "priority": 1,
                "available_commands": ["return_to_base", "surface"]
            },
            analysis_method="decision-tree",
            conclusion="무인체 반환 필요",
            confidence=0.98
        ),
        decision={
            "action": "assign_task",
            "rationale": "Battery critical + 4.2km from base"
        }
    )
    store.record_decision(control_decision)
    print(f"✅ Decision (Control): Task allocated")

    # 전체 결정 조회
    decisions = store.get_decisions_for_target("UUV-002")
    print(f"\n📊 Decisions for UUV-002: {len(decisions)}")
    for i, decision in enumerate(decisions):
        print(f"  {i+1}. {decision.made_by_role.upper()}: {decision.decision_type.value}")
        if decision.reasoning:
            print(f"     └─ {decision.reasoning.conclusion}")


def test_system_layer():
    """System Layer 테스트"""
    print("\n" + "="*70)
    print("TEST 3: System Layer")
    print("="*70)

    store = get_coverse_store()

    # 시스템 메트릭 생성
    metrics = SystemMetrics(
        operational_load=0.72,
        task_queue_length=5,
        active_task_count=12,
        failure_rate=0.001,
        components={
            "analysis_agent": ComponentMetrics(
                status="healthy",
                last_health_check=datetime.now(timezone.utc).isoformat(),
                metrics={
                    "latency": 45,
                    "cpu_usage": 35,
                    "memory_usage": 45
                }
            ),
            "control_agent": ComponentMetrics(
                status="degraded",
                last_health_check=datetime.now(timezone.utc).isoformat(),
                metrics={
                    "latency": 320,
                    "cpu_usage": 85,
                    "memory_usage": 72
                },
                alerts=[
                    {
                        "severity": "warning",
                        "message": "Control Agent latency high"
                    }
                ]
            ),
            "database": ComponentMetrics(
                status="healthy",
                last_health_check=datetime.now(timezone.utc).isoformat(),
                metrics={
                    "query_latency": 12,
                    "connections": 15
                }
            )
        }
    )
    store.set_system_metrics(metrics)
    print(f"✅ System metrics recorded")

    # 메트릭 조회
    retrieved = store.get_system_metrics()
    if retrieved:
        print(f"\n📊 System Status:")
        print(f"  • Operational Load: {retrieved.operational_load*100:.1f}%")
        print(f"  • Active Tasks: {retrieved.active_task_count}")
        print(f"  • Failure Rate: {retrieved.failure_rate*100:.2f}%")
        print(f"\n  Components:")
        for comp_name, comp_metrics in retrieved.components.items():
            print(f"    • {comp_name}: {comp_metrics.status}")
            if comp_metrics.alerts:
                for alert in comp_metrics.alerts:
                    print(f"      ⚠️  {alert['message']}")


def test_spatial_layer():
    """Spatial Layer 테스트"""
    print("\n" + "="*70)
    print("TEST 4: Spatial Layer (거리 계산)")
    print("="*70)

    store = get_coverse_store()

    # 공간 관계 계산
    spatial = store.compute_spatial_relationships()
    print(f"✅ Spatial relationships computed")

    if spatial:
        print(f"\n📍 Entity Positions:")
        for entity_id, position in spatial.entities.items():
            print(f"  • {entity_id}: ({position.latitude:.4f}, {position.longitude:.4f})")

        print(f"\n📏 Distances:")
        for pair, distance in spatial.distances.items():
            print(f"  • {pair}: {distance:.2f}m ({distance/1000:.2f}km)")


def test_temporal_layer():
    """Temporal Layer 테스트"""
    print("\n" + "="*70)
    print("TEST 5: Temporal Layer (이벤트 히스토리)")
    print("="*70)

    store = get_coverse_store()

    # 최근 이벤트 조회
    recent_events = store.get_recent_events(10)
    print(f"✅ Total events recorded: {len(store.get_all_events())}")
    print(f"\n📋 Recent Events (최근 10개):")
    for i, event in enumerate(recent_events):
        print(f"  {i+1}. [{event.type.value}] {event.description}")
        if event.severity:
            print(f"     └─ Severity: {event.severity}")


def test_coverse_snapshot():
    """전체 CoVerse 스냅샷"""
    print("\n" + "="*70)
    print("TEST 6: CoVerse Snapshot (전체 상황)")
    print("="*70)

    store = get_coverse_store()
    snapshot = store.get_coverse_snapshot()

    print(f"✅ CoVerse snapshot taken at: {snapshot['timestamp']}")
    print(f"\n📊 Summary:")
    print(f"  • Entities: {len(snapshot['entityLayer']['entities'])}")
    print(f"  • Missions: {len(snapshot['operationLayer']['missions'])}")
    print(f"  • Tasks: {len(snapshot['operationLayer']['tasks'])}")
    print(f"  • Recent Decisions: {len(snapshot['operationLayer']['decisions'])}")
    print(f"  • Recent Events: {len(snapshot['temporalLayer']['recentEvents'])}")

    # JSON으로 출력 (일부만)
    print(f"\n🔍 Sample Task:")
    if snapshot['operationLayer']['tasks']:
        task = snapshot['operationLayer']['tasks'][0]
        print(json.dumps(task, indent=2, default=str, ensure_ascii=False)[:500] + "...")


def main():
    """테스트 실행"""
    print("\n" + "🚀 "*30)
    print("CoVerse Store Prototype Test".center(70))
    print("🚀 "*30)

    try:
        test_entity_layer()
        test_operation_layer()
        test_system_layer()
        test_spatial_layer()
        test_temporal_layer()
        test_coverse_snapshot()

        print("\n" + "="*70)
        print("✅ ALL TESTS PASSED".center(70))
        print("="*70 + "\n")

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
