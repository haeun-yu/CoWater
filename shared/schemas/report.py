from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal


REPORT_SCHEMA_VERSION = 1


@dataclass
class GeoPoint:
    lat: float
    lon: float


@dataclass
class PlatformReport:
    """모든 외부 프로토콜을 정규화한 내부 공통 포맷.

    Redis pub/sub 직렬화(to_dict / from_dict) 기준이 되는 단일 정의.
    moth-bridge → Redis → agents 파이프라인 전체에서 이 스키마를 사용한다.
    """

    platform_id: str
    timestamp: datetime

    # 위치 — Redis wire format과 일치하도록 flat 필드
    lat: float
    lon: float
    schema_version: int = REPORT_SCHEMA_VERSION
    depth_m: float | None = None  # ROV / AUV 수심
    altitude_m: float | None = None  # 드론 고도

    # 운동
    sog: float | None = None  # Speed Over Ground (knots)
    cog: float | None = None  # Course Over Ground (0-360°)
    heading: float | None = None  # True Heading (0-360°)
    rot: float | None = None  # Rate of Turn (°/min)

    # AIS 항법 상태 (선박 외 플랫폼은 None)
    nav_status: str | None = None

    platform_type: str | None = None
    name: str | None = None

    # 시뮬레이터 태그 — True이면 에이전트가 실경보 생성을 건너뛸 수 있다
    is_simulator: bool = False

    # 원본 정보 보존
    source_protocol: Literal["ais", "ros", "mavlink", "nmea", "custom"] = "custom"
    raw_payload_b64: str | None = None
    raw_payload_cache_key: str | None = None
    raw_payload_truncated: bool = False

    def to_dict(self) -> dict:
        payload = {
            "platform_id": self.platform_id,
            "timestamp": self.timestamp.isoformat(),
            "schema_version": self.schema_version,
            "lat": self.lat,
            "lon": self.lon,
            "depth_m": self.depth_m,
            "altitude_m": self.altitude_m,
            "sog": self.sog,
            "cog": self.cog,
            "heading": self.heading,
            "rot": self.rot,
            "nav_status": self.nav_status,
            "platform_type": self.platform_type,
            "name": self.name,
            "source_protocol": self.source_protocol,
            "is_simulator": self.is_simulator,
        }
        if self.raw_payload_b64 is not None:
            payload["raw_payload_b64"] = self.raw_payload_b64
            payload["raw_payload_truncated"] = self.raw_payload_truncated
        if self.raw_payload_cache_key is not None:
            payload["raw_payload_cache_key"] = self.raw_payload_cache_key
            payload["raw_payload_truncated"] = self.raw_payload_truncated
        return payload

    @classmethod
    def from_dict(cls, d: dict) -> "PlatformReport":
        timestamp = datetime.fromisoformat(d["timestamp"])
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        else:
            timestamp = timestamp.astimezone(timezone.utc)
        return cls(
            platform_id=d["platform_id"],
            timestamp=timestamp,
            schema_version=d.get("schema_version", REPORT_SCHEMA_VERSION),
            lat=d["lat"],
            lon=d["lon"],
            depth_m=d.get("depth_m"),
            altitude_m=d.get("altitude_m"),
            sog=d.get("sog"),
            cog=d.get("cog"),
            heading=d.get("heading"),
            rot=d.get("rot"),
            nav_status=d.get("nav_status"),
            platform_type=d.get("platform_type"),
            name=d.get("name"),
            source_protocol=d.get("source_protocol", "custom"),
            raw_payload_b64=d.get("raw_payload_b64"),
            raw_payload_cache_key=d.get("raw_payload_cache_key"),
            raw_payload_truncated=d.get("raw_payload_truncated", False),
        )
