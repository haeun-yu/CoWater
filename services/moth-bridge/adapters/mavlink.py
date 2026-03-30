"""MAVLink Protocol Adapter (스텁 — 추후 구현)."""

from __future__ import annotations

import logging

from adapters.base import ParsedReport, ProtocolAdapter

logger = logging.getLogger(__name__)


class MAVLinkAdapter(ProtocolAdapter):
    """
    MAVLink v2 메시지 파서.

    GLOBAL_POSITION_INT (msg_id=33) 메시지에서 위치/속도를 추출한다.
    pymavlink 라이브러리 필요 (requirements에 추가 후 활성화).
    """

    name = "MAVLinkAdapter"

    def supports_mime(self, mime: str) -> bool:
        return "mavlink" in mime.lower()

    def parse(self, raw: bytes, mime: str) -> ParsedReport | None:
        # TODO: pymavlink 기반 파서 구현
        logger.warning("MAVLinkAdapter is not yet implemented")
        return None
