from __future__ import annotations

# USV 디바이스에 대한 추천과 판단 규칙을 담는다.

from typing import Any, List

from ..core.models import AgentRecommendationRecord, DeviceAgentStateRecord
from .base import DeviceAgentBase


class USVAgent(DeviceAgentBase):
    device_type = "usv"

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
        motion = payload.get("motion") or {}
        speed = float(motion.get("speed") or 0.0)

        if speed > float(profile["rules"]["max_speed_mps"]):
            recommendations.append(
                AgentRecommendationRecord(
                    action="hold_position",
                    reason="USV speed is higher than the safe recommendation threshold.",
                    priority="high",
                    params={"target_speed_mps": profile["rules"]["max_speed_mps"]},
                )
            )

        if self.sonar_target_detected(payload):
            recommendations.append(
                AgentRecommendationRecord(
                    action="follow_target",
                    reason="USV sonar indicates a possible target.",
                    priority="high",
                    params={"source": envelope.get("stream", "telemetry")},
                )
            )

        home = session.home_position
        current = payload.get("position") or {}
        if home and isinstance(current, dict):
            lat_delta = abs(float(current.get("latitude", 0.0)) - float(home.get("latitude", 0.0)))
            lon_delta = abs(float(current.get("longitude", 0.0)) - float(home.get("longitude", 0.0)))
            if lat_delta + lon_delta > float(profile["rules"]["home_radius_deg"]):
                recommendations.append(
                    AgentRecommendationRecord(
                        action="return_to_base",
                        reason="USV moved outside the home radius.",
                        priority="normal",
                        params={"home_position": home},
                    )
                )

        return self.finalize(session, recommendations)
