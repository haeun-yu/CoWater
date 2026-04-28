from __future__ import annotations


class RoutePlanner:
    def hold_position(self, position: dict) -> dict:
        return {"route": [dict(position)] if position else []}

