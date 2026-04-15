"""
Detection Agent 기본 클래스.

모든 Detection Agent가 상속하는 기본 클래스.
- Event 발행 로직
- Fallback 처리 (필수 데이터 부족 시 API 호출)
- Heartbeat 송신
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import asdict
from datetime import datetime
from typing import Optional

import httpx
import redis.asyncio as aioredis

from shared.events import Event, EventType, get_channel_for_event
from shared.schemas.report import PlatformReport

logger = logging.getLogger(__name__)


class DetectionAgent(ABC):
    """Detection 계층 Agent 기본 클래스"""

    agent_id: str = "detection-base"
    agent_type: str = "detection"

    def __init__(self, redis: aioredis.Redis, core_api_url: str) -> None:
        self._redis = redis
        self._core_api_url = core_api_url

    @abstractmethod
    async def on_platform_report(self, report: PlatformReport) -> None:
        """
        선박 위치 보고 수신.

        Args:
            report: PlatformReport 객체
        """
        pass

    # ─────────────────────────────────────────────────────────────────────────
    # Event 발행
    # ─────────────────────────────────────────────────────────────────────────

    async def emit_event(
        self,
        event_type: EventType,
        payload: dict,
        flow_id: Optional[str] = None,
        causation_id: Optional[str] = None,
    ) -> None:
        """
        Event 발행.

        Args:
            event_type: Event 타입
            payload: Event payload (dict)
            flow_id: 사건 ID (기본: 새로 생성)
            causation_id: 직전 Event ID (선택)
        """
        from uuid import uuid4

        event = Event(
            flow_id=flow_id or str(uuid4()),
            type=event_type,
            agent_id=self.agent_id,
            payload=payload,
            causation_id=causation_id,
            timestamp=datetime.utcnow(),
        )

        channel = get_channel_for_event(event)
        await self._redis.publish(channel, event.to_json())

        logger.info(
            "Event emitted: %s → %s (flow=%s)",
            event_type.value,
            channel,
            event.flow_id[:8],
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Fallback 처리
    # ─────────────────────────────────────────────────────────────────────────

    async def enrich_payload(
        self, payload: dict, required_fields: list[str]
    ) -> Optional[dict]:
        """
        필요시 추가 정보를 요청하여 payload 보충.

        필요한 필드가 모두 있으면 그냥 반환.
        부족하면:
        1. API 호출로 데이터 추가
        2. 실패하면 부분 데이터로 처리 가능한지 확인
        3. 불가능하면 None 반환 (Event 처리 스킵)

        Args:
            payload: 현재 payload
            required_fields: 필수 필드 이름 목록

        Returns:
            보충된 payload, 또는 None (처리 불가능한 경우)
        """
        # 1. 필수 필드 확인
        missing = [f for f in required_fields if f not in payload]

        if not missing:
            return payload  # OK, 그냥 반환

        logger.debug(
            "Missing fields in payload: %s. Attempting to enrich...", missing
        )

        # 2. 추가 정보 요청 시도
        try:
            enriched = await self._fetch_missing_data(missing, payload)
            if enriched:
                payload.update(enriched)
                logger.debug("Payload enriched with: %s", list(enriched.keys()))
                return payload
        except Exception as e:
            logger.warning("Failed to enrich payload: %s. Proceeding partially.", e)

        # 3. Fallback: 부분 데이터로도 처리 가능?
        if self._can_process_with_partial_data(payload, missing):
            logger.warning(
                "Processing with partial data (missing: %s)", missing
            )
            return payload

        # 4. 불가능하면 skip
        logger.error(
            "Cannot process event without required fields: %s. Skipping.", missing
        )
        return None

    async def _fetch_missing_data(
        self, missing: list[str], context: dict
    ) -> dict:
        """
        Core API 또는 Redis에서 누락된 데이터 조회.

        Args:
            missing: 누락된 필드명 목록
            context: 현재 context (platform_id 등)

        Returns:
            조회된 데이터 dict
        """
        enriched = {}

        for field in missing:
            if field == "platform_history":
                history = await self._get_platform_history(
                    context.get("platform_id"), limit=20
                )
                if history:
                    enriched["platform_history"] = history

            elif field == "nearby_platforms":
                nearby = await self._get_nearby_platforms(
                    context.get("latitude"),
                    context.get("longitude"),
                    radius_nm=5.0,
                )
                if nearby:
                    enriched["nearby_platforms"] = nearby

            elif field == "zone_context":
                zones = await self._get_nearby_zones(
                    context.get("latitude"),
                    context.get("longitude"),
                    radius_nm=5.0,
                )
                if zones:
                    enriched["zone_context"] = zones

        return enriched

    async def _get_platform_history(
        self, platform_id: str, limit: int = 20
    ) -> Optional[list[dict]]:
        """
        선박의 최근 N개 위치 조회.

        1. Redis 캐시 확인 (빠름, 최신 1개만)
        2. Core API 호출 (슬로우, 최근 N개)
        3. 모두 실패 → None (fallback)
        """
        if not platform_id:
            return None

        try:
            # 1. Redis cache (최신 1개)
            cache_key = f"platform:state:{platform_id}"
            cached = await self._redis.get(cache_key)
            if cached:
                data = json.loads(cached)
                return [data]  # 최신 1개를 리스트로
        except Exception as e:
            logger.debug("Redis cache miss: %s", e)

        try:
            # 2. Core API (최근 N개)
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(
                    f"{self._core_api_url}/platforms/{platform_id}/track"
                    f"?limit={limit}",
                    timeout=2.0,
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.debug("Core API request failed: %s", e)

        # 3. Fallback
        return None

    async def _get_nearby_platforms(
        self, latitude: float, longitude: float, radius_nm: float = 5.0
    ) -> Optional[list[dict]]:
        """근처 선박 목록 조회"""
        if latitude is None or longitude is None:
            return None

        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(
                    f"{self._core_api_url}/platforms/{latitude},{longitude}"
                    f"/nearby?radius_nm={radius_nm}",
                    timeout=2.0,
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.debug("Failed to fetch nearby platforms: %s", e)
            return None

    async def _get_nearby_zones(
        self, latitude: float, longitude: float, radius_nm: float = 5.0
    ) -> Optional[list[dict]]:
        """근처 구역 목록 조회"""
        if latitude is None or longitude is None:
            return None

        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(
                    f"{self._core_api_url}/platforms/{latitude},{longitude}"
                    f"/zones?radius_nm={radius_nm}",
                    timeout=2.0,
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.debug("Failed to fetch nearby zones: %s", e)
            return None

    def _can_process_with_partial_data(
        self, payload: dict, missing: list[str]
    ) -> bool:
        """
        부분 데이터로 처리 가능한지 판단.

        기본: False (subclass에서 override)

        Args:
            payload: 현재 payload
            missing: 누락된 필드들

        Returns:
            True면 부분 데이터로 처리, False면 skip
        """
        return False

    # ─────────────────────────────────────────────────────────────────────────
    # Heartbeat
    # ─────────────────────────────────────────────────────────────────────────

    async def send_heartbeat(self) -> None:
        """주기적으로 agent 상태 신호 송신"""
        event = Event(
            flow_id="heartbeat",
            type=EventType.SYSTEM_HEARTBEAT,
            agent_id=self.agent_id,
            payload={
                "status": "healthy",
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

        channel = get_channel_for_event(event)
        await self._redis.publish(channel, event.to_json())
