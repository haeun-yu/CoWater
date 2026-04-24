from __future__ import annotations

# ROV 디바이스에 대한 추천과 판단 규칙을 담는다.

from typing import Any, List

from ..models import AgentRecommendationRecord, DeviceAgentStateRecord
from .base import DeviceAgentBase


class ROVAgent(DeviceAgentBase):
    device_type = "rov"

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

        if self.camera_low_light(payload, float(profile["rules"]["low_light_lux"])):
            recommendations.append(
                AgentRecommendationRecord(
                    action="light_on",
                    reason="ROV camera light level is low.",
                    priority="high",
                    params={"low_light_lux": profile["rules"]["low_light_lux"]},
                )
            )

        if self.sonar_target_detected(payload):
            recommendations.append(
                AgentRecommendationRecord(
                    action="move_to_device",
                    reason="ROV sonar detected a target that should be inspected more closely.",
                    priority="normal",
                )
            )

        motion = payload.get("motion") or {}
        speed = float(motion.get("speed") or 0.0)
        if speed > float(profile["rules"]["slow_speed_mps"]):
            recommendations.append(
                AgentRecommendationRecord(
                    action="hold_position",
                    reason="ROV is moving faster than the conservative inspection speed.",
                    priority="normal",
                    params={"target_speed_mps": profile["rules"]["slow_speed_mps"]},
                )
            )

        return self.finalize(session, recommendations)
