"""GPS Reader Tool - reads simulated GPS sensor data"""

from typing import Any


class GPSReader:
    """Reads GPS position data"""

    def __init__(self) -> None:
        self.last_latitude: float = 37.005
        self.last_longitude: float = 129.425
        self.last_altitude: float = 0.0
        self.satellites: int = 12
        self.hdop: float = 0.8  # Horizontal Dilution of Precision

    def read(self) -> dict[str, Any]:
        """Read GPS sensor"""
        return {
            "latitude": self.last_latitude,
            "longitude": self.last_longitude,
            "altitude": self.last_altitude,
            "hdop": self.hdop,
            "satellites": self.satellites,
            "status": "fixed" if self.satellites >= 4 else "searching",
        }

    def update_position(self, latitude: float, longitude: float, altitude: float = 0.0) -> None:
        """Update simulated position"""
        self.last_latitude = latitude
        self.last_longitude = longitude
        self.last_altitude = altitude
