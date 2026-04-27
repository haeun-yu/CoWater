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
    }


APP_SETTINGS = load_runtime_config(CONFIG_PATH)

