#!/usr/bin/env python3
"""
CoVerse API 통합 테스트

CoVerseStore에서 데이터를 로드하여 API 응답을 검증합니다.
"""

import sys
from pathlib import Path
import json

# CoWater 서버 모듈 import
sys.path.insert(0, str(Path(__file__).parent.parent / "server"))
from shared.storage.coverse_store import get_coverse_store


def test_coverse_endpoints():
    """CoVerse 엔드포인트 데이터 검증"""
    print("\n" + "="*70)
    print("CoVerse API Integration Test (Data Validation)")
    print("="*70)

    # CoVerse Store 초기화
    store = get_coverse_store()

    # Test 1: Snapshot
    print("\n📍 Testing /coverse/snapshot endpoint")
    snapshot = store.get_coverse_snapshot()
    assert "timestamp" in snapshot
    assert "entityLayer" in snapshot
    assert "operationLayer" in snapshot
    assert "systemLayer" in snapshot
    assert "temporalLayer" in snapshot
    assert "spatialLayer" in snapshot
    print(f"✅ Snapshot structure valid")
    print(f"   - Entities: {len(snapshot['entityLayer']['entities'])}")
    print(f"   - Missions: {len(snapshot['operationLayer']['missions'])}")
    print(f"   - Tasks: {len(snapshot['operationLayer']['tasks'])}")
    print(f"   - Decisions: {len(snapshot['operationLayer']['decisions'])}")

    # Test 2: Entity Layer
    print("\n📍 Testing /coverse/entity-layer endpoint")
    entity_layer = snapshot['entityLayer']
    assert "entities" in entity_layer
    entities = entity_layer['entities']
    assert len(entities) > 0
    print(f"✅ Entity Layer valid: {len(entities)} entities")
    for entity in entities:
        print(f"     • {entity['id']}: {entity['name']}")

    # Test 3: Operation Layer
    print("\n📍 Testing /coverse/operation-layer endpoint")
    op_layer = snapshot['operationLayer']
    assert "missions" in op_layer
    assert "tasks" in op_layer
    assert "decisions" in op_layer
    print(f"✅ Operation Layer valid")
    print(f"   - Missions: {len(op_layer['missions'])}")
    print(f"   - Tasks: {len(op_layer['tasks'])}")
    print(f"   - Decisions: {len(op_layer['decisions'])}")

    # Test 4: System Layer
    print("\n📍 Testing /coverse/system-layer endpoint")
    sys_layer = snapshot['systemLayer']
    print(f"✅ System Layer data: {type(sys_layer).__name__}")

    # Test 5: Temporal Layer
    print("\n📍 Testing /coverse/temporal-layer endpoint")
    temp_layer = snapshot['temporalLayer']
    assert "recentEvents" in temp_layer
    print(f"✅ Temporal Layer valid: {len(temp_layer['recentEvents'])} events")

    # Test 6: Spatial Layer
    print("\n📍 Testing /coverse/spatial-layer endpoint")
    spatial_layer = snapshot['spatialLayer']
    print(f"✅ Spatial Layer data: {type(spatial_layer).__name__}")

    # Test 7: JSON Serialization (FastAPI will use this)
    print("\n📍 Testing JSON serialization (FastAPI compatibility)")
    try:
        json_str = json.dumps(snapshot, default=str)
        assert len(json_str) > 0
        print(f"✅ Snapshot is JSON serializable ({len(json_str)} bytes)")
    except Exception as e:
        print(f"❌ JSON serialization failed: {e}")
        raise

    print("\n" + "="*70)
    print("✅ ALL TESTS PASSED")
    print("="*70)


if __name__ == "__main__":
    test_coverse_endpoints()
