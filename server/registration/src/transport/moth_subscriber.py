"""
Moth Heartbeat Subscriber: Device Registration Server 측 heartbeat 수신

Moth meb (broadcast) 채널을 통해 모든 디바이스의 heartbeat를 수신합니다:
- device.heartbeat: 모든 디바이스의 하트비트를 통합 수신
- Server는 heartbeat_monitor를 통해 device 상태 추적 (online/offline)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional, TYPE_CHECKING
from urllib.parse import urlsplit, urlunsplit

try:
    import websockets
except ImportError:
    websockets = None

if TYPE_CHECKING:
    from src.registry.device_registry import DeviceRegistry

logger = logging.getLogger(__name__)
ALLOWED_MOTH_BASE_URLS = {"ws://cobot.center:8286", "wss://cobot.center:8287"}
MOTH_HEALTHCHECK_PATH = "/pang/ws/meb"
MOTH_HEALTHCHECK_QUERY = "channel=instant&name=heartbeat&source=base&track=base"
DEFAULT_MOTH_URL = f"wss://cobot.center:8287{MOTH_HEALTHCHECK_PATH}?{MOTH_HEALTHCHECK_QUERY}"


def _extract_base_url(raw_url: str) -> str:
    parsed = urlsplit((raw_url or "").strip())
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return ""


def _build_healthcheck_url(base_url: str, query: str = "") -> str:
    parsed = urlsplit(base_url)
    final_query = query if query else MOTH_HEALTHCHECK_QUERY
    return urlunsplit((parsed.scheme, parsed.netloc, MOTH_HEALTHCHECK_PATH, final_query, ""))


class MothHeartbeatSubscriber:
    """
    Moth meb 채널을 구독하여 모든 디바이스의 heartbeat을 수신하고
    HeartbeatMonitor를 통해 device 상태를 추적합니다.
    """

    def __init__(self, registry: DeviceRegistry, moth_server_url: str):
        """
        Moth Heartbeat Subscriber 초기화

        Args:
            registry: DeviceRegistry (heartbeat_monitor 포함)
            moth_server_url: Moth 서버 URL (ws(s)://host:port 또는 전체 URL)
        """
        self.registry = registry
        requested_base_url = _extract_base_url(moth_server_url)
        selected_base_url = requested_base_url if requested_base_url in ALLOWED_MOTH_BASE_URLS else "wss://cobot.center:8287"
        parsed = urlsplit(moth_server_url)
        query_string = parsed.query if parsed.query else ""
        self.moth_server_url = _build_healthcheck_url(selected_base_url, query_string)
        self.ws: Optional[Any] = None
        self.is_connected = False
        self.is_running = False
        self._binary_ping_interval_seconds = 10

    def _ws_is_closed(self) -> bool:
        """websockets 버전별 연결 객체 차이를 흡수해 종료 상태를 판별합니다."""
        if self.ws is None:
            return True

        closed_attr = getattr(self.ws, "closed", None)
        if isinstance(closed_attr, bool):
            return closed_attr
        if closed_attr is not None:
            try:
                return bool(closed_attr)
            except Exception:
                pass

        state = getattr(self.ws, "state", None)
        if state is not None:
            state_name = getattr(state, "name", str(state)).upper()
            if state_name in {"CLOSED", "CLOSING"}:
                return True
            if state_name in {"OPEN", "OPENING", "CONNECTING"}:
                return False

        return False

    async def connect(self) -> None:
        """Moth WebSocket 서버에 연결"""
        if websockets is None:
            logger.info("websockets 미설치 - Moth 구독 비활성화")
            return

        if self.ws is not None and not self._ws_is_closed():
            return

        try:
            logger.info(f"Moth 연결 중: {self.moth_server_url}")
            self.ws = await websockets.connect(
                self.moth_server_url,
                # Moth는 애플리케이션 레벨 바이너리 ping을 사용하므로
                # websockets 내부 keepalive(ping/pong)는 비활성화합니다.
                ping_interval=None,
                ping_timeout=None,
            )
            self.is_connected = True
            logger.info(f"Moth 연결 성공 - URL: {self.moth_server_url}")
        except Exception as e:
            logger.error(f"Moth 연결 실패 (url={self.moth_server_url}): {e}")
            self.is_connected = False
            raise

    async def subscribe_heartbeat_meb(self) -> None:
        """
        Moth meb (broadcast) 채널에 heartbeat 구독

        meb 채널은 모든 디바이스의 heartbeat을 통합 수신하는 broadcast stream입니다.
        각 디바이스가 자신의 heartbeat을 발행할 때, 이 구독이 모든 heartbeat을 수신합니다.
        """
        if not self.is_connected or self.ws is None or self._ws_is_closed():
            logger.warning("Cannot subscribe: not connected to Moth")
            return

        try:
            # meb 채널 구독 요청 (모든 heartbeat을 한 곳에서 수신)
            subscribe_msg = {
                "type": "subscribe",
                "channel": "device.heartbeat",  # meb로 모든 heartbeat을 수신
                "channel_type": "meb",
            }
            await self.ws.send(json.dumps(subscribe_msg))
            logger.info("Moth meb 채널 구독 완료: device.heartbeat 채널")
        except Exception as e:
            logger.error(f"meb 채널 구독 실패: {e}")
            self.is_connected = False

    async def _receive_loop(self) -> None:
        """Moth로부터 heartbeat 메시지 수신 루프"""
        while self.is_running:
            if not self.is_connected or self.ws is None or self._ws_is_closed():
                await asyncio.sleep(1)
                continue

            try:
                msg = await asyncio.wait_for(self.ws.recv(), timeout=60)
                logger.debug(f"Moth 메시지 수신: {type(msg).__name__}")
                await self._handle_message(msg)
            except asyncio.TimeoutError:
                logger.warning("Moth 수신 timeout (60초) - 재연결 시도")
                self.is_connected = False
            except Exception as e:
                logger.error(f"Moth 수신 오류: {e}")
                self.is_connected = False
                await asyncio.sleep(1)

    async def _binary_ping_loop(self) -> None:
        """Moth ping track 규격에 맞춰 바이너리 ping 프레임을 주기 전송합니다."""
        while self.is_running:
            try:
                if self.is_connected and self.ws is not None and not self._ws_is_closed():
                    await self.ws.send(b"ping")
                    logger.debug("Moth 바이너리 ping 전송")
                await asyncio.sleep(self._binary_ping_interval_seconds)
            except Exception as e:
                logger.warning(f"Moth 바이너리 ping 전송 실패: {e}")
                self.is_connected = False
                await asyncio.sleep(1)

    async def _handle_message(self, msg: str | bytes) -> None:
        """
        Moth로부터 수신한 메시지 처리

        메시지 형식:
        {
            "type": "publish",
            "channel": "device.heartbeat",
            "payload": {
                "device_id": int,
                "agent_id": str,
                "layer": "lower" | "middle" | "system",
                "timestamp": str (ISO),
                "status": "online" | "offline",
                "battery_percent": float
            }
        }
        """
        try:
            if isinstance(msg, (bytes, bytearray)):
                logger.debug("Moth 바이너리 프레임 수신")
                return

            data = json.loads(msg)

            payload, channel, msg_type = self._extract_payload(data)
            if msg_type and msg_type != "publish":
                logger.debug(f"Non-publish message type: {msg_type}")

            if not isinstance(payload, dict) or not payload:
                logger.debug(f"Ignored message without heartbeat payload: channel={channel}")
                return
            device_id = payload.get("device_id")
            status = payload.get("status", "online")
            latitude = payload.get("latitude")
            longitude = payload.get("longitude")
            battery_percent = payload.get("battery_percent")

            if device_id is None:
                logger.warning(f"Invalid heartbeat: device_id 없음 - {payload}")
                return

            # HeartbeatMonitor에 기록 (위치 정보 포함)
            self.registry.heartbeat_monitor.record_heartbeat(
                device_id,
                status,
                latitude,
                longitude,
                battery_percent,
            )
            logger.debug(
                "Heartbeat 기록: device_id=%s, status=%s, location=(%s, %s), battery=%s, channel=%s",
                device_id,
                status,
                latitude,
                longitude,
                battery_percent,
                channel,
            )

        except json.JSONDecodeError:
            logger.debug(f"JSON 파싱 실패: {msg}")
        except Exception as e:
            logger.error(f"메시지 처리 오류: {e}")

    def _extract_payload(self, data: dict[str, Any]) -> tuple[dict[str, Any], str, str]:
        """Moth 구현 차이에 따른 래핑(data/payload)을 흡수해 heartbeat payload를 추출한다."""
        channel = str(data.get("channel") or data.get("topic") or "")
        msg_type = str(data.get("type") or "")
        payload = data.get("payload")

        if isinstance(payload, dict):
            return payload, channel, msg_type

        nested = data.get("data")
        if isinstance(nested, dict):
            nested_channel = str(nested.get("channel") or nested.get("topic") or channel)
            nested_type = str(nested.get("type") or msg_type)
            nested_payload = nested.get("payload")
            if isinstance(nested_payload, dict):
                return nested_payload, nested_channel, nested_type
            if nested.get("device_id") is not None:
                return nested, nested_channel, nested_type

        if data.get("device_id") is not None:
            return data, channel, msg_type

        return {}, channel, msg_type

    async def _reconnect_loop(self) -> None:
        """자동 재연결 루프"""
        reconnect_interval = 5

        while self.is_running:
            try:
                if not self.is_connected or self.ws is None or self._ws_is_closed():
                    await self.connect()
                    if self.is_connected:
                        await self.subscribe_heartbeat_meb()
                await asyncio.sleep(reconnect_interval)
            except Exception as e:
                logger.debug(f"재연결 오류: {e}")
                await asyncio.sleep(reconnect_interval)

    async def start(self) -> None:
        """Moth 구독 시작"""
        if websockets is None:
            logger.info("websockets 미설치 - Moth 구독 스킵")
            return

        self.is_running = True
        logger.info(f"MothHeartbeatSubscriber 시작: {self.moth_server_url}")

        # 초기 연결
        await self.connect()
        if self.is_connected:
            await self.subscribe_heartbeat_meb()

        # 백그라운드 루프 시작
        asyncio.create_task(self._receive_loop())
        asyncio.create_task(self._reconnect_loop())
        asyncio.create_task(self._binary_ping_loop())

    async def stop(self) -> None:
        """Moth 구독 중지"""
        self.is_running = False
        if self.ws is not None and not self._ws_is_closed():
            try:
                await self.ws.close()
            except Exception as e:
                logger.error(f"WebSocket 종료 오류: {e}")
        logger.info("MothHeartbeatSubscriber 중지")
