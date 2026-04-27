"""
Event 시스템 기본 테스트.

Event 생성, 직렬화, 채널 매핑 등이 제대로 작동하는지 확인.
"""

import json
from datetime import datetime

import pytest

from shared.events import (
    Event,
    EventType,
    get_channel_for_event,
    DetectCPAPayload,
)


def test_event_creation():
    """Event 생성"""
    event = Event(
        flow_id="test-flow-123",
        type=EventType.DETECT_CPA,
        agent_id="detection-cpa",
        payload={
            "platform_id": "vessel-1",
            "target_platform_id": "vessel-2",
            "cpa_minutes": 5.0,
        },
    )

    assert event.type == EventType.DETECT_CPA
    assert event.agent_id == "detection-cpa"
    assert event.flow_id == "test-flow-123"
    assert event.payload["platform_id"] == "vessel-1"


def test_event_serialization():
    """Event JSON 직렬화/역직렬화"""
    original = Event(
        flow_id="test-flow-123",
        type=EventType.DETECT_ANOMALY,
        agent_id="detection-anomaly",
        payload={"platform_id": "vessel-1", "anomaly_type": "rot"},
    )

    # 직렬화
    json_str = original.to_json()
    data = json.loads(json_str)

    assert data["type"] == "detect.anomaly"
    assert data["agent_id"] == "detection-anomaly"

    # 역직렬화
    restored = Event.from_json(json_str)

    assert restored.event_id == original.event_id
    assert restored.type == original.type
    assert restored.payload == original.payload


def test_channel_resolution():
    """Event → Redis 채널 매핑"""
    event = Event(
        flow_id="test-flow",
        type=EventType.DETECT_CPA,
        agent_id="detection-cpa",
        payload={
            "platform_id": "vessel-123",
            "target_platform_id": "vessel-456",
            "cpa_minutes": 3.0,
        },
    )

    channel = get_channel_for_event(event)
    assert channel == "detect.cpa.vessel-123"


def test_channel_resolution_with_alert():
    """analyze.anomaly 이벤트의 채널"""
    event = Event(
        flow_id="test-flow",
        type=EventType.ANALYZE_ANOMALY,
        agent_id="analysis-anomaly",
        payload={
            "alert_id": "alert-uuid-123",
            "analysis_result": "...",
        },
    )

    channel = get_channel_for_event(event)
    assert channel == "analyze.anomaly.alert-uuid-123"


def test_channel_resolution_with_mine_detection():
    event = Event(
        flow_id="test-flow",
        type=EventType.DETECT_MINE,
        agent_id="detection-mine",
        payload={
            "platform_id": "auv-01",
            "contact_id": "contact-123",
        },
    )

    channel = get_channel_for_event(event)
    assert channel == "detect.mine.auv-01"


def test_causation_chain():
    """Event chain: detect → analyze → respond"""
    # 1. Detection event
    detect_event = Event(
        flow_id="incident-001",
        type=EventType.DETECT_CPA,
        agent_id="detection-cpa",
        payload={"platform_id": "v1", "cpa_minutes": 3.0},
    )

    # 2. Analysis event (causation_id 참조)
    analyze_event = Event(
        flow_id="incident-001",  # 동일한 flow
        type=EventType.ANALYZE_ANOMALY,
        agent_id="analysis-anomaly",
        payload={"analysis_result": "high risk"},
        causation_id=detect_event.event_id,  # 직전 event 참조
    )

    # 3. Response event
    respond_event = Event(
        flow_id="incident-001",  # 동일한 flow
        type=EventType.RESPOND_ALERT,
        agent_id="response-alert",
        payload={"alert_id": "..."},
        causation_id=analyze_event.event_id,
    )

    # 검증: 같은 사건이 추적되어야 함
    assert detect_event.flow_id == analyze_event.flow_id == respond_event.flow_id
    assert analyze_event.causation_id == detect_event.event_id
    assert respond_event.causation_id == analyze_event.event_id


def test_payload_dataclass():
    """DetectCPAPayload 활용"""
    payload_dict = {
        "platform_id": "vessel-1",
        "target_platform_id": "vessel-2",
        "cpa_minutes": 5.0,
        "tcpa_minutes": 10.0,
        "latitude": 37.5,
        "longitude": 126.5,
        "platform_name": "Vessel A",
        "target_name": "Vessel B",
        "platform_sog": 10.0,
        "platform_cog": 90.0,
        "target_sog": 8.0,
        "target_cog": 180.0,
    }

    payload = DetectCPAPayload(**payload_dict)
    assert payload.platform_id == "vessel-1"
    assert payload.cpa_minutes == 5.0
