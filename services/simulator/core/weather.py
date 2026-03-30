"""간단한 기상 생성기 — 향후 실제 기상 API 연동 시 교체."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass
class WeatherState:
    wind_speed_knots: float     # 풍속
    wind_dir_deg: float         # 풍향 (진북 기준)
    wave_height_m: float        # 유의파고
    current_speed_knots: float  # 조류 속도
    current_dir_deg: float      # 조류 방향
    visibility_nm: float        # 시정


class WeatherGenerator:
    """
    시간에 따라 서서히 변하는 기상 상태 생성.
    Perlin noise 대신 단순 sin wave 기반 변동 적용.
    """

    def __init__(self, seed: int = 42) -> None:
        random.seed(seed)
        self._t = 0.0
        self._base = WeatherState(
            wind_speed_knots=random.uniform(5, 15),
            wind_dir_deg=random.uniform(0, 360),
            wave_height_m=random.uniform(0.3, 1.5),
            current_speed_knots=random.uniform(0.5, 2.0),
            current_dir_deg=random.uniform(0, 360),
            visibility_nm=random.uniform(5, 10),
        )

    def tick(self, dt_s: float) -> None:
        self._t += dt_s

    def current_state(self) -> WeatherState:
        t = self._t
        return WeatherState(
            wind_speed_knots=max(0, self._base.wind_speed_knots + 3 * math.sin(t / 600)),
            wind_dir_deg=(self._base.wind_dir_deg + 10 * math.sin(t / 1200)) % 360,
            wave_height_m=max(0.1, self._base.wave_height_m + 0.2 * math.sin(t / 900)),
            current_speed_knots=max(0, self._base.current_speed_knots + 0.3 * math.sin(t / 1800)),
            current_dir_deg=(self._base.current_dir_deg + 5 * math.sin(t / 2400)) % 360,
            visibility_nm=max(1.0, self._base.visibility_nm + 2 * math.sin(t / 3600)),
        )
