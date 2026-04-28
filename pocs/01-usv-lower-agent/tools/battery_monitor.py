"""Battery Monitor Tool - monitors battery status"""

from typing import Any


class BatteryMonitor:
    """Monitors battery status"""

    def __init__(self, initial_percent: float = 100.0) -> None:
        self.percent: float = initial_percent
        self.voltage: float = 12.0  # Volts
        self.current: float = 0.0  # Amps
        self.temperature: float = 25.0  # Celsius
        self.estimated_remaining_minutes: int = 180

    def read(self) -> dict[str, Any]:
        """Read battery status"""
        return {
            "percent": self.percent,
            "voltage": self.voltage,
            "current": self.current,
            "temperature": self.temperature,
            "estimated_remaining_minutes": self.estimated_remaining_minutes,
            "health": self._assess_health(),
        }

    def discharge(self, rate: float = 0.5) -> None:
        """Simulate battery discharge (0-1% per read)"""
        self.percent = max(0, self.percent - rate)
        self.voltage = 12.0 * (self.percent / 100.0)
        if self.percent > 50:
            self.estimated_remaining_minutes = int(200 - (100 - self.percent) * 2)
        else:
            self.estimated_remaining_minutes = int(100 - (100 - self.percent))

    def _assess_health(self) -> str:
        """Assess battery health status"""
        if self.percent >= 80:
            return "excellent"
        elif self.percent >= 50:
            return "good"
        elif self.percent >= 30:
            return "warning"
        else:
            return "critical"
