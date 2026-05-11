from __future__ import annotations

from typing import Any

from agent.state import AgentState
from simulator.base import BaseDeviceSimulator


class DeviceSimulator(BaseDeviceSimulator):
    def _platform_telemetry(self, state: AgentState) -> dict[str, Any]:
        child_registry = getattr(self, "_child_registry", None)
        tether = getattr(self, "_rov_tether_controller", None)
        wired = getattr(self, "_wired_link_monitor", None)
        telemetry = {
            "navigation": {
                "route_mode": self.mission_state.get("mode"),
                "target_position": self.mission_state.get("target_position"),
            },
            "children": child_registry.list_children() if child_registry is not None else [],
            "tether": tether.get_tether_info() if tether is not None else {"current_length_meters": 0.0, "tension_status": "normal"},
            "wired_link": wired.check_link_health() if wired is not None else {"connected": False, "status": "degraded"},
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
        self._child_registry = tools.get("child_registry")
        self._rov_tether_controller = tools.get("rov_tether_controller")
        self._wired_link_monitor = tools.get("wired_link_monitor")
        self._video_processor = tools.get("video_processor") or tools.get("camera_controller") or tools.get("high_def_camera")
        self._a2a_router = tools.get("a2a_router")

        if action == "manage_tether_length":
            length = float(params.get("length_m") or params.get("tether_length_m") or 0.0)
            if self._rov_tether_controller is not None:
                self._rov_tether_controller.set_tether_length(length)
            tension = "critical" if length > 800 else "warning" if length > 500 else "normal"
            self.mission_state.update({"mode": "tether_management", "status": "adjusting", "active_action": action, "tether_length_m": length, "tether_tension": tension})
            result["artifacts"].append({"type": "tether_update", "length_m": length, "tension": tension})
            return True
        if action == "coordinate_children":
            children = self._child_registry.list_children() if self._child_registry is not None else []
            self.mission_state.update({"mode": "coordination", "status": "coordinating", "active_action": action, "child_count": len(children)})
            self._children_snapshot = children
            if self._a2a_router is not None:
                for child in children:
                    child_id = child.get("id") or child.get("device_id")
                    endpoint = child.get("endpoint")
                    if child_id is not None and endpoint:
                        try:
                            self._a2a_router.update_route(int(child_id), str(endpoint))
                        except Exception:
                            continue
            result["artifacts"].append({"type": "child_coordination", "children": children})
            return True
        if action == "manage_rov_power":
            power_budget = float(params.get("budget_percent") or 100.0)
            self.mission_state.update({"mode": "power_management", "status": "balancing", "active_action": action, "rov_power_budget": power_budget})
            result["artifacts"].append({"type": "power_budget", "budget_percent": power_budget})
            return True
        if action == "capture_video":
            self.mission_state.update({"mode": "video_capture", "status": "capturing", "active_action": action})
            if self._video_processor is not None:
                if params.get("recording", True) and hasattr(self._video_processor, "start_recording"):
                    self._video_processor.start_recording()
                frame = None
                if hasattr(self._video_processor, "capture_frame"):
                    frame = self._video_processor.capture_frame()
                if params.get("recording") is False and hasattr(self._video_processor, "stop_recording"):
                    self._video_processor.stop_recording()
                result["artifacts"].append(
                    {
                        "type": "video_frame",
                        "captured": frame is not None,
                        "camera_status": self._video_processor.get_status() if hasattr(self._video_processor, "get_status") else {},
                    }
                )
            else:
                result["status"] = "failed"
                result["usable_output"] = False
                result["failure_reason"] = "video_processor_unavailable"
                result["artifacts"].append({"type": "video_frame", "captured": False})
            return True
        if action == "relay_data":
            if self._wired_link_monitor is not None:
                self._wired_link_monitor.connected = True
            self.mission_state.update({"mode": "relay", "status": "relaying", "active_action": action, "relay_active": True, "last_relay": params.get("channel") or "general"})
            result["artifacts"].append({"type": "relay_ack", "channel": params.get("channel") or "general"})
            return True
        if action in {"route_move", "hold_position", "slow_down", "return_to_base", "abort_mission", "emergency_stop"}:
            if action == "abort_mission":
                self.mission_state["route_canceled"] = True
            result["artifacts"].append({"type": "ship_navigation", "action": action})
            return False
        return False
