"""Child Registry Tool - manages child agents"""

from typing import Any


class ChildRegistry:
    """Registry of child agents"""

    def __init__(self) -> None:
        self.children: dict[int, dict[str, Any]] = {}

    def register_child(self, device_id: int, name: str, device_type: str, endpoint: str) -> bool:
        """Register a child agent"""
        self.children[device_id] = {
            "id": device_id,
            "name": name,
            "device_type": device_type,
            "endpoint": endpoint,
            "status": "online",
            "last_seen": None,
        }
        return True

    def list_children(self) -> list[dict[str, Any]]:
        """List all children"""
        return list(self.children.values())

    def get_child_health(self, device_id: int) -> dict[str, Any]:
        """Get child health status"""
        if device_id in self.children:
            return {
                "device_id": device_id,
                "battery_percent": 75.0,
                "signal_strength": 0.8,
                "last_message_age_seconds": 2,
            }
        return {}

    def remove_child(self, device_id: int) -> bool:
        """Remove child from registry"""
        if device_id in self.children:
            del self.children[device_id]
            return True
        return False
