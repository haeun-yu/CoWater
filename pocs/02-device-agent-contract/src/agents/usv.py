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

        # 주행 속도가 안전 기준을 넘으면 속도를 낮추도록 권고한다.
        if speed > float(profile["rules"]["max_speed_mps"]):
            recommendations.append(
                AgentRecommendationRecord(
                    action="slow_down",
                    reason="USV speed is higher than the safe recommendation threshold.",
                    priority="high",
                    params={"target_speed_mps": profile["rules"]["max_speed_mps"]},
                )
            )

        # 배터리가 매우 낮으면 전력 타워로 이동해서 충전하도록 권고한다.
        battery = self.battery_percent(payload)
        if battery is not None and battery < float(profile["rules"]["battery_critical_percent"]):
            recommendations.append(
                AgentRecommendationRecord(
                    action="charge_at_tower",
                    reason="USV battery is critically low.",
                    priority="high",
                    params={"target_device_id": "ocean-power-tower-01"},
                )
            )
        # 배터리가 낮지만 아직 치명적이지 않으면 사용자에게 먼저 알린다.
        elif battery is not None and battery < float(profile["rules"]["battery_warn_percent"]):
            recommendations.append(
                AgentRecommendationRecord(
                    action="alert_operator",
                    reason="USV battery is getting low.",
                    priority="normal",
                    params={"battery_percent": round(battery, 1)},
                )
            )

        # 소나가 타깃을 감지하면 정확한 의미를 단정하지 않고 사용자에게 알린다.
        if self.sonar_target_detected(payload):
            recommendations.append(
                AgentRecommendationRecord(
                    action="alert_operator",
                    reason="USV sonar indicates a possible target.",
                    priority="normal",
                    params={"source": envelope.get("stream", "telemetry")},
                )
            )

        # 진행 중인 임무가 없는데 home 범위를 벗어났다면 이탈 알림을 보낸다.
        if not self.has_active_mission(session, payload):
            deviation = self.home_deviation_deg(session, payload)
            if deviation is not None and deviation > float(profile["rules"]["home_radius_deg"]):
                recommendations.append(
                    AgentRecommendationRecord(
                        action="alert_operator",
                        reason="USV moved outside the home radius without an active mission.",
                        priority="normal",
                        params={"home_deviation_deg": round(deviation, 6)},
                    )
                )

        return self.finalize(session, recommendations)
