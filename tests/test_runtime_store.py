from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_runtime_store_pop_uses_default_and_persists(tmp_path) -> None:
    runtime_store = load_module(
        "runtime_store_for_test",
        ROOT / "server" / "system-agent" / "storage" / "runtime_store.py",
    )

    store = runtime_store.RuntimeStore(tmp_path / "runtime.db")
    mapping = runtime_store.PersistentMapping(store, "children")

    assert mapping.pop("missing", None) is None

    mapping["child-1"] = {"agent_id": "child-1", "last_healthcheck_at": "now"}
    assert mapping.pop("child-1") == {"agent_id": "child-1", "last_healthcheck_at": "now"}
    store.close()


def test_runtime_log_snapshot_limit_returns_latest_entries(tmp_path) -> None:
    runtime_store = load_module(
        "runtime_store_for_test_logs",
        ROOT / "server" / "system-agent" / "storage" / "runtime_store.py",
    )

    store = runtime_store.RuntimeStore(tmp_path / "runtime.db")
    log = runtime_store.PersistentLog(store, "inbox", keep_last_n=100)

    log.append({"seq": 1})
    log.append({"seq": 2})
    log.append({"seq": 3})

    assert [item["seq"] for item in log.snapshot(limit=2)] == [2, 3]
    store.close()
