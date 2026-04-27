from __future__ import annotations

# AUV 디바이스에 대한 추천과 판단 규칙을 담는다.

from typing import Any, List

from ..core.models import AgentRecommendationRecord, DeviceAgentStateRecord
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
        depth = self.pressure_depth(payload)
        # 수면에 너무 가깝거나 깊이가 위험하면 즉시 수면 복귀를 권고한다.
        if altitude >= float(profile["rules"]["surface_altitude_m"]) or depth >= float(profile["rules"]["deep_depth_m"]):
            recommendations.append(
                AgentRecommendationRecord(
                    action="surface",
                    reason="AUV is close to the surface or at a risky depth and should surface.",
                    priority="high",
                    params={"current_altitude_m": altitude, "current_depth_m": depth},
                )
            )

        motion = payload.get("motion") or {}
        speed = float(motion.get("speed") or 0.0)
        # 주행 속도가 안전 기준을 넘으면 속도를 낮추도록 권고한다.
        if speed > float(profile["rules"]["max_speed_mps"]):
            recommendations.append(
                AgentRecommendationRecord(
                    action="slow_down",
                    reason="AUV speed is higher than the safe recommendation threshold.",
                    priority="high",
                    params={"target_speed_mps": profile["rules"]["max_speed_mps"]},
                )
            )

        # 배터리가 매우 낮으면 충전 타워로 이동하도록 권고한다.
        battery = self.battery_percent(payload)
        if battery is not None and battery < float(profile["rules"]["battery_critical_percent"]):
            recommendations.append(
                AgentRecommendationRecord(
                    action="charge_at_tower",
                    reason="AUV battery is critically low.",
                    priority="high",
                    params={"target_device_id": "ocean-power-tower-01"},
                )
            )
        # 배터리가 낮지만 아직 치명적이지 않으면 사용자에게 알린다.
        elif battery is not None and battery < float(profile["rules"]["battery_warn_percent"]):
            recommendations.append(
                AgentRecommendationRecord(
                    action="alert_operator",
                    reason="AUV battery is getting low.",
                    priority="normal",
                    params={"battery_percent": round(battery, 1)},
                )
            )

        # 소나가 타깃을 감지하면 세부 의미를 확정하지 않고 사용자에게 알린다.
        if self.sonar_target_detected(payload):
            recommendations.append(
                AgentRecommendationRecord(
                    action="alert_operator",
                    reason="AUV sonar indicates a possible target.",
                    priority="normal",
                    params={"source": envelope.get("stream", "telemetry")},
                )
            )

        # 임무가 없는 상태에서 home 범위를 벗어나면 이탈 알림을 보낸다.
        if not self.has_active_mission(session, payload):
            deviation = self.home_deviation_deg(session, payload)
            if deviation is not None and deviation > 0.01:
                recommendations.append(
                    AgentRecommendationRecord(
                        action="alert_operator",
                        reason="AUV moved outside the home radius without an active mission.",
                        priority="normal",
                        params={"home_deviation_deg": round(deviation, 6)},
                    )
                )

        return self.finalize(session, recommendations)
