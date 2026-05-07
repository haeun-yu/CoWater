from __future__ import annotations

from typing import Any

from agent.state import AgentState
from simulator.base import BaseDeviceSimulator


class DeviceSimulator(BaseDeviceSimulator):
    def _advance_motion(self, interval: float) -> None:
        super()._advance_motion(interval)
        if self.mission_state.get("active_action") == "move_up":
            current = float(self.position.get("altitude", 0.0))
            self.position["altitude"] = max(0.0, current - max(0.05, self.motion["speed"] * interval * 0.3))

    def _platform_telemetry(self, state: AgentState) -> dict[str, Any]:
        manipulator = getattr(self, "_manipulator_arm", None)
        camera = getattr(self, "_camera", None)
        tether = getattr(self, "_tether_monitor", None)
        telemetry = {
            "depth": round(abs(float(self.position.get("altitude", 0.0))), 2),
            "manipulator": manipulator.get_status() if manipulator is not None else {"is_gripping": False, "grip_force": 0.0},
            "camera": camera.get_status() if camera is not None else {"recording": False},
            "tether": tether.get_tether_info() if tether is not None else {"current_length_meters": 0.0, "status": "normal"},
            "mission": dict(self.mission_state),
        }
        return telemetry

    def _apply_platform_action(
        self,
        action: str,
        params: dict[str, Any],
        tools: dict[str, Any],
        result: dict[str, Any],
    ) -> bool:
        self._manipulator_arm = tools.get("manipulator_arm")
        self._camera = tools.get("camera_controller") or tools.get("high_def_camera")
        self._tether_monitor = tools.get("tether_monitor")
        self._route_planner = tools.get("route_planner")

        if action == "move_forward":
            self.mission_state.update({"mode": "navigation", "status": "advancing", "active_action": action, "speed_limit": float(params.get("speed_mps") or 0.5)})
            result["artifacts"].append({"type": "motion_step", "direction": "forward"})
            return True
        if action == "move_up":
            current_depth = float(self.position.get("altitude", 0.0))
            self.mission_state.update({"mode": "ascent", "status": "ascending", "active_action": action, "target_position": {"latitude": float(self.position.get("latitude", 0.0)), "longitude": float(self.position.get("longitude", 0.0)), "altitude": max(0.0, current_depth - 1.0)}})
            result["artifacts"].append({"type": "ascent_step", "current_depth": current_depth})
            return True
        if action == "rotate":
            angle = float(params.get("angle_deg") or 0.0)
            self.motion["heading"] = (self.motion.get("heading", 0.0) + angle) % 360
            self.mission_state.update({"mode": "rotation", "status": "rotating", "active_action": action})
            result["artifacts"].append({"type": "heading_update", "angle_deg": angle, "heading": self.motion["heading"]})
            return True
        if action in {"grab_object", "remove_mine"}:
            if self._manipulator_arm is not None and hasattr(self._manipulator_arm, "grip"):
                self._manipulator_arm.grip(float(params.get("force") or 80.0))
            self.mission_state.update({"mode": "manipulation", "status": "working", "active_action": action})
            result["artifacts"].append({"type": "manipulation", "action": action, "grip": True})
            return True
        if action == "release_object":
            if self._manipulator_arm is not None and hasattr(self._manipulator_arm, "release"):
                self._manipulator_arm.release()
            self.mission_state.update({"mode": "manipulation", "status": "released", "active_action": action})
            result["artifacts"].append({"type": "manipulation", "action": action, "grip": False})
            return True
        if action == "adjust_lights":
            if self._camera is not None and hasattr(self._camera, "light_level"):
                self._camera.light_level = int(params.get("brightness") or params.get("level") or 50)
            result["artifacts"].append({"type": "camera_light", "brightness": getattr(self._camera, "light_level", 50)})
            return True
        if action == "record_video":
            if self._camera is not None:
                if params.get("recording", True):
                    if hasattr(self._camera, "start_recording"):
                        self._camera.start_recording()
                else:
                    if hasattr(self._camera, "stop_recording"):
                        self._camera.stop_recording()
            self.mission_state.update({"mode": "recording", "status": "recording", "active_action": action})
            result["artifacts"].append({"type": "video_recording", "recording": params.get("recording", True)})
            return True
        if action in {"inspect_target", "scan_target"}:
            self.mission_state.update({"mode": "inspection", "status": "inspecting", "active_action": action})
            if self._camera is not None and hasattr(self._camera, "start_recording"):
                self._camera.start_recording()
            result["artifacts"].append({"type": "inspection_report", "target": params.get("target_id") or params.get("location")})
            return True
        if action == "detonate_mine":
            self.mission_state.update({"mode": "safe_retreat", "status": "retreating", "active_action": action})
            result["artifacts"].append({"type": "detonation_ack", "safe_distance_m": params.get("safe_distance_m", 20)})
            return True
        if action == "abort_mission":
            self.mission_state.update({"mode": "abort", "status": "aborted", "active_action": action, "target_position": None})
            result["artifacts"].append({"type": "abort_ack"})
            return True
        return False

