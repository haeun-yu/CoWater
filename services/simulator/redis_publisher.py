"""
Redis pub/sub를 통한 NMEA 데이터 발행.

시뮬레이터에서 생성한 AIS NMEA 데이터를 Redis pub/sub 채널로 직접 발행.
Moth 채널 대신 Redis를 사용하여 안정성 확보.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from urllib.parse import urlparse

import redis.asyncio as aioredis

from config import settings

logger = logging.getLogger(__name__)


class RedisPublisher:
    """Redis pub/sub을 통해 NMEA 데이터를 발행."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=512)
        self._redis: aioredis.Redis | None = None
        self._connected = False

    async def publish(self, nmea_sentence: str) -> None:
        """NMEA 문장을 큐에 넣는다 (논블로킹)."""
        try:
            self._queue.put_nowait(nmea_sentence)
        except asyncio.QueueFull:
            logger.warning("Redis publish queue full — dropping frame")

    async def run(self) -> None:
        """Redis 연결 + 발행 루프."""
        while True:
            try:
                await self._publish_loop()
            except Exception as e:
                logger.warning("Redis publisher error: %s, reconnecting...", e)
                self._connected = False
            await asyncio.sleep(5.0)

    async def _publish_loop(self) -> None:
        """Redis 연결 유지 및 데이터 발행."""
        parsed = urlparse(settings.redis_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 6379
        db = int(parsed.path.lstrip("/")) if parsed.path else 0

        async with aioredis.from_url(
            settings.redis_url, decode_responses=True
        ) as redis:
            self._redis = redis
            self._connected = True
            logger.info("Redis publisher connected → %s:%d (db=%d)", host, port, db)

            sent_count = 0
            while True:
                try:
                    # 큐에서 메시지 꺼내기 (최대 100ms 대기)
                    sentence = await asyncio.wait_for(
                        self._queue.get(), timeout=0.1
                    )

                    # NMEA를 JSON으로 변환하여 platform.report.{mmsi} 채널에 발행
                    # NMEA 문장에서 MMSI 추출 (대략적: "!AIVDM,...*XX" 형식)
                    try:
                        # 간단한 파싱: NMEA 문장에는 MMSI 정보가 암호화되어 있음
                        # 여기서는 raw NMEA를 그대로 발행하고, core에서 파싱하도록 함
                        payload = json.dumps(
                            {
                                "nmea": sentence,
                                "timestamp": datetime.utcnow().isoformat(),
                                "source": "simulator",
                            }
                        )

                        # 여러 채널에 발행 (core와 agents가 구독)
                        await redis.publish("ais.nmea.raw", payload)

                        sent_count += 1
                        if sent_count % 15 == 0:
                            logger.debug("Redis publisher sent %d messages", sent_count)
                    except Exception as e:
                        logger.warning("Failed to publish message: %s", e)

                except asyncio.TimeoutError:
                    pass
