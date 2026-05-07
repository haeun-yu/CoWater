"""Route Planner Tool - generates navigation routes"""

from typing import Any, Optional
from math import sqrt


class RoutePlanner:
    """Plans navigation routes from current position to target"""

    def __init__(self) -> None:
        self.waypoints: list[tuple[float, float]] = []
        self.current_waypoint_index: int = 0

    def plan_route(self, start_lat: float, start_lon: float, end_lat: float, end_lon: float, step_size_meters: float = 100.0) -> list[tuple[float, float]]:
        """Plan route with waypoints - simple linear interpolation"""
        distance = sqrt((end_lat - start_lat) ** 2 + (end_lon - start_lon) ** 2) * 111000
        num_waypoints = max(2, int(distance / step_size_meters))

        self.waypoints = []
        for i in range(num_waypoints):
            t = i / (num_waypoints - 1) if num_waypoints > 1 else 0
            lat = start_lat + (end_lat - start_lat) * t
            lon = start_lon + (end_lon - start_lon) * t
            self.waypoints.append((lat, lon))

        self.current_waypoint_index = 0
        return self.waypoints

    def get_next_waypoint(self) -> Optional[tuple[float, float]]:
        """Get next waypoint"""
        if self.current_waypoint_index < len(self.waypoints):
            waypoint = self.waypoints[self.current_waypoint_index]
            self.current_waypoint_index += 1
            return waypoint
        return None

    def get_current_route(self) -> dict[str, Any]:
        """Get current route info"""
        return {
            "total_waypoints": len(self.waypoints),
            "current_index": self.current_waypoint_index,
            "progress_percent": (self.current_waypoint_index / len(self.waypoints) * 100) if self.waypoints else 0,
            "remaining_waypoints": max(0, len(self.waypoints) - self.current_waypoint_index),
        }
