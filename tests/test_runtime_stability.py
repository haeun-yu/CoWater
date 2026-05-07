from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_device_llm_requires_ollama(monkeypatch) -> None:
    llm_client = load_module(
        "device_llm_client_for_test",
        ROOT / "device" / "agent" / "llm_client.py",
    )

    with patch.object(llm_client.urllib.request, "urlopen", side_effect=OSError("connection refused")):
        with pytest.raises(RuntimeError, match="Ollama is not available"):
            llm_client.make_llm_client({"provider": "ollama", "endpoint": "http://localhost:11434", "model": "test"})


def test_system_llm_requires_ollama(monkeypatch) -> None:
    llm_client = load_module(
        "system_llm_client_for_test",
        ROOT / "server" / "system-agent" / "agent" / "llm_client.py",
    )

    with patch.object(llm_client.urllib.request, "urlopen", side_effect=OSError("connection refused")):
        with pytest.raises(RuntimeError, match="Ollama is not available"):
            llm_client.make_llm_client({"provider": "ollama", "endpoint": "http://localhost:11434", "model": "test"})


def test_moth_publisher_can_be_disabled_by_environment(monkeypatch) -> None:
    monkeypatch.setenv("COWATER_MOTH_ENABLED", "false")
    moth_publisher = load_module(
        "moth_publisher_for_test",
        ROOT / "device" / "transport" / "moth_publisher.py",
    )

    publisher = moth_publisher.MothPublisher(
        {"moth": {"enabled": True, "server_url": "wss://cobot.center:8287"}},
        state=object(),
    )

    assert publisher.enabled is False


def test_system_fleet_summary_accepts_registry_public_ids(monkeypatch) -> None:
    import sys

    for name in list(sys.modules):
        if name == "agent" or name.startswith("agent."):
            sys.modules.pop(name, None)
    monkeypatch.syspath_prepend(str(ROOT / "server" / "system-agent"))
    from agent.decision import DecisionEngine
    from skills.catalog import SkillCatalog

    class DummyResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    with patch("urllib.request.urlopen", return_value=DummyResponse()):
        engine = DecisionEngine(
            {"llm": {"provider": "ollama", "endpoint": "http://localhost:11434", "model": "test"}},
            SkillCatalog({"actions": ["mission.plan"]}),
        )

    summary = engine._fleet_summary(
        [
            {
                "id": "id-middle-public",
                "registry_id": 2,
                "name": "통제 함정",
                "device_type": "CONTROL_SHIP",
                "layer": "middle",
                "connected": True,
            },
            {
                "id": "id-lower-public",
                "registry_id": 5,
                "name": "작업용 ROV",
                "device_type": "ROV",
                "layer": "lower",
                "connected": True,
                "parent_id": 2,
            },
        ]
    )

    assert "통제 함정" in summary
    assert "작업용 ROV" in summary
