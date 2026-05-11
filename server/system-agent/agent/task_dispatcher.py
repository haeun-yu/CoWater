"""
Task Dispatcher: Multi-factor Device Selection

다중 요소(거리, 배터리, 능력, 신뢰도, 작업부하)를 고려하여
가장 적합한 디바이스를 선택하는 알고리즘.

Scoring Formula:
    Score = W1*distance + W2*battery + W3*capability + W4*reliability + W5*workload + W6*availability

Author: CoWater AI Agent
Version: v1.0 (Phase 2, Step 3)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Device Selection Weights
# ──────────────────────────────────────────────

@dataclass
class SelectionWeights:
    """Device 선택 가중치"""
    distance: float = 0.25         # 거리: 25%
    battery: float = 0.20          # 배터리: 20%
    capability: float = 0.20       # 능력: 20%
    reliability: float = 0.15      # 신뢰도: 15%
    workload: float = 0.15         # 작업부하: 15%
    availability: float = 0.05     # 가용성: 5%

    def validate(self) -> bool:
        """가중치 합계 = 1.0 검증"""
        total = self.distance + self.battery + self.capability + self.reliability + self.workload + self.availability
        return abs(total - 1.0) < 0.01

    def to_dict(self) -> dict[str, float]:
        """Dict 변환"""
        return {
            "distance": self.distance,
            "battery": self.battery,
            "capability": self.capability,
            "reliability": self.reliability,
            "workload": self.workload,
            "availability": self.availability,
        }


# ──────────────────────────────────────────────
# Device Metric
# ──────────────────────────────────────────────

@dataclass
class DeviceMetric:
    """Device 메트릭"""
    device_id: int
    device_name: str
    distance_m: float
    battery_percent: int
    capability_score: float      # 0-1: native(1.0), alias(0.8), fallback(0.5)
    reliability_score: float     # 0-1: 성공률
    current_tasks: int
    max_concurrent_tasks: int
    idle_seconds: int
    last_used_at: Optional[str] = None

    def get_normalized_metrics(self, max_distance: float) -> dict[str, float]:
        """정규화된 메트릭 반환"""
        # Distance: 0 = closest, 1 = farthest
        norm_distance = (
            min(1.0, max(0.0, self.distance_m / max(1.0, max_distance)))
            if max_distance > 0
            else 0.5
        )

        # Battery: 0-1, 배터리 30% 미만이면 penalty
        battery_norm = self.battery_percent / 100.0
        battery_penalty = 0.0 if self.battery_percent >= 30 else (30 - self.battery_percent) / 300.0
        norm_battery = max(0.0, battery_norm - battery_penalty)

        # Workload: 0-1, 작업 많을수록 높음
        norm_workload = min(1.0, self.current_tasks / max(1, self.max_concurrent_tasks))

        # Availability: idle 시간이 길면 보너스
        idle_threshold_sec = 300  # 5분 이상 유휴: 보너스
        norm_availability = 1.0 if self.idle_seconds >= idle_threshold_sec else (self.idle_seconds / idle_threshold_sec)

        return {
            "distance": norm_distance,
            "battery": norm_battery,
            "capability": self.capability_score,
            "reliability": self.reliability_score,
            "workload": norm_workload,
            "availability": norm_availability,
        }

    def to_dict(self) -> dict[str, Any]:
        """Dict 변환"""
        return {
            "device_id": self.device_id,
            "device_name": self.device_name,
            "distance_m": self.distance_m,
            "battery_percent": self.battery_percent,
            "capability_score": self.capability_score,
            "reliability_score": self.reliability_score,
            "current_tasks": self.current_tasks,
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "idle_seconds": self.idle_seconds,
        }


# ──────────────────────────────────────────────
# Task Dispatcher
# ──────────────────────────────────────────────

class TaskDispatcher:
    """다중 요소 기반 Task 할당 엔진"""

    def __init__(
        self,
        registry_client: Any,
        weights: Optional[SelectionWeights] = None,
        enable_logging: bool = True,
    ):
        self.registry_client = registry_client
        self.weights = weights or SelectionWeights()
        self.enable_logging = enable_logging

        # Validate weights
        if not self.weights.validate():
            logger.warning(
                f"SelectionWeights sum != 1.0: {sum(self.weights.to_dict().values()):.2f}. "
                "Using default weights."
            )
            self.weights = SelectionWeights()

        logger.info(f"TaskDispatcher initialized with weights: {self.weights.to_dict()}")

    def select_best_device(
        self,
        devices: list[dict[str, Any]],
        action: str,
        location: dict[str, Any],
        exclude_ids: Optional[set[int]] = None,
        preferred_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """
        다중 요소를 고려하여 가장 적합한 device 선택

        Scoring Factors:
        1. Distance: 목표 위치와의 거리 (가까울수록 좋음)
        2. Battery: 배터리 수준 (높을수록 좋음, 30% 미만 페널티)
        3. Capability: 해당 action 수행 능력 (native > alias > fallback)
        4. Reliability: 역사적 성공률 (높을수록 좋음)
        5. Workload: 현재 작업 부하 (작을수록 좋음)
        6. Availability: 유휴 시간 (길수록 좋음 = 덜 바쁨)

        Args:
            devices: 모든 디바이스 목록
            action: 요청 action (e.g., "survey_depth", "remove_mine")
            location: 작업 위치 {"latitude": ..., "longitude": ...}
            exclude_ids: 제외할 device ID 세트
            preferred_id: LLM이 추천한 device ID (우선 사용)

        Returns:
            선택된 device dict, 또는 None (candidate 없음)
        """
        excluded = exclude_ids or set()

        # Step 1: Filter candidates
        candidates = self._filter_candidates(devices, action, excluded)
        if not candidates:
            logger.warning(f"No candidates for action '{action}' at {location}")
            return None

        # Step 2: Check preferred device
        if preferred_id:
            preferred = next(
                (d for d in candidates if self._device_matches_id(d, preferred_id)),
                None,
            )
            if preferred:
                if self.enable_logging:
                    logger.info(f"Using LLM-preferred device: {preferred.get('name')} (ID={preferred.get('id')})")
                return preferred

        # Step 3: Calculate metrics for each candidate
        scored_candidates: list[tuple[float, DeviceMetric, dict[str, Any]]] = []
        for device in candidates:
            try:
                metric = self._calculate_device_metric(device, action, location)
                scored_candidates.append((0.0, metric, device))
            except Exception as e:
                logger.warning(f"Failed to calculate metric for device {device.get('id')}: {e}")
                continue

        if not scored_candidates:
            logger.warning(f"No valid metrics calculated for {len(candidates)} candidates")
            return None

        # Step 4: Calculate max distance (for normalization)
        max_distance = max((metric.distance_m for _, metric, _ in scored_candidates), default=1000.0)

        # Step 5: Score each device
        scores: list[tuple[float, DeviceMetric, dict[str, Any]]] = []
        for _, metric, device in scored_candidates:
            try:
                score = self._calculate_score(metric, max_distance)
                scores.append((score, metric, device))
            except Exception as e:
                logger.warning(f"Failed to calculate score for device {metric.device_id}: {e}")
                continue

        if not scores:
            logger.warning("No valid scores calculated")
            return None

        # Step 6: Select best (highest score)
        best_score, best_metric, best_device = max(scores, key=lambda item: item[0])

        if self.enable_logging:
            logger.info(
                f"Selected device: {best_metric.device_name} (ID={best_metric.device_id}) "
                f"with score {best_score:.3f} for action '{action}'"
            )

        return best_device

    def _filter_candidates(
        self,
        devices: list[dict[str, Any]],
        action: str,
        excluded_ids: set[int],
    ) -> list[dict[str, Any]]:
        """조건을 만족하는 후보 device 필터링"""
        candidates = []
        for device in devices:
            device_id = self._device_numeric_id(device)
            if device_id in excluded_ids:
                continue

            # Connected check
            if not self._is_device_connected(device):
                continue

            # Layer check (lower or middle)
            if str(device.get("layer") or "") not in {"lower", "middle"}:
                continue

            # Action capability check
            if not self._device_can_execute(device, action):
                continue

            # Reserve check (if available)
            if hasattr(self, '_is_device_reserved') and self._is_device_reserved(device_id):
                continue

            candidates.append(device)

        return candidates

    def _calculate_device_metric(
        self,
        device: dict[str, Any],
        action: str,
        location: dict[str, Any],
    ) -> DeviceMetric:
        """Device의 모든 메트릭 계산"""
        device_id = device.get("id")
        device_name = device.get("name") or f"Device-{device_id}"

        # Distance
        distance_m = self._calculate_distance(device, location)

        # Battery
        battery_percent = device.get("battery_percent") or 50
        if isinstance(battery_percent, str):
            try:
                battery_percent = int(battery_percent)
            except:
                battery_percent = 50

        # Capability score
        capability_score = self._get_capability_score(device, action)

        # Reliability score (from device history if available)
        reliability_score = self._get_reliability_score(device)

        # Workload
        current_tasks = len(device.get("current_tasks", []))
        max_concurrent = device.get("max_concurrent_tasks", 5)

        # Idle duration
        last_used_at = device.get("last_used_at")
        idle_seconds = self._calculate_idle_seconds(last_used_at)

        return DeviceMetric(
            device_id=device_id,
            device_name=device_name,
            distance_m=distance_m,
            battery_percent=battery_percent,
            capability_score=capability_score,
            reliability_score=reliability_score,
            current_tasks=current_tasks,
            max_concurrent_tasks=max_concurrent,
            idle_seconds=idle_seconds,
            last_used_at=last_used_at,
        )

    def _calculate_score(
        self,
        metric: DeviceMetric,
        max_distance: float,
    ) -> float:
        """복합 스코어 계산"""
        # Get normalized metrics
        norms = metric.get_normalized_metrics(max_distance)

        # Calculate weighted score
        # Higher is better, so invert distance and workload (they increase badness)
        score = (
            self.weights.distance * (1.0 - norms["distance"]) +
            self.weights.battery * norms["battery"] +
            self.weights.capability * norms["capability"] +
            self.weights.reliability * norms["reliability"] +
            self.weights.workload * (1.0 - norms["workload"]) +
            self.weights.availability * norms["availability"]
        )

        return score

    # ──────────────────────────────────────────────
    # Helper Methods (To be overridden by runtime)
    # ──────────────────────────────────────────────

    def _is_device_connected(self, device: dict[str, Any]) -> bool:
        """Device가 연결되어 있는가?"""
        if not device.get("connected"):
            return False
        agent = device.get("agent") or {}
        return isinstance(agent, dict) and bool(agent.get("endpoint"))

    def _device_can_execute(self, device: dict[str, Any], action: str) -> bool:
        """Device가 해당 action을 수행할 수 있는가?"""
        supported_actions = list(device.get("actions", {}).get("custom", []) or [])
        agent = device.get("agent") or {}
        if isinstance(agent, dict):
            supported_actions.extend(agent.get("available_actions", []))
            supported_actions.extend(agent.get("skills", []))
        
        action_lower = str(action).lower()
        return any(str(a).lower() == action_lower for a in supported_actions)

    def _device_numeric_id(self, device: dict[str, Any]) -> int:
        """Registry/공개 id 중 숫자로 해석 가능한 값을 우선 반환한다."""
        for key in ("registry_id", "id"):
            raw = device.get(key)
            if raw is None or raw == "":
                continue
            try:
                return int(raw)
            except (TypeError, ValueError):
                continue
        return 0

    def _device_matches_id(self, device: dict[str, Any], expected_id: str) -> bool:
        """공개 id 또는 registry_id 어느 쪽이든 일치하면 True."""
        if expected_id is None:
            return False
        needle = str(expected_id)
        for key in ("id", "registry_id"):
            raw = device.get(key)
            if raw is None:
                continue
            if str(raw) == needle:
                return True
        return False

    def _calculate_distance(self, device: dict[str, Any], location: dict[str, Any]) -> float:
        """Device와 위치 간 거리 (미터)"""
        device_lat = device.get("latitude", 0)
        device_lon = device.get("longitude", 0)
        target_lat = location.get("latitude", 0)
        target_lon = location.get("longitude", 0)

        if not all([device_lat, device_lon, target_lat, target_lon]):
            return 10000.0  # Default large distance

        # Haversine formula
        from math import radians, cos, sin, asin, sqrt

        lon1, lat1, lon2, lat2 = map(radians, [device_lon, device_lat, target_lon, target_lat])
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * asin(sqrt(a))
        r = 6371000  # Earth radius in meters
        return c * r

    def _get_capability_score(self, device: dict[str, Any], action: str) -> float:
        """Device의 action 수행 능력 점수"""
        device_type = str(device.get("device_type", "")).upper()
        action_lower = str(action).lower()

        # Native capability (device_type과 action이 정확히 매칭)
        capability_map = {
            ("AUV", "survey_depth"): 1.0,
            ("ROV", "remove_mine"): 1.0,
            ("USV", "patrol"): 1.0,
            ("SHIP", "escort"): 1.0,
        }

        for (dev_type, act), score in capability_map.items():
            if device_type == dev_type and action_lower == act.lower():
                return score

        # Alias capability
        if action_lower in ["scan_area", "sonar_scan"] and device_type == "AUV":
            return 0.8
        if action_lower in ["grab_object", "manipulate"] and device_type == "ROV":
            return 0.8

        # Fallback
        if self._device_can_execute(device, action):
            return 0.5

        return 0.0

    def _get_reliability_score(self, device: dict[str, Any]) -> float:
        """Device의 신뢰도 점수 (역사적 성공률)"""
        stats = device.get("execution_stats", {})
        if not stats:
            return 0.5  # Default for new device

        completed = stats.get("completed_tasks", 0)
        failed = stats.get("failed_tasks", 0)
        total = completed + failed

        if total == 0:
            return 0.5  # Default

        success_rate = completed / total
        return success_rate

    def _calculate_idle_seconds(self, last_used_at: Optional[str]) -> int:
        """마지막 사용 이후 경과 시간 (초)"""
        if not last_used_at:
            return 600  # 10분 (유휴 상태로 가정)

        try:
            from datetime import datetime, timezone
            last_used = datetime.fromisoformat(last_used_at.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            return int((now - last_used).total_seconds())
        except:
            return 600


__all__ = ["TaskDispatcher", "SelectionWeights", "DeviceMetric"]
