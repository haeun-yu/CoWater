from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.json"
DEFAULT_SERVER_HOST = "192.168.1.100"
DEFAULT_SERVER_PORT = 9001
DEFAULT_PING_ENDPOINT = "/pang/ping"
DEFAULT_SECRET_KEY = "server-secret"
DEFAULT_AGENT_SCHEME = "ws"
DEFAULT_AGENT_HOST = "127.0.0.1"
DEFAULT_AGENT_PORT = 9010
DEFAULT_AGENT_PATH_PREFIX = "/agents"
DEFAULT_AGENT_COMMAND_SCHEME = "http"
DEFAULT_AGENT_COMMAND_PATH_PREFIX = "/agents"
DEFAULT_CORS_ORIGINS = ["*"]

# ← NEW: Healthcheck & Re-binding
DEFAULT_HEALTHCHECK_INTERVAL_SECONDS = 1
DEFAULT_HEALTHCHECK_TIMEOUT_SECONDS = 20  # ← UPDATED: 3s → 20s (device-type default)
DEFAULT_HEALTHCHECK_TIMEOUT_BY_DEVICE_TYPE = {
    "usv": 20,      # Surface vehicle: 20 seconds
    "auv": 30,      # Underwater vehicle: 30 seconds (slow telemetry)
    "rov": 25,      # Tethered vehicle: 25 seconds (tether lag)
    "ship": 15,     # Surface ship: 15 seconds (fast comms)
}
DEFAULT_REBINDING_DISTANCE_DELTA_THRESHOLD_METERS = 500
DEFAULT_REBINDING_CHECK_INTERVAL_SECONDS = 1

# ← NEW: Moth (WebSocket for position updates)
DEFAULT_MOTH_SERVER_URL = "wss://cobot.center:8287/pang/ws/meb?channel=instant&name=agents&source=base&track=base"
DEFAULT_MOTH_HEALTHCHECK_TOPIC_TEMPLATE = "agents"
DEFAULT_MOTH_TELEMETRY_TOPIC_TEMPLATE = "device.telemetry.{device_id}.{track_type}"

CONFIG_PATH = Path(os.getenv("COWATER_DEVICE_CONFIG_PATH", str(DEFAULT_CONFIG_PATH)))


