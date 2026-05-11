"""
Test Suite: Task Dispatcher Multi-factor Selection

이 테스트 모듈은 Task Dispatcher의 다중 요소 기반 device 선택을 검증합니다:

1. SelectionWeights 가중치 검증
2. DeviceMetric 정규화
3. Device 필터링
4. Multi-factor Scoring
5. 시나리오 기반 선택

Author: CoWater AI Agent
Version: v1.0 (Phase 2, Step 3)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestSelectionWeights:
    """SelectionWeights 테스트"""

    def test_weights_sum_to_one(self):
        """가중치 합계가 1.0인가?"""
        try:
            from agent.task_dispatcher import SelectionWeights
            
            weights = SelectionWeights()
            assert weights.validate() is True
        except ImportError:
            pytest.skip("task_dispatcher module not available")

    def test_default_weights(self):
        """기본 가중치 확인"""
        try:
            from agent.task_dispatcher import SelectionWeights
            
            weights = SelectionWeights()
            assert weights.distance == 0.25
            assert weights.battery == 0.20
            assert weights.capability == 0.20
            assert weights.reliability == 0.15
            assert weights.workload == 0.15
            assert weights.availability == 0.05
        except ImportError:
            pytest.skip("task_dispatcher module not available")

    def test_custom_weights_validation(self):
        """커스텀 가중치 검증"""
        try:
            from agent.task_dispatcher import SelectionWeights
            
            # Invalid weights (sum != 1.0)
            weights = SelectionWeights(distance=0.5, battery=0.5)
            assert weights.validate() is False
            
            # Valid weights
            weights = SelectionWeights(
                distance=0.3,
                battery=0.2,
                capability=0.2,
                reliability=0.15,
                workload=0.1,
                availability=0.05,
            )
            assert weights.validate() is True
        except ImportError:
            pytest.skip("task_dispatcher module not available")

    def test_weights_to_dict(self):
        """가중치 dict 변환"""
        try:
            from agent.task_dispatcher import SelectionWeights
            
            weights = SelectionWeights()
            weights_dict = weights.to_dict()
            
            assert isinstance(weights_dict, dict)
            assert weights_dict["distance"] == 0.25
            assert weights_dict["battery"] == 0.20
        except ImportError:
            pytest.skip("task_dispatcher module not available")


class TestDeviceMetric:
    """DeviceMetric 테스트"""

    def test_metric_creation(self):
        """DeviceMetric 생성"""
        try:
            from agent.task_dispatcher import DeviceMetric
            
            metric = DeviceMetric(
                device_id=1,
                device_name="AUV-01",
                distance_m=500.0,
                battery_percent=75,
                capability_score=1.0,
                reliability_score=0.85,
                current_tasks=2,
                max_concurrent_tasks=5,
                idle_seconds=120,
            )
            
            assert metric.device_id == 1
            assert metric.battery_percent == 75
        except ImportError:
            pytest.skip("task_dispatcher module not available")

    def test_metric_normalization(self):
        """메트릭 정규화"""
        try:
            from agent.task_dispatcher import DeviceMetric
            
            metric = DeviceMetric(
                device_id=1,
                device_name="AUV-01",
                distance_m=500.0,
                battery_percent=75,
                capability_score=1.0,
                reliability_score=0.85,
                current_tasks=2,
                max_concurrent_tasks=5,
                idle_seconds=120,
            )
            
            norms = metric.get_normalized_metrics(max_distance=1000.0)
            
            # Distance normalization (0.5)
            assert norms["distance"] == 0.5
            
            # Battery normalization (0.75)
            assert norms["battery"] == 0.75
            
            # Capability and reliability unchanged
            assert norms["capability"] == 1.0
            assert norms["reliability"] == 0.85
            
            # Workload normalization (2/5 = 0.4)
            assert norms["workload"] == 0.4
        except ImportError:
            pytest.skip("task_dispatcher module not available")

    def test_metric_low_battery_penalty(self):
        """배터리 부족 패널티"""
        try:
            from agent.task_dispatcher import DeviceMetric
            
            metric = DeviceMetric(
                device_id=1,
                device_name="AUV-01",
                distance_m=0.0,
                battery_percent=20,  # 30% 미만
                capability_score=1.0,
                reliability_score=0.85,
                current_tasks=0,
                max_concurrent_tasks=5,
                idle_seconds=0,
            )
            
            norms = metric.get_normalized_metrics(max_distance=1000.0)
            
            # Battery with penalty: 20/100 - (30-20)/300 = 0.2 - 0.033 ≈ 0.167
            assert norms["battery"] < 0.2
        except ImportError:
            pytest.skip("task_dispatcher module not available")


class TestTaskDispatcher:
    """TaskDispatcher 테스트"""

    def test_dispatcher_initialization(self):
        """TaskDispatcher 초기화"""
        try:
            from agent.task_dispatcher import TaskDispatcher
            
            mock_registry = MagicMock()
            dispatcher = TaskDispatcher(mock_registry)
            
            assert dispatcher.registry_client == mock_registry
            assert dispatcher.weights.validate() is True
        except ImportError:
            pytest.skip("task_dispatcher module not available")

    def test_device_filtering(self):
        """Device 필터링"""
        try:
            from agent.task_dispatcher import TaskDispatcher
            
            mock_registry = MagicMock()
            dispatcher = TaskDispatcher(mock_registry)
            
            devices = [
                {
                    "id": 1,
                    "name": "AUV-01",
                    "connected": True,
                    "layer": "lower",
                    "agent": {"endpoint": "ws://localhost:9010"},
                    "actions": {"custom": ["survey_depth"]},
                },
                {
                    "id": 2,
                    "name": "ROV-01",
                    "connected": False,  # Not connected
                    "layer": "lower",
                    "agent": {"endpoint": None},
                },
                {
                    "id": 3,
                    "name": "Ship-01",
                    "connected": True,
                    "layer": "upper",  # Wrong layer
                    "agent": {"endpoint": "ws://localhost:9011"},
                },
            ]
            
            candidates = dispatcher._filter_candidates(devices, "survey_depth", set())
            
            # Only device 1 should be a candidate
            assert len(candidates) == 1
            assert candidates[0]["id"] == 1
        except ImportError:
            pytest.skip("task_dispatcher module not available")

    def test_device_can_execute_does_not_mutate_supported_actions(self):
        """지원 액션 목록이 호출 후 변형되지 않아야 함"""
        try:
            from agent.task_dispatcher import TaskDispatcher

            dispatcher = TaskDispatcher(MagicMock())
            device = {
                "id": 1,
                "connected": True,
                "layer": "lower",
                "agent": {
                    "endpoint": "ws://localhost:9010",
                    "available_actions": ["bar"],
                    "skills": ["baz"],
                },
                "actions": {"custom": ["foo"]},
            }

            snapshot = list(device["actions"]["custom"])
            assert dispatcher._device_can_execute(device, "foo") is True
            assert dispatcher._device_can_execute(device, "qux") is False
            assert device["actions"]["custom"] == snapshot
        except ImportError:
            pytest.skip("task_dispatcher module not available")

    def test_single_candidate_selection(self):
        """단일 후보 선택"""
        try:
            from agent.task_dispatcher import TaskDispatcher
            
            mock_registry = MagicMock()
            dispatcher = TaskDispatcher(mock_registry)
            
            devices = [
                {
                    "id": 1,
                    "name": "AUV-01",
                    "connected": True,
                    "layer": "lower",
                    "agent": {"endpoint": "ws://localhost:9010"},
                    "actions": {"custom": ["survey_depth"]},
                    "latitude": 37.5,
                    "longitude": 127.0,
                    "battery_percent": 80,
                }
            ]
            
            selected = dispatcher.select_best_device(
                devices=devices,
                action="survey_depth",
                location={"latitude": 37.5, "longitude": 127.0},
            )
            
            assert selected is not None
            assert selected["id"] == 1
        except ImportError:
            pytest.skip("task_dispatcher module not available")

    def test_distance_based_selection(self):
        """거리 기반 선택"""
        try:
            from agent.task_dispatcher import TaskDispatcher
            
            mock_registry = MagicMock()
            dispatcher = TaskDispatcher(mock_registry)
            
            # 2개 device: 거리만 다름
            devices = [
                {
                    "id": 1,
                    "name": "AUV-01",
                    "connected": True,
                    "layer": "lower",
                    "agent": {"endpoint": "ws://localhost:9010"},
                    "actions": {"custom": ["survey_depth"]},
                    "latitude": 37.0,  # 500m away
                    "longitude": 127.0,
                    "battery_percent": 80,
                    "execution_stats": {"completed_tasks": 10, "failed_tasks": 0},
                },
                {
                    "id": 2,
                    "name": "AUV-02",
                    "connected": True,
                    "layer": "lower",
                    "agent": {"endpoint": "ws://localhost:9011"},
                    "actions": {"custom": ["survey_depth"]},
                    "latitude": 37.5,  # Closest
                    "longitude": 127.0,
                    "battery_percent": 80,
                    "execution_stats": {"completed_tasks": 10, "failed_tasks": 0},
                },
            ]
            
            selected = dispatcher.select_best_device(
                devices=devices,
                action="survey_depth",
                location={"latitude": 37.5, "longitude": 127.0},
            )
            
            # AUV-02 (closer) should be selected
            assert selected is not None
            assert selected["id"] == 2
        except ImportError:
            pytest.skip("task_dispatcher module not available")

    def test_battery_based_selection(self):
        """배터리 기반 선택"""
        try:
            from agent.task_dispatcher import TaskDispatcher
            
            mock_registry = MagicMock()
            dispatcher = TaskDispatcher(mock_registry)
            
            # 2개 device: 거리 같음, 배터리 다름
            devices = [
                {
                    "id": 1,
                    "name": "AUV-01",
                    "connected": True,
                    "layer": "lower",
                    "agent": {"endpoint": "ws://localhost:9010"},
                    "actions": {"custom": ["survey_depth"]},
                    "latitude": 37.5,
                    "longitude": 127.0,
                    "battery_percent": 30,  # Low battery
                    "execution_stats": {"completed_tasks": 10, "failed_tasks": 0},
                },
                {
                    "id": 2,
                    "name": "AUV-02",
                    "connected": True,
                    "layer": "lower",
                    "agent": {"endpoint": "ws://localhost:9011"},
                    "actions": {"custom": ["survey_depth"]},
                    "latitude": 37.5,
                    "longitude": 127.0,
                    "battery_percent": 90,  # High battery
                    "execution_stats": {"completed_tasks": 10, "failed_tasks": 0},
                },
            ]
            
            selected = dispatcher.select_best_device(
                devices=devices,
                action="survey_depth",
                location={"latitude": 37.5, "longitude": 127.0},
            )
            
            # AUV-02 (higher battery) should be selected
            assert selected is not None
            assert selected["id"] == 2
        except ImportError:
            pytest.skip("task_dispatcher module not available")

    def test_preferred_device_priority(self):
        """LLM 추천 device 우선"""
        try:
            from agent.task_dispatcher import TaskDispatcher
            
            mock_registry = MagicMock()
            dispatcher = TaskDispatcher(mock_registry)
            
            devices = [
                {
                    "id": 1,
                    "name": "AUV-01",
                    "connected": True,
                    "layer": "lower",
                    "agent": {"endpoint": "ws://localhost:9010"},
                    "actions": {"custom": ["survey_depth"]},
                    "latitude": 37.5,
                    "longitude": 127.0,
                    "battery_percent": 90,  # Best score
                },
                {
                    "id": 2,
                    "name": "AUV-02",
                    "connected": True,
                    "layer": "lower",
                    "agent": {"endpoint": "ws://localhost:9011"},
                    "actions": {"custom": ["survey_depth"]},
                    "latitude": 37.5,
                    "longitude": 127.0,
                    "battery_percent": 50,  # LLM preferred
                },
            ]
            
            selected = dispatcher.select_best_device(
                devices=devices,
                action="survey_depth",
                location={"latitude": 37.5, "longitude": 127.0},
                preferred_id="2",
            )
            
            # AUV-02 (LLM preferred) should be selected
            assert selected is not None
            assert selected["id"] == 2
        except ImportError:
            pytest.skip("task_dispatcher module not available")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
