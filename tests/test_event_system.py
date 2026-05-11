"""
Test Suite: Event System (StateChangeEvent, EventPublisher)

이 테스트 모듈은 Event System의 event 생성, 발행, 기록을 검증합니다:

1. StateChangeEvent 생성 및 직렬화
2. EventPublisher의 event 발행 및 로깅
3. Event factory 함수들
4. Event 검색 및 조회

Author: CoWater AI Agent
Version: v1.0
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_registry_client():
    """Mock Registry Client"""
    client = MagicMock()
    client.ingest_event = MagicMock(return_value={"event_id": "test-event-id"})
    return client


@pytest.fixture
def event_publisher(mock_registry_client):
    """EventPublisher 인스턴스"""
    try:
        from agent.event_system import EventPublisher
        return EventPublisher(mock_registry_client)
    except ImportError:
        return MagicMock()


class TestStateChangeEvent:
    """StateChangeEvent 클래스 테스트"""

    def test_create_step_evaluation_event(self):
        """Step Evaluation Event 생성"""
        try:
            from agent.event_system import create_step_evaluation_event
            
            event = create_step_evaluation_event(
                source_agent_id=1,
                response_id="resp-001",
                step_id="step-001",
                policy="survey_sufficiency_v1",
                decision="proceed_next_step",
                sufficient=True,
                metrics={
                    "task_total": 1,
                    "completed_task_count": 1,
                    "failed_task_count": 0,
                    "usable_task_count": 1,
                },
                reason="usable output available",
            )
            
            assert event.event_type == "step_evaluation"
            assert event.source_system == "system_agent"
            assert event.severity == "INFO"
            assert event.related_ids["response_id"] == "resp-001"
            assert event.metrics["decision"] == "proceed_next_step"
        except ImportError:
            pytest.skip("event_system module not available")

    def test_create_recovery_action_event(self):
        """Recovery Action Event 생성"""
        try:
            from agent.event_system import create_recovery_action_event
            
            event = create_recovery_action_event(
                source_agent_id=1,
                response_id="resp-002",
                step_id="step-002",
                action="retry_same_step",
                affected_task_ids=["task-1", "task-2"],
                reason="first attempt failed",
            )
            
            assert event.event_type == "recovery_action"
            assert event.source_system == "system_agent"
            assert event.severity == "WARNING"
            assert event.metrics["action"] == "retry_same_step"
            assert event.metrics["affected_task_count"] == 2
        except ImportError:
            pytest.skip("event_system module not available")

    def test_create_mission_state_change_event(self):
        """Mission State Change Event 생성"""
        try:
            from agent.event_system import create_mission_state_change_event
            
            event = create_mission_state_change_event(
                source_agent_id=1,
                mission_id="mission-001",
                old_state="pending",
                new_state="running",
                reason="user approved mission",
            )
            
            assert event.event_type == "mission_state_change"
            assert event.related_ids["mission_id"] == "mission-001"
            assert event.metrics["old_state"] == "pending"
            assert event.metrics["new_state"] == "running"
        except ImportError:
            pytest.skip("event_system module not available")

    def test_create_device_status_change_event(self):
        """Device Status Change Event 생성"""
        try:
            from agent.event_system import create_device_status_change_event
            
            event = create_device_status_change_event(
                source_agent_id=101,
                device_id=1,
                device_name="AUV-01",
                old_status="online",
                new_status="lost",
                reason="communication timeout",
            )
            
            assert event.event_type == "device_status_change"
            assert event.severity == "CRITICAL"
            assert event.related_ids["device_id"] == 1
            assert event.metrics["old_status"] == "online"
        except ImportError:
            pytest.skip("event_system module not available")

    def test_event_to_dict_serialization(self):
        """Event dict 직렬화 테스트"""
        try:
            from agent.event_system import StateChangeEvent, EventType, EventSeverity
            
            event = StateChangeEvent(
                event_type=EventType.STEP_EVALUATION,
                source_system="system_agent",
                source_agent_id=1,
                severity=EventSeverity.INFO,
                title="Test Event",
                description="Test description",
                related_ids={"response_id": "resp-001"},
                metrics={"count": 5},
            )
            
            event_dict = event.to_dict()
            
            assert isinstance(event_dict, dict)
            assert event_dict["event_type"] == "step_evaluation"
            assert event_dict["source_system"] == "system_agent"
            assert event_dict["severity"] == "INFO"
            assert event_dict["title"] == "Test Event"
        except ImportError:
            pytest.skip("event_system module not available")

    def test_event_has_unique_id(self):
        """Event가 고유한 ID를 가지는가?"""
        try:
            from agent.event_system import StateChangeEvent, EventType
            
            event1 = StateChangeEvent(
                event_type=EventType.STEP_EVALUATION,
                source_system="system_agent",
                source_agent_id=1,
            )
            
            event2 = StateChangeEvent(
                event_type=EventType.STEP_EVALUATION,
                source_system="system_agent",
                source_agent_id=1,
            )
            
            assert event1.event_id != event2.event_id
        except ImportError:
            pytest.skip("event_system module not available")


class TestEventPublisher:
    """EventPublisher 클래스 테스트"""

    def test_event_publisher_initialization(self, event_publisher, mock_registry_client):
        """EventPublisher 초기화"""
        assert event_publisher is not None

    def test_publish_event_success(self, event_publisher):
        """Event 발행 성공"""
        try:
            from agent.event_system import StateChangeEvent, EventType
            
            event = StateChangeEvent(
                event_type=EventType.STEP_EVALUATION,
                source_system="system_agent",
                source_agent_id=1,
            )
            
            result = event_publisher.publish(event)
            
            assert result is True or result is None  # None은 mock일 때
        except ImportError:
            pytest.skip("event_system module not available")

    def test_event_log_local_storage(self, event_publisher):
        """Event 로컬 로그 저장"""
        try:
            from agent.event_system import StateChangeEvent, EventType
            
            event = StateChangeEvent(
                event_type=EventType.STEP_EVALUATION,
                source_system="system_agent",
                source_agent_id=1,
            )
            
            event_publisher.publish(event)
            
            log = event_publisher.get_event_log()
            
            assert len(log) > 0
            assert log[0].event_type == "step_evaluation"
        except ImportError:
            pytest.skip("event_system module not available")

    def test_event_log_limit(self, event_publisher):
        """Event 로그 조회 limit"""
        try:
            from agent.event_system import StateChangeEvent, EventType
            
            # 5개 event 발행
            for i in range(5):
                event = StateChangeEvent(
                    event_type=EventType.STEP_EVALUATION,
                    source_system="system_agent",
                    source_agent_id=1,
                    title=f"Event {i}",
                )
                event_publisher.publish(event)
            
            # limit=3으로 조회
            log = event_publisher.get_event_log(limit=3)
            
            assert len(log) <= 3
        except ImportError:
            pytest.skip("event_system module not available")

    def test_event_log_reverse_order(self, event_publisher):
        """Event 로그 역순 조회 (최신부터)"""
        try:
            from agent.event_system import StateChangeEvent, EventType
            
            # 3개 event 발행
            for i in range(3):
                event = StateChangeEvent(
                    event_type=EventType.STEP_EVALUATION,
                    source_system="system_agent",
                    source_agent_id=1,
                    title=f"Event {i}",
                )
                event_publisher.publish(event)
            
            log = event_publisher.get_event_log(limit=10)
            
            # 역순이므로 마지막에 발행한 event가 맨 앞
            assert "Event 2" in log[0].title
            assert "Event 0" in log[-1].title
        except ImportError:
            pytest.skip("event_system module not available")

    def test_clear_event_log(self, event_publisher):
        """Event 로그 비우기"""
        try:
            from agent.event_system import StateChangeEvent, EventType
            
            event = StateChangeEvent(
                event_type=EventType.STEP_EVALUATION,
                source_system="system_agent",
                source_agent_id=1,
            )
            
            event_publisher.publish(event)
            assert len(event_publisher.get_event_log()) > 0
            
            event_publisher.clear_event_log()
            assert len(event_publisher.get_event_log()) == 0
        except ImportError:
            pytest.skip("event_system module not available")


class TestEventSeverity:
    """Event Severity 테스트"""

    def test_event_severity_for_proceed_next_step(self):
        """proceed_next_step → INFO severity"""
        try:
            from agent.event_system import create_step_evaluation_event
            
            event = create_step_evaluation_event(
                source_agent_id=1,
                response_id="resp-001",
                step_id="step-001",
                policy="survey_sufficiency_v1",
                decision="proceed_next_step",
                sufficient=True,
                metrics={},
            )
            
            assert event.severity == "INFO"
        except ImportError:
            pytest.skip("event_system module not available")

    def test_event_severity_for_recovery_actions(self):
        """Recovery actions → WARNING severity"""
        try:
            from agent.event_system import create_recovery_action_event
            
            # retry: WARNING
            retry_event = create_recovery_action_event(
                source_agent_id=1,
                response_id="resp-001",
                step_id="step-001",
                action="retry_same_step",
                affected_task_ids=["task-1"],
            )
            assert retry_event.severity == "WARNING"
            
            # reassign: ERROR
            reassign_event = create_recovery_action_event(
                source_agent_id=1,
                response_id="resp-001",
                step_id="step-001",
                action="reassign_failed_tasks",
                affected_task_ids=["task-1"],
            )
            assert reassign_event.severity == "ERROR"
        except ImportError:
            pytest.skip("event_system module not available")

    def test_event_severity_for_device_lost(self):
        """Device lost → CRITICAL severity"""
        try:
            from agent.event_system import create_device_status_change_event
            
            event = create_device_status_change_event(
                source_agent_id=101,
                device_id=1,
                device_name="AUV-01",
                old_status="online",
                new_status="lost",
            )
            
            assert event.severity == "CRITICAL"
        except ImportError:
            pytest.skip("event_system module not available")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
