"""
Moth Publisher: Real-time Telemetry & Heartbeat Streaming

엔드포인트 규칙:
  Heartbeat  : /pang/ws/meb?channel=instant&name=heartbeat&source=base&track=base
               → 모든 디바이스가 동일 MEB 채널에 publish, Registry가 구독
  Telemetry  : /pang/ws/pub?channel=instant&name={device_id}&source=base&track=telemetry
               → 디바이스별 pub 스트림, 클라이언트는 sub로 구독
"""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.request
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional
from urllib.parse import urlsplit, urlunsplit

try:
    import websockets
except ImportError:
    websockets = None

if TYPE_CHECKING:
    from agent.state import AgentState

logger = logging.getLogger(__name__)

ALLOWED_MOTH_BASE_URLS = {"ws://cobot.center:8286", "wss://cobot.center:8287"}
DEFAULT_MOTH_BASE_URL = "wss://cobot.center:8287"

HEARTBEAT_MEB_PATH = "/pang/ws/meb?channel=instant&name=heartbeat&source=base&track=base"
HEARTBEAT_CHANNEL  = "device.heartbeat"


def _extract_base_url(raw_url: str) -> str:
    parsed = urlsplit((raw_url or "").strip())
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return ""


def _build_heartbeat_url(base: str) -> str:
    parsed = urlsplit(base)
    ep = urlsplit(HEARTBEAT_MEB_PATH)
    return urlunsplit((parsed.scheme, parsed.netloc, ep.path, ep.query, ""))


def _build_telemetry_pub_url(base: str, device_id: int | str) -> str:
    parsed = urlsplit(base)
    path = "/pang/ws/pub"
    query = f"channel=instant&name={device_id}&source=base&track=telemetry"
    return urlunsplit((parsed.scheme, parsed.netloc, path, query, ""))


