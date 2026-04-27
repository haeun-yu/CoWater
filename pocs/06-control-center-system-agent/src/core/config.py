from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.json"
CONFIG_PATH = Path(os.getenv("COWATER_CONTROL_CENTER_CONFIG_PATH", str(DEFAULT_CONFIG_PATH)))
DEFAULT_SERVER_HOST = "127.0.0.1"
DEFAULT_SERVER_PORT = 9012
DEFAULT_AGENT_ID = "system_center-01"
DEFAULT_AGENT_ROLE = "system_center"
DEFAULT_PARENT_ID = ""
DEFAULT_PARENT_ENDPOINT = ""
DEFAULT_CORS_ORIGINS = ["*"]
DEFAULT_MISSION_PREFIX = "mission"
DEFAULT_A2A_BINDING = "HTTP+JSON"
DEFAULT_DEVICE_REGISTRY_URL = "http://127.0.0.1:8003"
DEFAULT_CONTROL_SHIP_ROLE = "regional_orchestrator"
DEFAULT_DIRECT_DEVICE_ROLES = ["usv", "auv", "rov"]
DEFAULT_AUTO_SYNC_ON_START = True
DEFAULT_SYNC_INTERVAL_SECONDS = 30
DEFAULT_AUTO_RESPONSE = True
DEFAULT_APPROVAL_REQUIRED_ACTIONS = ["mission.abort", "system.shutdown", "task.cancel"]
DEFAULT_LLM_PROVIDER = "ollama"
DEFAULT_LLM_MODEL = "gemma4"
DEFAULT_LLM_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_LLM_TEMPERATURE = 0.2
DEFAULT_ALWAYS_ALERT = True
DEFAULT_NOTIFICATION_RETAIN = 100
DEFAULT_NOTIFICATION_STORE_URL = "http://127.0.0.1:8003"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_runtime_config(config_path: Path) -> dict[str, Any]:
    raw = _load_json_file(config_path)
    server_cfg = raw.get("server") or {}
    agent_cfg = raw.get("agent") or {}
    registry_cfg = raw.get("registry") or {}
    analysis_cfg = raw.get("analysis") or {}
    llm_cfg = analysis_cfg.get("llm") or {}
    notifications_cfg = raw.get("notifications") or {}
    cors_cfg = raw.get("cors") or {}

    host = str(server_cfg.get("host") or DEFAULT_SERVER_HOST)
    port = int(server_cfg.get("port") or DEFAULT_SERVER_PORT)
    cors_origins = cors_cfg.get("allow_origins") or DEFAULT_CORS_ORIGINS
    if isinstance(cors_origins, str):
        cors_origins = [origin.strip() for origin in cors_origins.split(",") if origin.strip()]
    if not isinstance(cors_origins, list) or not cors_origins:
        cors_origins = list(DEFAULT_CORS_ORIGINS)

    return {
        "config_path": str(config_path),
        "server": {"host": host, "port": port},
        "cors": {"allow_origins": cors_origins},
        "agent": {
            "id": str(agent_cfg.get("id") or DEFAULT_AGENT_ID),
            "role": str(agent_cfg.get("role") or DEFAULT_AGENT_ROLE),
            "parent_id": str(agent_cfg.get("parent_id") or DEFAULT_PARENT_ID),
            "parent_endpoint": str(agent_cfg.get("parent_endpoint") or DEFAULT_PARENT_ENDPOINT).rstrip("/"),
            "direct_route_allowed": bool(agent_cfg.get("direct_route_allowed", True)),
            "mission_prefix": str(agent_cfg.get("mission_prefix") or DEFAULT_MISSION_PREFIX),
        },
        "registry": {
            "device_registry_url": str(registry_cfg.get("device_registry_url") or DEFAULT_DEVICE_REGISTRY_URL).rstrip("/"),
            "control_ship_role": str(registry_cfg.get("control_ship_role") or DEFAULT_CONTROL_SHIP_ROLE),
            "direct_device_roles": list(registry_cfg.get("direct_device_roles") or DEFAULT_DIRECT_DEVICE_ROLES),
            "auto_sync_on_start": bool(registry_cfg.get("auto_sync_on_start", DEFAULT_AUTO_SYNC_ON_START)),
            "sync_interval_seconds": int(registry_cfg.get("sync_interval_seconds") or DEFAULT_SYNC_INTERVAL_SECONDS),
        },
        "analysis": {
            "auto_response": bool(analysis_cfg.get("auto_response", DEFAULT_AUTO_RESPONSE)),
            "approval_required_actions": list(
                analysis_cfg.get("approval_required_actions") or DEFAULT_APPROVAL_REQUIRED_ACTIONS
            ),
            "llm": {
                "provider": str(llm_cfg.get("provider") or DEFAULT_LLM_PROVIDER).strip(),
                "model": str(llm_cfg.get("model") or DEFAULT_LLM_MODEL).strip(),
                "base_url": str(llm_cfg.get("base_url") or DEFAULT_LLM_BASE_URL).rstrip("/"),
                "temperature": float(llm_cfg.get("temperature") or DEFAULT_LLM_TEMPERATURE),
            },
        },
        "notifications": {
            "retain": int(notifications_cfg.get("retain") or DEFAULT_NOTIFICATION_RETAIN),
            "always_alert": bool(notifications_cfg.get("always_alert", DEFAULT_ALWAYS_ALERT)),
            "notification_store_url": str(
                notifications_cfg.get("notification_store_url") or DEFAULT_NOTIFICATION_STORE_URL
            ).rstrip("/"),
        },
    }
