from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent))

from application.bootstrap import build_agent_runtime
from controller.api import run


ROLE_PROFILES = {
    "request_handler": {
        "server": {"port": 9116},
        "agent": {
            "id": "request-handler-agent",
            "name": "RequestHandler",
            "role": "request_handler",
            "description": "Classifies user intent and routes work to specialized System Agents.",
        },
    },
    "device_bridge": {
        "server": {"port": 9110},
        "agent": {
            "id": "device-bridge-agent",
            "name": "DeviceBridge",
            "role": "device_bridge",
            "description": "Bridges Device Agent A2A task assignment and task result collection.",
        },
    },
    "mission_planner": {
        "server": {"port": 9111},
        "agent": {
            "id": "mission-planner-agent",
            "name": "MissionPlanner",
            "role": "mission_planner",
            "description": "Creates Proposals, Missions, and Tasks from classified intent.",
        },
    },
    "policy_manager": {
        "server": {"port": 9112},
        "agent": {
            "id": "policy-manager-agent",
            "name": "PolicyManager",
            "role": "policy_manager",
            "description": "Evaluates policies and triggers approved automatic responses.",
        },
    },
    "system_sentinel": {
        "server": {"port": 9113},
        "agent": {
            "id": "system-sentinel-agent",
            "name": "SystemSentinel",
            "role": "system_sentinel",
            "description": "Monitors system health, device state, and AgentConnection state.",
        },
    },
    "insight_reporter": {
        "server": {"port": 9114},
        "agent": {
            "id": "insight-reporter-agent",
            "name": "InsightReporter",
            "role": "insight_reporter",
            "description": "Generates insight and reporting responses from Registry state.",
        },
    },
}


def _load_overrides(path: Path | None) -> dict:
    if path is None:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _merge(target: dict, updates: dict) -> dict:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge(target[key], value)
        else:
            target[key] = value
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a CoWater System Agent role process.")
    parser.add_argument("--config", default=str(Path(__file__).resolve().parent / "config.json"))
    parser.add_argument("--role", choices=sorted(ROLE_PROFILES), default=os.getenv("COWATER_SYSTEM_AGENT_ROLE", "request_handler"))
    parser.add_argument("--override", type=Path)
    args = parser.parse_args()

    overrides = copy.deepcopy(ROLE_PROFILES[args.role])
    _merge(overrides, _load_overrides(args.override))
    runtime = build_agent_runtime(Path(args.config), overrides=overrides)
    run(runtime.config_path, runtime, argv=[])
