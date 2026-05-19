"""
CoVerse API Server

간단한 Flask 기반 REST API로 CoVerse 데이터를 제공합니다.
"""

from flask import Flask, jsonify, render_template_string
from flask_cors import CORS
import sys
from pathlib import Path
import json

# CoWater 모듈 import
sys.path.insert(0, str(Path(__file__).parent.parent / "server"))
from shared.storage.coverse_store import (
    get_coverse_store,
    Entity, EntityStatus, Measurement, Connectivity,
    Mission, MissionStatus, Task, TaskStatus,
    Decision, DecisionType, DecisionReasoning,
    SystemMetrics, ComponentMetrics,
    Position
)
from datetime import datetime, timezone


app = Flask(__name__)
CORS(app)

# ============================================================================
# REST API Endpoints
# ============================================================================

@app.route("/api/health", methods=["GET"])
def health():
    """상태 확인"""
    return jsonify({"status": "ok", "message": "CoVerse API is running"})


@app.route("/api/coverse/snapshot", methods=["GET"])
def get_snapshot():
    """전체 CoVerse 스냅샷"""
    store = get_coverse_store()
    snapshot = store.get_coverse_snapshot()
    return jsonify(snapshot, default=str)


@app.route("/api/entities", methods=["GET"])
def list_entities():
    """모든 엔티티 조회"""
    store = get_coverse_store()
    entities = store.get_all_entities()
    return jsonify({
        "entities": [
            {
                "id": e.id,
                "name": e.name,
                "type": e.type,
                "status": e.status.value,
                "measurements": {
                    k: {
                        "value": v.value,
                        "unit": v.unit,
                        "timestamp": v.timestamp
                    } for k, v in e.measurements.items()
                },
                "connectivity": {
                    "is_connected": e.connectivity.is_connected,
                    "signal_strength": e.connectivity.signal_strength,
                    "latency": e.connectivity.latency
                } if e.connectivity else None
            } for e in entities
        ]
    }, default=str)


@app.route("/api/missions", methods=["GET"])
def list_missions():
    """모든 미션 조회"""
    store = get_coverse_store()
    missions = store.get_all_missions()
    return jsonify({
        "missions": [
            {
                "id": m.id,
                "type": m.type,
                "description": m.description,
                "status": m.status.value,
                "priority": m.priority,
                "task_count": len(m.task_ids),
                "created_at": m.created_at
            } for m in missions
        ]
    }, default=str)


@app.route("/api/tasks", methods=["GET"])
def list_tasks():
    """모든 태스크 조회"""
    store = get_coverse_store()
    tasks = store.get_all_tasks()
    return jsonify({
        "tasks": [
            {
                "id": t.id,
                "type": t.type,
                "assigned_entity_id": t.assigned_entity_id,
                "status": t.status.value,
                "priority": t.priority,
                "progress_percentage": t.progress_percentage,
                "created_at": t.created_at
            } for t in tasks
        ]
    }, default=str)


@app.route("/api/decisions", methods=["GET"])
def list_decisions():
    """최근 결정 조회"""
    store = get_coverse_store()
    decisions = store.decisions[-20:]  # 최근 20개
    return jsonify({
        "decisions": [
            {
                "id": d.id,
                "decision_type": d.decision_type.value,
                "made_by_role": d.made_by_role,
                "target_id": d.target_id,
                "made_at": d.made_at,
                "reasoning": {
                    "conclusion": d.reasoning.conclusion,
                    "confidence": d.reasoning.confidence
                } if d.reasoning else None
            } for d in decisions
        ]
    }, default=str)


@app.route("/api/system-metrics", methods=["GET"])
def get_system_metrics():
    """시스템 메트릭"""
    store = get_coverse_store()
    metrics = store.get_system_metrics()
    if not metrics:
        return jsonify({"error": "No metrics recorded"})

    return jsonify({
        "timestamp": metrics.timestamp,
        "operational_load": metrics.operational_load,
        "task_queue_length": metrics.task_queue_length,
        "active_task_count": metrics.active_task_count,
        "failure_rate": metrics.failure_rate,
        "components": {
            name: {
                "status": comp.status,
                "metrics": comp.metrics,
                "alerts": comp.alerts
            } for name, comp in metrics.components.items()
        }
    }, default=str)


@app.route("/api/spatial", methods=["GET"])
def get_spatial():
    """공간 관계"""
    store = get_coverse_store()
    spatial = store.get_spatial_relationships()
    if not spatial:
        return jsonify({"error": "No spatial data"})

    return jsonify({
        "timestamp": spatial.timestamp,
        "entities": {
            eid: {
                "latitude": pos.latitude,
                "longitude": pos.longitude,
                "altitude": pos.altitude
            } for eid, pos in spatial.entities.items()
        },
        "distances": spatial.distances
    }, default=str)


