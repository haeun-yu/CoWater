"""Wired Link Monitor - monitors wired connection to ROV"""

from typing import Any


class WiredLinkMonitor:
    """Monitors wired link to ROV"""

    def __init__(self) -> None:
        self.connected: bool = False
        self.bandwidth_mbps: float = 100.0
        self.latency_ms: float = 5.0
        self.packet_loss_percent: float = 0.0

    def check_link_health(self) -> dict[str, Any]:
        """Check wired link health"""
        return {
            "connected": self.connected,
            "bandwidth_mbps": self.bandwidth_mbps,
            "latency_ms": self.latency_ms,
            "packet_loss_percent": self.packet_loss_percent,
            "status": "excellent" if self.packet_loss_percent < 1.0 else "degraded",
        }
