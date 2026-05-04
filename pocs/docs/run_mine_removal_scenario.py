#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REGISTRY_ROOT = ROOT / "pocs" / "00-device-registration-server"
sys.path.insert(0, str(REGISTRY_ROOT))

from src.core.models import DeviceRegistrationRequest  # noqa: E402
from src.registry.device_registry import DeviceRegistry  # noqa: E402


def make_registry(db_dir: Path) -> DeviceRegistry:
    return DeviceRegistry(
        secret_key="server-secret",
        host="127.0.0.1",
        port=9100,
        ping_endpoint="/ping",
        agent_scheme="http",
        agent_host="127.0.0.1",
        agent_port=9000,
        agent_path_prefix="/agents",
        agent_command_scheme="http",
        agent_command_path_prefix="/agents",
        db_path=db_dir / "devices.db",
    )


def registration_request(
    *,
    name: str,
    device_type: str,
    layer: str,
    latitude: float,
    longitude: float,
    altitude: float,
    tracks: list[dict[str, Any]],
) -> DeviceRegistrationRequest:
    return DeviceRegistrationRequest(
        secretKey="server-secret",
        name=name,
        device_type=device_type,
        layer=layer,
        connectivity="wired" if device_type == "ROV" else "acoustic" if device_type == "AUV" else "wireless",
        location={"latitude": latitude, "longitude": longitude, "altitude": altitude},
        tracks=tracks,
        actions={"custom": ["deploy", "survey_depth", "scan_area", "remove_mine", "return_to_base"]},
    )


def run_scenario() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        registry = make_registry(Path(tmp))

        control_ship = registry.register(
            registration_request(
                name="CONTROL-SHIP-01",
                device_type="CONTROL_SHIP",
                layer="middle",
                latitude=37.005,
                longitude=129.418,
                altitude=3.0,
                tracks=[{"type": "GPS", "name": "gps"}, {"type": "TOPIC", "name": "wired_link"}],
            )
        )
        auv = registry.register(
            registration_request(
                name="AUV-01",
                device_type="AUV",
                layer="lower",
                latitude=37.002,
                longitude=129.428,
                altitude=-25.0,
                tracks=[{"type": "DEPTH", "name": "depth"}, {"type": "TOPIC", "name": "sonar"}],
            )
        )
        rov = registry.register(
            registration_request(
                name="ROV-01",
                device_type="ROV",
                layer="lower",
                latitude=37.003,
                longitude=129.430,
                altitude=-60.0,
                tracks=[{"type": "VIDEO", "name": "main_camera"}, {"type": "PRESSURE", "name": "depth"}],
            )
        )

        registry.update_auv_submersion(auv.id, True)
        registry.update_device_connectivity_state(rov.id, parent_id=control_ship.id, force_parent_routing=True)

        steps = [
            {"step": 1, "actor": "system_agent", "action": "assign_mission", "target": control_ship.name},
            {"step": 2, "actor": control_ship.name, "action": "deploy", "target": "AUV-01"},
            {"step": 3, "actor": "AUV-01", "action": "survey_depth", "target": "MINE-001"},
            {"step": 4, "actor": control_ship.name, "action": "deploy", "target": "ROV-01"},
            {"step": 5, "actor": "ROV-01", "action": "remove_mine", "target": "MINE-001"},
            {"step": 6, "actor": control_ship.name, "action": "return_to_base", "target": "AUV-01,ROV-01"},
        ]

        auv_assignment = registry.assignment_for(auv.id)
        rov_assignment = registry.assignment_for(rov.id)
        checks = {
            "auv_submerged_via_parent": auv.is_submerged and auv_assignment["route_mode"] == "via_parent",
            "rov_wired_force_parent": rov_assignment["force_parent_routing"] and rov_assignment["route_mode"] == "via_parent",
            "unique_track_endpoints": len({track.endpoint for track in auv.tracks + rov.tracks}) == len(auv.tracks + rov.tracks),
        }

        return {
            "scenario": "mine_removal",
            "mission_id": "MINE-REMOVAL-001",
            "mine_id": "MINE-001",
            "checks": checks,
            "passed": all(checks.values()),
            "assignments": {
                "AUV-01": auv_assignment,
                "ROV-01": rov_assignment,
            },
            "steps": steps,
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--format", choices=["json", "timeline"], default="timeline")
    args = parser.parse_args()
    result = run_scenario()
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print("MINE REMOVAL SCENARIO")
    print(f"mission_id={result['mission_id']} mine_id={result['mine_id']}")
    print(f"passed={str(result['passed']).lower()}")
    print("-" * 72)
    for step in result["steps"]:
        print(f"{step['step']:>2}. {step['actor']} -> {step['target']} : {step['action']}")
    print("-" * 72)
    for name, passed in result["checks"].items():
        print(f"{'OK' if passed else 'FAIL'} {name}")
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
