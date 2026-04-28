"""Motor Control Tool - controls propulsion"""

from typing import Any


class MotorControl:
    """Controls USV motors"""

    def __init__(self) -> None:
        self.forward_thrust: float = 0.0  # -1.0 to 1.0 (back to forward)
        self.yaw_thrust: float = 0.0  # -1.0 to 1.0 (left to right)
        self.port_rpm: int = 0
        self.starboard_rpm: int = 0
        self.max_rpm: int = 3000

    def set_thrust(self, forward: float, yaw: float) -> bool:
        """Set motor thrust"""
        self.forward_thrust = max(-1.0, min(1.0, forward))
        self.yaw_thrust = max(-1.0, min(1.0, yaw))

        # Calculate motor RPM from thrust
        port_thrust = self.forward_thrust + self.yaw_thrust
        starboard_thrust = self.forward_thrust - self.yaw_thrust

        self.port_rpm = int(max(-self.max_rpm, min(self.max_rpm, port_thrust * self.max_rpm)))
        self.starboard_rpm = int(max(-self.max_rpm, min(self.max_rpm, starboard_thrust * self.max_rpm)))

        return True

    def get_status(self) -> dict[str, Any]:
        """Get motor status"""
        return {
            "forward_thrust": self.forward_thrust,
            "yaw_thrust": self.yaw_thrust,
            "port_rpm": self.port_rpm,
            "starboard_rpm": self.starboard_rpm,
            "max_rpm": self.max_rpm,
        }

    def stop(self) -> bool:
        """Stop motors"""
        self.forward_thrust = 0.0
        self.yaw_thrust = 0.0
        self.port_rpm = 0
        self.starboard_rpm = 0
        return True
