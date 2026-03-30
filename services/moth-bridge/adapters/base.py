from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone

from dataclasses import dataclass, field


@dataclass
class GeoPoint:
    lat: float
    lon: float


@dataclass
class ParsedReport:
    """Protocol Adapter가 반환하는 정규화된 플랫폼 보고."""
    platform_id: str
    timestamp: datetime
    position: GeoPoint
    depth_m: float | None = None
    altitude_m: float | None = None
    sog: float | None = None
    cog: float | None = None
    heading: float | None = None
    rot: float | None = None
    nav_status: str | None = None
    source_protocol: str = "custom"
    raw_payload: bytes | None = None

    def to_redis_payload(self) -> dict:
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


class ProtocolAdapter(ABC):
    """모든 Protocol Adapter의 기본 클래스."""

    name: str = "base"

    @abstractmethod
    def parse(self, raw: bytes, mime: str) -> ParsedReport | None:
        """
        raw 바이너리와 MIME 타입을 받아 ParsedReport를 반환한다.
        파싱 불가 또는 위치 정보 없으면 None 반환.
        """
        ...

    def supports_mime(self, mime: str) -> bool:
        return True
