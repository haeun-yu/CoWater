from __future__ import annotations

import random
from typing import Any

from agent.state import AgentState
from simulator.base import BaseDeviceSimulator


class DeviceSimulator(BaseDeviceSimulator):
    def _platform_telemetry(self, state: AgentState) -> dict[str, Any]:
        telemetry: dict[str, Any] = {
            "navigation": {
                "route_mode": self.mission_state.get("mode"),
                "target_position": self.mission_state.get("target_position"),
                "follow_target_id": self.mission_state.get("follow_target_id"),
            }
        }
        motor_control = getattr(self, "_motor_control", None)
        route_planner = getattr(self, "_route_planner", None)
        obstacle_detector = getattr(self, "_obstacle_detector", None)
        imu_reader = getattr(self, "_imu_reader", None)
        battery_monitor = getattr(self, "_battery_monitor", None)
        gps_reader = getattr(self, "_gps_reader", None)
        if motor_control is not None:
            telemetry["motor"] = motor_control.get_status()
        if route_planner is not None:
            telemetry["route"] = route_planner.get_current_route()
        if obstacle_detector is not None:
            telemetry["obstacles"] = obstacle_detector.detect()
        if imu_reader is not None:
            telemetry["imu"] = imu_reader.read()
        if battery_monitor is not None:
            telemetry["battery"] = battery_monitor.read()
        if gps_reader is not None:
            telemetry["gps"] = gps_reader.read()
        telemetry["children"] = getattr(self, "_children_snapshot", [])
        telemetry["a2a"] = {
            "relay_active": self.mission_state.get("relay_active", False),
            "last_relay": self.mission_state.get("last_relay"),
        }
        return telemetry

    def _apply_platform_action(
        self,
        action: str,
        params: dict[str, Any],
        tools: dict[str, Any],
        result: dict[str, Any],
    ) -> bool:
        self._motor_control = tools.get("motor_control")
        self._route_planner = tools.get("route_planner")
        self._obstacle_detector = tools.get("obstacle_detector")
        self._imu_reader = tools.get("imu_reader")
        self._battery_monitor = tools.get("battery_monitor")
        self._gps_reader = tools.get("gps_reader")

        if action == "follow_target":
            target = self._resolve_target_position(params)
            if target is not None:
                self.mission_state["target_position"] = target
            self.mission_state["follow_target_id"] = str(params.get("target_id") or params.get("target_device_id") or "") or None
            if self._motor_control is not None:
                self._motor_control.set_thrust(0.65, random.uniform(-0.15, 0.15))
            result["artifacts"].append({"type": "target_tracking", "target_id": self.mission_state.get("follow_target_id")})
            return True
        if action == "abort_mission":
            if self._motor_control is not None:
                self._motor_control.stop()
            self.mission_state["reason"] = "operator_abort"
            result["artifacts"].append({"type": "abort_ack"})
            return True
        if action == "emergency_stop":
            if self._motor_control is not None:
                self._motor_control.stop()
            self.mission_state["reason"] = "emergency_stop"
            result["artifacts"].append({"type": "emergency_stop_ack"})
            return True
        return False

