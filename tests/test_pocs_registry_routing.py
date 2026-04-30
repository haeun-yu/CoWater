from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_ROOT = ROOT / "pocs/00-device-registration-server"
sys.path.insert(0, str(REGISTRY_ROOT))

from src.core.models import DeviceAgentRegistrationRequest, DeviceRegistrationRequest  # noqa: E402
from src.registry.device_registry import DeviceRegistry  # noqa: E402


def make_registry(tmpdir: str) -> DeviceRegistry:
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
        db_path=Path(tmpdir) / "devices.db",
    )


def request(
    *,
    name: str,
    device_type: str,
    layer: str,
    lat: float = 37.0,
    lon: float = 129.0,
    alt: float = 0.0,
    tracks: list[dict] | None = None,
) -> DeviceRegistrationRequest:
    return DeviceRegistrationRequest(
        secretKey="server-secret",
        name=name,
        device_type=device_type,
        layer=layer,
        connectivity="wired" if device_type == "ROV" else "wireless",
        location={"latitude": lat, "longitude": lon, "altitude": alt},
        tracks=tracks if tracks is not None else [{"type": "GPS", "name": "gps"}],
        actions={"custom": ["hold_position"]},
    )


class RegistryRoutingTest(unittest.TestCase):
    def test_track_endpoints_are_device_and_track_specific(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry = make_registry(tmp)
            device = registry.register(
                request(
                    name="rov",
                    device_type="ROV",
                    layer="lower",
                    tracks=[
                        {"type": "VIDEO", "name": "main_camera"},
                        {"type": "PRESSURE", "name": "depth"},
                    ],
                )
            )

        endpoints = [track.endpoint for track in device.tracks]
        self.assertEqual(len(set(endpoints)), 2)
        self.assertIn("name=device-1", endpoints[0])
        self.assertIn("track=main_camera", endpoints[0])

    def test_auv_routes_via_parent_only_when_submerged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry = make_registry(tmp)
            middle = registry.register(request(name="control-ship", device_type="CONTROL_SHIP", layer="middle"))
            auv = registry.register(request(name="auv", device_type="AUV", layer="lower", alt=-20.0))

            submerged_assignment = registry.assignment_for(auv.id)
            registry.update_auv_submersion(auv.id, False)
            surfaced_assignment = registry.assignment_for(auv.id)

        self.assertEqual(submerged_assignment["parent_id"], middle.id)
        self.assertEqual(submerged_assignment["route_mode"], "via_parent")
        self.assertIsNone(surfaced_assignment["parent_id"])
        self.assertEqual(surfaced_assignment["route_mode"], "direct_to_system")

    def test_rov_requires_middle_parent_and_disconnected_attach_does_not_set_connected_at(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry = make_registry(tmp)
            middle = registry.register(request(name="control-ship", device_type="CONTROL_SHIP", layer="middle"))
            rov = registry.register(request(name="rov", device_type="ROV", layer="lower", alt=-40.0))

            assignment = registry.assignment_for(rov.id)
            registry.attach_agent(
                rov.id,
                DeviceAgentRegistrationRequest(secretKey="server-secret", connected=False),
            )
            updated = registry.get_device(rov.id)

        self.assertEqual(assignment["parent_id"], middle.id)
        self.assertTrue(assignment["force_parent_routing"])
        self.assertEqual(assignment["route_mode"], "via_parent")
        self.assertIsNone(updated.agent.connected_at)

    def test_heartbeat_topic_is_shared_across_devices(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry = make_registry(tmp)
            usv = registry.register(request(name="usv", device_type="USV", layer="lower"))
            system = registry.register(request(name="system", device_type="SYSTEM", layer="system", tracks=[]))

        self.assertEqual(usv.heartbeat_topic, "device.heartbeat")
        self.assertEqual(system.heartbeat_topic, "device.heartbeat")


if __name__ == "__main__":
    unittest.main()
