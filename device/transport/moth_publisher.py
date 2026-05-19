"""
Moth Publisher: Real-time Telemetry & Healthcheck Streaming

엔드포인트 규칙:
    Healthcheck: /pang/ws/meb?channel=instant&name=agents&source=base&track=base
                             → 모든 디바이스가 단일 agents MEB 채널에 DEVICE_HEALTHCHECK 발행
    Telemetry  : /pang/ws/pub?channel=instant&name={device_id}&source=base&track=telemetry
                             → 디바이스별 pub 스트림, 클라이언트는 sub로 구독
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.request
from datetime import datetime
from time import monotonic
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

HEALTHCHECK_MEB_PATH = "/pang/ws/meb?channel=instant&name=agents&source=base&track=base"
HEALTHCHECK_CHANNEL = "agents"


def _env_bool(name: str) -> bool | None:
    value = os.getenv(name)
    if value is None or value == "":
        return None
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _extract_base_url(raw_url: str) -> str:
    parsed = urlsplit((raw_url or "").strip())
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return ""


def _build_healthcheck_url(base: str) -> str:
    parsed = urlsplit(base)
    ep = urlsplit(HEALTHCHECK_MEB_PATH)
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
    healthcheck_ws  → MEB healthcheck 채널 (모든 디바이스 공유)
      track_ws_dict → 각 track type별 pub 스트림 (디바이스별)
    """

    def __init__(self, config: dict[str, Any], state: "AgentState"):
        self.config = config
        self.state = state
        self.moth_config = config.get("moth", {})
        env_enabled = _env_bool("COWATER_MOTH_ENABLED")
        self.enabled = env_enabled if env_enabled is not None else bool(self.moth_config.get("enabled", True))

        configured = self.moth_config.get("server_url", DEFAULT_MOTH_BASE_URL)
        base = _extract_base_url(configured)
        self.moth_base_url = base if base in ALLOWED_MOTH_BASE_URLS else DEFAULT_MOTH_BASE_URL

        # URL: registration 전에는 임시값, initialize() 이후 확정
        self.healthcheck_url: str = _build_healthcheck_url(self.moth_base_url)
        self.telemetry_url: Optional[str] = None  # device_id 알기 전까지 None

        self.healthcheck_ws: Optional[Any] = None
        self.healthcheck_connected = False
        
        # Track별 WebSocket 관리
        self.track_ws_dict: dict[str, Optional[Any]] = {}  # {track_type: ws}
        self.track_urls: dict[str, str] = {}  # {track_type: url}
        self.track_connected: dict[str, bool] = {}  # {track_type: is_connected}
        self._closed = False
        self._last_log_at: dict[str, float] = {}

    def _log_throttled(self, key: str, level: int, message: str, *args: Any, interval: float = 30.0) -> None:
        now = monotonic()
        if now - self._last_log_at.get(key, 0.0) >= interval:
            logger.log(level, message, *args)
            self._last_log_at[key] = now

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
        logger.info(f"  Healthcheck MEB : {self.healthcheck_url}")
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
        """healthcheck + track별 WebSocket 연결"""
        if self._closed:
            return
        await self._connect_healthcheck()
        await self._connect_tracks()

    async def _connect_healthcheck(self) -> None:
        if not self.enabled or websockets is None:
            return
        if not self._is_closed(self.healthcheck_ws):
            return
        try:
            logger.info(f"Healthcheck Moth 연결 시작: {self.healthcheck_url}")
            self.healthcheck_ws = await websockets.connect(
                self.healthcheck_url,
                ping_interval=30,
                ping_timeout=10,
                open_timeout=3,
            )
            self.healthcheck_connected = True
            logger.info(f"Healthcheck Moth 연결 성공: {self.healthcheck_url}")
        except Exception as e:
            self._log_throttled(
                "healthcheck_connect_failed",
                logging.WARNING,
                "Healthcheck Moth 연결 실패: %s",
                e,
            )
            self.healthcheck_connected = False
            self.healthcheck_ws = None

    async def _connect_tracks(self) -> None:
        """각 track type별 pub WebSocket 연결"""
        if not self.enabled or websockets is None:
            return
        
        for track_type, track_url in self.track_urls.items():
            if self._is_closed(self.track_ws_dict.get(track_type)):
                try:
                    logger.info(f"Track {track_type} Moth 연결 시작: {track_url}")
                    ws = await websockets.connect(
                        track_url,
                        ping_interval=30,
                        ping_timeout=10,
                        open_timeout=3,
                    )
                    self.track_ws_dict[track_type] = ws
                    self.track_connected[track_type] = True
                    logger.info(f"Track {track_type} Moth 연결 성공")
                except Exception as e:
                    self._log_throttled(
                        f"track_connect_failed:{track_type}",
                        logging.WARNING,
                        "Track %s Moth 연결 실패, 해당 telemetry는 일시 중단: %s",
                        track_type,
                        e,
                    )
                    self.track_connected[track_type] = False
                    self.track_ws_dict[track_type] = None

    async def _reconnect_loop(self) -> None:
        interval = self.moth_config.get("reconnect_interval_seconds", 5)
        while not self._closed:
            try:
                if self._is_closed(self.healthcheck_ws):
                    await self._connect_healthcheck()
                # Track별 재연결
                await self._connect_tracks()
            except Exception as e:
                logger.warning(f"재연결 루프 오류: {e}")
            await asyncio.sleep(interval)

    # ── Healthcheck 발행 (MEB) ───────────────────────────────────────────────

    async def healthcheck_loop(self) -> None:
        interval = self.config.get("registry", {}).get("healthcheck_interval_seconds",
                                                        1)
        logger.info(f"Healthcheck loop 시작: interval={interval}초")
        while not self._closed:
            await asyncio.sleep(interval)
            try:
                await self.publish_healthcheck()
            except Exception as e:
                logger.warning(f"Healthcheck loop 오류: {e}")

    async def publish_healthcheck(self) -> None:
        payload = self._healthcheck_payload()
        payload["route_mode"] = self._determine_route_mode()
        await self.publish_healthcheck_payload(payload)
        if payload["route_mode"] == "via_parent" and self.state.parent_endpoint:
            self._send_healthcheck_to_parent(payload)

    async def publish_healthcheck_payload(self, payload: dict[str, Any]) -> None:
        if not self.healthcheck_connected or self._is_closed(self.healthcheck_ws):
            self._log_throttled(
                "healthcheck_publish_unavailable",
                logging.WARNING,
                "Healthcheck 발행 일시 중단: MEB 미연결",
            )
            return
        try:
            msg = json.dumps({
                "type": "publish",
                "channel": HEALTHCHECK_CHANNEL,
                "payload": {
                    "event_type": "DEVICE_HEALTHCHECK",
                    "target_agents": ["SystemSentinel", "InsightReporter"],
                    "payload": payload,
                    "timestamp": payload.get("timestamp"),
                    "source_agent": self.state.agent_id,
                },
            })
            await self.healthcheck_ws.send(msg)
            logger.info(
                f"Healthcheck 발행 완료: device_id={payload.get('device_id')}, "
                f"url={self.healthcheck_url}"
            )
        except Exception as e:
            logger.error(f"Healthcheck 발행 실패: {e}")
            self.healthcheck_connected = False

    def _healthcheck_payload(self) -> dict[str, Any]:
        hb: dict[str, Any] = {
            "event_type": "DEVICE_HEALTHCHECK",
            "device_id": self.state.registry_id,
            "agent_id": self.state.agent_id,
            "layer": self.state.layer,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "status": "ONLINE" if self.state.connected else "OFFLINE",
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

    def _send_healthcheck_to_parent(self, payload: dict[str, Any]) -> None:
        try:
            req = urllib.request.Request(
                f"{self.state.parent_endpoint.rstrip('/')}/children/healthcheck",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=0.5).close()
        except Exception as e:
            logger.debug(f"Parent healthcheck relay 실패: {e}")

    # ── Telemetry 발행 (pub) ─────────────────────────────────────────────────

    async def publish_telemetry(self, telemetry: dict[str, Any]) -> None:
        """
        센서 데이터를 track type별 pub 스트림으로 발행.
        """
        if not self.enabled:
            return

        # P8 원칙: Telemetry 초기화 보호 - initialize() 호출 후에만 발행
        if not self.telemetry_url or not self.state.registry_id:
            logger.debug("Telemetry 발행 준비 미완료: registry_id 또는 telemetry_url 미설정")
            return

        device_id = self.state.registry_id

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

    async def publish_a2a_event(
        self,
        from_device_id: str | int | None,
        message_type: str,
        task_id: str | None = None,
        action: str | None = None,
        extra: dict | None = None,
    ) -> None:
        """A2A 이벤트를 수신 디바이스의 A2A 전용 트랙으로 발행한다.
        
        발행 구조: {"a2a_event": {"from": sender, "to": receiver, "type": ..., ...}}
        - system agent 개입 없음
        - TOPIC(센서 데이터)과 완전히 분리된 A2A 전용 채널
        - 프론트엔드가 from/to 파싱해 디바이스 간 직접 링크 표시
        """
        if not self.enabled or not self.state.registry_id:
            self._log_throttled(
                "a2a_publish_skipped_unavailable",
                logging.DEBUG,
                "A2A publish skipped: publisher disabled or device not registered",
                interval=30.0,
            )
            return

        if not self.track_connected.get("A2A") or self._is_closed(self.track_ws_dict.get("A2A")):
            self._log_throttled(
                "a2a_publish_skipped_track",
                logging.WARNING,
                "A2A publish skipped: track not connected or closed",
                interval=10.0,
            )
            return

        event: dict = {
            "from": str(from_device_id) if from_device_id is not None else None,
            "to": str(self.state.registry_id),
            "type": message_type,
        }
        if task_id:
            event["task_id"] = task_id
        if action:
            event["action"] = action
        if extra:
            event.update(extra)

        payload = {
            "device_id": self.state.registry_id,
            "agent_id": self.state.agent_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "a2a_event": event,
        }
        try:
            await self.track_ws_dict["A2A"].send(json.dumps(payload))
            logger.info(f"A2A 이벤트 발행: from={event.get('from')} → to={event.get('to')} type={event.get('type')}")
        except Exception as e:
            logger.warning(f"A2A 이벤트 발행 실패: {e}")
            self.track_connected["A2A"] = False

    # ── 하위 호환 ─────────────────────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        return self.healthcheck_connected or any(self.track_connected.values())

    async def close(self) -> None:
        self._closed = True
        sockets = [self.healthcheck_ws, *self.track_ws_dict.values()]
        self.healthcheck_ws = None
        self.healthcheck_connected = False
        for track_type in list(self.track_connected):
            self.track_connected[track_type] = False
        for ws in sockets:
            if ws is None or self._is_closed(ws):
                continue
            try:
                await ws.close()
            except Exception as exc:
                logger.debug("Moth WebSocket close failed: %s", exc)
