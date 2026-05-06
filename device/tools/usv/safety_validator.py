"""Safety Validator Tool - validates action safety"""

from typing import Any


class SafetyValidator:
    """Validates if actions are safe to execute"""

    def __init__(self) -> None:
        self.max_speed_mps: float = 2.5
        self.min_battery_percent: float = 10.0
        self.collision_distance_meters: float = 5.0

    def validate_action(self, action: str, params: dict[str, Any]) -> tuple[bool, str]:
        """Validate action safety"""
        if action == "route_move":
            speed = params.get("speed_mps", 1.0)
            if speed > self.max_speed_mps:
                return (False, f"Speed {speed} exceeds max {self.max_speed_mps}")
            return (True, "Safe to move")

        elif action == "emergency_stop":
            return (True, "Emergency stop always allowed")

        elif action == "hold_position":
            return (True, "Safe to hold")

        return (True, "Action allowed")

    def check_battery(self, battery_percent: float) -> bool:
        """Check if battery is safe"""
        return battery_percent >= self.min_battery_percent

    def check_collision(self, obstacle_distance: float) -> bool:
        """Check collision risk"""
        return obstacle_distance > self.collision_distance_meters
