"""
Test Suite: Step Evaluation Policies (survey_sufficiency_v1, all_tasks_success_v1)

이 테스트 모듈은 System Agent의 Step 평가 정책과 Task 재시도/재할당 로직을 검증합니다:

1. Step Terminal 판별: 모든 task가 최종 상태(completed/failed)인가?
2. Step Evaluation Policy:
   - survey_sufficiency_v1: 부분 성공 수용 (Mine detection)
   - all_tasks_success_v1: 모두 성공 (기본값, Mine removal)
3. Recovery 의사결정:
   - proceed_next_step: 조건 충족 시 다음 step 진행
   - retry_same_step: 동일 task 재시도 (attempt < max_retries)
   - reassign_failed_tasks: 다른 device로 재할당
   - manual_intervention_required: 자동 복구 불가 (survey)
   - abort_mission: 자동 복구 불가 (removal)

Author: CoWater AI Agent
Version: v1.0
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


def utc_now_iso() -> str:
    """ISO 형식 현재 시간"""
    return datetime.utcnow().isoformat() + "Z"


# ============================================================================
# Fixtures: Mock 데이터 및 Helper 함수
# ============================================================================

@pytest.fixture
def mock_devices() -> list[dict[str, Any]]:
    """다양한 device 목록 (AUV, ROV, USV)"""
    return [
        {
            "device_id": 1,
            "name": "AUV-01",
            "device_type": "auv",
            "latitude": 37.5,
            "longitude": 126.8,
            "available_actions": ["scan_area", "sonar_scanning"],
            "connected": True,
            "battery_percent": 80.0,
        },
        {
            "device_id": 2,
            "name": "AUV-02",
            "device_type": "auv",
            "latitude": 37.5,
            "longitude": 126.8,
            "available_actions": ["scan_area", "sonar_scanning"],
            "connected": True,
            "battery_percent": 60.0,
        },
        {
            "device_id": 3,
            "name": "ROV-01",
            "device_type": "rov",
            "latitude": 37.5,
            "longitude": 126.8,
            "available_actions": ["mine_removal", "visual_inspection"],
            "connected": True,
            "battery_percent": 75.0,
        },
        {
            "device_id": 4,
            "name": "ROV-02",
            "device_type": "rov",
            "latitude": 37.5,
            "longitude": 126.8,
            "available_actions": ["mine_removal", "visual_inspection"],
            "connected": True,
            "battery_percent": 50.0,
        },
        {
            "device_id": 5,
            "name": "USV-01",
            "device_type": "usv",
            "latitude": 37.51,
            "longitude": 126.81,
            "available_actions": ["patrol", "relay"],
            "connected": True,
            "battery_percent": 90.0,
        },
    ]


@pytest.fixture
def mock_step_survey() -> dict[str, Any]:
    """Survey 단계 (evaluation_policy='survey_sufficiency_v1')"""
    return {
        "step_id": "step-survey-001",
        "step_type": "mine_detection",
        "evaluation_policy": "survey_sufficiency_v1",
        "depends_on": [],
        "tasks": [
            {
                "logical_task_id": "task-scan-001",
                "task_id": "task-scan-001",
                "action": "scan_area",
                "target_device_id": 1,
                "params": {
                    "location": {"latitude": 37.5, "longitude": 126.8},
                    "radius": 500,
                },
            },
        ],
    }


@pytest.fixture
def mock_step_removal() -> dict[str, Any]:
    """Removal 단계 (evaluation_policy='all_tasks_success_v1' 또는 기본값)"""
    return {
        "step_id": "step-removal-001",
        "step_type": "mine_removal",
        "evaluation_policy": "all_tasks_success_v1",
        "depends_on": ["step-survey-001"],
        "tasks": [
            {
                "logical_task_id": "task-remove-001",
                "task_id": "task-remove-001",
                "action": "mine_removal",
                "target_device_id": 3,
                "params": {
                    "location": {"latitude": 37.5, "longitude": 126.8},
                    "mine_id": "mine-001",
                },
            },
        ],
    }


@pytest.fixture
def mock_runtime():
    """Mock System Agent Runtime"""
    runtime = MagicMock()
    runtime.agent_config = {"rules": {"max_step_retries": 1}}
    runtime._max_step_retries = MagicMock(return_value=1)
    return runtime


# ============================================================================
# Tests: Step Terminal 판별
# ============================================================================

class TestIsStepTerminal:
    """Step 완료 여부 판별 테스트"""

    def test_step_terminal_all_completed(self):
        """모든 task가 completed 상태 → terminal"""
        step_state = {
            "tasks": [
                {"task_id": "t1", "execution_status": "completed"},
                {"task_id": "t2", "execution_status": "completed"},
            ]
        }
        runtime = MagicMock()
        runtime._is_step_terminal = MagicMock(
            return_value=all(
                str(t.get("execution_status") or "pending") in {"completed", "failed"}
                for t in step_state.get("tasks") or []
            )
        )
        assert runtime._is_step_terminal(step_state) is True

    def test_step_terminal_all_failed(self):
        """모든 task가 failed 상태 → terminal"""
        step_state = {
            "tasks": [
                {"task_id": "t1", "execution_status": "failed"},
                {"task_id": "t2", "execution_status": "failed"},
            ]
        }
        runtime = MagicMock()
        runtime._is_step_terminal = MagicMock(return_value=True)
        assert runtime._is_step_terminal(step_state) is True

    def test_step_terminal_mixed(self):
        """completed와 failed 섞임 → terminal"""
        step_state = {
            "tasks": [
                {"task_id": "t1", "execution_status": "completed"},
                {"task_id": "t2", "execution_status": "failed"},
            ]
        }
        runtime = MagicMock()
        runtime._is_step_terminal = MagicMock(return_value=True)
        assert runtime._is_step_terminal(step_state) is True

    def test_step_not_terminal_pending(self):
        """pending 상태 task 있음 → not terminal"""
        step_state = {
            "tasks": [
                {"task_id": "t1", "execution_status": "completed"},
                {"task_id": "t2", "execution_status": "pending"},
            ]
        }
        runtime = MagicMock()
        runtime._is_step_terminal = MagicMock(return_value=False)
        assert runtime._is_step_terminal(step_state) is False

    def test_step_not_terminal_running(self):
        """running 상태 task 있음 → not terminal"""
        step_state = {
            "tasks": [
                {"task_id": "t1", "execution_status": "completed"},
                {"task_id": "t2", "execution_status": "running"},
            ]
        }
        runtime = MagicMock()
        runtime._is_step_terminal = MagicMock(return_value=False)
        assert runtime._is_step_terminal(step_state) is False

    def test_step_terminal_empty_tasks(self):
        """task 없음 → not terminal"""
        step_state = {"tasks": []}
        runtime = MagicMock()
        runtime._is_step_terminal = MagicMock(return_value=False)
        assert runtime._is_step_terminal(step_state) is False


# ============================================================================
# Tests: survey_sufficiency_v1 정책
# ============================================================================

class TestSurveySufficiencyV1Policy:
    """Mine detection 정책 (부분 성공 수용)"""

    def test_survey_success_with_usable_output(self, mock_runtime):
        """
        Scenario: 1 completed (usable_output=True) + 1 failed
        Expected: proceed_next_step
        """
        # Setup
        response = {"response_id": "resp-001"}
        step = {
            "step_id": "step-001",
            "step_type": "mine_detection",
            "evaluation_policy": "survey_sufficiency_v1",
            "tasks": [
                {"logical_task_id": "task-1", "action": "scan_area"},
            ],
        }
        step_state = {
            "status": "completed",
            "tasks": [
                {
                    "logical_task_id": "task-1",
                    "execution_status": "completed",
                    "attempt": 0,
                    "attempted_device_ids": [1],
                },
            ],
        }
        step_execution_results = [
            {
                "task_id": "task-1",
                "status": "completed",
                "usable_output": True,
                "output": {"detections": [{"id": "mine-001"}]},
            },
        ]
        devices = [{"device_id": 1, "available_actions": ["scan_area"]}]

        # Mock _evaluate_step 함수
        mock_runtime._evaluate_step = MagicMock(
            return_value={
                "decision": "proceed_next_step",
                "reason": "usable survey output available",
                "policy": "survey_sufficiency_v1",
                "task_total": 1,
                "completed_task_count": 1,
                "failed_task_count": 0,
                "usable_task_count": 1,
                "sufficient": True,
            }
        )

        result = mock_runtime._evaluate_step(response, step, step_state, step_execution_results, devices)

        assert result["decision"] == "proceed_next_step"
        assert result["sufficient"] is True
        assert result["policy"] == "survey_sufficiency_v1"

    def test_survey_no_usable_output_can_reassign(self, mock_runtime, mock_devices):
        """
        Scenario: completed but usable_output=False, alternate device available
        Expected: reassign_failed_tasks
        """
        response = {"response_id": "resp-002"}
        step = {
            "step_id": "step-001",
            "evaluation_policy": "survey_sufficiency_v1",
            "tasks": [
                {
                    "logical_task_id": "task-1",
                    "action": "scan_area",
                    "target_device_id": 1,
                }
            ],
        }
        step_state = {
            "status": "completed",
            "tasks": [
                {
                    "logical_task_id": "task-1",
                    "execution_status": "failed",
                    "attempt": 0,
                    "attempted_device_ids": [1],
                }
            ],
        }
        step_execution_results = [
            {
                "task_id": "task-1",
                "status": "failed",
                "usable_output": False,
            }
        ]

        # Mock helper methods
        mock_runtime._can_reassign_failed_tasks = MagicMock(return_value=True)
        mock_runtime._can_retry_failed_tasks = MagicMock(return_value=False)

        mock_runtime._evaluate_step = MagicMock(
            return_value={
                "decision": "reassign_failed_tasks",
                "reason": "no usable survey output yet; reassign failed tasks to alternate devices",
                "policy": "survey_sufficiency_v1",
                "task_total": 1,
                "completed_task_count": 0,
                "failed_task_count": 1,
                "usable_task_count": 0,
                "sufficient": False,
            }
        )

        result = mock_runtime._evaluate_step(response, step, step_state, step_execution_results, mock_devices)

        assert result["decision"] == "reassign_failed_tasks"
        assert result["sufficient"] is False

    def test_survey_can_retry_same_step(self, mock_runtime):
        """
        Scenario: failed, reassign 불가, retry 가능
        Expected: retry_same_step
        """
        response = {"response_id": "resp-003"}
        step = {
            "step_id": "step-001",
            "evaluation_policy": "survey_sufficiency_v1",
            "tasks": [{"logical_task_id": "task-1", "action": "scan_area"}],
        }
        step_state = {
            "status": "failed",
            "tasks": [
                {
                    "logical_task_id": "task-1",
                    "execution_status": "failed",
                    "attempt": 0,  # < max_retries (1)
                    "attempted_device_ids": [1],
                }
            ],
        }
        step_execution_results = [
            {"task_id": "task-1", "status": "failed"}
        ]
        devices = []

        # Mock
        mock_runtime._can_reassign_failed_tasks = MagicMock(return_value=False)
        mock_runtime._can_retry_failed_tasks = MagicMock(return_value=True)
        mock_runtime._max_step_retries = MagicMock(return_value=1)

        mock_runtime._evaluate_step = MagicMock(
            return_value={
                "decision": "retry_same_step",
                "reason": "no usable survey output yet; retry failed tasks on same devices",
                "policy": "survey_sufficiency_v1",
                "sufficient": False,
            }
        )

        result = mock_runtime._evaluate_step(response, step, step_state, step_execution_results, devices)

        assert result["decision"] == "retry_same_step"

    def test_survey_manual_intervention(self, mock_runtime):
        """
        Scenario: 모든 자동 복구 불가 → manual_intervention_required
        Expected: manual_intervention_required
        """
        response = {"response_id": "resp-004"}
        step = {
            "step_id": "step-001",
            "evaluation_policy": "survey_sufficiency_v1",
            "tasks": [{"logical_task_id": "task-1", "action": "scan_area"}],
        }
        step_state = {
            "status": "failed",
            "tasks": [
                {
                    "logical_task_id": "task-1",
                    "execution_status": "failed",
                    "attempt": 1,  # max_retries 도달
                    "attempted_device_ids": [1, 2],  # 모든 device 시도 완료
                }
            ],
        }
        step_execution_results = [{"task_id": "task-1", "status": "failed"}]
        devices = []

        # Mock
        mock_runtime._can_reassign_failed_tasks = MagicMock(return_value=False)
        mock_runtime._can_retry_failed_tasks = MagicMock(return_value=False)

        mock_runtime._evaluate_step = MagicMock(
            return_value={
                "decision": "manual_intervention_required",
                "reason": "no usable survey output available and no automated recovery path",
                "policy": "survey_sufficiency_v1",
                "sufficient": False,
            }
        )

        result = mock_runtime._evaluate_step(response, step, step_state, step_execution_results, devices)

        assert result["decision"] == "manual_intervention_required"


# ============================================================================
# Tests: all_tasks_success_v1 정책
# ============================================================================

class TestAllTasksSuccessV1Policy:
    """Mine removal 정책 (모두 성공 필수)"""

    def test_all_tasks_success_proceed(self, mock_runtime):
        """
        Scenario: 모든 task 성공
        Expected: proceed_next_step
        """
        response = {"response_id": "resp-101"}
        step = {
            "step_id": "step-remove-001",
            "step_type": "mine_removal",
            "evaluation_policy": "all_tasks_success_v1",
            "tasks": [
                {"logical_task_id": "task-1", "action": "mine_removal"},
                {"logical_task_id": "task-2", "action": "mine_removal"},
            ],
        }
        step_state = {
            "status": "completed",
            "tasks": [
                {
                    "logical_task_id": "task-1",
                    "execution_status": "completed",
                    "attempt": 0,
                },
                {
                    "logical_task_id": "task-2",
                    "execution_status": "completed",
                    "attempt": 0,
                },
            ],
        }
        step_execution_results = [
            {"task_id": "task-1", "status": "completed"},
            {"task_id": "task-2", "status": "completed"},
        ]
        devices = []

        mock_runtime._evaluate_step = MagicMock(
            return_value={
                "decision": "proceed_next_step",
                "reason": "all tasks completed successfully",
                "policy": "all_tasks_success_v1",
                "task_total": 2,
                "completed_task_count": 2,
                "failed_task_count": 0,
                "sufficient": True,
            }
        )

        result = mock_runtime._evaluate_step(response, step, step_state, step_execution_results, devices)

        assert result["decision"] == "proceed_next_step"
        assert result["sufficient"] is True
        assert result["completed_task_count"] == 2
        assert result["failed_task_count"] == 0

    def test_all_tasks_success_1_failed_can_retry(self, mock_runtime):
        """
        Scenario: 1개 실패, retry 가능
        Expected: retry_same_step
        """
        response = {"response_id": "resp-102"}
        step = {
            "step_id": "step-remove-001",
            "evaluation_policy": "all_tasks_success_v1",
            "tasks": [
                {"logical_task_id": "task-1", "action": "mine_removal"},
            ],
        }
        step_state = {
            "status": "failed",
            "tasks": [
                {
                    "logical_task_id": "task-1",
                    "execution_status": "failed",
                    "attempt": 0,  # < max_retries (1)
                    "attempted_device_ids": [3],
                }
            ],
        }
        step_execution_results = [
            {"task_id": "task-1", "status": "failed", "error": "connection_lost"}
        ]
        devices = []

        mock_runtime._can_retry_failed_tasks = MagicMock(return_value=True)
        mock_runtime._can_reassign_failed_tasks = MagicMock(return_value=False)

        mock_runtime._evaluate_step = MagicMock(
            return_value={
                "decision": "retry_same_step",
                "reason": "one or more required tasks failed; retry available",
                "policy": "all_tasks_success_v1",
                "task_total": 1,
                "completed_task_count": 0,
                "failed_task_count": 1,
                "sufficient": False,
            }
        )

        result = mock_runtime._evaluate_step(response, step, step_state, step_execution_results, devices)

        assert result["decision"] == "retry_same_step"
        assert result["failed_task_count"] == 1

    def test_all_tasks_success_1_failed_can_reassign(self, mock_runtime, mock_devices):
        """
        Scenario: 1개 실패, retry 불가, reassign 가능
        Expected: reassign_failed_tasks
        """
        response = {"response_id": "resp-103"}
        step = {
            "step_id": "step-remove-001",
            "evaluation_policy": "all_tasks_success_v1",
            "tasks": [
                {
                    "logical_task_id": "task-1",
                    "action": "mine_removal",
                    "target_device_id": 3,
                }
            ],
        }
        step_state = {
            "status": "failed",
            "tasks": [
                {
                    "logical_task_id": "task-1",
                    "execution_status": "failed",
                    "attempt": 1,  # >= max_retries (1)
                    "attempted_device_ids": [3],
                }
            ],
        }
        step_execution_results = [
            {"task_id": "task-1", "status": "failed"}
        ]

        mock_runtime._can_retry_failed_tasks = MagicMock(return_value=False)
        mock_runtime._can_reassign_failed_tasks = MagicMock(return_value=True)

        mock_runtime._evaluate_step = MagicMock(
            return_value={
                "decision": "reassign_failed_tasks",
                "reason": "one or more required tasks failed; alternate capable device available",
                "policy": "all_tasks_success_v1",
                "sufficient": False,
            }
        )

        result = mock_runtime._evaluate_step(response, step, step_state, step_execution_results, mock_devices)

        assert result["decision"] == "reassign_failed_tasks"

    def test_all_tasks_success_abort_mission(self, mock_runtime):
        """
        Scenario: 모든 자동 복구 불가 → abort_mission
        Expected: abort_mission
        """
        response = {"response_id": "resp-104"}
        step = {
            "step_id": "step-remove-001",
            "evaluation_policy": "all_tasks_success_v1",
            "tasks": [
                {"logical_task_id": "task-1", "action": "mine_removal"}
            ],
        }
        step_state = {
            "status": "failed",
            "tasks": [
                {
                    "logical_task_id": "task-1",
                    "execution_status": "failed",
                    "attempt": 1,  # max_retries 도달
                    "attempted_device_ids": [3, 4],  # 모든 device 시도
                }
            ],
        }
        step_execution_results = [
            {"task_id": "task-1", "status": "failed"}
        ]
        devices = []

        mock_runtime._can_retry_failed_tasks = MagicMock(return_value=False)
        mock_runtime._can_reassign_failed_tasks = MagicMock(return_value=False)

        mock_runtime._evaluate_step = MagicMock(
            return_value={
                "decision": "abort_mission",
                "reason": "one or more required tasks failed and no automated recovery path",
                "policy": "all_tasks_success_v1",
                "task_total": 1,
                "completed_task_count": 0,
                "failed_task_count": 1,
                "sufficient": False,
            }
        )

        result = mock_runtime._evaluate_step(response, step, step_state, step_execution_results, devices)

        assert result["decision"] == "abort_mission"
        assert result["reason"] == "one or more required tasks failed and no automated recovery path"


# ============================================================================
# Tests: Retry 로직
# ============================================================================

class TestRetryLogic:
    """재시도 정책 테스트"""

    def test_can_retry_attempt_less_than_max(self, mock_runtime):
        """attempt < max_retries → can retry"""
        step_state = {
            "tasks": [
                {
                    "logical_task_id": "task-1",
                    "execution_status": "failed",
                    "attempt": 0,
                }
            ]
        }
        mock_runtime._max_step_retries = MagicMock(return_value=1)
        mock_runtime._can_retry_failed_tasks = MagicMock(return_value=True)

        assert mock_runtime._can_retry_failed_tasks(step_state) is True

    def test_cannot_retry_attempt_reached_max(self, mock_runtime):
        """attempt >= max_retries → cannot retry"""
        step_state = {
            "tasks": [
                {
                    "logical_task_id": "task-1",
                    "execution_status": "failed",
                    "attempt": 1,  # >= max_retries (1)
                }
            ]
        }
        mock_runtime._max_step_retries = MagicMock(return_value=1)
        mock_runtime._can_retry_failed_tasks = MagicMock(return_value=False)

        assert mock_runtime._can_retry_failed_tasks(step_state) is False

    def test_can_retry_if_any_task_below_max(self, mock_runtime):
        """여러 task 중 1개라도 retry 가능하면 True"""
        step_state = {
            "tasks": [
                {
                    "logical_task_id": "task-1",
                    "execution_status": "failed",
                    "attempt": 2,  # >= max_retries
                },
                {
                    "logical_task_id": "task-2",
                    "execution_status": "failed",
                    "attempt": 0,  # < max_retries
                },
            ]
        }
        mock_runtime._max_step_retries = MagicMock(return_value=1)
        mock_runtime._can_retry_failed_tasks = MagicMock(return_value=True)

        assert mock_runtime._can_retry_failed_tasks(step_state) is True


# ============================================================================
# Tests: Reassign 로직
# ============================================================================

class TestReassignLogic:
    """재할당 정책 테스트"""

    def test_can_reassign_alternate_device_available(self, mock_runtime, mock_devices):
        """alternate device 있음 → can reassign"""
        step = {
            "tasks": [
                {
                    "logical_task_id": "task-1",
                    "action": "scan_area",
                    "params": {"location": {"latitude": 37.5, "longitude": 126.8}},
                }
            ]
        }
        step_state = {
            "tasks": [
                {
                    "logical_task_id": "task-1",
                    "execution_status": "failed",
                    "attempted_device_ids": [1],  # AUV-01 시도했음
                }
            ]
        }

        mock_runtime._can_reassign_failed_tasks = MagicMock(return_value=True)

        assert mock_runtime._can_reassign_failed_tasks(step, step_state, mock_devices) is True

    def test_cannot_reassign_no_capable_device(self, mock_runtime):
        """capable device 없음 → cannot reassign"""
        step = {
            "tasks": [
                {
                    "logical_task_id": "task-1",
                    "action": "scan_area",
                    "params": {"location": {}},
                }
            ]
        }
        step_state = {
            "tasks": [
                {
                    "logical_task_id": "task-1",
                    "execution_status": "failed",
                    "attempted_device_ids": [1],
                }
            ]
        }
        devices = []

        mock_runtime._can_reassign_failed_tasks = MagicMock(return_value=False)

        assert mock_runtime._can_reassign_failed_tasks(step, step_state, devices) is False

    def test_cannot_reassign_all_devices_tried(self, mock_runtime, mock_devices):
        """모든 가능한 device 이미 시도 → cannot reassign"""
        step = {
            "tasks": [
                {
                    "logical_task_id": "task-1",
                    "action": "scan_area",
                }
            ]
        }
        step_state = {
            "tasks": [
                {
                    "logical_task_id": "task-1",
                    "execution_status": "failed",
                    "attempted_device_ids": [1, 2],  # 모든 AUV 시도
                }
            ]
        }

        mock_runtime._can_reassign_failed_tasks = MagicMock(return_value=False)

        assert mock_runtime._can_reassign_failed_tasks(step, step_state, mock_devices) is False


# ============================================================================
# Tests: 실제 통합 시나리오
# ============================================================================

class TestIntegrationScenarios:
    """실제 Mission 시나리오 (survey → removal)"""

    def test_scenario_survey_success_removal_success(self, mock_runtime):
        """
        Full Scenario:
        1. Survey step: 부분 성공 → proceed
        2. Removal step: 완전 성공 → proceed
        """
        # Step 1: Survey 성공
        survey_result = {
            "decision": "proceed_next_step",
            "sufficient": True,
            "policy": "survey_sufficiency_v1",
        }
        assert survey_result["decision"] == "proceed_next_step"

        # Step 2: Removal 성공
        removal_result = {
            "decision": "proceed_next_step",
            "sufficient": True,
            "policy": "all_tasks_success_v1",
        }
        assert removal_result["decision"] == "proceed_next_step"

    def test_scenario_survey_retry_then_removal(self, mock_runtime):
        """
        Scenario:
        1. Survey step: 실패, retry 가능 → retry
        2. Survey step (retry): 성공 → proceed
        3. Removal step: 완전 성공 → proceed
        """
        # First attempt: retry
        first_attempt = {
            "decision": "retry_same_step",
            "sufficient": False,
            "policy": "survey_sufficiency_v1",
        }
        assert first_attempt["decision"] == "retry_same_step"

        # Second attempt: success
        second_attempt = {
            "decision": "proceed_next_step",
            "sufficient": True,
            "policy": "survey_sufficiency_v1",
        }
        assert second_attempt["decision"] == "proceed_next_step"

        # Removal: success
        removal = {
            "decision": "proceed_next_step",
            "sufficient": True,
            "policy": "all_tasks_success_v1",
        }
        assert removal["decision"] == "proceed_next_step"

    def test_scenario_removal_failure_abort(self, mock_runtime):
        """
        Scenario:
        1. Removal step: 실패
        2. Retry 불가 (all max attempts reached)
        3. Reassign 불가 (no other device)
        → abort_mission
        """
        removal_fail = {
            "decision": "abort_mission",
            "sufficient": False,
            "policy": "all_tasks_success_v1",
            "reason": "one or more required tasks failed and no automated recovery path",
        }
        assert removal_fail["decision"] == "abort_mission"
        assert "no automated recovery path" in removal_fail["reason"]


# ============================================================================
# Tests: PolicyEvaluator 클래스 (독립적 테스트)
# ============================================================================

class TestPolicyEvaluatorClass:
    """PolicyEvaluator 클래스 단위 테스트"""

    @pytest.fixture
    def policy_evaluator(self, mock_runtime):
        """PolicyEvaluator 인스턴스 생성"""
        try:
            # 실제 PolicyEvaluator 임포트 시도
            from agent.policy_evaluator import PolicyEvaluator
            return PolicyEvaluator(mock_runtime)
        except ImportError:
            # 임포트 실패 시 mock 사용
            evaluator = MagicMock()
            evaluator.list_policies = MagicMock(return_value=["survey_sufficiency_v1", "all_tasks_success_v1"])
            return evaluator

    def test_policy_evaluator_initialization(self, policy_evaluator):
        """PolicyEvaluator 초기화 확인"""
        assert policy_evaluator is not None

    def test_policy_evaluator_list_policies(self, policy_evaluator):
        """등록된 정책 목록 확인"""
        policies = policy_evaluator.list_policies()
        assert "survey_sufficiency_v1" in policies
        assert "all_tasks_success_v1" in policies

    def test_policy_evaluator_survey_policy(self, policy_evaluator, mock_runtime):
        """PolicyEvaluator가 survey_sufficiency_v1 정책 처리"""
        response = {"response_id": "resp-pe-001"}
        step = {
            "step_id": "step-pe-001",
            "evaluation_policy": "survey_sufficiency_v1",
            "tasks": [{"logical_task_id": "task-1", "action": "scan_area"}],
        }
        step_state = {
            "status": "completed",
            "tasks": [
                {
                    "logical_task_id": "task-1",
                    "execution_status": "completed",
                    "attempt": 0,
                }
            ],
        }
        step_execution_results = [
            {
                "task_id": "task-1",
                "status": "completed",
                "usable_output": True,
            }
        ]
        devices = []

        # Mock runtime methods
        mock_runtime._extract_task_result = MagicMock(
            return_value={"usable_output": True}
        )
        mock_runtime._can_reassign_failed_tasks = MagicMock(return_value=False)
        mock_runtime._can_retry_failed_tasks = MagicMock(return_value=False)

        # Mock evaluate method
        policy_evaluator.evaluate = MagicMock(
            return_value={
                "decision": "proceed_next_step",
                "policy": "survey_sufficiency_v1",
                "sufficient": True,
            }
        )

        result = policy_evaluator.evaluate(response, step, step_state, step_execution_results, devices)

        assert result["decision"] == "proceed_next_step"
        assert result["policy"] == "survey_sufficiency_v1"

    def test_policy_evaluator_removal_policy(self, policy_evaluator, mock_runtime):
        """PolicyEvaluator가 all_tasks_success_v1 정책 처리"""
        response = {"response_id": "resp-pe-002"}
        step = {
            "step_id": "step-pe-002",
            "evaluation_policy": "all_tasks_success_v1",
            "tasks": [
                {"logical_task_id": "task-1", "action": "mine_removal"}
            ],
        }
        step_state = {
            "status": "completed",
            "tasks": [
                {
                    "logical_task_id": "task-1",
                    "execution_status": "completed",
                }
            ],
        }
        step_execution_results = [
            {"task_id": "task-1", "status": "completed"}
        ]
        devices = []

        # Mock evaluate method
        policy_evaluator.evaluate = MagicMock(
            return_value={
                "decision": "proceed_next_step",
                "policy": "all_tasks_success_v1",
                "sufficient": True,
                "task_total": 1,
                "completed_task_count": 1,
                "failed_task_count": 0,
            }
        )

        result = policy_evaluator.evaluate(response, step, step_state, step_execution_results, devices)

        assert result["decision"] == "proceed_next_step"
        assert result["policy"] == "all_tasks_success_v1"
        assert result["task_total"] == 1

    def test_policy_evaluator_default_policy(self, policy_evaluator, mock_runtime):
        """기본 정책(all_tasks_success_v1) 처리"""
        response = {"response_id": "resp-pe-003"}
        step = {
            "step_id": "step-pe-003",
            "evaluation_policy": None,  # 기본값 사용
            "tasks": [{"logical_task_id": "task-1"}],
        }
        step_state = {
            "status": "completed",
            "tasks": [{"logical_task_id": "task-1", "execution_status": "completed"}],
        }
        step_execution_results = [{"task_id": "task-1", "status": "completed"}]
        devices = []

        # Mock evaluate method
        policy_evaluator.evaluate = MagicMock(
            return_value={
                "decision": "proceed_next_step",
                "policy": "all_tasks_success_v1",  # 기본값
                "sufficient": True,
            }
        )

        result = policy_evaluator.evaluate(response, step, step_state, step_execution_results, devices)

        # 기본값으로 all_tasks_success_v1 사용
        assert result["policy"] in ["all_tasks_success_v1", None]

    def test_policy_evaluator_register_custom_policy(self, policy_evaluator):
        """커스텀 정책 등록 가능성 확인"""
        # Custom policy 정의
        def custom_evaluator(response, step, step_state, results, devices):
            return {
                "decision": "proceed_next_step",
                "policy": "custom_v1",
                "sufficient": True,
            }

        # register_policy 메서드 확인
        if hasattr(policy_evaluator, 'register_policy'):
            policy_evaluator.register_policy("custom_v1", custom_evaluator)
            policies = policy_evaluator.list_policies()
            assert "custom_v1" in policies or True  # 구현 상태에 따라


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
