"""
Policy Evaluator: Step Evaluation 정책 분리

System Agent의 Step 평가 로직을 별도 클래스로 분리하여 확장성 향상.

정책:
- survey_sufficiency_v1: 부분 성공 수용 (Mine detection)
- all_tasks_success_v1: 모두 성공 필수 (Mine removal)

Author: CoWater AI Agent
Version: v1.0
"""

from __future__ import annotations

from typing import Any, Callable
from agent.state import utc_now


class PolicyEvaluator:
    """Step Evaluation 정책 평가기"""

    def __init__(self, runtime: Any) -> None:
        """
        Args:
            runtime: System Agent runtime (self를 전달받음)
                    _can_retry_failed_tasks, _can_reassign_failed_tasks, 
                    _extract_task_result 등의 메서드 사용
        """
        self.runtime = runtime
        self._policies: dict[str, Callable] = {
            "survey_sufficiency_v1": self._evaluate_survey_sufficiency_v1,
            "all_tasks_success_v1": self._evaluate_all_tasks_success_v1,
        }

    def evaluate(
        self,
        response: dict[str, Any],
        step: dict[str, Any],
        step_state: dict[str, Any],
        step_execution_results: list[dict[str, Any]],
        devices: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Step 평가: policy에 따라 의사결정

        Args:
            response: Mission response 정보
            step: Step 정의
            step_state: Step 실행 상태
            step_execution_results: Task 실행 결과 목록
            devices: 사용 가능한 device 목록

        Returns:
            평가 결과 dict:
                - decision: proceed_next_step | retry_same_step | reassign_failed_tasks | 
                           manual_intervention_required | abort_mission
                - sufficient: bool (충분한가?)
                - reason: str (이유)
                - policy: str (사용된 정책)
                - task_total, completed_task_count, failed_task_count, usable_task_count
                - at: ISO 시간
        """
        policy = str(step.get("evaluation_policy") or "all_tasks_success_v1")
        
        # 정책에 따른 평가
        if policy not in self._policies:
            policy = "all_tasks_success_v1"
        
        result = self._policies[policy](
            response, step, step_state, step_execution_results, devices
        )
        
        return result

    def _evaluate_survey_sufficiency_v1(
        self,
        response: dict[str, Any],
        step: dict[str, Any],
        step_state: dict[str, Any],
        step_execution_results: list[dict[str, Any]],
        devices: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Mine Detection 정책: 부분 성공 수용
        
        결정 트리:
        1. usable_output 있으면 → proceed_next_step
        2. 없으면, reassign 가능 → reassign_failed_tasks
        3. 없으면, retry 가능 → retry_same_step
        4. 없으면 → manual_intervention_required
        
        원칙: 리스크 평가 목적이므로 완벽한 survey 불필요
        """
        step_type = str(step.get("step_type") or "generic_action")
        task_total = len([task for task in (step_state.get("tasks") or []) if isinstance(task, dict)])
        completed_results = [
            item for item in step_execution_results
            if self.runtime._task_status(item.get("status")) == "COMPLETED"
        ]
        failed_results = [
            item for item in step_execution_results
            if self.runtime._task_status(item.get("status")) in {"FAILED", "ABORTED", "CANCELLED"}
        ]
        usable_results = [
            item for item in completed_results
            if self.runtime._extract_task_result(item).get("usable_output", True) is not False
        ]

        # P3 (보고 기반): usable_output을 기준으로 의사결정
        sufficient = bool(usable_results)
        
        if sufficient:
            decision = "proceed_next_step"
            reason = "usable survey output available"
        elif self.runtime._can_reassign_failed_tasks(step, step_state, devices):
            decision = "reassign_failed_tasks"
            reason = "no usable survey output yet; reassign failed tasks to alternate devices"
        elif self.runtime._can_retry_failed_tasks(step_state):
            decision = "retry_same_step"
            reason = "no usable survey output yet; retry failed tasks on same devices"
        else:
            decision = "manual_intervention_required"
            reason = "no usable survey output available and no automated recovery path"

        return {
            "at": utc_now(),
            "response_id": response.get("response_id"),
            "step_id": step.get("step_id"),
            "step_type": step_type,
            "policy": "survey_sufficiency_v1",
            "task_total": task_total,
            "completed_task_count": len(completed_results),
            "failed_task_count": len(failed_results),
            "usable_task_count": len(usable_results),
            "step_execution_status": step_state.get("status"),
            "sufficient": sufficient,
            "decision": decision,
            "reason": reason,
        }

    def _evaluate_all_tasks_success_v1(
        self,
        response: dict[str, Any],
        step: dict[str, Any],
        step_state: dict[str, Any],
        step_execution_results: list[dict[str, Any]],
        devices: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Mine Removal 정책: 모두 성공 필수 (기본값)
        
        결정 트리:
        1. 모든 task 성공 → proceed_next_step
        2. 없으면, retry 가능 → retry_same_step
        3. 없으면, reassign 가능 → reassign_failed_tasks
        4. 없으면 → abort_mission
        
        원칙: Mission critical action이므로 엄격한 성공 요구
        """
        step_type = str(step.get("step_type") or "generic_action")
        task_total = len([task for task in (step_state.get("tasks") or []) if isinstance(task, dict)])
        completed_results = [
            item for item in step_execution_results
            if self.runtime._task_status(item.get("status")) == "COMPLETED"
        ]
        failed_results = [
            item for item in step_execution_results
            if self.runtime._task_status(item.get("status")) in {"FAILED", "ABORTED", "CANCELLED"}
        ]

        # P5 (최종 판단): Task 수행 가능 여부의 최종 판단은 Device가 함
        # 하지만 Step 평가에서는 모든 task의 성공 여부로 판정
        sufficient = task_total > 0 and len(completed_results) == task_total and not failed_results
        
        if sufficient:
            decision = "proceed_next_step"
            reason = "all tasks completed successfully"
        elif self.runtime._can_retry_failed_tasks(step_state):
            decision = "retry_same_step"
            reason = "one or more required tasks failed; retry available"
        elif self.runtime._can_reassign_failed_tasks(step, step_state, devices):
            decision = "reassign_failed_tasks"
            reason = "one or more required tasks failed; alternate capable device available"
        else:
            decision = "abort_mission"
            reason = "one or more required tasks failed and no automated recovery path"

        return {
            "at": utc_now(),
            "response_id": response.get("response_id"),
            "step_id": step.get("step_id"),
            "step_type": step_type,
            "policy": "all_tasks_success_v1",
            "task_total": task_total,
            "completed_task_count": len(completed_results),
            "failed_task_count": len(failed_results),
            "usable_task_count": len(completed_results),  # 모두 성공한 task만 카운트
            "step_execution_status": step_state.get("status"),
            "sufficient": sufficient,
            "decision": decision,
            "reason": reason,
        }

    def register_policy(
        self,
        policy_name: str,
        evaluator_func: Callable,
    ) -> None:
        """
        새로운 정책 등록 (향후 확장용)

        Args:
            policy_name: 정책 이름 (예: "survey_sufficiency_v2")
            evaluator_func: 평가 함수
                signature: (response, step, step_state, step_execution_results, devices) -> dict
        """
        self._policies[policy_name] = evaluator_func

    def list_policies(self) -> list[str]:
        """등록된 정책 목록 반환"""
        return list(self._policies.keys())
