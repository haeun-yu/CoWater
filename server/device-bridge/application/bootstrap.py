from __future__ import annotations
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_AGENT_ROOT = _HERE.parent  # e.g. server/request-handler/
_SHARED = _AGENT_ROOT.parent / "shared"

# shared/ first (base_runtime, state, etc.), then agent root (local agent/runtime.py)
for p in [str(_SHARED), str(_AGENT_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from role.runtime import DeviceBridgeRuntime


def build_agent_runtime(config_path: Path | str, overrides: dict | None = None) -> DeviceBridgeRuntime:
    return DeviceBridgeRuntime(Path(config_path), overrides=overrides)
