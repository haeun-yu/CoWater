from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ.setdefault(
    "COWATER_DEVICE_DB_PATH",
    str(Path(tempfile.mkdtemp(prefix="cowater-test-registry-")) / "devices.db"),
)

from fastapi.testclient import TestClient

from src.api import app
from src.core.models import DeviceAgentRegistrationRequest, DeviceRegistrationRequest
from src.registry.device_registry import DeviceRegistry
from src.registry.healthcheck_monitor import HealthcheckMonitor


SECRET_KEY = "server-secret"


def make_registry(db_path: Path) -> DeviceRegistry:
    return DeviceRegistry(
        secret_key=SECRET_KEY,
        host="127.0.0.1",
        port=8280,
        ping_endpoint="/pang/ping",
        agent_scheme="ws",
        agent_host="127.0.0.1",
        agent_port=9010,
        agent_path_prefix="/agents",
        agent_command_scheme="http",
        agent_command_path_prefix="/agents",
        db_path=db_path,
    )


def registration_request(
    name: str,
    *,
    device_type: str = "USV",
    layer: str = "lower",
    tracks: list[dict[str, str]] | None = None,
) -> DeviceRegistrationRequest:
    return DeviceRegistrationRequest(
        secretKey=SECRET_KEY,
        name=name,
        device_type=device_type,
        layer=layer,
        connectivity="rf",
        tracks=tracks
        or [
            {"type": "ODOMETRY", "name": "odometry"},
            {"type": "BATTERY", "name": "battery"},
        ],
    )


def attach_connected_agent(registry: DeviceRegistry, device_id: int) -> None:
    registry.attach_agent(
        device_id,
        DeviceAgentRegistrationRequest(
            secretKey=SECRET_KEY,
            endpoint=f"http://127.0.0.1:9/agents/{device_id}",
            commandEndpoint=f"http://127.0.0.1:9/agents/{device_id}/command",
            connected=True,
        ),
    )


def test_mission_stats_route_is_reachable_before_dynamic_mission_route() -> None:
    client = TestClient(app)
    client.post("/admin/reset")

    response = client.get("/missions/stats")

    assert response.status_code == 200
    assert response.json() == {
        "total": 0,
        "pending_approval": 0,
        "approved": 0,
        "running": 0,
        "completed": 0,
        "failed": 0,
        "rejected": 0,
        "canceled": 0,
    }


def test_create_mission_accepts_query_parameters_without_json_body() -> None:
    client = TestClient(app)
    client.post("/admin/reset")

    response = client.post(
        "/missions",
        params={
            "alert_id": "alert-1",
            "event_id": "event-1",
        },
        json={
            "title": "Test Mission",
            "mission_type": "generic_mission",
            "goal": "Test goal",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["title"] == "Test Mission"
    assert payload["mission_type"] == "generic_mission"
    assert payload["alert_id"] == "alert-1"
    assert payload["event_id"] == "event-1"
    assert client.get("/missions/stats").json()["pending_approval"] == 1


def test_main_video_track_update_is_persisted(tmp_path: Path) -> None:
    db_path = tmp_path / "devices.db"
    registry = make_registry(db_path)
    device = registry.register(
        registration_request(
            "rov-camera",
            device_type="ROV",
            tracks=[
                {"type": "VIDEO", "name": "front_camera"},
                {"type": "VIDEO", "name": "rear_camera"},
            ],
        )
    )

    registry.update_main_video_track(device.id, "rear_camera")

    restored = make_registry(db_path).get_device(device.id)
    assert restored.main_video_track_name == "rear_camera"
    assert restored.resolved_main_video_track_name() == "rear_camera"


def test_deleting_middle_parent_reassigns_lower_devices(tmp_path: Path) -> None:
    registry = make_registry(tmp_path / "devices.db")
    first_parent = registry.register(
        registration_request("ship-1", device_type="CONTROL_SHIP", layer="middle")
    )
    attach_connected_agent(registry, first_parent.id)
    second_parent = registry.register(
        registration_request("ship-2", device_type="CONTROL_SHIP", layer="middle")
    )
    attach_connected_agent(registry, second_parent.id)
    child = registry.register(
        registration_request("rov-1", device_type="ROV", layer="lower")
    )

    assert registry.get_device(child.id).parent_id == first_parent.id

    registry.delete(first_parent.id)

    reassigned_child = registry.get_device(child.id)
    assert reassigned_child.parent_id == second_parent.id
    assert reassigned_child.force_parent_routing is True


def test_unknown_moth_healthcheck_is_ignored(tmp_path: Path) -> None:
    registry = make_registry(tmp_path / "devices.db")
    monitor = HealthcheckMonitor(registry)

    monitor.record_healthcheck("id-from-previous-run", battery_percent=0)

    assert registry.list_devices() == []
