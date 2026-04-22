"""
Event 기반 Redis 채널 매핑.

Event 타입과 payload에 따라 발행할 Redis 채널을 결정.
"""

from __future__ import annotations

from typing import Optional
from .event import Event, EventType


# ─────────────────────────────────────────────────────────────────────────────
# 채널 이름 템플릿
# ─────────────────────────────────────────────────────────────────────────────

CHANNEL_TEMPLATES = {
    # Detection
    EventType.DETECT_CPA: "detect.cpa.{platform_id}",
    EventType.DETECT_ANOMALY: "detect.anomaly.{platform_id}",
    EventType.DETECT_ZONE: "detect.zone.{platform_id}",
    EventType.DETECT_DISTRESS: "detect.distress.{platform_id}",
    EventType.DETECT_MINE: "detect.mine.{platform_id}",

    # Analysis
    EventType.ANALYZE_ANOMALY: "analyze.anomaly.{alert_id}",
    EventType.ANALYZE_REPORT: "analyze.report.{alert_id}",

    # Response
    EventType.RESPOND_ALERT: "respond.alert.{alert_id}",
    EventType.RESPOND_COMMAND: "respond.command.{flow_id}",

    # Learning
    EventType.LEARN_FEEDBACK: "learn.feedback.{flow_id}",
    EventType.LEARN_RULE_UPDATE: "learn.rule_update.{agent_id}",

    # System
    EventType.SYSTEM_HEARTBEAT: "system.heartbeat.{agent_id}",
    EventType.SYSTEM_ALERT_ACKNOWLEDGE: "system.ack.{alert_id}",
}

# ─────────────────────────────────────────────────────────────────────────────
# 구독 패턴 (pub/sub 패턴 매칭)
# ─────────────────────────────────────────────────────────────────────────────

SUBSCRIBE_PATTERNS = {
    # Detection Agent가 구독할 패턴
    "detection": "detect.*",

    # Analysis Agent가 구독할 패턴
    "analysis": "detect.*",

    # Response Agent가 구독할 패턴
    "response": "analyze.*",

    # Learning Agent가 구독할 패턴
    "learning": "system.ack.*",

    # Supervisor가 구독할 패턴
    "supervisor": "system.heartbeat.*",
}


def get_channel_for_event(event: Event) -> str:
    """
    Event의 type과 payload에 따라 Redis 채널 결정.

    Args:
        event: Event 객체

    Returns:
        Redis 채널 이름 (예: "detect.cpa.vessel-123")

    Raises:
        ValueError: 알 수 없는 Event 타입
    """
    template = CHANNEL_TEMPLATES.get(event.type)
    if not template:
        raise ValueError(f"Unknown event type: {event.type}")

    # 템플릿의 {placeholder} 채우기
    substitutions = {}

    if "{platform_id}" in template:
        substitutions["platform_id"] = event.payload.get(
            "platform_id", "unknown"
        )

    if "{alert_id}" in template:
        substitutions["alert_id"] = event.payload.get("alert_id", "unknown")

    if "{flow_id}" in template:
        substitutions["flow_id"] = event.flow_id

    if "{agent_id}" in template:
        substitutions["agent_id"] = event.payload.get(
            "target_agent_id", event.agent_id
        )

    # 모든 placeholder 대체
    channel = template
    for key, value in substitutions.items():
        channel = channel.replace(f"{{{key}}}", str(value))

    # 만약 아직도 {placeholder}가 남아있으면 오류
    if "{" in channel:
        raise ValueError(
            f"Incomplete channel template after substitution: {channel} "
            f"(event type: {event.type.value}, payload keys: {list(event.payload.keys())})"
        )

    return channel


def get_subscribe_pattern(agent_category: str) -> str:
    """
    Agent 카테고리에 따라 구독 패턴 반환.

    Args:
        agent_category: "detection" | "analysis" | "response" | "learning" | "supervisor"

    Returns:
        Redis pub/sub 패턴 (예: "detect.*")
    """
    pattern = SUBSCRIBE_PATTERNS.get(agent_category)
    if not pattern:
        raise ValueError(
            f"Unknown agent category: {agent_category}. "
            f"Valid: {list(SUBSCRIBE_PATTERNS.keys())}"
        )
    return pattern


# ─────────────────────────────────────────────────────────────────────────────
# 유틸 함수들
# ─────────────────────────────────────────────────────────────────────────────


def is_event_type(message_type: str, event_type: EventType) -> bool:
    """
    메시지 타입이 특정 Event 타입과 일치하는지 확인.

    예: is_event_type("detect.cpa", EventType.DETECT_CPA) → True
    """
    return message_type == event_type.value


def extract_entity_id(channel: str, entity_type: str) -> Optional[str]:
    """
    채널 이름에서 특정 entity ID 추출.

    Args:
        channel: Redis 채널 이름 (예: "detect.cpa.vessel-123")
        entity_type: "platform_id" | "alert_id" | "flow_id" | "agent_id"

    Returns:
        추출된 ID, 또는 None
    """
    parts = channel.split(".")
    if entity_type == "platform_id" and len(parts) >= 3:
        return ".".join(parts[2:])  # "detect.cpa.vessel-123" → "vessel-123"
    if entity_type == "alert_id" and len(parts) >= 3:
        return ".".join(parts[2:])  # "analyze.anomaly.alert-uuid" → "alert-uuid"
    return None
