"""Acoustic Relay Tool - relays underwater communication"""

from typing import Any, Optional


class AcousticRelay:
    """Relays acoustic messages from underwater devices"""

    def __init__(self) -> None:
        self.relay_queue: list[dict[str, Any]] = []

    def relay_message(self, source_id: int, message: str) -> bool:
        """Relay message from child device"""
        self.relay_queue.append({
            "source_id": source_id,
            "message": message,
            "timestamp": None,
        })
        return True

    def get_relayed_messages(self) -> list[dict[str, Any]]:
        """Get queued messages"""
        messages = self.relay_queue.copy()
        self.relay_queue.clear()
        return messages

    def relay_telemetry(self, child_id: int, telemetry: dict[str, Any]) -> bool:
        """Relay child telemetry to surface"""
        return True
