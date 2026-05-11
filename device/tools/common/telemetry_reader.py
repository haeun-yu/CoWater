from __future__ import annotations

from typing import Any


class TelemetryReader:
    def normalize(self, telemetry: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(telemetry)
        position = normalized.get("position")
        if not isinstance(position, dict):
            position = {}
        normalized["position"] = {
            "latitude": position.get("latitude"),
            "longitude": position.get("longitude"),
            "altitude": position.get("altitude"),
        }

        motion = normalized.get("motion")
        if not isinstance(motion, dict):
            motion = {}
        normalized["motion"] = {
            "heading": motion.get("heading"),
            "speed": motion.get("speed"),
            "roll": motion.get("roll", 0.0),
            "pitch": motion.get("pitch", 0.0),
        }

        battery = normalized.get("battery")
        if not isinstance(battery, dict):
            battery = {}
        battery_percent = battery.get("charge_percent", normalized.get("battery_percent", 100.0))
        normalized["battery_percent"] = float(battery_percent or 0.0)
        normalized["battery"] = {
            "charge_percent": float(battery_percent or 0.0),
        }

        mission = normalized.get("mission")
        if not isinstance(mission, dict):
            mission = {}
        normalized["mission"] = dict(mission)

        sensors = normalized.get("sensors")
        if not isinstance(sensors, dict):
            sensors = {}
        normalized["sensors"] = dict(sensors)
        return normalized
