"""Depth Sensor Tool - measures water depth"""

from typing import Any


class DepthSensor:
    """Measures water depth and pressure"""

    def __init__(self) -> None:
        self.depth_meters: float = 0.0
        self.pressure_bar: float = 1.0
        self.temperature: float = 20.0
        self.max_depth: float = 300.0

    def read(self) -> dict[str, Any]:
        """Read depth sensor"""
        return {
            "depth_meters": self.depth_meters,
            "pressure_bar": self.pressure_bar,
            "temperature": self.temperature,
            "status": "normal" if self.depth_meters < self.max_depth else "at_limit",
        }

    def set_depth(self, depth: float) -> None:
        """Update depth (simulation)"""
        self.depth_meters = max(0, min(depth, self.max_depth))
        self.pressure_bar = 1.0 + (self.depth_meters / 10.0)
        self.temperature = max(5, 25 - (self.depth_meters / 50.0))
