"""
표준 Event 모델 — 모든 Agent 간 통신의 기초.

Event는 다음 속성을 가집니다:
- event_id: 이 Event의 고유 ID
- flow_id: 같은 사건(incident)을 추적하는 체인 ID
- causation_id: 직전 Event ID (인과관계 추적)
- type: Event 타입 (detect.*, analyze.*, respond.*, learn.*, system.*)
- agent_id: 이 Event를 발행한 Agent
- timestamp: 발행 시각
- payload: Event 데이터 (타입별로 다름)
- metadata: 디버깅용 (실행시간, Agent 버전 등)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class EventType(str, Enum):
    """모든 Event 타입 정의"""

    # Detection: 원본 데이터 → 이상 감지
    DETECT_CPA = "detect.cpa"
    DETECT_ANOMALY = "detect.anomaly"
    DETECT_ZONE = "detect.zone"
    DETECT_DISTRESS = "detect.distress"
    DETECT_MINE = "detect.mine"

    # Analysis: 이벤트 → 상세 분석
    ANALYZE_ANOMALY = "analyze.anomaly"
    ANALYZE_REPORT = "analyze.report"

    # Response: 분석 → 사용자 액션
    RESPOND_ALERT = "respond.alert"
    RESPOND_COMMAND = "respond.command"

    # Learning: 피드백 → 규칙 조정
    LEARN_FEEDBACK = "learn.feedback"
    LEARN_RULE_UPDATE = "learn.rule_update"

    # System: 모니터링 & 제어
    SYSTEM_HEARTBEAT = "system.heartbeat"
    SYSTEM_ALERT_ACKNOWLEDGE = "system.alert_acknowledge"


@dataclass
class Event:
    """
    표준 Event 구조.

    Attributes:
        event_id: 이 Event의 UUID
        flow_id: 같은 사건(incident)을 추적하는 ID
        type: Event 타입
        agent_id: 이 Event를 발행한 Agent ID
        timestamp: 발행 시각 (UTC)
        payload: Event 데이터 (dict)
        metadata: 디버깅 정보 (선택)
        causation_id: 직전 Event의 event_id (선택)
    """

    event_id: str = field(default_factory=lambda: str(uuid4()))
    flow_id: str = field(default_factory=lambda: str(uuid4()))
    type: EventType = field(default=EventType.DETECT_ANOMALY)
    agent_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    causation_id: str | None = None

    def to_json(self) -> str:
        """Event를 JSON 문자열로 직렬화"""
        data = asdict(self)
        data['type'] = self.type.value
        data['timestamp'] = self.timestamp.isoformat()
        return json.dumps(data, default=str)

    @classmethod
    def from_json(cls, json_str: str) -> Event:
        """JSON 문자열에서 Event 역직렬화"""
        data = json.loads(json_str)
        data['type'] = EventType(data['type'])
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        if data['timestamp'].tzinfo is None:
            data['timestamp'] = data['timestamp'].replace(tzinfo=timezone.utc)
        return cls(**data)

    def __repr__(self) -> str:
        return (
            f"Event(type={self.type.value}, agent={self.agent_id}, "
            f"flow={self.flow_id[:8]}..., event={self.event_id[:8]}...)"
        )
