"""
GPS Reader Tool: GPS 센서 읽기 (위치 정보)

현재 위치(위도, 경도, 고도)와 GPS 고정 품질을 추적합니다.
Simulation Loop에서 update_position()을 호출하여 위치를 업데이트합니다.
Server의 Dynamic Re-binding은 이 위치 정보를 기반으로 부모 agent를 변경합니다.
"""

from typing import Any


class GPSReader:
    """
    GPS 센서 리더

    현재 위치를 추적하고, Moth를 통해 Server에 전송됩니다.
    Server는 이 위치 정보를 기반으로 Haversine 거리를 계산하여
    더 가까운 중간 agent로의 동적 재연결을 판단합니다.
    """

    def __init__(self) -> None:
        """GPS 센서 초기화 (한반도 중부 기본 위치)"""
        self.last_latitude: float = 37.005  # 위도 (°)
        self.last_longitude: float = 129.425  # 경도 (°)
        self.last_altitude: float = 0.0  # 고도 (m, 바다면 0)
        self.satellites: int = 12  # 수신 중인 위성 개수 (4개 이상 = 고정)
        self.hdop: float = 0.8  # Horizontal Dilution of Precision (낮을수록 좋음)

    def read(self) -> dict[str, Any]:
        """
        현재 GPS 정보 읽기

        Returns:
            dict: GPS 정보
                {
                  "latitude": 위도 (°),
                  "longitude": 경도 (°),
                  "altitude": 고도 (m),
                  "hdop": 수평 정확도 (낮을수록 좋음),
                  "satellites": 수신 위성 개수,
                  "status": "fixed" (위치 고정) 또는 "searching" (위성 탐색 중)
                }
        """
        return {
            "latitude": self.last_latitude,
            "longitude": self.last_longitude,
            "altitude": self.last_altitude,
            "hdop": self.hdop,
            "satellites": self.satellites,
            "status": "fixed" if self.satellites >= 4 else "searching",
        }

    def update_position(self, latitude: float, longitude: float, altitude: float = 0.0) -> None:
        """
        위치 업데이트 (Simulation Loop에서 호출)

        Simulator가 계산한 새로운 위치를 반영합니다.
        이 위치가 Moth를 통해 Server에 전송되어
        Dynamic Re-binding의 기초가 됩니다.

        Args:
            latitude: 위도 (°)
            longitude: 경도 (°)
            altitude: 고도 (m, 기본값 0)
        """
        self.last_latitude = latitude
        self.last_longitude = longitude
        self.last_altitude = altitude
