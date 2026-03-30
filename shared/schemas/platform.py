from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

PlatformType = Literal["vessel", "rov", "usv", "auv", "drone", "buoy"]
SourceProtocol = Literal["ais", "ros", "mavlink", "nmea", "custom"]


@dataclass
class PlatformDimensions:
    length_m: float | None = None
    beam_m: float | None = None
    draft_m: float | None = None


@dataclass
class Platform:
    platform_id: str
    platform_type: PlatformType
    name: str
    source_protocol: SourceProtocol
    flag: str | None = None
    moth_channel: str | None = None          # Moth 채널명
    capabilities: list[str] = field(default_factory=list)
    dimensions: PlatformDimensions | None = None
    metadata: dict = field(default_factory=dict)
