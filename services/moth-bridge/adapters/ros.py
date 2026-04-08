"""ROS Protocol Adapter (스텁 — 추후 구현)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from adapters.base import GeoPoint, ParsedReport, ProtocolAdapter

logger = logging.getLogger(__name__)


class ROSAdapter(ProtocolAdapter):
    """
    ROS topic JSON 직렬화 파서.

    sensor_msgs/NavSatFix 포맷을 기본으로 지원:
    {
      "header": { "stamp": { "secs": ..., "nsecs": ... } },
      "latitude": ..., "longitude": ..., "altitude": ...
    }
    """

    name = "ROSAdapter"

    def supports_mime(self, mime: str) -> bool:
        base = mime.split(";")[0].strip().lower()
        return base in {"application/json", "application/ros"}

    def parse(self, raw: bytes, mime: str) -> ParsedReport | None:
        try:
            data = json.loads(raw.decode("utf-8"))

            lat = data.get("latitude")
            lon = data.get("longitude")
            if lat is None or lon is None:
                return None

            platform_id = data.get("platform_id", "ros-unknown")
            altitude = data.get("altitude")

            return ParsedReport(
                platform_id=platform_id,
                timestamp=datetime.now(tz=timezone.utc),
                position=GeoPoint(lat=float(lat), lon=float(lon)),
                altitude_m=float(altitude) if altitude is not None else None,
                source_protocol="ros",
                raw_payload=raw,
            )
        except Exception:
            logger.exception("ROSAdapter parse error")
            return None