def _load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_runtime_config(config_path: Path) -> dict[str, Any]:
    raw = _load_json_file(config_path)
    server_cfg = raw.get("server") or {}
    agent_cfg = raw.get("agent") or {}
    device_cfg = raw.get("device") or {}
    cors_cfg = raw.get("cors") or {}
    healthcheck_cfg = raw.get("healthcheck") or {}
    rebinding_cfg = raw.get("rebinding") or {}
    moth_cfg = raw.get("moth") or {}

    def pick(env_name: str, value: Any, default: Any) -> Any:
        env_value = os.getenv(env_name)
        if env_value is not None and env_value != "":
            return env_value
        if value is not None:
            return value
        return default

    host = str(pick("COWATER_DEVICE_SERVER_HOST", server_cfg.get("host"), DEFAULT_SERVER_HOST))
    port = int(pick("COWATER_DEVICE_SERVER_PORT", server_cfg.get("port"), DEFAULT_SERVER_PORT))
    ping_endpoint = str(
        pick(
            "COWATER_DEVICE_PING_ENDPOINT",
            server_cfg.get("ping_endpoint"),
            DEFAULT_PING_ENDPOINT,
        )
    )
    agent_scheme = str(
        pick(
            "COWATER_DEVICE_AGENT_SCHEME",
            agent_cfg.get("scheme"),
            DEFAULT_AGENT_SCHEME,
        )
    )
    agent_host = str(
        pick(
            "COWATER_DEVICE_AGENT_HOST",
            agent_cfg.get("host"),
            DEFAULT_AGENT_HOST,
        )
    )
    agent_port = int(
        pick(
            "COWATER_DEVICE_AGENT_PORT",
            agent_cfg.get("port"),
            DEFAULT_AGENT_PORT,
        )
    )
    agent_path_prefix = str(
        pick(
            "COWATER_DEVICE_AGENT_PATH_PREFIX",
            agent_cfg.get("path_prefix"),
            DEFAULT_AGENT_PATH_PREFIX,
        )
    )
    agent_command_scheme = str(
        pick(
            "COWATER_DEVICE_AGENT_COMMAND_SCHEME",
            agent_cfg.get("command_scheme"),
            "http" if agent_scheme == "ws" else "https",
        )
    )
    agent_command_path_prefix = str(
        pick(
            "COWATER_DEVICE_AGENT_COMMAND_PATH_PREFIX",
            agent_cfg.get("command_path_prefix"),
            DEFAULT_AGENT_COMMAND_PATH_PREFIX,
        )
    )
    secret_key = str(
        pick(
            "COWATER_DEVICE_SECRET_KEY",
            device_cfg.get("secret_key"),
            DEFAULT_SECRET_KEY,
        )
    )
    cors_origins = pick(
        "COWATER_DEVICE_CORS_ORIGINS",
        cors_cfg.get("allow_origins"),
        DEFAULT_CORS_ORIGINS,
    )
    if isinstance(cors_origins, str):
        cors_origins = [origin.strip() for origin in cors_origins.split(",") if origin.strip()]
    if not isinstance(cors_origins, list) or not cors_origins:
        cors_origins = list(DEFAULT_CORS_ORIGINS)

    # ← NEW: Healthcheck
    healthcheck_interval = int(pick(
        "COWATER_HEALTHCHECK_INTERVAL_SECONDS",
        healthcheck_cfg.get("interval_seconds"),
        DEFAULT_HEALTHCHECK_INTERVAL_SECONDS,
    ))
    healthcheck_timeout = int(pick(
        "COWATER_HEALTHCHECK_TIMEOUT_SECONDS",
        healthcheck_cfg.get("timeout_seconds"),
        DEFAULT_HEALTHCHECK_TIMEOUT_SECONDS,
    ))
    # ← NEW: Device-type specific timeouts
    healthcheck_timeout_by_device_type = pick(
        "COWATER_HEALTHCHECK_TIMEOUT_BY_DEVICE_TYPE",
        healthcheck_cfg.get("timeout_by_device_type"),
        DEFAULT_HEALTHCHECK_TIMEOUT_BY_DEVICE_TYPE,
    )
    if isinstance(healthcheck_timeout_by_device_type, str):
        try:
            import json as json_module
            healthcheck_timeout_by_device_type = json_module.loads(healthcheck_timeout_by_device_type)
        except:
            healthcheck_timeout_by_device_type = DEFAULT_HEALTHCHECK_TIMEOUT_BY_DEVICE_TYPE
    if not isinstance(healthcheck_timeout_by_device_type, dict):
        healthcheck_timeout_by_device_type = DEFAULT_HEALTHCHECK_TIMEOUT_BY_DEVICE_TYPE

    # ← NEW: Re-binding
    rebinding_threshold = int(pick(
        "COWATER_REBINDING_DISTANCE_DELTA_THRESHOLD_METERS",
        rebinding_cfg.get("distance_delta_threshold_meters"),
        DEFAULT_REBINDING_DISTANCE_DELTA_THRESHOLD_METERS
    ))
    rebinding_check_interval = int(pick(
        "COWATER_REBINDING_CHECK_INTERVAL_SECONDS",
        rebinding_cfg.get("check_interval_seconds"),
        DEFAULT_REBINDING_CHECK_INTERVAL_SECONDS
    ))

    # ← NEW: Moth
    moth_url = str(pick(
        "COWATER_MOTH_SERVER_URL",
        moth_cfg.get("server_url"),
        DEFAULT_MOTH_SERVER_URL
    ))
    moth_healthcheck_topic = str(pick(
        "COWATER_MOTH_HEALTHCHECK_TOPIC_TEMPLATE",
        moth_cfg.get("healthcheck_topic_template"),
        DEFAULT_MOTH_HEALTHCHECK_TOPIC_TEMPLATE,
    ))
    moth_telemetry_topic = str(pick(
        "COWATER_MOTH_TELEMETRY_TOPIC_TEMPLATE",
        moth_cfg.get("telemetry_topic_template"),
        DEFAULT_MOTH_TELEMETRY_TOPIC_TEMPLATE
    ))

    return {
        "config_path": str(config_path),
        "secret_key": secret_key,
        "server": {
            "host": host,
            "port": port,
            "ping_endpoint": ping_endpoint,
        },
        "agent": {
            "scheme": agent_scheme,
            "host": agent_host,
            "port": agent_port,
            "path_prefix": agent_path_prefix,
            "command_scheme": agent_command_scheme,
            "command_path_prefix": agent_command_path_prefix,
        },
        "cors": {
            "allow_origins": cors_origins,
        },
        "healthcheck": {
            "interval_seconds": healthcheck_interval,
            "timeout_seconds": healthcheck_timeout,
            "timeout_by_device_type": healthcheck_timeout_by_device_type,
        },
        "rebinding": {
            "distance_delta_threshold_meters": rebinding_threshold,
            "check_interval_seconds": rebinding_check_interval,
        },
        "moth": {
            "server_url": moth_url,
            "healthcheck_topic_template": moth_healthcheck_topic,
            "telemetry_topic_template": moth_telemetry_topic,
        },
    }


APP_SETTINGS = load_runtime_config(CONFIG_PATH)
