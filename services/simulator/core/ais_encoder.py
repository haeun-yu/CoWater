"""
AIS NMEA 0183 인코더.

pyais의 encode 모듈을 사용하여 VesselState → NMEA 문장 변환.
Message Type 1 (Class A Position Report) 생성.
"""

from __future__ import annotations

import logging

from pyais.encode import encode_msg
from pyais.messages import MessageType1

from core.vessel import VesselState

logger = logging.getLogger(__name__)


def encode_position_report(state: VesselState) -> str | None:
    """
    VesselState를 AIS Message Type 1 NMEA 문장으로 인코딩.
    AIS 침묵 상태이면 None 반환.
    """
    if state.ais_silent:
        return None

    try:
        mmsi = int(state.mmsi.replace("MMSI-", ""))

        sentences = encode_msg(MessageType1(
            msg_type=1,
            repeat=0,
            mmsi=mmsi,
            status=int(state.nav_status),
            turn=_clamp_rot(state.rot),
            speed=state.sog,
            accuracy=0,
            lon=state.lon,
            lat=state.lat,
            course=state.cog,
            heading=round(state.heading) % 360,
            second=0,
            maneuver=0,
            spare_1=0,
            raim=0,
            radio=0,
        ))
        # encode_msg는 리스트 반환 (멀티파트 대비)
        return "\n".join(sentences)

    except Exception:
        logger.exception("AIS encode failed for %s", state.mmsi)
        return None


def _clamp_rot(rot_deg_per_min: float) -> int:
    """ROT를 AIS 인코딩 범위 (-127 ~ 127)로 변환."""
    if abs(rot_deg_per_min) < 0.1:
        return 0
    sign = 1 if rot_deg_per_min > 0 else -1
    # AIS ROT = sign * (4.733 * sqrt(|ROT|))^2 — 역산은 생략, 클램프만
    return max(-127, min(127, int(rot_deg_per_min)))
