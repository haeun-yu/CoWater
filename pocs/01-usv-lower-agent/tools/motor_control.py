"""
Motor Control Tool: 모터 제어 (추진력 제어)

USV(무인선)의 두 개 모터(포트/스타보드)를 제어합니다.
Decision Engine의 권장사항(slow_down, change_heading, return_to_base 등)을
모터 thrust로 변환하여 실행합니다.

모터 구조:
- 포트 모터 (좌측): forward_thrust + yaw_thrust
- 스타보드 모터 (우측): forward_thrust - yaw_thrust
이를 통해 전진/후진과 회전을 동시에 제어합니다.
"""

from typing import Any


class MotorControl:
    """
    USV 모터 제어기

    USV의 두 개 모터를 제어하여 전진/후진/좌회전/우회전을 수행합니다.
    Decision Engine의 권장사항을 thrust 명령으로 변환합니다.
    """

    def __init__(self) -> None:
        """모터 제어기 초기화"""
        self.forward_thrust: float = 0.0  # 전진 추력 (-1.0=후진 ~ 1.0=전진)
        self.yaw_thrust: float = 0.0  # 회전 추력 (-1.0=좌회전 ~ 1.0=우회전)
        self.port_rpm: int = 0  # 포트(좌측) 모터 RPM
        self.starboard_rpm: int = 0  # 스타보드(우측) 모터 RPM
        self.max_rpm: int = 3000  # 최대 RPM

    def set_thrust(self, forward: float, yaw: float) -> bool:
        """
        모터 추력 설정 (Decision Engine에서 호출)

        Forward와 Yaw thrust를 각 모터의 RPM으로 변환합니다:
        - Port RPM = (forward + yaw) * max_rpm
        - Starboard RPM = (forward - yaw) * max_rpm

        Examples:
        - set_thrust(1.0, 0.0): 최대 전진
        - set_thrust(0.0, 1.0): 우회전 (port forward, starboard backward)
        - set_thrust(0.5, 0.25): 전진 + 약간 우회전

        Args:
            forward: 전진 추력 (-1.0 ~ 1.0)
            yaw: 회전 추력 (-1.0 ~ 1.0)

        Returns:
            bool: 항상 True (성공)
        """
        # Thrust를 -1.0 ~ 1.0 범위로 정규화
        self.forward_thrust = max(-1.0, min(1.0, forward))
        self.yaw_thrust = max(-1.0, min(1.0, yaw))

        # 각 모터의 실제 추력 계산
        port_thrust = self.forward_thrust + self.yaw_thrust  # 포트 모터
        starboard_thrust = self.forward_thrust - self.yaw_thrust  # 스타보드 모터

        # 추력을 RPM으로 변환 (-max_rpm ~ max_rpm)
        self.port_rpm = int(max(-self.max_rpm, min(self.max_rpm, port_thrust * self.max_rpm)))
        self.starboard_rpm = int(max(-self.max_rpm, min(self.max_rpm, starboard_thrust * self.max_rpm)))

        return True

    def get_status(self) -> dict[str, Any]:
        """
        현재 모터 상태 조회

        Returns:
            dict: 모터 상태
                {
                  "forward_thrust": 전진 추력,
                  "yaw_thrust": 회전 추력,
                  "port_rpm": 포트 모터 RPM,
                  "starboard_rpm": 스타보드 모터 RPM,
                  "max_rpm": 최대 RPM
                }
        """
        return {
            "forward_thrust": self.forward_thrust,
            "yaw_thrust": self.yaw_thrust,
            "port_rpm": self.port_rpm,
            "starboard_rpm": self.starboard_rpm,
            "max_rpm": self.max_rpm,
        }

    def stop(self) -> bool:
        """
        모터 정지 (all-stop)

        Decision Engine의 "stop" 권장사항 실행 시 호출됩니다.

        Returns:
            bool: 항상 True (성공)
        """
        self.forward_thrust = 0.0
        self.yaw_thrust = 0.0
        self.port_rpm = 0
        self.starboard_rpm = 0
        return True
