"""
선박 물리 모델.

상태: 위치(lat/lon), 속도(SOG), 선수 방향(heading), COG, ROT, Nav Status
행동: Waypoint 추종, 속도 변경, 강제 정지, AIS 침묵
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from core.geo import advance_position, bearing, distance_nm, angle_diff

logger = logging.getLogger(__name__)


class NavStatus(int, Enum):
    UNDERWAY_ENGINE  = 0
    AT_ANCHOR        = 1
    NOT_UNDER_COMMAND = 2
    RESTRICTED_MANEUVERABILITY = 3
    MOORED           = 5
    AGROUND          = 6
    ENGAGED_FISHING  = 7
    UNDERWAY_SAILING = 8
    UNDEFINED        = 15


@dataclass
class Waypoint:
    lat: float
    lon: float
    speed_knots: float | None = None    # None = 현재 속도 유지


@dataclass
class VesselState:
    mmsi: str
    name: str
    lat: float
    lon: float
    heading: float          # 0-360°
    cog: float              # 0-360°
    sog: float              # knots
    rot: float = 0.0        # degrees/min
    nav_status: NavStatus = NavStatus.UNDERWAY_ENGINE
    ais_silent: bool = False

    # 물리 파라미터
    max_speed_knots: float = 15.0
    max_rot_deg_per_min: float = 10.0   # 최대 선회율
    acceleration_knots_per_s: float = 0.05

    # 항법
    waypoints: list[Waypoint] = field(default_factory=list)
    waypoint_arrival_radius_nm: float = 0.05


class VesselSimulator:
    """단일 선박의 물리 시뮬레이션."""

    def __init__(self, state: VesselState) -> None:
        self.state = state
        self._target_speed: float = state.sog

    def inject_event(self, event_type: str, **kwargs) -> None:
        """시나리오 이벤트 주입."""
        if event_type == "engine_stop":
            logger.info("[%s] Event: engine_stop", self.state.mmsi)
            self._target_speed = 0.0
            self.state.nav_status = NavStatus.NOT_UNDER_COMMAND

        elif event_type == "engine_restore":
            logger.info("[%s] Event: engine_restore", self.state.mmsi)
            self._target_speed = kwargs.get("speed", self.state.max_speed_knots * 0.5)
            self.state.nav_status = NavStatus.UNDERWAY_ENGINE

        elif event_type == "ais_silence":
            logger.info("[%s] Event: ais_silence", self.state.mmsi)
            self.state.ais_silent = True

        elif event_type == "ais_restore":
            logger.info("[%s] Event: ais_restore", self.state.mmsi)
            self.state.ais_silent = False

        elif event_type == "set_speed":
            self._target_speed = float(kwargs["speed"])

        elif event_type == "emergency_stop":
            # 즉각 정지 — 속도 0으로 순간 감속 (속도 이상 감지용, nav_status 유지)
            logger.info("[%s] Event: emergency_stop (sog: %.1f→0)", self.state.mmsi, self.state.sog)
            self.state.sog = 0.0
            self._target_speed = 0.0

        elif event_type == "set_waypoint":
            wp = Waypoint(lat=kwargs["lat"], lon=kwargs["lon"],
                          speed_knots=kwargs.get("speed"))
            self.state.waypoints.insert(0, wp)

    def tick(self, dt_s: float) -> None:
        """dt_s 초 경과 후 상태 갱신."""
        s = self.state

        # 속도 가감속
        speed_diff = self._target_speed - s.sog
        max_delta = self.state.acceleration_knots_per_s * dt_s
        s.sog += max(-max_delta, min(max_delta, speed_diff))
        s.sog = max(0.0, min(s.sog, s.max_speed_knots))

        # Waypoint 추종
        if s.waypoints:
            wp = s.waypoints[0]
            dist = distance_nm(s.lat, s.lon, wp.lat, wp.lon)

            if dist <= s.waypoint_arrival_radius_nm:
                logger.debug("[%s] Arrived at waypoint (%.4f, %.4f)", s.mmsi, wp.lat, wp.lon)
                s.waypoints.pop(0)
                if wp.speed_knots is not None:
                    self._target_speed = wp.speed_knots
            else:
                target_bearing = bearing(s.lat, s.lon, wp.lat, wp.lon)
                diff = angle_diff(s.heading, target_bearing)
                max_turn = s.max_rot_deg_per_min * (dt_s / 60.0)
                turn = max(-max_turn, min(max_turn, diff))
                s.rot = turn / (dt_s / 60.0) if dt_s > 0 else 0.0
                s.heading = (s.heading + turn) % 360
                s.cog = s.heading  # 단순화: COG ≈ heading

        # 위치 갱신
        if s.sog > 0.01:
            dist_moved = s.sog * (dt_s / 3600.0)   # knots × hours = NM
            s.lat, s.lon = advance_position(s.lat, s.lon, s.heading, dist_moved)

        # 정지 상태면 ROT = 0
        if s.sog < 0.1:
            s.rot = 0.0
            if s.nav_status == NavStatus.UNDERWAY_ENGINE and not s.waypoints:
                s.nav_status = NavStatus.AT_ANCHOR
