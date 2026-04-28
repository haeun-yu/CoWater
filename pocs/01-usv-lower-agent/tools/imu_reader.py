"""IMU Reader Tool - reads inertial measurement unit data"""

from typing import Any


class IMUReader:
    """Reads IMU/Odometry sensor data"""

    def __init__(self) -> None:
        self.roll: float = 0.0
        self.pitch: float = 0.0
        self.yaw: float = 0.0
        self.ax: float = 0.0  # acceleration X
        self.ay: float = 0.0  # acceleration Y
        self.az: float = 9.81  # acceleration Z (gravity)
        self.temperature: float = 25.0

    def read(self) -> dict[str, Any]:
        """Read IMU sensor"""
        return {
            "roll": self.roll,
            "pitch": self.pitch,
            "yaw": self.yaw,
            "ax": self.ax,
            "ay": self.ay,
            "az": self.az,
            "temperature": self.temperature,
        }

    def set_orientation(self, roll: float, pitch: float, yaw: float) -> None:
        """Set simulated orientation"""
        self.roll = roll
        self.pitch = pitch
        self.yaw = yaw