@app.route("/api/events", methods=["GET"])
def get_events():
    """최근 이벤트"""
    store = get_coverse_store()
    events = store.get_recent_events(30)  # 최근 30개
    return jsonify({
        "events": [
            {
                "id": e.id,
                "type": e.type.value,
                "timestamp": e.timestamp,
                "source_type": e.source_type,
                "source_id": e.source_id,
                "description": e.description,
                "severity": e.severity
            } for e in events
        ]
    }, default=str)


# ============================================================================
# Dashboard (HTML)
# ============================================================================

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>CoVerse Dashboard</title>
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
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }

        .header h1 {
            color: #1e3c72;
            margin-bottom: 10px;
        }

        .header p {
            color: #666;
            font-size: 14px;
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }

        .card {
            background: white;
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            transition: transform 0.2s;
        }

        .card:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }

        .card h3 {
            color: #1e3c72;
            margin-bottom: 15px;
            font-size: 16px;
            border-bottom: 2px solid #2a5298;
            padding-bottom: 10px;
        }

        .stat-value {
            font-size: 32px;
            font-weight: bold;
            color: #2a5298;
            margin-bottom: 5px;
        }

        .stat-label {
            font-size: 12px;
            color: #999;
        }

        .layer {
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
        }

        .layer h2 {
            color: #1e3c72;
            margin-bottom: 15px;
            font-size: 18px;
            border-bottom: 3px solid #2a5298;
            padding-bottom: 10px;
        }

        .entity-card {
            background: white;
            padding: 15px;
            border-radius: 6px;
            margin-bottom: 10px;
            border-left: 4px solid #2a5298;
        }

        .entity-name {
            font-weight: bold;
            color: #1e3c72;
        }

        .entity-info {
            font-size: 12px;
            color: #666;
            margin-top: 5px;
        }

        .status-badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: bold;
            margin-left: 10px;
        }

        .status-active {
            background: #4CAF50;
            color: white;
        }

        .status-idle {
            background: #FFC107;
            color: white;
        }

        .status-error {
            background: #f44336;
            color: white;
        }

        .decision-item {
            background: white;
            padding: 12px;
            border-radius: 6px;
            margin-bottom: 8px;
            border-left: 3px solid #2a5298;
        }

        .decision-role {
            font-weight: bold;
            color: #1e3c72;
            font-size: 12px;
            text-transform: uppercase;
        }

        .decision-type {
            color: #666;
            font-size: 12px;
            margin-top: 3px;
        }

        .event-item {
            background: white;
            padding: 12px;
            border-radius: 6px;
            margin-bottom: 8px;
            border-left: 3px solid #4CAF50;
        }

        .event-time {
            font-size: 11px;
            color: #999;
        }

        .event-desc {
            font-size: 13px;
            color: #333;
            margin-top: 3px;
        }

        .fullwidth {
            grid-column: 1 / -1;
        }

        .loading {
            text-align: center;
            color: #666;
            padding: 40px;
        }

        .error {
            background: #ffebee;
            color: #c62828;
            padding: 15px;
            border-radius: 6px;
            margin-bottom: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🌐 CoVerse Dashboard</h1>
            <p>실시간 상황 인식 (Situational Awareness) 플랫폼</p>
            <p id="timestamp" style="margin-top: 10px; font-size: 12px;"></p>
        </div>

        <div id="error"></div>

        <!-- 1. Entity Layer -->
        <div class="layer">
            <h2>1️⃣ Entity Layer (실체 상태)</h2>
            <div id="entities" class="loading">로딩 중...</div>
        </div>

        <!-- 2. Operation Layer (Summary) -->
        <div class="grid">
            <div class="card">
                <h3>Missions</h3>
                <div class="stat-value" id="mission-count">-</div>
                <div class="stat-label">Active Missions</div>
            </div>
            <div class="card">
                <h3>Tasks</h3>
                <div class="stat-value" id="task-count">-</div>
                <div class="stat-label">Total Tasks</div>
            </div>
            <div class="card">
                <h3>Decisions</h3>
                <div class="stat-value" id="decision-count">-</div>
                <div class="stat-label">Recent Decisions</div>
            </div>
        </div>

        <!-- Decision Trail -->
        <div class="layer">
            <h2>2️⃣ Operation Layer + Decision Trail (판단 근거)</h2>
            <div id="decisions" class="loading">로딩 중...</div>
        </div>

        <!-- 3. System Layer -->
        <div class="layer">
            <h2>3️⃣ System Layer (시스템 건강도)</h2>
            <div id="system" class="loading">로딩 중...</div>
        </div>

        <!-- 4. Spatial Layer -->
        <div class="layer">
            <h2>4️⃣ Spatial Layer (공간 관계)</h2>
            <div id="spatial" class="loading">로딩 중...</div>
        </div>

        <!-- 5. Temporal Layer -->
        <div class="layer">
            <h2>5️⃣ Temporal Layer (시간 흐름 & 이벤트)</h2>
            <div id="events" class="loading">로딩 중...</div>
        </div>
    </div>

    <script>
        const API_BASE = "/api";

        async function loadDashboard() {
            try {
                // 동시에 모든 데이터 로드
                const [entities, missions, tasks, decisions, system, spatial, events] = await Promise.all([
                    fetch(`${API_BASE}/entities`).then(r => r.json()),
                    fetch(`${API_BASE}/missions`).then(r => r.json()),
                    fetch(`${API_BASE}/tasks`).then(r => r.json()),
                    fetch(`${API_BASE}/decisions`).then(r => r.json()),
                    fetch(`${API_BASE}/system-metrics`).then(r => r.json()),
                    fetch(`${API_BASE}/spatial`).then(r => r.json()),
                    fetch(`${API_BASE}/events`).then(r => r.json())
                ]);

                // 데이터 렌더링
                renderEntities(entities);
                renderMissions(missions);
                renderTasks(tasks);
                renderDecisions(decisions);
                renderSystem(system);
                renderSpatial(spatial);
                renderEvents(events);

                // 타임스탬프
                document.getElementById('timestamp').textContent =
                    `마지막 업데이트: ${new Date().toLocaleString('ko-KR')}`;

            } catch (error) {
                document.getElementById('error').innerHTML =
                    `<div class="error">❌ 데이터 로드 실패: ${error.message}</div>`;
            }
        }

        function renderEntities(data) {
            const html = data.entities.map(e => `
                <div class="entity-card">
                    <span class="entity-name">${e.name}</span>
                    <span class="status-badge status-${e.status}">${e.status}</span>
                    <div class="entity-info">
                        <div>위치: ${e.measurements.location?.value?.lat?.toFixed(4)}°, ${e.measurements.location?.value?.lon?.toFixed(4)}°</div>
                        <div>배터리: ${e.measurements.battery?.value || '-'}${e.measurements.battery?.unit || ''}</div>
                    </div>
                </div>
            `).join('');
            document.getElementById('entities').innerHTML = html || '<p>엔티티 없음</p>';
        }

        function renderMissions(data) {
            document.getElementById('mission-count').textContent = data.missions?.length || 0;
        }

        function renderTasks(data) {
            document.getElementById('task-count').textContent = data.tasks?.length || 0;
        }

        function renderDecisions(data) {
            document.getElementById('decision-count').textContent = data.decisions?.length || 0;
            const html = data.decisions?.map(d => `
                <div class="decision-item">
                    <div class="decision-role">${d.made_by_role}</div>
                    <div class="decision-type">${d.decision_type}</div>
                    <div style="font-size: 12px; color: #666; margin-top: 5px;">
                        근거: ${d.reasoning?.conclusion || '(없음)'}
                        <br/>신뢰도: ${(d.reasoning?.confidence || 0).toFixed(2)}
                    </div>
                </div>
            `).join('');
            document.getElementById('decisions').innerHTML = html || '<p>판단 없음</p>';
        }

        function renderSystem(data) {
            if (data.error) {
                document.getElementById('system').innerHTML = '<p>시스템 데이터 없음</p>';
                return;
            }

            const html = `
                <div style="display: grid; gap: 10px;">
                    <div style="padding: 10px; background: white; border-radius: 6px;">
                        <div>운영 부하: <strong>${(data.operational_load * 100).toFixed(1)}%</strong></div>
                        <div style="margin-top: 5px;">활성 태스크: <strong>${data.active_task_count}</strong></div>
                        <div>실패율: <strong>${(data.failure_rate * 100).toFixed(2)}%</strong></div>
                    </div>
                    ${Object.entries(data.components || {}).map(([name, comp]) => `
                        <div style="padding: 10px; background: white; border-radius: 6px; border-left: 3px solid #2a5298;">
                            <div><strong>${name}</strong> - ${comp.status}</div>
                            ${comp.alerts?.length ? `<div style="color: #f44336; font-size: 12px; margin-top: 5px;">⚠️ ${comp.alerts[0].message}</div>` : ''}
                        </div>
                    `).join('')}
                </div>
            `;
            document.getElementById('system').innerHTML = html;
        }

        function renderSpatial(data) {
            if (data.error) {
                document.getElementById('spatial').innerHTML = '<p>공간 데이터 없음</p>';
                return;
            }

            const html = Object.entries(data.distances || {}).map(([pair, distance]) => {
                return `<div style="padding: 10px; background: white; border-radius: 6px; margin-bottom: 8px;">
                    <strong>${pair}</strong>: ${(distance / 1000).toFixed(2)}km
                </div>`;
            }).join('');

            document.getElementById('spatial').innerHTML = html || '<p>거리 데이터 없음</p>';
        }

        function renderEvents(data) {
            const html = data.events?.slice().reverse().map(e => `
                <div class="event-item">
                    <div class="event-time">${new Date(e.timestamp).toLocaleTimeString('ko-KR')}</div>
                    <div class="event-desc">${e.description}</div>
                </div>
            `).join('');
            document.getElementById('events').innerHTML = html || '<p>이벤트 없음</p>';
        }

        // 로드 및 자동 새로고침
        loadDashboard();
        setInterval(loadDashboard, 5000); // 5초마다 새로고침
    </script>
</body>
</html>
"""


@app.route("/", methods=["GET"])
def dashboard():
    """CoVerse 대시보드"""
    return render_template_string(DASHBOARD_HTML)


# ============================================================================
# Test Data 생성
# ============================================================================

def create_test_data():
    """테스트 데이터 생성"""
    store = get_coverse_store()

    # 테스트 데이터가 이미 있으면 스킵
    if store.get_all_entities():
        return

    # 엔티티 생성
    from shared.storage.coverse_store import Entity, Measurement, Connectivity, Position

    uuv1 = Entity(
        id="UUV-001",
        type="device",
        name="AUV Alpha",
        status=EntityStatus.ACTIVE,
        measurements={
            "location": Measurement(value={"lat": 37.5, "lon": 126.8, "depth": 50}),
            "battery": Measurement(value=85, unit="%"),
        },
        connectivity=Connectivity(is_connected=True, last_heartbeat=datetime.now(timezone.utc).isoformat(), signal_strength=92)
    )
    store.add_or_update_entity(uuv1)

    uuv2 = Entity(
        id="UUV-002",
        type="device",
        name="AUV Beta",
        status=EntityStatus.ACTIVE,
        measurements={
            "location": Measurement(value={"lat": 37.52, "lon": 126.85, "depth": 30}),
            "battery": Measurement(value=18, unit="%"),
        },
        connectivity=Connectivity(is_connected=True, last_heartbeat=datetime.now(timezone.utc).isoformat(), signal_strength=45)
    )
    store.add_or_update_entity(uuv2)

    # 미션 생성
    mission = Mission(id="MISSION-001", type="surveillance", description="해역 모니터링")
    store.create_mission(mission)

    # 태스크 생성
    task = Task(
        id="",
        parent_mission_id="MISSION-001",
        type="return_to_base",
        assigned_entity_id="UUV-002",
        status=TaskStatus.ASSIGNED,
        priority=1,
        command={"action": "return_to_base"}
    )
    store.create_task(task)

    # 판단 기록
    decision = Decision(
        id="",
        decision_type=DecisionType.ANOMALY_DETECTED,
        made_by_role="monitoring",
        target_type="entity",
        target_id="UUV-002",
        reasoning=DecisionReasoning(
            source_data={"battery": 18},
            analysis_method="rule-based",
            conclusion="배터리 부족 감지",
            confidence=0.99
        ),
        decision={"action": "alert"}
    )
    store.record_decision(decision)

    # 시스템 메트릭
    metrics = SystemMetrics(
        operational_load=0.72,
        active_task_count=5,
        components={
            "analysis_agent": ComponentMetrics(status="healthy", last_health_check=datetime.now(timezone.utc).isoformat()),
            "control_agent": ComponentMetrics(status="healthy", last_health_check=datetime.now(timezone.utc).isoformat()),
        }
    )
    store.set_system_metrics(metrics)

    # 공간 관계
    store.compute_spatial_relationships()


if __name__ == "__main__":
    create_test_data()
    print("\n" + "="*70)
    print("🌐 CoVerse API Server")
    print("="*70)
    print("\n📊 Dashboard: http://localhost:5000")
    print("📡 API: http://localhost:5000/api/coverse/snapshot")
    print("\nPress Ctrl+C to stop\n")
    app.run(debug=True, host="0.0.0.0", port=5000)
