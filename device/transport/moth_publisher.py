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


def _build_track_pub_url(base: str, device_id: int | str, track_type: str) -> str:
    """각 track type별 pub URL 생성"""
    parsed = urlsplit(base)
    path = "/pang/ws/pub"
    query = f"channel=instant&name={device_id}&source=base&track={track_type.lower()}"
    return urlunsplit((parsed.scheme, parsed.netloc, path, query, ""))


def _resolve_track_pub_url(base: str, endpoint: str, device_id: int | str, track_type: str) -> str:
    """등록 응답 endpoint를 우선 사용하고, 필요 시 publish 가능한 URL로 정규화한다."""
    ep = (endpoint or "").strip()
    if not ep:
        return _build_track_pub_url(base, device_id, track_type)

    ep = ep.replace("/pang/ws/sub", "/pang/ws/pub").replace("/pang/ws/meb", "/pang/ws/pub")
    parsed_ep = urlsplit(ep)
    if parsed_ep.scheme and parsed_ep.netloc:
        return ep

    parsed_base = urlsplit(base)
    return urlunsplit((parsed_base.scheme, parsed_base.netloc, parsed_ep.path, parsed_ep.query, ""))


class MothPublisher:
    """
    Moth WebSocket 발행자.

    연결 구조:
      heartbeat_ws  → MEB heartbeat 채널 (모든 디바이스 공유)
      track_ws_dict → 각 track type별 pub 스트림 (디바이스별)
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
        self.heartbeat_connected = False
        
        # Track별 WebSocket 관리
        self.track_ws_dict: dict[str, Optional[Any]] = {}  # {track_type: ws}
        self.track_urls: dict[str, str] = {}  # {track_type: url}
        self.track_connected: dict[str, bool] = {}  # {track_type: is_connected}

    # ── 초기화 ────────────────────────────────────────────────────────────────

    async def initialize(self, registration_response: dict[str, Any]) -> None:
        """등록 응답을 받아 track별 pub URL을 생성한다."""
        if not self.enabled or websockets is None:
            logger.info("MothPublisher 비활성화 또는 websockets 미설치")
            return

        device_id = (
            registration_response.get("id")
            or self.state.registry_id
        )
        self.telemetry_url = _build_telemetry_pub_url(self.moth_base_url, device_id)

        # Track별 URL 생성
        tracks = registration_response.get("tracks", [])
        for track in tracks:
            track_type = track.get("type", "").upper()
            if track_type:
                track_url = _resolve_track_pub_url(
                    self.moth_base_url,
                    str(track.get("endpoint") or ""),
                    device_id,
                    track_type,
                )
                self.track_urls[track_type] = track_url
                self.track_ws_dict[track_type] = None
                self.track_connected[track_type] = False

        logger.info("MothPublisher 초기화 완료")
        logger.info(f"  Heartbeat MEB : {self.heartbeat_url}")
        logger.info(f"  Track URLs   : {list(self.track_urls.keys())}")

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
        """heartbeat + track별 WebSocket 연결"""
        await self._connect_heartbeat()
        await self._connect_tracks()

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

    async def _connect_tracks(self) -> None:
        """각 track type별 pub WebSocket 연결"""
        if not self.enabled or websockets is None:
            return
        
        for track_type, track_url in self.track_urls.items():
            if self._is_closed(self.track_ws_dict.get(track_type)):
                try:
                    logger.info(f"Track {track_type} Moth 연결 시작: {track_url}")
                    ws = await websockets.connect(track_url, ping_interval=30, ping_timeout=10)
                    self.track_ws_dict[track_type] = ws
                    self.track_connected[track_type] = True
                    logger.info(f"Track {track_type} Moth 연결 성공")
                except Exception as e:
                    logger.error(f"Track {track_type} Moth 연결 실패: {e}")
                    self.track_connected[track_type] = False
                    self.track_ws_dict[track_type] = None

    async def _reconnect_loop(self) -> None:
        interval = self.moth_config.get("reconnect_interval_seconds", 5)
        while True:
            try:
                if self._is_closed(self.heartbeat_ws):
                    await self._connect_heartbeat()
                # Track별 재연결
                await self._connect_tracks()
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
        # 깊이 정보 추가 (AUV/ROV용)
        if self.state.last_telemetry and "depth" in self.state.last_telemetry:
            hb["depth"] = self.state.last_telemetry["depth"]
        # 방향 및 속도 정보 추가
        if self.state.last_telemetry and "motion" in self.state.last_telemetry:
            motion = self.state.last_telemetry["motion"]
            if isinstance(motion, dict):
                if "heading" in motion:
                    hb["heading"] = motion["heading"]
                if "speed" in motion:
                    hb["speed"] = motion["speed"]
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
        센서 데이터를 track type별 pub 스트림으로 발행.
        """
        if not self.enabled:
            return

        device_id = self.state.registry_id
        if not device_id:
            return

        # Base 페이로드
        base_payload: dict[str, Any] = {
            "device_id": device_id,
            "agent_id": self.state.agent_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

        # Track type별로 데이터 분류 및 발행
        
        # ODOMETRY: 위치, 방향, 속도
        if "position" in telemetry or "motion" in telemetry:
            if self.track_connected.get("ODOMETRY") and not self._is_closed(self.track_ws_dict.get("ODOMETRY")):
                payload = {**base_payload}
                if "position" in telemetry:
                    pos = telemetry["position"]
                    if isinstance(pos, dict):
                        payload["latitude"] = pos.get("latitude")
                        payload["longitude"] = pos.get("longitude")
                if "motion" in telemetry:
                    motion = telemetry["motion"]
                    if isinstance(motion, dict):
                        payload["heading"] = motion.get("heading")
                        payload["speed"] = motion.get("speed")
                try:
                    await self.track_ws_dict["ODOMETRY"].send(json.dumps(payload))
                except Exception as e:
                    logger.debug(f"ODOMETRY 발행 실패: {e}")
                    self.track_connected["ODOMETRY"] = False

        # GPS: GPS 데이터 (ODOMETRY과 동일)
        if "position" in telemetry:
            if self.track_connected.get("GPS") and not self._is_closed(self.track_ws_dict.get("GPS")):
                payload = {**base_payload}
                pos = telemetry["position"]
                if isinstance(pos, dict):
                    payload["latitude"] = pos.get("latitude")
                    payload["longitude"] = pos.get("longitude")
                try:
                    await self.track_ws_dict["GPS"].send(json.dumps(payload))
                except Exception as e:
                    logger.debug(f"GPS 발행 실패: {e}")
                    self.track_connected["GPS"] = False

        # DEPTH: 깊이
        if "depth" in telemetry:
            if self.track_connected.get("DEPTH") and not self._is_closed(self.track_ws_dict.get("DEPTH")):
                payload = {**base_payload, "depth": telemetry["depth"]}
                try:
                    await self.track_ws_dict["DEPTH"].send(json.dumps(payload))
                except Exception as e:
                    logger.debug(f"DEPTH 발행 실패: {e}")
                    self.track_connected["DEPTH"] = False

        # BATTERY: 배터리
        if "battery_percent" in telemetry:
            if self.track_connected.get("BATTERY") and not self._is_closed(self.track_ws_dict.get("BATTERY")):
                payload = {**base_payload, "battery_percent": telemetry["battery_percent"]}
                try:
                    await self.track_ws_dict["BATTERY"].send(json.dumps(payload))
                except Exception as e:
                    logger.debug(f"BATTERY 발행 실패: {e}")
                    self.track_connected["BATTERY"] = False

        # TOPIC: 기타 센서 데이터
        if "sensors" in telemetry:
            if self.track_connected.get("TOPIC") and not self._is_closed(self.track_ws_dict.get("TOPIC")):
                payload = {**base_payload, "sensors": telemetry["sensors"]}
                try:
                    await self.track_ws_dict["TOPIC"].send(json.dumps(payload))
                except Exception as e:
                    logger.debug(f"TOPIC 발행 실패: {e}")
                    self.track_connected["TOPIC"] = False

    # ── 하위 호환 ─────────────────────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        return self.heartbeat_connected or any(self.track_connected.values())
