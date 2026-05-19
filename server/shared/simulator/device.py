from __future__ import annotations

import random
from typing import Any

from agent.state import AgentState, utc_now


class DeviceSimulator:
    def __init__(self, simulation_config: dict[str, Any], tracks: list[dict[str, Any]]) -> None:
        self.config = simulation_config
        self.tracks = tracks
        self.position = dict(simulation_config.get("start_position") or {})
        self.motion = {
            "heading": random.uniform(0, 360),
            "speed": random.uniform(*simulation_config.get("speed_range", [0.2, 1.0])),
        }
        self.battery = random.uniform(65, 100)

    def interval_seconds(self) -> float:
        return float(self.config.get("interval_seconds") or 2)

    def next_telemetry(self, state: AgentState) -> dict[str, Any]:
        self._step_position(self.interval_seconds())
        telemetry = {
            "device_id": state.registry_id,
            "agent_id": state.agent_id,
            "device_type": state.device_type,
            "timestamp": utc_now(),
            "position": self.position,
            "motion": self.motion,
            "battery_percent": round(self.battery, 2),
            "sensors": self._sensor_values(),
        }
        self.battery = max(0, self.battery - random.uniform(0.01, 0.08))
        return telemetry

    def _step_position(self, interval: float) -> None:
        if not self.position:
            return
        speed_min, speed_max = self.config.get("speed_range", [0.2, 1.0])
        self.motion["speed"] = max(float(speed_min), min(float(speed_max), self.motion["speed"] + random.uniform(-0.1, 0.1)))
        self.motion["heading"] = (self.motion["heading"] + random.uniform(-8, 8)) % 360
        meters = self.motion["speed"] * interval
        self.position["latitude"] = float(self.position["latitude"]) + random.uniform(-1, 1) * meters / 111000
        self.position["longitude"] = float(self.position["longitude"]) + random.uniform(-1, 1) * meters / 111000
        altitude_range = self.config.get("altitude_range")
        if altitude_range:
            self.position["altitude"] = max(
                float(altitude_range[0]),
                min(float(altitude_range[1]), float(self.position.get("altitude", 0)) + random.uniform(-0.3, 0.3)),
            )

    def _sensor_values(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for track in self.tracks:
            name = track.get("name")
            if not name:
                continue
            if name == "battery":
                values[name] = {"percent": round(self.battery, 2)}
            elif name == "pressure":
                values[name] = {"depth_m": abs(float(self.position.get("altitude", 0)))}
            elif name == "temperature":
                values[name] = {"celsius": round(random.uniform(2, 18), 2)}
            elif name == "camera":
                values[name] = {"status": "streaming", "light_lux": random.randint(80, 900)}
            else:
                values[name] = {"status": "ok"}
        return values

