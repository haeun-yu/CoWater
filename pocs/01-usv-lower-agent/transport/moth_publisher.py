"""
Moth Publisher: Real-time Telemetry & Heartbeat Streaming

Moth WebSocket을 통해 Device의 센서 데이터와 하트비트를 실시간으로 발행합니다.
- Heartbeat: 10초마다 (Health monitoring + Dynamic re-binding용)
- Telemetry: 각 iteration마다 (GPS, Battery, IMU 등)

Server는 Moth 스트림을 수신하여:
1. Position update → 동적 재연결 판단 (Haversine 거리 계산)
2. Heartbeat → Timeout 감지 및 offline 처리
3. Telemetry → 센서 분석 및 통계
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

try:
    import websockets
except ImportError:
    websockets = None

if TYPE_CHECKING:
    from agent.state import AgentState

logger = logging.getLogger(__name__)


class MothPublisher:
    """
    Moth WebSocket 발행자: 센서 데이터 및 하트비트 실시간 전송

    Device Registration Server의 응답으로 받은 topics를 통해
    Moth 서버(wss://cobot.center:8287)에 데이터를 발행합니다.

    Topic 구조:
    - device.heartbeat.{device_id}: 주기적 하트비트 (10초)
    - device.telemetry.{device_id}.gps: GPS 위치
    - device.telemetry.{device_id}.battery: 배터리 상태
    - device.telemetry.{device_id}.imu: IMU/Odometry
    """

    def __init__(self, config: dict[str, Any], state: AgentState):
        """
        Moth Publisher 초기화

        Args:
            config: Agent 설정 (moth 섹션 포함)
            state: Agent 상태 (device_id, registry_id 등)
        """
        self.config = config
        self.state = state
        self.moth_config = config.get("moth", {})
        self.moth_url = self.moth_config.get("server_url", "wss://cobot.center:8287")
        self.enabled = self.moth_config.get("enabled", True)
        self.ws: Optional[Any] = None
        self.is_connected = False

        # Server의 Device Registration 응답에서 할당받은 topics
        self.heartbeat_topic: Optional[str] = None
        self.telemetry_topics: dict[str, str] = {}  # {track_type: topic}

    async def initialize(self, registration_response: dict[str, Any]) -> None:
        """
        Server 등록 응답에서 Topics 초기화 + Moth URL 업데이트

        Device Registration Server에서 받은 응답에서:
        - heartbeat_topic: device.heartbeat.{device_id}
        - telemetry_topics: [GPS, BATTERY, ODOMETRY 등의 topic 목록]
        - server: Moth 서버의 실제 주소 (host, port, ping_endpoint)

        이후 이 topics을 통해 Moth에 데이터를 발행합니다.

        Args:
            registration_response: Device Registration 응답 (id, token, heartbeat_topic, telemetry_topics, server 포함)
        """
        if not self.enabled or websockets is None:
            logger.info("MothPublisher 비활성화 또는 websockets 미설치")
            return

        # Server에서 할당한 실제 Moth 서버 정보 추출
        server_info = registration_response.get("server", {})
        if server_info:
            moth_host = server_info.get("host", "cobot.center")
            moth_port = server_info.get("port", 8286)
            # wss://host:port 형식으로 URL 구성
            self.moth_url = f"wss://{moth_host}:{moth_port}"
            logger.info(f"Moth 서버 URL 업데이트: {self.moth_url}")

        # Server에서 할당한 heartbeat topic 저장
        self.heartbeat_topic = registration_response.get("heartbeat_topic")

        # 각 track type별 telemetry topic 저장
        telemetry_topics_list = registration_response.get("telemetry_topics", [])
        for topic_info in telemetry_topics_list:
            track_type = topic_info.get("track_type")  # "GPS", "BATTERY", "ODOMETRY" 등
            topic = topic_info.get("topic")  # "device.telemetry.{id}.{track_name}"
            if track_type and topic:
                self.telemetry_topics[track_type] = topic

        logger.info(f"MothPublisher 초기화 완료: Moth={self.moth_url}, {len(self.telemetry_topics)}개 telemetry topics")
        logger.debug(f"Heartbeat topic: {self.heartbeat_topic}")

    async def connect(self) -> None:
        """
        Moth WebSocket 서버에 연결

        WebSocket 연결 설정:
        - ping_interval=30: 30초마다 ping 전송 (연결 유지)
        - ping_timeout=10: 10초 내에 pong 응답 없으면 연결 끊김
        """
        if not self.enabled or websockets is None:
            return

        # 이미 연결되어 있으면 스킵
        if self.ws is not None and not self.ws.closed:
            return

        try:
            logger.info(f"Moth 연결 중: {self.moth_url}")
            self.ws = await websockets.connect(self.moth_url, ping_interval=30, ping_timeout=10)
            self.is_connected = True
            logger.info("Moth 연결 성공")
        except Exception as e:
            logger.error(f"Moth 연결 실패: {e}")
            self.is_connected = False

    async def _reconnect_loop(self) -> None:
        """
        자동 재연결 루프 (백그라운드 task)

        주기적으로 Moth 연결 상태를 확인하고,
        연결이 끊어졌으면 자동으로 재연결합니다.

        Default: 5초마다 확인 (환경변수로 커스터마이징 가능)
        """
        reconnect_interval = self.moth_config.get("reconnect_interval_seconds", 5)

        while True:
            try:
                # 연결 끊김 감지 시 재연결 시도
                if not self.is_connected or self.ws is None or self.ws.closed:
                    await self.connect()
                await asyncio.sleep(reconnect_interval)
            except Exception as e:
                logger.debug(f"재연결 오류: {e}")
                await asyncio.sleep(reconnect_interval)

    async def publish_heartbeat(self) -> None:
        """
        Device Heartbeat 주기적 발행

        Server의 HeartbeatMonitor가 이를 수신하여:
        1. 접속 상태 추적 (마지막 heartbeat 시각 기록)
        2. Timeout 감지 (30초 이상 없으면 offline으로 표시)
        3. 자동 재할당 (Middle Agent offline 시 자식 재할당)

        Heartbeat 내용:
        - device_id: Server에서 할당한 ID
        - layer: "lower", "middle", "system"
        - status: "online" 또는 "offline"
        - battery_percent: 현재 배터리 상태
        """
        if not self.heartbeat_topic or not self.is_connected or self.ws is None or self.ws.closed:
            return

        # Heartbeat payload 구성
        payload = {
            "device_id": self.state.registry_id,
            "agent_id": self.state.agent_id,
            "layer": self.state.layer,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "status": "online" if self.state.connected else "offline",
            "battery_percent": self.state.last_telemetry.get("battery_percent", 100) if self.state.last_telemetry else 100,
        }

        try:
            # Moth에 발행
            await self.ws.send(
                json.dumps(
                    {"type": "publish", "topic": self.heartbeat_topic, "payload": payload}
                )
            )
            logger.debug(f"Heartbeat 발행: {self.heartbeat_topic}")
        except Exception as e:
            logger.error(f"Heartbeat 발행 실패: {e}")
            self.is_connected = False

    async def publish_telemetry(self, telemetry: dict[str, Any]) -> None:
        """
        센서 Telemetry 데이터를 각 Track Type별로 발행

        Simulation Loop에서 주기적으로 호출되어 센서 데이터를 Moth에 발행합니다.
        Server는 이를 수신하여:
        1. Position (GPS): Dynamic re-binding 판단용 (거리 계산)
        2. Battery: 배터리 상태 모니터링
        3. Motion (IMU): 움직임 분석

        Args:
            telemetry: 현재 센서 데이터 딕셔너리
        """
        if not self.is_connected or self.ws is None or self.ws.closed:
            return

        # ===== GPS/Position 데이터 발행 (Dynamic re-binding 판단 용) =====
        if self.telemetry_topics.get("GPS") and self.state.latitude is not None:
            try:
                gps_payload = {
                    "device_id": self.state.registry_id,
                    "latitude": self.state.latitude,
                    "longitude": self.state.longitude,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
                await self.ws.send(
                    json.dumps(
                        {
                            "type": "publish",
                            "topic": self.telemetry_topics["GPS"],
                            "payload": gps_payload,
                        }
                    )
                )
                logger.debug(f"GPS published: {self.state.latitude}, {self.state.longitude}")
            except Exception as e:
                logger.debug(f"Failed to publish GPS: {e}")

        # Battery data
        if self.telemetry_topics.get("BATTERY") and "battery_percent" in telemetry:
            try:
                battery_payload = {
                    "device_id": self.state.registry_id,
                    "percent": telemetry["battery_percent"],
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
                await self.ws.send(
                    json.dumps(
                        {
                            "type": "publish",
                            "topic": self.telemetry_topics["BATTERY"],
                            "payload": battery_payload,
                        }
                    )
                )
                logger.debug(f"Battery published: {telemetry['battery_percent']}%")
            except Exception as e:
                logger.debug(f"Failed to publish battery: {e}")

        # Motion/ODOMETRY data
        if self.telemetry_topics.get("ODOMETRY") and "motion" in telemetry:
            try:
                motion_payload = {
                    "device_id": self.state.registry_id,
                    "motion": telemetry["motion"],
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
                await self.ws.send(
                    json.dumps(
                        {
                            "type": "publish",
                            "topic": self.telemetry_topics["ODOMETRY"],
                            "payload": motion_payload,
                        }
                    )
                )
            except Exception as e:
                logger.debug(f"Failed to publish odometry: {e}")

        # Depth/Pressure (for AUV)
        if self.telemetry_topics.get("DEPTH") and "depth" in telemetry:
            try:
                depth_payload = {
                    "device_id": self.state.registry_id,
                    "depth_meters": telemetry["depth"],
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
                await self.ws.send(
                    json.dumps(
                        {
                            "type": "publish",
                            "topic": self.telemetry_topics["DEPTH"],
                            "payload": depth_payload,
                        }
                    )
                )
            except Exception as e:
                logger.debug(f"Failed to publish depth: {e}")

    async def heartbeat_loop(self) -> None:
        """
        주기적 Heartbeat 발행 루프 (백그라운드 task)

        설정된 주기(기본 10초)마다 heartbeat를 Moth에 발행합니다.
        Server의 HeartbeatMonitor가 이를 수신하여 device의 건강 상태를 추적합니다.

        - 정상 작동: heartbeat 계속 수신
        - Timeout (30초 이상 미수신): offline으로 표시 + 자동 재할당
        """
        interval = self.config.get("registry", {}).get("heartbeat_interval_seconds", 10)

        logger.info(f"Heartbeat loop 시작: interval={interval}초")

        while True:
            try:
                await asyncio.sleep(interval)
                await self.publish_heartbeat()
            except Exception as e:
                logger.debug(f"Heartbeat loop 오류: {e}")
