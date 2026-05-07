from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _clear_device_module_cache() -> None:
    for name in list(sys.modules):
        if name == "agent" or name.startswith("agent."):
            sys.modules.pop(name, None)
        elif name == "controller" or name.startswith("controller."):
            sys.modules.pop(name, None)
        elif name == "skills" or name.startswith("skills."):
            sys.modules.pop(name, None)
        elif name == "storage" or name.startswith("storage."):
            sys.modules.pop(name, None)
        elif name == "transport" or name.startswith("transport."):
            sys.modules.pop(name, None)
        elif name == "simulator" or name.startswith("simulator."):
            sys.modules.pop(name, None)
        elif name == "tools" or name.startswith("tools."):
            sys.modules.pop(name, None)


def test_device_platform_resolution() -> None:
    platforms = load_module(
        "device_platforms_for_test",
        ROOT / "device" / "infrastructure" / "platforms.py",
    )

    assert platforms.resolve_device_dir("CONTROL_SHIP") == "ship"
    assert platforms.resolve_device_platform("ROV").device_dir == "rov"


def test_platform_loader_discovers_mismatched_class_names(monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "device"))
    try:
        platforms = load_module(
            "device_platforms_loader_for_test",
            ROOT / "device" / "infrastructure" / "platforms.py",
        )

        rov_tools = platforms.resolve_device_platform("ROV").load_tools(ROOT / "device")
        ship_tools = platforms.resolve_device_platform("CONTROL_SHIP").load_tools(ROOT / "device")

        assert "camera_controller" in rov_tools
        assert "rov_tether_controller" in ship_tools
        assert "video_processor" in ship_tools
    finally:
        _clear_device_module_cache()


