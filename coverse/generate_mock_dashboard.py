#!/usr/bin/env python3
"""
Mock CoVerse Dashboard 생성 스크립트

풍부한 Mock 데이터로 CoVerse의 실제 모습을 시각화합니다.
"""

import sys
from pathlib import Path
import json
from datetime import datetime, timezone, timedelta
import random

# CoWater 모듈 import
sys.path.insert(0, str(Path(__file__).parent.parent / "server"))
from shared.storage.coverse_store import (
    get_coverse_store,
    Entity, EntityStatus, Measurement, Connectivity,
    Mission, MissionStatus, Task, TaskStatus,
    Decision, DecisionType, DecisionReasoning,
    SystemMetrics, ComponentMetrics,
)


def generate_mock_data():
    """풍부한 Mock 데이터 생성"""
    store = get_coverse_store()

    print("🚀 Mock 데이터 생성 중...")

    # ========================================================================
    # 1. Entity Layer: 5개의 무인체 생성
    # ========================================================================
    print("  1️⃣ Entity Layer 생성...")

    entities_data = [
        {
            "id": "UUV-001",
            "name": "AUV Alpha",
            "lat": 37.50, "lon": 126.80, "depth": 50,
            "battery": 85,
            "temperature": 12.3,
            "salinity": 34.5,
            "status": EntityStatus.ACTIVE
        },
        {
            "id": "UUV-002",
            "name": "AUV Beta",
            "lat": 37.52, "lon": 126.85, "depth": 30,
            "battery": 18,  # 낮음
            "temperature": 11.8,
            "salinity": 34.2,
            "status": EntityStatus.ACTIVE
        },
        {
            "id": "UUV-003",
            "name": "AUV Gamma",
            "lat": 37.48, "lon": 126.75, "depth": 20,
            "battery": 62,
            "temperature": 12.1,
            "salinity": 34.6,
            "status": EntityStatus.ACTIVE
        },
        {
            "id": "GATEWAY-001",
            "name": "Gateway Station",
            "lat": 37.55, "lon": 126.90, "depth": 0,
            "battery": 100,
            "temperature": 15.2,
            "salinity": 34.0,
            "status": EntityStatus.ACTIVE
        },
        {
            "id": "SENSOR-001",
            "name": "Environmental Sensor",
            "lat": 37.50, "lon": 126.82, "depth": 100,
            "battery": 45,
            "temperature": 8.5,
            "salinity": 35.1,
            "status": EntityStatus.ACTIVE
        },
    ]

    for entity_data in entities_data:
        entity = Entity(
            id=entity_data["id"],
            type="device",
            name=entity_data["name"],
            status=entity_data["status"],
            measurements={
                "location": Measurement(
                    value={
                        "lat": entity_data["lat"],
                        "lon": entity_data["lon"],
                        "depth": entity_data["depth"]
                    },
                    unit="degrees/meters"
                ),
                "battery": Measurement(value=entity_data["battery"], unit="%"),
                "temperature": Measurement(value=entity_data["temperature"], unit="°C"),
                "salinity": Measurement(value=entity_data["salinity"], unit="PSU"),
            },
            connectivity=Connectivity(
                is_connected=True,
                last_heartbeat=datetime.now(timezone.utc).isoformat(),
                signal_strength=random.randint(40, 100),
                latency=random.randint(10, 200)
            )
        )
        store.add_or_update_entity(entity)

    # ========================================================================
    # 2. Operation Layer: Mission 생성
    # ========================================================================
    print("  2️⃣ Operation Layer 생성...")

    # Mission 1: 해역 모니터링
    mission1 = Mission(
        id="MISSION-001",
        type="surveillance",
        description="특정 해역의 수질 모니터링",
        status=MissionStatus.IN_PROGRESS,
        priority=2
    )
    store.create_mission(mission1)

    # Mission 2: 데이터 수집
    mission2 = Mission(
        id="MISSION-002",
        type="data_collection",
        description="해저 지형 지질 데이터 수집",
        status=MissionStatus.IN_PROGRESS,
        priority=2
    )
    store.create_mission(mission2)

    # ========================================================================
    # 3. Task 생성 및 Decision Trail
    # ========================================================================
    print("  3️⃣ Task & Decision Trail 생성...")

    # Task 1: UUV-002 (배터리 부족) 복귀
    # → Detection: 배터리 부족 감지
    detection_decision = Decision(
        id="",
        decision_type=DecisionType.ANOMALY_DETECTED,
        made_by_role="monitoring",
        target_type="entity",
        target_id="UUV-002",
        reasoning=DecisionReasoning(
            source_data={
                "entity_id": "UUV-002",
                "battery": 18,
                "threshold": 20,
                "location": "37.52°N, 126.85°E"
            },
            analysis_method="rule-based",
            parameters={"threshold_type": "critical"},
            conclusion="배터리 임계값 이하 - 즉시 조치 필요",
            confidence=0.99
        ),
        decision={
            "action": "escalate_alert",
            "severity": "critical",
            "rationale": f"18% < 20% threshold"
        }
    )
    store.record_decision(detection_decision)

    # → Analysis: 우선도 결정
    analysis_decision = Decision(
        id="",
        decision_type=DecisionType.PRIORITY_ADJUSTMENT,
        made_by_role="analysis",
        target_type="task",
        target_id="",
        reasoning=DecisionReasoning(
            source_data={
                "battery_level": 18,
                "distance_to_base": 4.94,
                "current_load": 0.72,
                "weather_forecast": "stable",
                "mission_priority": 2
            },
            analysis_method="ml-model",
            parameters={
                "model": "priority-scorer-v2",
                "factors": ["battery", "distance", "load", "mission"]
            },
            conclusion="높은 우선도 - 배터리 위험 + 원격거리",
            confidence=0.95
        ),
        decision={
            "action": "set_priority",
            "newValue": 1,
            "rationale": "Low battery + 4.94km from base + High system load"
        }
    )
    store.record_decision(analysis_decision)

    # → Control: Task 할당
    task1 = Task(
        id="",
        parent_mission_id="MISSION-001",
        type="return_to_base",
        assigned_entity_id="UUV-002",
        status=TaskStatus.ASSIGNED,
        priority=1,
        command={
            "action": "return_to_base",
            "parameters": {
                "baseStation": "GATEWAY-001",
                "coordinates": [37.55, 126.90, 0],
                "speed": "maximum",
                "route": "direct"
            }
        }
    )
    created_task1 = store.create_task(task1)

    control_decision = Decision(
        id="",
        decision_type=DecisionType.TASK_ALLOCATION,
        made_by_role="control",
        target_type="task",
        target_id=created_task1.id,
        reasoning=DecisionReasoning(
            source_data={
                "entity_id": "UUV-002",
                "priority": 1,
                "current_task": None,
                "system_load": 0.72,
                "available_resources": 3,
                "weather": "stable"
            },
            analysis_method="decision-tree",
            parameters={"strategy": "minimize_risk"},
            conclusion="무인체 반환 명령 발행",
            confidence=0.98
        ),
        decision={
            "action": "assign_return_task",
            "rationale": "Battery critical, 4.94km from base, system resources available"
        }
    )
    store.record_decision(control_decision)

    # Task 2: UUV-001 계속 모니터링
    task2 = Task(
        id="",
        parent_mission_id="MISSION-001",
        type="monitor",
        assigned_entity_id="UUV-001",
        status=TaskStatus.IN_PROGRESS,
        priority=2,
        progress_percentage=45,
        progress_stage="Data collection phase",
        command={
            "action": "continue_monitoring",
            "parameters": {
                "area": "Survey Grid A",
                "depth_range": [30, 60],
                "sample_interval": 60  # seconds
            }
        }
    )
    created_task2 = store.create_task(task2)

    # Task 3: UUV-003 정찰
    task3 = Task(
        id="",
        parent_mission_id="MISSION-002",
        type="patrol",
        assigned_entity_id="UUV-003",
        status=TaskStatus.IN_PROGRESS,
        priority=3,
        progress_percentage=62,
        progress_stage="Waypoint 3/5",
        command={
            "action": "patrol_route",
            "parameters": {
                "route": "Survey Route B",
                "waypoints": 5,
                "speed": "normal"
            }
        }
    )
    created_task3 = store.create_task(task3)

    # ========================================================================
    # 4. System Layer: 시스템 메트릭
    # ========================================================================
    print("  4️⃣ System Layer 생성...")

    system_metrics = SystemMetrics(
        operational_load=0.72,
        task_queue_length=5,
        active_task_count=3,
        failure_rate=0.001,
        components={
            "detection_agent": ComponentMetrics(
                status="healthy",
                last_health_check=datetime.now(timezone.utc).isoformat(),
                metrics={
                    "cpu_usage": 32,
                    "memory_usage": 48,
                    "latency": 23,
                    "messages_processed": 1247
                }
            ),
            "analysis_agent": ComponentMetrics(
                status="healthy",
                last_health_check=datetime.now(timezone.utc).isoformat(),
                metrics={
                    "cpu_usage": 45,
                    "memory_usage": 62,
                    "latency": 56,
                    "model_accuracy": 0.94
                }
            ),
            "control_agent": ComponentMetrics(
                status="degraded",
                last_health_check=datetime.now(timezone.utc).isoformat(),
                metrics={
                    "cpu_usage": 85,
                    "memory_usage": 78,
                    "latency": 320
                },
                alerts=[
                    {
                        "severity": "warning",
                        "message": "High CPU usage - consider load balancing",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                ]
            ),
            "database": ComponentMetrics(
                status="healthy",
                last_health_check=datetime.now(timezone.utc).isoformat(),
                metrics={
                    "query_latency": 12,
                    "connections": 15,
                    "storage_usage_gb": 45.2
                }
            ),
            "redis": ComponentMetrics(
                status="healthy",
                last_health_check=datetime.now(timezone.utc).isoformat(),
                metrics={
                    "memory_usage_mb": 256,
                    "connected_clients": 8,
                    "throughput_ops_sec": 1450
                }
            )
        }
    )
    store.set_system_metrics(system_metrics)

    # ========================================================================
    # 5. Temporal Layer: 이벤트 생성 (자동으로 생성됨)
    # ========================================================================
    print("  5️⃣ Temporal Layer 생성 (자동)...")

    # ========================================================================
    # 6. Spatial Layer: 공간 관계 계산
    # ========================================================================
    print("  6️⃣ Spatial Layer 생성...")
    store.compute_spatial_relationships()

    print("\n✅ Mock 데이터 생성 완료!\n")
    return store


def generate_html_dashboard(store):
    """HTML 대시보드 생성"""
    snapshot = store.get_coverse_snapshot()

    html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>CoVerse Dashboard - Mock</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            color: #333;
            padding: 20px;
            min-height: 100vh;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
        }

        .header {
            background: white;
            padding: 30px;
            border-radius: 12px;
            margin-bottom: 20px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            border-left: 5px solid #2a5298;
        }

        .header h1 {
            color: #1e3c72;
            margin-bottom: 10px;
            font-size: 32px;
        }

        .header p {
            color: #666;
            font-size: 16px;
        }

        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-top: 20px;
        }

        .stat-box {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
        }

        .stat-value {
            font-size: 28px;
            font-weight: bold;
            margin-bottom: 5px;
        }

        .stat-label {
            font-size: 12px;
            opacity: 0.9;
        }

        .layer {
            background: white;
            padding: 25px;
            border-radius: 12px;
            margin-bottom: 20px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            border-top: 4px solid #2a5298;
        }

        .layer h2 {
            color: #1e3c72;
            margin-bottom: 20px;
            font-size: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #f0f0f0;
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 15px;
        }

        .card {
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }

        .card h3 {
            color: #1e3c72;
            margin-bottom: 10px;
            font-size: 14px;
            font-weight: bold;
        }

        .card-info {
            font-size: 12px;
            color: #555;
            line-height: 1.6;
        }

        .status-badge {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: bold;
            margin-left: 5px;
        }

        .status-active {
            background: #4CAF50;
            color: white;
        }

        .status-critical {
            background: #f44336;
            color: white;
        }

        .status-warning {
            background: #FFC107;
            color: black;
        }

        .priority-1 {
            color: #f44336;
            font-weight: bold;
        }

        .priority-2 {
            color: #FFC107;
            font-weight: bold;
        }

        .priority-3 {
            color: #4CAF50;
            font-weight: bold;
        }

        .decision-item {
            background: #f9f9f9;
            padding: 12px;
            border-radius: 6px;
            margin-bottom: 10px;
            border-left: 3px solid #667eea;
        }

        .decision-role {
            font-weight: bold;
            color: #667eea;
            font-size: 11px;
            text-transform: uppercase;
            margin-bottom: 3px;
        }

        .decision-conclusion {
            color: #333;
            font-size: 12px;
            margin-bottom: 3px;
        }

        .decision-confidence {
            color: #999;
            font-size: 10px;
        }

        .event-item {
            background: #f9f9f9;
            padding: 10px;
            border-radius: 6px;
            margin-bottom: 8px;
            border-left: 3px solid #4CAF50;
            font-size: 11px;
        }

        .event-time {
            color: #999;
            font-size: 10px;
        }

        .metric-row {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #eee;
            font-size: 12px;
        }

        .metric-row:last-child {
            border-bottom: none;
        }

        .metric-label {
            color: #666;
        }

        .metric-value {
            color: #1e3c72;
            font-weight: bold;
        }

        .fullwidth {
            grid-column: 1 / -1;
        }

        .timestamp {
            text-align: right;
            color: #999;
            font-size: 12px;
            margin-top: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🌐 CoVerse Dashboard</h1>
            <p>상황인식 논리적 데이터 공간 - Mock Visualization</p>
            <p style="margin-top: 10px; font-size: 13px; color: #999;">
                5개 레이어의 실시간 데이터를 한 곳에서 보고, 시스템의 판단 근거를 명확히 이해합니다.
            </p>
            <div class="stats">
                <div class="stat-box">
                    <div class="stat-value">""" + str(len(snapshot['entityLayer']['entities'])) + """</div>
                    <div class="stat-label">Active Entities</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value">""" + str(len(snapshot['operationLayer']['missions'])) + """</div>
                    <div class="stat-label">Missions</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value">""" + str(len(snapshot['operationLayer']['tasks'])) + """</div>
                    <div class="stat-label">Tasks</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value">""" + str(len(snapshot['operationLayer']['decisions'])) + """</div>
                    <div class="stat-label">Decisions</div>
                </div>
            </div>
        </div>

        <!-- 1. Entity Layer -->
        <div class="layer">
            <h2>1️⃣ Entity Layer (실체 상태)</h2>
            <div class="grid">
"""
    for entity in snapshot['entityLayer']['entities']:
        location = entity['measurements'].get('location', {}).get('value', {})
        battery = entity['measurements'].get('battery', {})
        temp = entity['measurements'].get('temperature', {})

        status_class = 'status-active' if battery.get('value', 100) > 20 else 'status-critical'

        html += f"""
                <div class="card">
                    <h3>
                        {entity['name']}
                        <span class="status-badge {status_class}">{entity['status']}</span>
                    </h3>
                    <div class="card-info">
                        <div>🌍 위치: {location.get('lat', '?'):.2f}°, {location.get('lon', '?'):.2f}°</div>
                        <div>🔋 배터리: <strong>{battery.get('value', '?')}%</strong></div>
                        <div>🌡️ 온도: {temp.get('value', '?')}°C</div>
                        <div>📡 신호: {entity['connectivity']['signal_strength'] if entity['connectivity'] else '?'}%</div>
                    </div>
                </div>
"""
    html += """
            </div>
        </div>

        <!-- 2. Operation Layer: Missions -->
        <div class="layer">
            <h2>2️⃣ Operation Layer - Missions (상위 목표)</h2>
            <div class="grid">
"""
    for mission in snapshot['operationLayer']['missions']:
        task_count = len(mission.get('task_ids', []))
        html += f"""
                <div class="card">
                    <h3>{mission['description']}</h3>
                    <div class="card-info">
                        <div>ID: {mission['id']}</div>
                        <div>상태: <strong>{mission['status']}</strong></div>
                        <div>우선도: <span class="priority-{mission['priority']}">{mission['priority']}</span></div>
                        <div>Task 수: {task_count}</div>
                    </div>
                </div>
"""
    html += """
            </div>
        </div>

        <!-- 3. Operation Layer: Tasks + Decision Trail -->
        <div class="layer">
            <h2>3️⃣ Operation Layer - Tasks + Decision Trail (판단 근거)</h2>
            <div class="grid fullwidth">
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                    <div>
                        <h3 style="color: #1e3c72; margin-bottom: 15px;">📋 Tasks</h3>
"""
    for task in snapshot['operationLayer']['tasks']:
        html += f"""
                        <div class="decision-item">
                            <div class="decision-role">{task['type'].upper()}</div>
                            <div class="card-info">
                                <div>할당: <strong>{task['assigned_entity_id']}</strong></div>
                                <div>상태: {task['status']}</div>
                                <div>우선도: <span class="priority-{task['priority']}">{task['priority']}</span></div>
                                <div>진행: {task['progress_percentage']}%</div>
                            </div>
                        </div>
"""
    html += """
                    </div>
                    <div>
                        <h3 style="color: #1e3c72; margin-bottom: 15px;">🔍 Decision Trail (왜 이렇게 됐는가)</h3>
"""
    for decision in snapshot['operationLayer']['decisions']:
        confidence = decision.get('reasoning', {}).get('confidence', 0)
        html += f"""
                        <div class="decision-item">
                            <div class="decision-role">👤 {decision['made_by_role'].upper()}</div>
                            <div class="decision-conclusion">
                                📌 {decision['reasoning']['conclusion'] if decision.get('reasoning') else 'N/A'}
                            </div>
                            <div class="decision-confidence">
                                신뢰도: {confidence:.2%} | 타입: {decision['decision_type']}
                            </div>
                        </div>
"""
    html += """
                    </div>
                </div>
            </div>
        </div>

        <!-- 4. System Layer -->
        <div class="layer">
            <h2>4️⃣ System Layer (시스템 건강도)</h2>
            <div class="grid fullwidth">
"""
    if snapshot['systemLayer']:
        sys_data = snapshot['systemLayer']
        html += f"""
                <div class="card" style="grid-column: 1/-1;">
                    <h3>전체 시스템</h3>
                    <div class="metric-row">
                        <span class="metric-label">운영 부하</span>
                        <span class="metric-value">{sys_data['operational_load']*100:.1f}%</span>
                    </div>
                    <div class="metric-row">
                        <span class="metric-label">활성 Task</span>
                        <span class="metric-value">{sys_data['active_task_count']}</span>
                    </div>
                    <div class="metric-row">
                        <span class="metric-label">실패율</span>
                        <span class="metric-value">{sys_data['failure_rate']*100:.2f}%</span>
                    </div>
                </div>
"""
        for comp_name, comp_data in sys_data['components'].items():
            status_badge = 'status-active' if comp_data['status'] == 'healthy' else 'status-warning' if comp_data['status'] == 'degraded' else 'status-critical'
            html += f"""
                <div class="card">
                    <h3>
                        {comp_name}
                        <span class="status-badge {status_badge}">{comp_data['status']}</span>
                    </h3>
                    <div class="card-info">
"""
            for metric_name, metric_value in comp_data['metrics'].items():
                if isinstance(metric_value, float):
                    html += f"<div>{metric_name}: {metric_value:.1f}</div>"
                else:
                    html += f"<div>{metric_name}: {metric_value}</div>"

            if comp_data['alerts']:
                html += f"""
                        <div style="margin-top: 8px; color: #f44336; font-size: 11px;">
                            ⚠️ {comp_data['alerts'][0]['message']}
                        </div>
"""
            html += """
                    </div>
                </div>
"""
    html += """
            </div>
        </div>

        <!-- 5. Spatial Layer -->
        <div class="layer">
            <h2>5️⃣ Spatial Layer (공간 관계)</h2>
            <div class="card fullwidth">
"""
    if snapshot['spatialLayer']:
        spatial = snapshot['spatialLayer']
        html += """<h3>엔티티 간 거리</h3><div class="card-info">"""
        for pair, distance in list(spatial['distances'].items())[:5]:  # 처음 5개만
            html += f"<div>🔗 {pair}: {distance/1000:.2f}km</div>"
        html += """</div>"""
    html += """
            </div>
        </div>

        <!-- 6. Temporal Layer -->
        <div class="layer">
            <h2>6️⃣ Temporal Layer (시간 흐름 & 이벤트)</h2>
            <div class="card fullwidth">
                <h3>최근 이벤트 타임라인</h3>
"""
    for event in reversed(snapshot['temporalLayer']['recentEvents'][-10:]):
        html += f"""
                <div class="event-item">
                    <div class="event-time">{event['timestamp'][-8:]}</div>
                    <div>{event['description']}</div>
                </div>
"""
    html += """
            </div>
        </div>

        <div class="timestamp">
            📊 생성 시간: """ + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + """
        </div>
    </div>
</body>
</html>
"""

    return html


def main():
    """메인 함수"""
    print("\n" + "🌐 "*35)
    print("CoVerse Mock Dashboard 생성".center(70))
    print("🌐 "*35 + "\n")

    # Mock 데이터 생성
    store = generate_mock_data()

    # HTML 대시보드 생성
    html = generate_html_dashboard(store)

    # 파일로 저장
    output_path = Path(__file__).parent / "mock_dashboard.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ Mock 대시보드 생성 완료!")
    print(f"\n📂 파일: {output_path}")
    print(f"\n🌐 사용 방법:")
    print(f"   1. 위 파일을 브라우저에서 열기")
    print(f"   2. 또는 커맨드: open {output_path}")
    print(f"\n💡 이 HTML에서 볼 수 있는 것:")
    print(f"   • 5개 무인체의 실시간 상태 (Entity Layer)")
    print(f"   • 2개 미션과 3개 태스크 (Operation Layer)")
    print(f"   • Decision Trail: Monitoring → Analysis → Control의 판단 근거")
    print(f"   • 시스템 컴포넌트 상태와 알람 (System Layer)")
    print(f"   • 엔티티 간 거리 계산 (Spatial Layer)")
    print(f"   • 모든 이벤트 타임라인 (Temporal Layer)\n")


if __name__ == "__main__":
    main()
