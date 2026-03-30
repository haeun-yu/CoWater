from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass
class GeoPoint:
    lat: float
    lon: float


@dataclass
class PlatformReport:
    """모든 외부 프로토콜을 정규화한 내부 공통 포맷."""

    platform_id: str
    timestamp: datetime

    # 위치
    position: GeoPoint
    depth_m: float | None = None        # ROV / AUV 수심
    altitude_m: float | None = None     # 드론 고도

    # 운동
    sog: float | None = None            # Speed Over Ground (knots)
    cog: float | None = None            # Course Over Ground (0-360°)
    heading: float | None = None        # True Heading (0-360°)
    rot: float | None = None            # Rate of Turn (°/min)

    # AIS 항법 상태 (선박 외 플랫폼은 None)
    nav_status: str | None = None

    # 원본 정보 보존
    source_protocol: Literal["ais", "ros", "mavlink", "nmea", "custom"] = "custom"
    raw_payload: bytes | None = None

    def to_dict(self) -> dict:
        return {
            "platform_id": self.platform_id,
            "timestamp": self.timestamp.isoformat(),
            "lat": self.position.lat,
            "lon": self.position.lon,
            "depth_m": self.depth_m,
            "altitude_m": self.altitude_m,
            "sog": self.sog,
            "cog": self.cog,
            "heading": self.heading,
            "rot": self.rot,
            "nav_status": self.nav_status,
            "source_protocol": self.source_protocol,
        }
