"""NMEA 0183 AIS 문장 파서."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from pyais import decode
from pyais.exceptions import InvalidNMEAMessageException

from adapters.base import GeoPoint, ParsedReport, ProtocolAdapter

logger = logging.getLogger(__name__)

# AIS Nav Status 코드 → 문자열
_NAV_STATUS = {
    0: "underway_engine",
    1: "at_anchor",
    2: "not_under_command",
    3: "restricted_maneuverability",
    4: "constrained_by_draught",
    5: "moored",
    6: "aground",
    7: "engaged_in_fishing",
    8: "underway_sailing",
    15: "undefined",
}


class NMEAAdapter(ProtocolAdapter):
    """
    AIS NMEA 0183 문장 파서.

    Moth 채널에서 text/plain 또는 application/nmea MIME으로 수신된
    AIS 문장 (예: !AIVDM,1,1,,B,...)을 파싱한다.

    단일 문장 및 멀티파트 문장(2-part) 모두 지원.
    """

    name = "NMEAAdapter"
    _SUPPORTED_MIME = {"text/plain", "application/nmea"}

    def supports_mime(self, mime: str) -> bool:
        base = mime.split(";")[0].strip().lower()
        return base in self._SUPPORTED_MIME

    def parse(self, raw: bytes, mime: str) -> ParsedReport | None:
        try:
            text = raw.decode("ascii", errors="replace").strip()
            if not text:
                return None

            msg = decode(text)
            decoded = msg.asdict()

            # AIS Message Type 1, 2, 3, 18 (위치 보고) 만 처리
            msg_type = decoded.get("msg_type")
            if msg_type not in (1, 2, 3, 18, 19):
                return None

            mmsi = str(decoded.get("mmsi", ""))
            if not mmsi:
                return None

            lat = decoded.get("lat")
            lon = decoded.get("lon")
            if lat is None or lon is None or lat == 91.0 or lon == 181.0:
                # AIS 위치 미상 값 필터링
                return None

            sog = decoded.get("speed")
            cog = decoded.get("course")
            heading = decoded.get("heading")
            rot = decoded.get("turn")
            nav_code = decoded.get("status")

            return ParsedReport(
                platform_id=f"MMSI-{mmsi}",
                timestamp=datetime.now(tz=timezone.utc),
                position=GeoPoint(lat=float(lat), lon=float(lon)),
                sog=float(sog) if sog is not None else None,
                cog=float(cog) if cog is not None else None,
                heading=float(heading) if heading not in (None, 511) else None,
                rot=float(rot) if rot not in (None, -128, 128) else None,
                nav_status=_NAV_STATUS.get(nav_code, "undefined") if nav_code is not None else None,
                source_protocol="ais",
                raw_payload=raw,
            )

        except InvalidNMEAMessageException:
            logger.debug("Invalid NMEA sentence received")
            return None
        except Exception:
            logger.exception("NMEAAdapter parse error")
            return None
