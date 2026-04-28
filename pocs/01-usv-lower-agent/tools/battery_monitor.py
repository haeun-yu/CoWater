"""
Battery Monitor Tool: 배터리 상태 모니터링

배터리의 상태를 추적하고, 전력 소비에 따라 방전을 시뮬레이션합니다.
Simulation Loop에서 주기적으로 discharge()를 호출하여 배터리가 소모되도록 합니다.

배터리 건강도:
- 80% 이상: excellent (매우 좋음)
- 50-80%: good (좋음)
- 30-50%: warning (경고)
- 30% 미만: critical (위험)
"""

from typing import Any


class BatteryMonitor:
    """
    배터리 모니터

    배터리의 충전율, 전압, 전류, 온도 등을 추적하고,
    시뮬레이션상에서 전력 소비에 따라 방전을 처리합니다.
    """

    def __init__(self, initial_percent: float = 100.0) -> None:
        """
        배터리 초기화

        Args:
            initial_percent: 초기 배터리 충전율 (%, 기본값 100%)
        """
        self.percent: float = initial_percent  # 충전율 (0-100%)
        self.voltage: float = 12.0  # 전압 (V)
        self.current: float = 0.0  # 전류 (A)
        self.temperature: float = 25.0  # 온도 (°C)
        self.estimated_remaining_minutes: int = 180  # 예상 남은 시간 (분)

    def read(self) -> dict[str, Any]:
        """
        현재 배터리 상태 읽기

        Returns:
            dict: 배터리 상태 정보
                {
                  "percent": 충전율 (0-100),
                  "voltage": 전압 (V),
                  "current": 전류 (A),
                  "temperature": 온도 (°C),
                  "estimated_remaining_minutes": 예상 남은 시간 (분),
                  "health": 건강도 ("excellent", "good", "warning", "critical")
                }
        """
        return {
            "percent": self.percent,
            "voltage": self.voltage,
            "current": self.current,
            "temperature": self.temperature,
            "estimated_remaining_minutes": self.estimated_remaining_minutes,
            "health": self._assess_health(),
        }

    def discharge(self, rate: float = 0.5) -> None:
        """
        배터리 방전 시뮬레이션

        Simulation Loop에서 주기적으로 호출되어 배터리가 소모되도록 합니다.
        모터 부하를 고려하여 방전 속도가 결정됩니다.

        Args:
            rate: 방전 속도 (%, 기본값 0.5% per iteration)
                  - 모터 idle: 0.2%/iteration
                  - 모터 full thrust: 0.5%/iteration
        """
        # 배터리 충전율 감소 (0% 이하로 내려가지 않음)
        self.percent = max(0, self.percent - rate)

        # 충전율에 따른 전압 변화 (선형 모델)
        # 100% = 12V, 0% = 0V
        self.voltage = 12.0 * (self.percent / 100.0)

        # 예상 남은 시간 계산 (충전율에 따른 추정)
        if self.percent > 50:
            # 50% 이상: 퀵 감소 (초반에 에너지 많이 소모)
            self.estimated_remaining_minutes = int(200 - (100 - self.percent) * 2)
        else:
            # 50% 이하: 슬로우 감소 (후반에 남은 에너지로 오래 사용)
            self.estimated_remaining_minutes = int(100 - (100 - self.percent))

    def _assess_health(self) -> str:
        """
        배터리 건강도 평가

        Returns:
            str: 건강도 상태
                - "excellent": 80% 이상 (매우 좋음)
                - "good": 50-80% (좋음)
                - "warning": 30-50% (경고, 곧 회귀 필요)
                - "critical": 30% 미만 (위험, 즉시 회귀 필요)
        """
        if self.percent >= 80:
            return "excellent"
        elif self.percent >= 50:
            return "good"
        elif self.percent >= 30:
            return "warning"
        else:
            return "critical"
