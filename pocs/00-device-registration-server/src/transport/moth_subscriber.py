"""
Moth Heartbeat Subscriber: Device Registration Server 측 heartbeat 수신

Moth meb (broadcast) 채널을 통해 모든 디바이스의 heartbeat를 수신합니다:
- device.heartbeat.{device_id}: 모든 디바이스의 하트비트를 통합 수신
- Server는 heartbeat_monitor를 통해 device 상태 추적 (online/offline)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional, TYPE_CHECKING

try:
    import websockets
except ImportError:
    websockets = None

if TYPE_CHECKING:
    from src.registry.device_registry import DeviceRegistry

logger = logging.getLogger(__name__)
ALLOWED_MOTH_URLS = {"ws://cobot.center:8286", "wss://cobot.center:8287"}
DEFAULT_MOTH_URL = "wss://cobot.center:8287"


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
            moth_server_url: Moth 서버 URL (wss://host:port)
        """
        self.registry = registry
        self.moth_server_url = moth_server_url if moth_server_url in ALLOWED_MOTH_URLS else DEFAULT_MOTH_URL
        self.ws: Optional[Any] = None
        self.is_connected = False
        self.is_running = False

    async def connect(self) -> None:
        """Moth WebSocket 서버에 연결"""
        if websockets is None:
            logger.info("websockets 미설치 - Moth 구독 비활성화")
            return

        if self.ws is not None and not self.ws.closed:
            return

        try:
            logger.info(f"Moth 연결 중: {self.moth_server_url}")
            self.ws = await websockets.connect(
                self.moth_server_url,
                ping_interval=30,
                ping_timeout=10
            )
            self.is_connected = True
            logger.info("Moth 연결 성공")
        except Exception as e:
            logger.error(f"Moth 연결 실패: {e}")
            self.is_connected = False

    async def subscribe_heartbeat_meb(self) -> None:
        """
        Moth meb (broadcast) 채널에 heartbeat 구독

        meb 채널은 모든 디바이스의 heartbeat을 통합 수신하는 broadcast stream입니다.
        각 디바이스가 자신의 heartbeat을 발행할 때, 이 구독이 모든 heartbeat을 수신합니다.
        """
        if not self.is_connected or self.ws is None or self.ws.closed:
            return

        try:
            # meb 채널 구독 요청 (모든 heartbeat을 한 곳에서 수신)
            subscribe_msg = {
                "type": "subscribe",
                "channel": "device.heartbeat",  # meb로 모든 heartbeat을 수신
                "channel_type": "meb",
            }
            await self.ws.send(json.dumps(subscribe_msg))
            logger.info("Moth meb 채널 구독: device.heartbeat (모든 디바이스의 heartbeat 통합 수신)")
        except Exception as e:
            logger.error(f"meb 채널 구독 실패: {e}")
            self.is_connected = False

    async def _receive_loop(self) -> None:
        """Moth로부터 heartbeat 메시지 수신 루프"""
        while self.is_running:
            if not self.is_connected or self.ws is None or self.ws.closed:
                await asyncio.sleep(1)
                continue

            try:
                msg = await asyncio.wait_for(self.ws.recv(), timeout=60)
                await self._handle_message(msg)
            except asyncio.TimeoutError:
                # 60초 동안 메시지 없음 - 재연결 시도
                logger.warning("Moth 수신 timeout - 재연결 시도")
                self.is_connected = False
            except Exception as e:
                logger.error(f"Moth 수신 오류: {e}")
                self.is_connected = False
                await asyncio.sleep(1)

    async def _handle_message(self, msg: str) -> None:
        """
        Moth로부터 수신한 메시지 처리

        메시지 형식:
        {
            "type": "publish",
            "channel": "device.heartbeat.{device_id}",
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
            data = json.loads(msg)
            if data.get("type") != "publish":
                return

            channel = data.get("channel") or data.get("topic") or ""
            if channel != "device.heartbeat":
                return

            payload = data.get("payload", {})
            device_id = payload.get("device_id")
            status = payload.get("status", "online")

            if device_id is None:
                logger.warning(f"Invalid heartbeat: device_id 없음 - {payload}")
                return

            # HeartbeatMonitor에 기록
            self.registry.heartbeat_monitor.record_heartbeat(device_id, status)
            logger.debug(f"Heartbeat 기록: device_id={device_id}, status={status}")

        except json.JSONDecodeError:
            logger.debug(f"JSON 파싱 실패: {msg}")
        except Exception as e:
            logger.error(f"메시지 처리 오류: {e}")

    async def _reconnect_loop(self) -> None:
        """자동 재연결 루프"""
        reconnect_interval = 5

        while self.is_running:
            try:
                if not self.is_connected or self.ws is None or self.ws.closed:
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

    async def stop(self) -> None:
        """Moth 구독 중지"""
        self.is_running = False
        if self.ws is not None and not self.ws.closed:
            try:
                await self.ws.close()
            except Exception as e:
                logger.error(f"WebSocket 종료 오류: {e}")
        logger.info("MothHeartbeatSubscriber 중지")
