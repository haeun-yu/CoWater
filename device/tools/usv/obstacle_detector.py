"""Obstacle Detector Tool - detects obstacles via sonar"""

from typing import Any


class ObstacleDetector:
    """Detects obstacles using sonar"""

    def __init__(self) -> None:
        self.max_range_meters: float = 50.0
        self.obstacles: list[dict[str, Any]] = []

    def detect(self) -> dict[str, Any]:
        """Scan for obstacles"""
        # Simulated obstacle detection
        return {
            "obstacles": self.obstacles,
            "safe": len(self.obstacles) == 0,
            "nearest_obstacle_distance": min([o["distance"] for o in self.obstacles], default=self.max_range_meters),
            "scan_count": 0,
        }

    def add_obstacle(self, distance: float, bearing: float) -> None:
        """Add detected obstacle"""
        self.obstacles.append({"distance": distance, "bearing": bearing})

    def clear(self) -> None:
        """Clear obstacle list"""
        self.obstacles = []
