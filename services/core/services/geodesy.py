from geographiclib.geodesic import Geodesic

WGS84 = Geodesic.WGS84


def inverse_distance_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    result = WGS84.Inverse(lat1, lon1, lat2, lon2)
    return result["s12"] / 1852.0


def inverse_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    result = WGS84.Inverse(lat1, lon1, lat2, lon2)
    return result["azi1"] % 360


def advance_position(
    lat: float, lon: float, bearing_deg: float, distance_nm: float
) -> tuple[float, float]:
    result = WGS84.Direct(lat, lon, bearing_deg, distance_nm * 1852.0)
    return result["lat2"], result["lon2"]


def sample_projected_track(
    lat: float,
    lon: float,
    bearing_deg: float,
    speed_knots: float,
    minutes_ahead: int,
    step_minutes: int,
) -> list[dict[str, float | int]]:
    points: list[dict[str, float | int]] = []
    if speed_knots <= 0 or minutes_ahead <= 0 or step_minutes <= 0:
        return points

    for minute in range(step_minutes, minutes_ahead + 1, step_minutes):
        distance_nm = speed_knots * (minute / 60.0)
        lat2, lon2 = advance_position(lat, lon, bearing_deg, distance_nm)
        points.append(
            {
                "minute": minute,
                "lat": lat2,
                "lon": lon2,
                "distance_nm": distance_nm,
            }
        )

    if points and points[-1]["minute"] != minutes_ahead:
        distance_nm = speed_knots * (minutes_ahead / 60.0)
        lat2, lon2 = advance_position(lat, lon, bearing_deg, distance_nm)
        points.append(
            {
                "minute": minutes_ahead,
                "lat": lat2,
                "lon": lon2,
                "distance_nm": distance_nm,
            }
        )

    return points
