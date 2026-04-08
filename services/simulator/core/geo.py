"""간단한 구면 기하 유틸리티 (Haversine, Rhumb line)."""

import math

EARTH_RADIUS_NM = 3440.065  # 해리


def bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """두 지점 간 초기 진방위 (0~360°)."""
    lat1r, lat2r = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(lat2r)
    y = math.cos(lat1r) * math.sin(lat2r) - math.sin(lat1r) * math.cos(lat2r) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def distance_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """두 지점 간 Haversine 거리 (해리)."""
    lat1r, lat2r = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1r) * math.cos(lat2r) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_NM * math.asin(math.sqrt(a))


def advance_position(lat: float, lon: float, heading_deg: float, distance_nm: float) -> tuple[float, float]:
    """
    현재 위치에서 heading 방향으로 distance_nm 해리 이동한 좌표.
    Rhumb line 근사 (단거리에서 충분히 정확).
    """
    d = distance_nm / EARTH_RADIUS_NM
    lat_r = math.radians(lat)
    hdg_r = math.radians(heading_deg)

    new_lat_r = lat_r + d * math.cos(hdg_r)
    new_lat_r = max(min(new_lat_r, math.pi / 2), -math.pi / 2)

    dq = math.cos((new_lat_r + lat_r) / 2)
    dlon = d * math.sin(hdg_r) / (dq if abs(dq) > 1e-10 else 1e-10)

    new_lat = math.degrees(new_lat_r)
    new_lon = (lon + math.degrees(dlon) + 540) % 360 - 180
    return new_lat, new_lon


def angle_diff(a: float, b: float) -> float:
    """두 방위각의 최단 차이 (-180 ~ +180)."""
    d = (b - a + 540) % 360 - 180
    return d
