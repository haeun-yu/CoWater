from __future__ import annotations
import importlib
import importlib.util
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_AGENT_ROOT = _HERE.parent  # e.g. server/request-handler/
_SYSTEM_AGENT_ROOT = _AGENT_ROOT.parent / "system-agent"
_SHARED = _AGENT_ROOT.parent / "shared"

# system-agent runtime first for identical behavior, then shared helpers
# Load harness profile first to register agents
_HARNESS_DIR = _AGENT_ROOT / "harness"
for p in [str(_HARNESS_DIR), str(_AGENT_ROOT), str(_SHARED), str(_SYSTEM_AGENT_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Load harness profile to trigger @register_agent decorator
try:
    import profile as _harness_profile  # noqa: F401
except ImportError:
    pass

def _load_runtime_class():
    runtime_path = _SYSTEM_AGENT_ROOT / "agent" / "runtime.py"
    try:
        import pydantic  # noqa: F401
    except Exception:
        pydantic = None  # type: ignore[assignment]
    if pydantic is not None:
        try:
            spec = importlib.util.spec_from_file_location("cowater_system_agent_runtime_mission_planner", runtime_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                return module.AgentRuntime
        except Exception:
            pass
    original_path = list(sys.path)
    try:
        sys.path[:] = [str(_SHARED), str(_AGENT_ROOT), str(_SYSTEM_AGENT_ROOT)] + [
            p for p in sys.path if p not in {str(_SHARED), str(_AGENT_ROOT), str(_SYSTEM_AGENT_ROOT)}
        ]
        module = importlib.import_module("role.runtime")
        return module.MissionPlannerRuntime
    finally:
        sys.path[:] = original_path


def build_agent_runtime(config_path: Path | str, overrides: dict | None = None):
    runtime_class = _load_runtime_class()
    return runtime_class(Path(config_path), overrides=overrides)
