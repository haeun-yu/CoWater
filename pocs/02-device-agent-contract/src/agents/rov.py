from __future__ import annotations

# ROV 디바이스에 대한 추천과 판단 규칙을 담는다.

from typing import Any, List

from ..core.models import AgentRecommendationRecord, DeviceAgentStateRecord
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

        motion = payload.get("motion") or {}
        speed = float(motion.get("speed") or 0.0)
        # 정밀 작업 중 과속이면 속도를 낮추도록 권고한다.
        if speed > float(profile["rules"]["max_speed_mps"]):
            recommendations.append(
                AgentRecommendationRecord(
                    action="slow_down",
                    reason="ROV speed is higher than the conservative inspection speed.",
                    priority="high",
                    params={"target_speed_mps": profile["rules"]["max_speed_mps"]},
                )
            )

        # 배터리가 매우 낮으면 충전 타워로 복귀시키는 것이 우선이다.
        battery = self.battery_percent(payload)
        if battery is not None and battery < float(profile["rules"]["battery_critical_percent"]):
            recommendations.append(
                AgentRecommendationRecord(
                    action="charge_at_tower",
                    reason="ROV battery is critically low.",
                    priority="high",
                    params={"target_device_id": "ocean-power-tower-01"},
                )
            )
        # 배터리가 낮지만 아직 치명적이지 않으면 사용자에게 알린다.
        elif battery is not None and battery < float(profile["rules"]["battery_warn_percent"]):
            recommendations.append(
                AgentRecommendationRecord(
                    action="alert_operator",
                    reason="ROV battery is getting low.",
                    priority="normal",
                    params={"battery_percent": round(battery, 1)},
                )
            )

        # 조도가 낮고 조명이 꺼져 있으면 조명 점등을 권고한다.
        if self.camera_low_light(payload, float(profile["rules"]["low_light_lux"])):
            light_status = self.light_status(payload)
            if light_status == "off":
                recommendations.append(
                    AgentRecommendationRecord(
                        action="light_on",
                        reason="ROV camera light level is low and the light can be turned on.",
                        priority="high",
                        params={"low_light_lux": profile["rules"]["low_light_lux"]},
                    )
                )
            # 조명이 이미 켜져 있거나 상태를 확정할 수 없으면 사용자에게 알린다.
            else:
                recommendations.append(
                    AgentRecommendationRecord(
                        action="alert_operator",
                        reason="ROV camera light level is low but the light is already on or unavailable.",
                        priority="normal",
                        params={"light_status": light_status or "unknown"},
                    )
                )
        # 조도 판정이 없는데 조명 상태도 확인되지 않으면 상태 확인 알림을 남긴다.
        elif self.light_status(payload) is None:
            recommendations.append(
                AgentRecommendationRecord(
                    action="alert_operator",
                    reason="ROV light status is unavailable.",
                    priority="normal",
                )
            )

        # 소나가 타깃을 감지하면 우선 사용자에게 알린다.
        if self.sonar_target_detected(payload):
            recommendations.append(
                AgentRecommendationRecord(
                    action="alert_operator",
                    reason="ROV sonar indicates a possible target.",
                    priority="normal",
                    params={"source": envelope.get("stream", "telemetry")},
                )
            )

        # active mission이 없는데 home 범위를 벗어나면 이탈 알림을 보낸다.
        if not self.has_active_mission(session, payload):
            deviation = self.home_deviation_deg(session, payload)
            if deviation is not None and deviation > 0.01:
                recommendations.append(
                    AgentRecommendationRecord(
                        action="alert_operator",
                        reason="ROV moved outside the home radius without an active mission.",
                        priority="normal",
                        params={"home_deviation_deg": round(deviation, 6)},
                    )
                )

        return self.finalize(session, recommendations)
