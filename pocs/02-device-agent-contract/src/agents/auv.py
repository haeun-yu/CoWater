from __future__ import annotations

# AUV 디바이스에 대한 추천과 판단 규칙을 담는다.

from typing import Any, List

from ..models import AgentRecommendationRecord, DeviceAgentStateRecord
from .base import DeviceAgentBase


class AUVAgent(DeviceAgentBase):
    device_type = "auv"

    def recommend(
        self,
        session: DeviceAgentStateRecord,
        envelope: dict[str, Any],
        payload: dict[str, Any],
    ) -> List[AgentRecommendationRecord]:
        self.apply_profile(session)
        self.prepare_session(session, envelope, payload)

        profile = self.profile()
        recommendations: List[AgentRecommendationRecord] = []

        position = payload.get("position") or {}
        altitude = float(position.get("altitude") or 0.0)
        if altitude >= float(profile["rules"]["surface_altitude_m"]):
            recommendations.append(
                AgentRecommendationRecord(
                    action="surface",
                    reason="AUV is close to the surface and can surface safely.",
                    priority="high",
                    params={"current_altitude_m": altitude},
                )
            )

        depth = self.pressure_depth(payload)
        if depth >= float(profile["rules"]["deep_depth_m"]):
            recommendations.append(
                AgentRecommendationRecord(
                    action="hold_depth",
                    reason="AUV is operating at deep depth and should hold depth.",
                    priority="normal",
                    params={"current_depth_m": depth},
                )
            )

        if self.sonar_target_detected(payload):
            recommendations.append(
                AgentRecommendationRecord(
                    action="patrol_route",
                    reason="AUV sonar detected a target and a wider patrol path is recommended.",
                    priority="normal",
                )
            )

        return self.finalize(session, recommendations)
