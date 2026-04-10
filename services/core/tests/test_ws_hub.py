from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path


fastapi_module = types.ModuleType("fastapi")


class _WebSocket:
    async def accept(self) -> None: ...

    async def send_text(self, message: str) -> None: ...


fastapi_module.WebSocket = _WebSocket
sys.modules.setdefault("fastapi", fastapi_module)

WS_HUB_PATH = Path(__file__).resolve().parents[1] / "ws_hub.py"
spec = importlib.util.spec_from_file_location("test_ws_hub_module", WS_HUB_PATH)
assert spec is not None and spec.loader is not None
ws_hub_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ws_hub_module)

WebSocketHub = ws_hub_module.WebSocketHub


class _FakeWebSocket:
    def __init__(self, *, fail_on_send: bool = False) -> None:
        self.accepted = False
        self.messages: list[str] = []
        self.fail_on_send = fail_on_send

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, message: str) -> None:
        if self.fail_on_send:
            raise RuntimeError("socket closed")
        self.messages.append(message)


class WebSocketHubTests(unittest.IsolatedAsyncioTestCase):
    async def test_broadcast_removes_dead_connections_and_tracks_failures(self) -> None:
        hub = WebSocketHub()
        alive = _FakeWebSocket()
        dead = _FakeWebSocket(fail_on_send=True)

        await hub.connect(alive, "alerts")
        await hub.connect(dead, "alerts")
        await hub.broadcast("alerts", {"type": "alert_created", "message": "hello"})

        self.assertEqual(hub.connection_count("alerts"), 1)
        self.assertEqual(len(alive.messages), 1)
        stats = hub.stats()["alerts"]
        self.assertEqual(stats["broadcast_success"], 1)
        self.assertEqual(stats["broadcast_failure"], 1)


if __name__ == "__main__":
    unittest.main()
