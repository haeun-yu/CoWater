from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, List, Optional

from ..models import AgentRecommendationRecord, DeviceAgentStateRecord


class DeviceAgentBase(ABC):
    device_type: str = "usv"

    def __init__(self, profiles: dict[str, dict[str, Any]]) -> None:
        self._profiles = profiles

    def profile(self) -> dict[str, Any]:
        if self.device_type in self._profiles:
            return self._profiles[self.device_type]
        return self._profiles["usv"]

    def apply_profile(self, session: DeviceAgentStateRecord) -> None:
        profile = self.profile()
        session.device_type = self.device_type
        session.supported_modes = list(profile.get("supported_modes", []))
        session.agent_mode = (
            session.agent_mode if session.agent_mode in session.supported_modes else profile.get("preferred_mode", "dynamic")
        )
        session.llm_optional = bool(profile.get("llm_optional", True))
        session.skills = list(profile.get("skills", []))
        session.tools = list(profile.get("tools", []))
        session.constraints = list(profile.get("constraints", []))
        session.context["profile"] = {
            "device_side": profile.get("device_side", []),
            "agent_side": profile.get("agent_side", []),
            "rules": profile.get("rules", {}),
        }
        session.context["agent"] = {
            "type": self.device_type,
            "mode": session.agent_mode,
            "llm_optional": session.llm_optional,
        }

    def prepare_session(self, session: DeviceAgentStateRecord, envelope: dict[str, Any], payload: dict[str, Any]) -> None:
        if isinstance(payload.get("position"), dict) and session.home_position is None:
            session.home_position = payload["position"]
        session.context["last_stream"] = envelope.get("stream")

    def finalize(self, session: DeviceAgentStateRecord, recommendations: List[AgentRecommendationRecord]) -> List[AgentRecommendationRecord]:
        if session.agent_mode == "static":
            return recommendations[:1]
        return recommendations[:3]

    @abstractmethod
    def recommend(
        self,
        session: DeviceAgentStateRecord,
        envelope: dict[str, Any],
        payload: dict[str, Any],
    ) -> List[AgentRecommendationRecord]:
        raise NotImplementedError

    @staticmethod
    def sonar_target_detected(payload: dict[str, Any]) -> bool:
        sensors = payload.get("sensors")
        if not isinstance(sensors, dict):
            return False
        for sensor in sensors.values():
            if not isinstance(sensor, dict):
                continue
            if sensor.get("target_detected"):
                return True
        return False

    @staticmethod
    def pressure_depth(payload: dict[str, Any]) -> float:
        sensors = payload.get("sensors")
        if not isinstance(sensors, dict):
            return 0.0
        for sensor in sensors.values():
            if not isinstance(sensor, dict):
                continue
            depth = sensor.get("depth_m")
            if depth is not None:
                try:
                    return float(depth)
                except (TypeError, ValueError):
                    continue
        return 0.0

    @staticmethod
    def camera_low_light(payload: dict[str, Any], threshold_lux: float) -> bool:
        sensors = payload.get("sensors")
        if not isinstance(sensors, dict):
            return False
        for sensor in sensors.values():
            if not isinstance(sensor, dict):
                continue
            if sensor.get("type") != "hd_camera":
                continue
            light_level = sensor.get("light_level_lux")
            if light_level is None:
                continue
            try:
                return float(light_level) < threshold_lux
            except (TypeError, ValueError):
                continue
        return False
