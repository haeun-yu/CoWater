from __future__ import annotations

from typing import Any

from agent.state import AgentState
from simulator.base import BaseDeviceSimulator


class DeviceSimulator(BaseDeviceSimulator):
    def _advance_motion(self, interval: float) -> None:
        super()._advance_motion(interval)
        depth_target = None
        if isinstance(self.mission_state.get("target_position"), dict):
            depth_target = self.mission_state["target_position"].get("altitude")
        if depth_target is not None:
            current = float(self.position.get("altitude", 0.0))
            target = float(depth_target)
            step = max(0.05, min(abs(target - current), self.motion["speed"] * interval * 0.25))
            self.position["altitude"] = current + step if target > current else max(0.0, current - step)

    def _platform_telemetry(self, state: AgentState) -> dict[str, Any]:
        telemetry: dict[str, Any] = {
            "depth": round(abs(float(self.position.get("altitude", 0.0))), 2),
            "depth_sensor": {"depth_meters": round(abs(float(self.position.get("altitude", 0.0))), 2)},
            "navigation": {
                "mode": self.mission_state.get("mode"),
                "target_depth": (self.mission_state.get("target_position") or {}).get("altitude"),
            },
        }
        telemetry["sensors"] = {
            **telemetry.get("sensors", {}),
            "sonar": getattr(self, "_sonar_scanner", None).scan() if getattr(self, "_sonar_scanner", None) is not None else {"status": "idle"},
            "depth_sensor": getattr(self, "_depth_sensor", None).read() if getattr(self, "_depth_sensor", None) is not None else {"depth_meters": telemetry["depth"]},
            "acoustic_modem": getattr(self, "_acoustic_modem", None).get_link_status() if getattr(self, "_acoustic_modem", None) is not None else {"status": "ok"},
        }
        telemetry["mission"] = dict(self.mission_state)
        return telemetry

    def _apply_platform_action(
        self,
        action: str,
        params: dict[str, Any],
        tools: dict[str, Any],
        result: dict[str, Any],
    ) -> bool:
        self._sonar_scanner = tools.get("sonar_scanner")
        self._depth_sensor = tools.get("depth_sensor")
        self._acoustic_modem = tools.get("acoustic_modem")
        self._route_planner = tools.get("route_planner")

        if action in {"scan_area", "survey_depth"}:
            self.mission_state.update(
                {
                    "mode": "survey",
                    "status": "scanning",
                    "active_action": action,
                    "target_position": {
                        "latitude": float(self.position.get("latitude", 0.0)),
                        "longitude": float(self.position.get("longitude", 0.0)),
                        "altitude": float(params.get("depth_m") or params.get("target_depth_m") or self.position.get("altitude", 0.0)),
                    },
                }
            )
            if self._sonar_scanner is not None:
                self._sonar_scanner.last_scan = {
                    "at": result["at"],
                    "area": params.get("area") or params.get("location") or "current_position",
                    "depth_m": float(self.position.get("altitude", 0.0)),
                }
            if self._depth_sensor is not None and hasattr(self._depth_sensor, "set_depth"):
                self._depth_sensor.set_depth(float(self.position.get("altitude", 0.0)))
            result["artifacts"].append(
                {
                    "type": "sonar_sweep",
                    "scan_mode": action,
                    "depth_m": round(float(self.position.get("altitude", 0.0)), 2),
                    "coverage": "full",
                }
            )
            return True
        if action in {"dive_to_depth", "hold_depth", "follow_route"}:
            target_depth = float(params.get("depth_m") or params.get("target_depth_m") or self.position.get("altitude", 0.0))
            if action == "hold_depth":
                target_depth = float(self.position.get("altitude", 0.0))
            self.mission_state.update(
                {
                    "mode": "subsurface_navigation",
                    "status": "moving",
                    "active_action": action,
                    "target_position": {
                        "latitude": float(self.position.get("latitude", 0.0)),
                        "longitude": float(self.position.get("longitude", 0.0)),
                        "altitude": target_depth,
                    },
                }
            )
            result["artifacts"].append({"type": "depth_target", "depth_m": target_depth})
            return True
        if action in {"surface", "emergency_ascent"}:
            self.mission_state.update(
                {
                    "mode": action,
                    "status": "ascending",
                    "active_action": action,
                    "target_position": {
                        "latitude": float(self.position.get("latitude", 0.0)),
                        "longitude": float(self.position.get("longitude", 0.0)),
                        "altitude": 0.0,
                    },
                    "speed_limit": max(float(self.motion.get("speed", 0.5)), 0.5),
                }
            )
            result["artifacts"].append({"type": "ascent_ack", "mode": action})
            return True
        if action == "abort_mission":
            self.mission_state.update({"mode": "abort", "status": "aborted", "active_action": action, "target_position": None})
            result["artifacts"].append({"type": "abort_ack"})
            return True
        return False
