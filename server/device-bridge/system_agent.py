from __future__ import annotations
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
# shared/ must come before the local agent dir to resolve base_runtime etc.
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent / "shared"))

from role.runtime import DeviceBridgeRuntime
from application.bootstrap import build_agent_runtime
from controller.api import run

ROLE_PROFILE = {
    "server": {"port": 9110},
    "agent": {
        "id": "device-bridge-agent",
        "name": "DeviceBridge",
        "role": "device_bridge",
        "description": "CoWater System Agent: DeviceBridge",
    },
}

if __name__ == "__main__":
    import argparse, copy
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(Path(__file__).resolve().parent / "config.json"))
    args = parser.parse_args()
    runtime = build_agent_runtime(Path(args.config), overrides=copy.deepcopy(ROLE_PROFILE))
    run(Path(args.config), runtime, argv=[])
