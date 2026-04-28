"""A2A Message Router - routes messages to children"""

from typing import Any, Optional


class A2ARouter:
    """Routes A2A messages to child agents"""

    def __init__(self) -> None:
        self.routing_table: dict[int, str] = {}

    def route_to_child(self, child_id: int, message: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Route message to child"""
        if child_id in self.routing_table:
            return {"status": "routed", "child_id": child_id}
        return None

    def update_route(self, child_id: int, endpoint: str) -> bool:
        """Update routing entry"""
        self.routing_table[child_id] = endpoint
        return True
