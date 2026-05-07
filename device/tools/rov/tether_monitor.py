"""Tether Monitoring Tool"""

from typing import Any


class TetherMonitor:
    """ROV tether status monitoring"""

    def __init__(self) -> None:
        self.length_meters: float = 0.0
        self.max_length_meters: float = 1000.0
        self.tension_newtons: float = 0.0
        self.breakpoint_newtons: float = 5000.0

    def read(self) -> dict[str, Any]:
        """Read tether status"""
        return {
            "length_meters": self.length_meters,
            "max_length_meters": self.max_length_meters,
            "tension_newtons": self.tension_newtons,
            "status": self._assess_status(),
        }

    def _assess_status(self) -> str:
        """Assess tether health"""
        if self.tension_newtons > self.breakpoint_newtons * 0.8:
            return "critical"
        elif self.tension_newtons > self.breakpoint_newtons * 0.5:
            return "warning"
        return "good"

    def set_length(self, length: float) -> bool:
        """Set tether deploy length"""
        self.length_meters = max(0, min(length, self.max_length_meters))
        return True
