"""
State Change Event System: Mission/Step/Task 상태 변화 이벤트

Event를 통해 모든 의사결정, 상태 변화, 복구 작업을 기록하여
P9 (기록 가능성) 원칙을 구현합니다.

Event 유형:
- step_evaluation: Step 평가 결과
- task_execution: Task 실행 결과
- recovery_action: 재시도/재할당 등 복구 작업
- mission_state_change: Mission 상태 변화
- alert_generated: 경고 생성

Author: CoWater AI Agent
Version: v1.0
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4


class EventSeverity(Enum):
    """Event 심각도"""
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class EventType(Enum):
    """Event 유형"""
    STEP_EVALUATION = "SYS_MISSION_UPDATED"
    TASK_EXECUTION = "SYS_TASK_RESULT"
    RECOVERY_ACTION = "SYS_MISSION_UPDATED"
    MISSION_STATE_CHANGE = "SYS_MISSION_UPDATED"
    ALERT_GENERATED = "SYS_ANOMALY_DETECTED"
    DEVICE_STATUS_CHANGE = "SYS_ANOMALY_DETECTED"
    POLICY_DECISION = "SYS_POLICY_DECISION"


class StateChangeEvent:
    """
    상태 변화 이벤트 (P9: 기록 가능성)
    
    모든 중요한 판단, 상태 변화, 복구 작업을 이벤트로 기록합니다.
    """

    def __init__(
        self,
        event_type: EventType | str,
        source_system: str,
        source_agent_id: int | str,
        severity: EventSeverity | str = EventSeverity.INFO,
        title: str = "",
        description: str = "",
        related_ids: Optional[dict[str, Any]] = None,
        metrics: Optional[dict[str, Any]] = None,
        recovery_history: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        """
        Args:
            event_type: Event 유형 (예: step_evaluation, task_execution)
            source_system: 이벤트 발생 시스템 (예: system_agent, device_agent)
            source_agent_id: 이벤트 발생 agent ID
            severity: 심각도 (INFO, WARNING, ERROR, CRITICAL)
            title: 간단한 제목
            description: 상세 설명
            related_ids: 관련 entity ID 모음 (response_id, step_id, task_id, mission_id 등)
            metrics: 관련 메트릭 (completed_count, failed_count, usable_count 등)
            recovery_history: 복구 이력 (retry/reassign 등)
        """
        self.event_id = str(uuid4())
        self.created_at = datetime.now(timezone.utc).isoformat() + "Z"
        
        # Event 유형 정규화
        if isinstance(event_type, EventType):
            self.event_type = event_type.value
        else:
            self.event_type = str(event_type)
        
        # Severity 정규화
        if isinstance(severity, EventSeverity):
            self.severity = severity.value
        else:
            normalized_severity = str(severity).upper()
            self.severity = "WARNING" if normalized_severity == "ERROR" else normalized_severity
        
        self.source_system = str(source_system)
        self.source_agent_id = source_agent_id
        self.title = str(title)
        self.description = str(description)
        self.related_ids = related_ids or {}
        self.metrics = metrics or {}
        self.recovery_history = recovery_history or []

    def to_dict(self) -> dict[str, Any]:
        """Event를 dict로 직렬화 (JSON 변환용)"""
        return {
            "event_id": self.event_id,
            "created_at": self.created_at,
            "event_type": self.event_type,
            "severity": self.severity,
            "source_system": self.source_system,
            "source_agent_id": self.source_agent_id,
            "title": self.title,
            "description": self.description,
            "target_agents": self._default_target_agents(),
            "data": {
                "related_ids": self.related_ids,
                "metrics": self.metrics,
                "recovery_history": self.recovery_history,
            },
        }

    def _default_target_agents(self) -> list[str]:
        routing = {
            "SYS_TASK_RESULT": ["MissionPlanner", "SystemSentinel", "InsightReporter"],
            "SYS_ANOMALY_DETECTED": ["PolicyManager", "InsightReporter"],
            "SYS_POLICY_DECISION": ["MissionPlanner", "InsightReporter"],
            "SYS_MISSION_UPDATED": ["InsightReporter", "SystemSentinel"],
        }
        return routing.get(self.event_type, ["InsightReporter"])

    def __repr__(self) -> str:
        return (
            f"StateChangeEvent("
            f"event_id={self.event_id[:8]}..., "
            f"type={self.event_type}, "
            f"severity={self.severity}, "
            f"at={self.created_at})"
        )


class EventPublisher:
    """
    이벤트 발행자 (P9: 기록 가능성)
    
    Events를 Registry 또는 Moth로 발행합니다.
    """

    def __init__(self, registry_client: Any) -> None:
        """
        Args:
            registry_client: Registry API client (ingest_event 메서드 필요)
        """
        self.registry_client = registry_client
        self.local_event_log: list[StateChangeEvent] = []

    def publish(self, event: StateChangeEvent) -> bool:
        """
        Event를 발행 (Registry 또는 로컬 로그)
        
        Args:
            event: 발행할 event
            
        Returns:
            성공 여부
        """
        # P9 (기록 가능성): 로컬 로그에 기록
        self.local_event_log.append(event)
        
        # Registry로 발행
        try:
            if self.registry_client:
                self.registry_client.ingest_event(event.to_dict())
            return True
        except Exception as e:
            # 발행 실패해도 로컬 로그는 유지 (가용성 우선)
            return False

    def get_event_log(self, limit: int = 100) -> list[StateChangeEvent]:
        """최근 event 로그 조회 (역순)"""
        return list(reversed(self.local_event_log[-limit:]))

    def clear_event_log(self) -> None:
        """로컬 event 로그 비우기"""
        self.local_event_log.clear()


# ============================================================================
# Factory Functions: Event 생성 헬퍼
# ============================================================================

def create_step_evaluation_event(
    source_agent_id: int | str,
    response_id: str,
    step_id: str,
    policy: str,
    decision: str,
    sufficient: bool,
    metrics: dict[str, Any],
    reason: str = "",
) -> StateChangeEvent:
    """
    Step 평가 이벤트 생성 (P3 보고 기반)
    
    Args:
        source_agent_id: System Agent ID
        response_id: Response ID
        step_id: Step ID
        policy: 사용된 정책 (survey_sufficiency_v1, all_tasks_success_v1)
        decision: 의사결정 (proceed_next_step, retry_same_step 등)
        sufficient: 조건 충족 여부
        metrics: 메트릭 (completed_count, failed_count 등)
        reason: 결정 이유
    """
    severity = EventSeverity.INFO if decision == "proceed_next_step" else EventSeverity.WARNING
    
    return StateChangeEvent(
        event_type=EventType.STEP_EVALUATION,
        source_system="system_agent",
        source_agent_id=source_agent_id,
        severity=severity,
        title=f"Step Evaluation: {decision}",
        description=reason,
        related_ids={
            "response_id": response_id,
            "step_id": step_id,
        },
        metrics={
            **metrics,
            "policy": policy,
            "decision": decision,
            "sufficient": sufficient,
        },
    )


def create_recovery_action_event(
    source_agent_id: int | str,
    response_id: str,
    step_id: str,
    action: str,  # "retry_same_step" | "reassign_failed_tasks"
    affected_task_ids: list[str],
    reason: str = "",
) -> StateChangeEvent:
    """
    복구 작업 이벤트 생성 (P5 최종 판단 + P9 기록)
    
    Args:
        source_agent_id: System Agent ID
        response_id: Response ID
        step_id: Step ID
        action: 복구 액션 (retry_same_step, reassign_failed_tasks)
        affected_task_ids: 영향받는 task ID 목록
        reason: 복구 이유
    """
    severity = EventSeverity.WARNING if action == "retry_same_step" else EventSeverity.WARNING
    
    return StateChangeEvent(
        event_type=EventType.RECOVERY_ACTION,
        source_system="system_agent",
        source_agent_id=source_agent_id,
        severity=severity,
        title=f"Recovery Action: {action}",
        description=reason,
        related_ids={
            "response_id": response_id,
            "step_id": step_id,
            "affected_task_ids": affected_task_ids,
        },
        metrics={
            "action": action,
            "affected_task_count": len(affected_task_ids),
        },
    )


def create_mission_state_change_event(
    source_agent_id: int | str,
    mission_id: str,
    old_state: str,
    new_state: str,
    reason: str = "",
) -> StateChangeEvent:
    """
    Mission 상태 변화 이벤트 (P9 기록)
    
    Args:
        source_agent_id: System Agent ID
        mission_id: Mission ID
        old_state: 이전 상태 (READY, IN_PROGRESS, COMPLETED, FAILED, CANCELLED)
        new_state: 새로운 상태
        reason: 상태 변화 이유
    """
    severity = EventSeverity.INFO if str(new_state).upper() == "COMPLETED" else EventSeverity.WARNING
    
    return StateChangeEvent(
        event_type=EventType.MISSION_STATE_CHANGE,
        source_system="system_agent",
        source_agent_id=source_agent_id,
        severity=severity,
        title=f"Mission State Change: {old_state} → {new_state}",
        description=reason,
        related_ids={
            "mission_id": mission_id,
        },
        metrics={
            "old_state": old_state,
            "new_state": new_state,
        },
    )


def create_device_status_change_event(
    source_agent_id: int | str,
    device_id: int,
    device_name: str,
    old_status: str,
    new_status: str,
    reason: str = "",
) -> StateChangeEvent:
    """
    Device 상태 변화 이벤트 (P9 기록)
    
    Args:
        source_agent_id: Device Agent ID
        device_id: Device ID
        device_name: Device 이름
        old_status: 이전 상태 (online, offline, lost, recovered)
        new_status: 새로운 상태
        reason: 상태 변화 이유
    """
    severity = EventSeverity.CRITICAL if new_status == "lost" else EventSeverity.WARNING
    
    return StateChangeEvent(
        event_type=EventType.DEVICE_STATUS_CHANGE,
        source_system="device_agent",
        source_agent_id=source_agent_id,
        severity=severity,
        title=f"Device Status Change: {old_status} → {new_status}",
        description=reason,
        related_ids={
            "device_id": device_id,
            "device_name": device_name,
        },
        metrics={
            "old_status": old_status,
            "new_status": new_status,
        },
    )