def test_runtime_child_state_roundtrip(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("COWATER_LLM_ENABLED", "false")
    monkeypatch.syspath_prepend(str(ROOT / "device"))
    try:
        runtime_mod = load_module(
            "device_runtime_for_test",
            ROOT / "device" / "agent" / "runtime.py",
        )

        config = json.loads((ROOT / "device" / "configs" / "usv-lower.json").read_text(encoding="utf-8"))
        config["registry"]["required"] = False
        config["moth"]["enabled"] = False
        config_path = tmp_path / "device-config.json"
        config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

        runtime = runtime_mod.AgentRuntime(config_path)
        child = runtime.register_child({"agent_id": "child-1", "name": "Child"})
        updated = runtime.relay_child_healthcheck({"agent_id": "child-1", "status": "ok"})

        assert child["agent_id"] == "child-1"
        assert updated["healthcheck"]["status"] == "ok"
        assert runtime.list_children()[0]["healthcheck"]["status"] == "ok"
    finally:
        _clear_device_module_cache()


def test_runtime_state_persists_across_restore(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("COWATER_LLM_ENABLED", "false")
    monkeypatch.setenv("COWATER_INSTANCE_ID", "persist-device")
    monkeypatch.syspath_prepend(str(ROOT / "device"))
    try:
        runtime_mod = load_module(
            "device_runtime_persist_for_test",
            ROOT / "device" / "agent" / "runtime.py",
        )
        storage_mod = load_module(
            "device_runtime_store_for_test",
            ROOT / "device" / "storage" / "runtime_store.py",
        )

        config = json.loads((ROOT / "device" / "configs" / "usv-lower.json").read_text(encoding="utf-8"))
        config["registry"]["required"] = False
        config["moth"]["enabled"] = False
        config_path = tmp_path / "device-config.json"
        config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

        runtime = runtime_mod.AgentRuntime(config_path)
        runtime.runtime_store = storage_mod.RuntimeStore(tmp_path / "runtime.json")
        runtime.register_child({"agent_id": "child-1", "name": "Child"})
        runtime.state.mission_state = {"mode": "route_move", "status": "navigating", "target_position": {"latitude": 37.1, "longitude": 129.1}}
        runtime.simulator.mission_state = dict(runtime.state.mission_state)
        runtime.simulator.position = {"latitude": 37.0, "longitude": 129.0}
        runtime._persist_runtime_state()

        restored = runtime_mod.AgentRuntime(config_path)
        restored.runtime_store = storage_mod.RuntimeStore(tmp_path / "runtime.json")
        restored._restore_runtime_snapshot(restored.runtime_store.load_snapshot("persist-device"))

        assert restored.list_children()[0]["agent_id"] == "child-1"
        assert restored.state.mission_state["mode"] == "route_move"
        assert restored.simulator.mission_state["mode"] == "route_move"
        assert restored.simulator.position["latitude"] == 37.0
    finally:
        _clear_device_module_cache()


def test_rov_video_command_updates_simulated_state(monkeypatch) -> None:
    monkeypatch.setenv("COWATER_LLM_ENABLED", "false")
    monkeypatch.syspath_prepend(str(ROOT / "device"))
    from agent.state import AgentState
    try:
        platforms = load_module(
            "device_platforms_for_rov_test",
            ROOT / "device" / "infrastructure" / "platforms.py",
        )
        simulator_mod = load_module(
            "device_rov_simulator_for_test",
            ROOT / "device" / "simulator" / "rov.py",
        )

        sim = simulator_mod.DeviceSimulator(
            {"interval_seconds": 1, "start_position": {"latitude": 37.0, "longitude": 129.0, "altitude": 8.0}},
            [],
        )
        state = AgentState(
            agent_id="rov-agent",
            role="device_agent",
            layer="lower",
            instance_id="instance-1",
            name="ROV",
            device_type="ROV",
        )
        tools = platforms.resolve_device_platform("ROV").load_tools(ROOT / "device")

        result = sim.apply_command(
            state,
            {
                "action": "record_video",
                "params": {"recording": True, "brightness": 80},
            },
            tools,
        )

        assert result["status"] == "completed"
        assert result["mission_state"]["mode"] == "recording"
        assert tools["camera_controller"].get_status()["recording"] is True
    finally:
        _clear_device_module_cache()


def test_ship_capture_video_uses_video_processor(monkeypatch) -> None:
    monkeypatch.setenv("COWATER_LLM_ENABLED", "false")
    monkeypatch.syspath_prepend(str(ROOT / "device"))
    from agent.state import AgentState

    try:
        platforms = load_module(
            "device_platforms_for_ship_test",
            ROOT / "device" / "infrastructure" / "platforms.py",
        )
        simulator_mod = load_module(
            "device_ship_simulator_for_test",
            ROOT / "device" / "simulator" / "ship.py",
        )

        sim = simulator_mod.DeviceSimulator(
            {"interval_seconds": 1, "start_position": {"latitude": 37.0, "longitude": 129.0}},
            [],
        )
        state = AgentState(
            agent_id="ship-agent",
            role="device_agent",
            layer="middle",
            instance_id="instance-ship",
            name="Ship",
            device_type="CONTROL_SHIP",
        )
        tools = platforms.resolve_device_platform("CONTROL_SHIP").load_tools(ROOT / "device")

        result = sim.apply_command(
            state,
            {
                "action": "capture_video",
                "params": {"recording": True},
            },
            tools,
        )

        assert result["status"] == "completed"
        assert result["artifacts"][0]["captured"] is True
        assert tools["video_processor"].get_status()["recording"] is True
    finally:
        _clear_device_module_cache()


def test_route_move_advances_through_waypoints(monkeypatch) -> None:
    monkeypatch.setenv("COWATER_LLM_ENABLED", "false")
    monkeypatch.syspath_prepend(str(ROOT / "device"))
    from agent.state import AgentState

    try:
        platforms = load_module(
            "device_platforms_for_route_test",
            ROOT / "device" / "infrastructure" / "platforms.py",
        )
        simulator_mod = load_module(
            "device_usv_simulator_for_test",
            ROOT / "device" / "simulator" / "usv.py",
        )

        sim = simulator_mod.DeviceSimulator(
            {"interval_seconds": 1, "start_position": {"latitude": 37.0, "longitude": 129.0}},
            [],
        )
        state = AgentState(
            agent_id="usv-agent",
            role="device_agent",
            layer="lower",
            instance_id="instance-usv",
            name="USV",
            device_type="USV",
        )
        tools = platforms.resolve_device_platform("USV").load_tools(ROOT / "device")

        result = sim.apply_command(
            state,
            {
                "action": "route_move",
                "params": {
                    "target_lat": 37.00002,
                    "target_lon": 129.00002,
                    "speed_mps": 10.0,
                    "step_size_meters": 2.0,
                },
            },
            tools,
        )

        assert result["mission_state"]["route"]["waypoints"]
        assert result["mission_state"]["route"]["current_index"] == 0

        for _ in range(4):
            telemetry = sim.next_telemetry(state)

        assert telemetry["mission"]["route"]["current_index"] >= 1
        assert sim.mission_state["route"]["current_index"] >= 1
    finally:
        _clear_device_module_cache()


def test_report_task_result_uses_actual_status(monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "device"))
    try:
        message_router = load_module(
            "device_message_router_for_test",
            ROOT / "device" / "agent" / "message_router.py",
        )

        runtime = SimpleNamespace(
            state=SimpleNamespace(agent_id="agent-1", registry_id="device-1"),
            config={"system_agent": {"url": "http://127.0.0.1:9116"}},
        )
        captured: dict[str, object] = {}

        class DummyResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b"{}"

        def fake_urlopen(request, timeout=0):
            captured["body"] = request.data
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            return DummyResponse()

        with patch("urllib.request.urlopen", fake_urlopen):
            import asyncio

            asyncio.run(
                message_router._report_task_result_to_system_agent(
                    runtime=runtime,
                    task_id="task-1",
                    command={"action": "hold_position"},
                    execution_result={"status": "success", "summary": "done"},
                    execution_status="completed",
                    system_agent_url="http://127.0.0.1:9116/message:send",
                )
            )

        payload = json.loads(captured["body"].decode("utf-8"))
        assert captured["url"].endswith("/message:send")
        assert payload["message"]["parts"][0]["data"]["status"] == "completed"
    finally:
        _clear_device_module_cache()


def test_command_controller_is_pure_executor(monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "device"))

    try:
        commands_mod = load_module(
            "device_commands_for_test",
            ROOT / "device" / "controller" / "commands.py",
        )

        class DummyExecutor:
            def execute(self, command):
                return {"delivered": True, "command": command}

        controller = commands_mod.CommandController(DummyExecutor())
        result = controller.execute({"action": "hold_position", "reason": "test"})

        assert result["status"] == "success"
        assert result["action"] == "hold_position"
        assert "result" in result
    finally:
        _clear_device_module_cache()


def test_telemetry_reader_normalizes_common_shapes(monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "device"))

    try:
        telemetry_mod = load_module(
            "device_telemetry_reader_for_test",
            ROOT / "device" / "tools" / "common" / "telemetry_reader.py",
        )

        reader = telemetry_mod.TelemetryReader()
        normalized = reader.normalize(
            {
                "battery_percent": 82.5,
                "position": {"latitude": 37.1, "longitude": 129.2},
                "motion": {"heading": 12.0, "speed": 1.4},
                "mission": ["unexpected"],
            }
        )

        assert normalized["battery"]["charge_percent"] == 82.5
        assert normalized["position"]["latitude"] == 37.1
        assert normalized["motion"]["roll"] == 0.0
        assert normalized["mission"] == {}
    finally:
        _clear_device_module_cache()
