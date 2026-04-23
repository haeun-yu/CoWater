from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.json"
DEFAULT_SERVER_HOST = "127.0.0.1"
DEFAULT_SERVER_PORT = 9010
DEFAULT_CORS_ORIGINS = ["*"]
DEFAULT_REGISTRY_URL = "http://localhost:8003"
DEFAULT_REGISTRY_SECRET_KEY = "server-secret"
CONFIG_PATH = Path(os.getenv("COWATER_AGENT_CONFIG_PATH", str(DEFAULT_CONFIG_PATH)))


DEFAULT_PROFILES: dict[str, dict[str, Any]] = {
    "usv": {
        "supported_modes": ["static", "dynamic"],
        "preferred_mode": "dynamic",
        "llm_optional": True,
        "device_side": [
            "surface_navigation",
            "position_update",
            "heading_update",
            "speed_update",
            "gps_report",
            "imu_report",
            "sonar_report",
            "magnetometer_report",
        ],
        "agent_side": [
            "patrol_route",
            "move_to_device",
            "follow_target",
            "return_to_base",
            "charge_at_tower",
            "hold_position",
            "route_move",
        ],
        "skills": [
            "route_planning",
            "target_tracking",
            "surface_navigation",
        ],
        "tools": [
            "planner",
            "executor",
            "validator",
        ],
        "constraints": [
            "stay_on_surface",
            "avoid_unplanned_high_speed",
        ],
        "rules": {
            "max_speed_mps": 2.5,
            "low_speed_mps": 0.2,
            "home_radius_deg": 0.01,
        },
    },
    "auv": {
        "supported_modes": ["static", "dynamic"],
        "preferred_mode": "dynamic",
        "llm_optional": True,
        "device_side": [
            "subsurface_navigation",
            "depth_update",
            "gps_report",
            "pressure_report",
            "side_scan_sonar_report",
            "temperature_report",
            "magnetometer_report",
        ],
        "agent_side": [
            "patrol_route",
            "move_to_device",
            "follow_target",
            "return_to_base",
            "charge_at_tower",
            "hold_depth",
            "surface",
        ],
        "skills": [
            "subsurface_navigation",
            "depth_holding",
            "sonar_patrol",
        ],
        "tools": [
            "planner",
            "executor",
            "validator",
        ],
        "constraints": [
            "respect_depth_limits",
            "prefer_surface_for_recovery",
        ],
        "rules": {
            "surface_altitude_m": -2.0,
            "deep_depth_m": 40.0,
        },
    },
    "rov": {
        "supported_modes": ["static", "dynamic"],
        "preferred_mode": "dynamic",
        "llm_optional": True,
        "device_side": [
            "deep_navigation",
            "depth_update",
            "pressure_report",
            "hd_camera_stream",
            "led_light_status",
            "profiling_sonar_report",
            "temperature_report",
            "magnetometer_report",
        ],
        "agent_side": [
            "patrol_route",
            "move_to_device",
            "follow_target",
            "return_to_base",
            "charge_at_tower",
            "light_on",
            "light_off",
            "camera_mode_switch",
            "sonar_scan_plan",
        ],
        "skills": [
            "inspection",
            "lighting_control",
            "camera_control",
        ],
        "tools": [
            "planner",
            "executor",
            "validator",
        ],
        "constraints": [
            "keep_clear_view_for_camera",
            "avoid_fast_motion_in_deep_water",
        ],
        "rules": {
            "low_light_lux": 250.0,
            "slow_speed_mps": 1.0,
        },
    },
}


def _load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_runtime_config(config_path: Path) -> dict[str, Any]:
    raw = _load_json_file(config_path)
    server_cfg = raw.get("server") or {}
    cors_cfg = raw.get("cors") or {}
    registry_cfg = raw.get("registry") or {}
    profiles_cfg = raw.get("profiles") or {}

    def pick(env_name: str, value: Any, default: Any) -> Any:
        env_value = os.getenv(env_name)
        if env_value is not None and env_value != "":
            return env_value
        if value is not None:
            return value
        return default

    host = str(pick("COWATER_AGENT_SERVER_HOST", server_cfg.get("host"), DEFAULT_SERVER_HOST))
    port = int(pick("COWATER_AGENT_SERVER_PORT", server_cfg.get("port"), DEFAULT_SERVER_PORT))
    cors_origins = pick(
        "COWATER_AGENT_CORS_ORIGINS",
        cors_cfg.get("allow_origins"),
        DEFAULT_CORS_ORIGINS,
    )
    if isinstance(cors_origins, str):
        cors_origins = [origin.strip() for origin in cors_origins.split(",") if origin.strip()]
    if not isinstance(cors_origins, list) or not cors_origins:
        cors_origins = list(DEFAULT_CORS_ORIGINS)

    registry_url = str(
        pick(
            "COWATER_AGENT_REGISTRY_URL",
            registry_cfg.get("url"),
            DEFAULT_REGISTRY_URL,
        )
    ).rstrip("/")
    registry_secret_key = str(
        pick(
            "COWATER_AGENT_REGISTRY_SECRET_KEY",
            registry_cfg.get("secret_key"),
            DEFAULT_REGISTRY_SECRET_KEY,
        )
    )

    profiles = json.loads(json.dumps(DEFAULT_PROFILES))
    for device_type, profile in profiles_cfg.items():
        if device_type in profiles and isinstance(profile, dict):
            profiles[device_type].update(profile)

    return {
        "config_path": str(config_path),
        "server": {
            "host": host,
            "port": port,
        },
        "cors": {
            "allow_origins": cors_origins,
        },
        "registry": {
            "url": registry_url,
            "secret_key": registry_secret_key,
        },
        "profiles": profiles,
    }