class MothPublisher:
    """
    Moth WebSocket 발행자.

    연결 두 개:
      heartbeat_ws  → MEB heartbeat 채널 (모든 디바이스 공유)
      telemetry_ws  → pub 스트림 (디바이스별)
    """

    def __init__(self, config: dict[str, Any], state: "AgentState"):
        self.config = config
        self.state = state
        self.moth_config = config.get("moth", {})
        self.enabled = self.moth_config.get("enabled", True)

        configured = self.moth_config.get("server_url", DEFAULT_MOTH_BASE_URL)
        base = _extract_base_url(configured)
        self.moth_base_url = base if base in ALLOWED_MOTH_BASE_URLS else DEFAULT_MOTH_BASE_URL

        # URL: registration 전에는 임시값, initialize() 이후 확정
        self.heartbeat_url: str = _build_heartbeat_url(self.moth_base_url)
        self.telemetry_url: Optional[str] = None  # device_id 알기 전까지 None

        self.heartbeat_ws: Optional[Any] = None
        self.telemetry_ws: Optional[Any] = None
        self.heartbeat_connected = False
        self.telemetry_connected = False

    # ── 초기화 ────────────────────────────────────────────────────────────────

    async def initialize(self, registration_response: dict[str, Any]) -> None:
        """등록 응답을 받아 telemetry pub URL을 확정한다."""
        if not self.enabled or websockets is None:
            logger.info("MothPublisher 비활성화 또는 websockets 미설치")
            return

        device_id = (
            registration_response.get("id")
            or self.state.registry_id
        )
        self.telemetry_url = _build_telemetry_pub_url(self.moth_base_url, device_id)

        logger.info("MothPublisher 초기화 완료")
        logger.info(f"  Heartbeat MEB : {self.heartbeat_url}")
        logger.info(f"  Telemetry pub : {self.telemetry_url}")

    # ── 연결 ─────────────────────────────────────────────────────────────────

    def _is_closed(self, ws: Optional[Any]) -> bool:
        if ws is None:
            return True
        closed = getattr(ws, "closed", None)
        if isinstance(closed, bool):
            return closed
        state = getattr(ws, "state", None)
        if state is not None:
            return getattr(state, "name", str(state)).upper() in {"CLOSED", "CLOSING"}
        return False

    async def connect(self) -> None:
        """heartbeat + telemetry WebSocket 연결"""
        await self._connect_heartbeat()
        await self._connect_telemetry()

    async def _connect_heartbeat(self) -> None:
        if not self.enabled or websockets is None:
            return
        if not self._is_closed(self.heartbeat_ws):
            return
        try:
            logger.info(f"Heartbeat Moth 연결 시작: {self.heartbeat_url}")
            self.heartbeat_ws = await websockets.connect(
                self.heartbeat_url, ping_interval=30, ping_timeout=10
            )
            self.heartbeat_connected = True
            logger.info(f"Heartbeat Moth 연결 성공: {self.heartbeat_url}")
        except Exception as e:
            logger.error(f"Heartbeat Moth 연결 실패: {e}")
            self.heartbeat_connected = False
            self.heartbeat_ws = None

    async def _connect_telemetry(self) -> None:
        if not self.enabled or websockets is None or not self.telemetry_url:
            return
        if not self._is_closed(self.telemetry_ws):
            return
        try:
            logger.info(f"Telemetry Moth 연결 시작: {self.telemetry_url}")
            self.telemetry_ws = await websockets.connect(
                self.telemetry_url, ping_interval=30, ping_timeout=10
            )
            self.telemetry_connected = True
            logger.info(f"Telemetry Moth 연결 성공: {self.telemetry_url}")
        except Exception as e:
            logger.error(f"Telemetry Moth 연결 실패: {e}")
            self.telemetry_connected = False
            self.telemetry_ws = None

    async def _reconnect_loop(self) -> None:
        interval = self.moth_config.get("reconnect_interval_seconds", 5)
        while True:
            try:
                if self._is_closed(self.heartbeat_ws):
                    await self._connect_heartbeat()
                if self.telemetry_url and self._is_closed(self.telemetry_ws):
                    await self._connect_telemetry()
            except Exception as e:
                logger.warning(f"재연결 루프 오류: {e}")
            await asyncio.sleep(interval)

    # ── Heartbeat 발행 (MEB) ─────────────────────────────────────────────────

    async def heartbeat_loop(self) -> None:
        interval = self.config.get("registry", {}).get("heartbeat_interval_seconds", 1)
        logger.info(f"Heartbeat loop 시작: interval={interval}초")
        while True:
            await asyncio.sleep(interval)
            try:
                await self.publish_heartbeat()
            except Exception as e:
                logger.warning(f"Heartbeat loop 오류: {e}")

    async def publish_heartbeat(self) -> None:
        payload = self._heartbeat_payload()
        payload["route_mode"] = self._determine_route_mode()
        await self.publish_heartbeat_payload(payload)
        if payload["route_mode"] == "via_parent" and self.state.parent_endpoint:
            self._send_heartbeat_to_parent(payload)

    async def publish_heartbeat_payload(self, payload: dict[str, Any]) -> None:
        if not self.heartbeat_connected or self._is_closed(self.heartbeat_ws):
            logger.warning("Heartbeat 발행 불가: MEB 미연결")
            return
        try:
            msg = json.dumps({
                "type": "publish",
                "channel": HEARTBEAT_CHANNEL,
                "payload": payload,
            })
            await self.heartbeat_ws.send(msg)
            logger.info(
                f"Heartbeat 발행 완료: device_id={payload.get('device_id')}, "
                f"url={self.heartbeat_url}"
            )
        except Exception as e:
            logger.error(f"Heartbeat 발행 실패: {e}")
            self.heartbeat_connected = False

    def _heartbeat_payload(self) -> dict[str, Any]:
        hb: dict[str, Any] = {
            "device_id": self.state.registry_id,
            "agent_id": self.state.agent_id,
            "layer": self.state.layer,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "status": "online" if self.state.connected else "offline",
            "timeout_seconds": 3,
            "route_mode": self.state.route_mode,
            "parent_id": self.state.parent_id,
            "force_parent_routing": self.state.force_parent_routing,
            "battery_percent": (
                self.state.last_telemetry.get("battery_percent", 100)
                if self.state.last_telemetry else 100
            ),
        }
        if self.state.latitude is not None and self.state.longitude is not None:
            hb["latitude"] = self.state.latitude
            hb["longitude"] = self.state.longitude
        return hb

    def _determine_route_mode(self) -> str:
        if self.state.force_parent_routing:
            return "via_parent"
        if hasattr(self.state, "is_submerged") and self.state.is_submerged:
            return "via_parent"
        return self.state.route_mode

    def _send_heartbeat_to_parent(self, payload: dict[str, Any]) -> None:
        try:
            req = urllib.request.Request(
                f"{self.state.parent_endpoint.rstrip('/')}/children/heartbeat",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=0.5).close()
        except Exception as e:
            logger.debug(f"Parent heartbeat relay 실패: {e}")

    # ── Telemetry 발행 (pub) ─────────────────────────────────────────────────

    async def publish_telemetry(self, telemetry: dict[str, Any]) -> None:
        """
        센서 데이터를 pub 스트림으로 발행.
        클라이언트는 /pang/ws/sub?...name={device_id}&track=telemetry 로 구독.
        """
        if not self.telemetry_connected or self._is_closed(self.telemetry_ws):
            return

        payload: dict[str, Any] = {
            "device_id": self.state.registry_id,
            "agent_id": self.state.agent_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

        if self.state.latitude is not None:
            payload["latitude"] = self.state.latitude
        if self.state.longitude is not None:
            payload["longitude"] = self.state.longitude
        if "battery_percent" in telemetry:
            payload["battery_percent"] = telemetry["battery_percent"]
        if "motion" in telemetry:
            payload["motion"] = telemetry["motion"]
        if "depth" in telemetry:
            payload["depth_m"] = telemetry["depth"]
        if "position" in telemetry:
            payload["position"] = telemetry["position"]

        try:
            await self.telemetry_ws.send(json.dumps(payload))
            logger.debug(f"Telemetry 발행: device_id={self.state.registry_id}")
        except Exception as e:
            logger.debug(f"Telemetry 발행 실패: {e}")
            self.telemetry_connected = False

    # ── 하위 호환 ─────────────────────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        return self.heartbeat_connected or self.telemetry_connected
