from __future__ import annotations

import json
import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType


MOTH_BRIDGE_ROOT = Path(__file__).resolve().parents[1]


def _load_device_stream_adapter():
    adapters_pkg = ModuleType("adapters")
    adapters_pkg.__path__ = [str(MOTH_BRIDGE_ROOT / "adapters")]
    sys.modules["adapters"] = adapters_pkg

    base_spec = importlib.util.spec_from_file_location(
        "adapters.base",
        MOTH_BRIDGE_ROOT / "adapters" / "base.py",
    )
    assert base_spec and base_spec.loader
    base_module = importlib.util.module_from_spec(base_spec)
    sys.modules["adapters.base"] = base_module
    base_spec.loader.exec_module(base_module)

    stream_spec = importlib.util.spec_from_file_location(
        "adapters.device_stream",
        MOTH_BRIDGE_ROOT / "adapters" / "device_stream.py",
    )
    assert stream_spec and stream_spec.loader
    stream_module = importlib.util.module_from_spec(stream_spec)
    sys.modules["adapters.device_stream"] = stream_module
    stream_spec.loader.exec_module(stream_module)
    return stream_module.DeviceStreamAdapter


DeviceStreamAdapter = _load_device_stream_adapter()


class DeviceStreamAdapterTests(unittest.TestCase):
    def test_parse_single_device_stream_message(self) -> None:
        payload = {
            "envelope": {
                "message_id": "msg-1",
                "schema_version": 1,
                "stream": "telemetry.position",
                "timestamp": "2026-04-22T00:00:00+00:00",
                "source": "simulator",
                "device_id": "auv-01",
                "device_type": "auv",
                "qos": "latest",
            },
            "payload": {
                "lat": 35.1,
                "lon": 129.1,
                "heading": 90,
            },
        }

        messages = DeviceStreamAdapter().parse_streams(
            json.dumps(payload).encode("utf-8"),
            "application/vnd.cowater.device-stream+json",
        )

        self.assertEqual(len(messages), 1)
        message = messages[0]
        self.assertEqual(message.stream, "telemetry.position")
        self.assertEqual(message.device_id, "auv-01")
        self.assertEqual(message.device_type, "auv")
        self.assertEqual(message.qos, "latest")
        self.assertEqual(message.payload["lat"], 35.1)

    def test_parse_batch_device_stream_messages(self) -> None:
        payload = [
            {
                "envelope": {
                    "stream": "telemetry.status",
                    "device_id": "auv-01",
                    "timestamp": "2026-04-22T00:00:00+00:00",
                },
                "payload": {"health": "nominal"},
            },
            {
                "envelope": {
                    "stream": "telemetry.network",
                    "device_id": "auv-01",
                    "timestamp": "2026-04-22T00:00:01+00:00",
                },
                "payload": {"connected": True},
            },
        ]

        messages = DeviceStreamAdapter().parse_streams(
            json.dumps(payload).encode("utf-8"),
            "application/json",
        )

        self.assertEqual([m.stream for m in messages], ["telemetry.status", "telemetry.network"])

    def test_missing_stream_or_device_id_is_skipped(self) -> None:
        payload = {
            "envelope": {
                "stream": "telemetry.status",
            },
            "payload": {"health": "nominal"},
        }

        with self.assertLogs("adapters.device_stream", level="WARNING"):
            messages = DeviceStreamAdapter().parse_streams(
                json.dumps(payload).encode("utf-8"),
                "application/vnd.cowater.device-stream+json",
            )

        self.assertEqual(messages, [])


if __name__ == "__main__":
    unittest.main()
