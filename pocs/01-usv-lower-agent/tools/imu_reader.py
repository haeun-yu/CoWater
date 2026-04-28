"""
IMU Reader Tool: IMU 센서 읽기 (관성 측정, 방향)

IMU(Inertial Measurement Unit)는 Device의 방향과 가속도를 측정합니다.
Simulation Loop에서 set_orientation()을 호출하여 현재 heading을 업데이트합니다.

각도 표기:
- Roll (롤): 좌우 기울기 (±180°)
- Pitch (피치): 앞뒤 기울기 (±90°)
- Yaw (요): 방향/Heading (0-360° 또는 ±180°)
"""

from typing import Any


class IMUReader:
    """
    IMU 센서 리더

    Device의 자세(attitude)를 3축 회전각(roll, pitch, yaw)으로 나타내고,
    가속도(ax, ay, az)를 측정합니다.
    """

    def __init__(self) -> None:
        """IMU 센서 초기화"""
        self.roll: float = 0.0  # 좌우 기울기 (라디안 또는 도, ±180°)
        self.pitch: float = 0.0  # 앞뒤 기울기 (라디안 또는 도, ±90°)
        self.yaw: float = 0.0  # 방향/Heading (라디안 또는 도, 0-360°)
        self.ax: float = 0.0  # X축 가속도 (m/s²)
        self.ay: float = 0.0  # Y축 가속도 (m/s²)
        self.az: float = 9.81  # Z축 가속도 (m/s², 중력값)
        self.temperature: float = 25.0  # IMU 온도 (°C)

    def read(self) -> dict[str, Any]:
        """
        현재 IMU 정보 읽기

        Returns:
            dict: IMU 정보
                {
                  "roll": 좌우 기울기,
                  "pitch": 앞뒤 기울기,
                  "yaw": 방향/Heading,
                  "ax": X축 가속도,
                  "ay": Y축 가속도,
                  "az": Z축 가속도,
                  "temperature": IMU 온도
                }
        """
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
        """
        자세 업데이트 (Simulation Loop에서 호출)

        Simulator가 계산한 새로운 자세를 반영합니다.
        특히 yaw(heading)는 Device의 나침반 방향을 나타냅니다.

        Args:
            roll: 좌우 기울기 (도 또는 라디안)
            pitch: 앞뒤 기울기 (도 또는 라디안)
            yaw: 방향/Heading (도 또는 라디안, 0-360° 또는 ±180°)
        """
        self.roll = roll
        self.pitch = pitch
        self.yaw = yaw
