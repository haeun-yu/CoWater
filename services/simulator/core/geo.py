"""지오데식 유틸리티 (GeographicLib 기반)."""

import math

from geographiclib.geodesic import Geodesic

EARTH_RADIUS_NM = 3440.065  # 해리
WGS84 = Geodesic.WGS84


def bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """두 지점 간 초기 진방위 (0~360°)."""
    result = WGS84.Inverse(lat1, lon1, lat2, lon2)
    return result["azi1"] % 360


def distance_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """두 지점 간 타원체 기준 거리 (해리)."""
    result = WGS84.Inverse(lat1, lon1, lat2, lon2)
    return result["s12"] / 1852.0


def advance_position(
    lat: float, lon: float, heading_deg: float, distance_nm: float
) -> tuple[float, float]:
    """현재 위치에서 heading 방향으로 distance_nm 해리 이동한 좌표."""
    result = WGS84.Direct(lat, lon, heading_deg, distance_nm * 1852.0)
    return result["lat2"], result["lon2"]


def angle_diff(a: float, b: float) -> float:
    """두 방위각의 최단 차이 (-180 ~ +180)."""
    d = (b - a + 540) % 360 - 180
    return d
