from __future__ import annotations

import math
import random
from typing import Any

from agent.state import AgentState, utc_now


class BaseDeviceSimulator:
    def __init__(self, simulation_config: dict[str, Any], tracks: list[dict[str, Any]]) -> None:
        self.config = simulation_config
        self.tracks = tracks
        self.home_position = dict(simulation_config.get("start_position") or {})
        self.position = dict(self.home_position)
        self.motion = {
            "heading": random.uniform(0, 360),
            "speed": random.uniform(*simulation_config.get("speed_range", [0.2, 1.0])),
        }
        self.battery = random.uniform(65, 100)
        self.command_history: list[dict[str, Any]] = []
        self.mission_state: dict[str, Any] = {
            "mode": "idle",
            "status": "ready",
            "active_action": None,
            "target_position": None,
            "speed_limit": self.motion["speed"],
            "follow_target_id": None,
            "route": {
                "waypoints": [],
                "current_index": 0,
                "completed": True,
                "route_mode": None,
            },
            "notes": [],
        }

    def interval_seconds(self) -> float:
        return float(self.config.get("interval_seconds") or 2)

    def next_telemetry(self, state: AgentState) -> dict[str, Any]:
        self._advance_motion(self.interval_seconds())
        telemetry = {
            "device_id": state.registry_id,
            "agent_id": state.agent_id,
            "device_type": state.device_type,
            "timestamp": utc_now(),
            "position": self.position,
            "motion": self.motion,
            "battery_percent": round(self.battery, 2),
            "battery": {"charge_percent": round(self.battery, 2)},
            "mission": dict(self.mission_state),
            "sensors": self._sensor_values(),
        }
        telemetry.update(self._platform_telemetry(state))
        self.battery = max(0, self.battery - self._battery_drain_rate())
        return telemetry

    def apply_command(self, state: AgentState, command: dict[str, Any], tools: dict[str, Any]) -> dict[str, Any]:
        action = str(command.get("action") or "").strip().lower()
        params = dict(command.get("params") or {})
        self.command_history.append({"at": utc_now(), "command": command})
        self.command_history = self.command_history[-50:]

        result: dict[str, Any] = {
            "delivered": True,
            "command": command,
            "at": utc_now(),
            "status": "completed",
            "usable_output": True,
            "failure_reason": None,
            "confidence": 0.88,
            "artifacts": [],
            "mission_state": {},
        }

        handled = self._apply_common_action(action, params, tools, result)
        if not handled:
            handled = self._apply_platform_action(action, params, tools, result)

        simulate_outcome = params.get("simulate_outcome") or {}
        if params.get("simulate_failure") is True:
            simulate_outcome = {
                **simulate_outcome,
                "status": "failed",
                "usable_output": False,
                "failure_reason": simulate_outcome.get("failure_reason") or "simulated_failure",
            }
        if isinstance(simulate_outcome, dict) and simulate_outcome:
            if "status" in simulate_outcome:
                result["status"] = str(simulate_outcome["status"])
            if "usable_output" in simulate_outcome:
                result["usable_output"] = bool(simulate_outcome["usable_output"])
            if "failure_reason" in simulate_outcome:
                result["failure_reason"] = simulate_outcome["failure_reason"]
            if "confidence" in simulate_outcome:
                result["confidence"] = float(simulate_outcome["confidence"])
            if "artifacts" in simulate_outcome and isinstance(simulate_outcome["artifacts"], list):
                result["artifacts"] = list(simulate_outcome["artifacts"])
            if "delivered" in simulate_outcome:
                result["delivered"] = bool(simulate_outcome["delivered"])
            if result.get("status") == "failed" and "usable_output" not in simulate_outcome:
                result["usable_output"] = False

        result["mission_state"] = dict(self.mission_state)
        if result.get("status") == "failed":
            result.setdefault("failure_reason", "simulated_failure")
        state.last_command = command  # type: ignore[attr-defined]
        state.mission_state = dict(self.mission_state)  # type: ignore[attr-defined]
        return result

    def _battery_drain_rate(self) -> float:
        speed = abs(float(self.motion.get("speed", 0.0)))
        load = min(1.0, speed / max(1.0, float(self.motion.get("max_speed", 1.0))))
        if self.mission_state.get("mode") in {"abort", "emergency_stop"}:
            return 0.02
        return 0.01 + (0.05 * load)

    def _advance_motion(self, interval: float) -> None:
        if not self.position:
            return
        self._advance_route_state()
        target = self._current_route_target() or self.mission_state.get("target_position") or {}
        speed_limit = float(self.mission_state.get("speed_limit") or self.motion.get("speed") or 0.0)
        self.motion["speed"] = max(0.0, min(max(speed_limit, 0.05), self.motion["speed"] + random.uniform(-0.05, 0.05)))
        if target:
            self._move_toward_target(target, interval)
        else:
            self._drift(interval)

    def _move_toward_target(self, target: dict[str, Any], interval: float) -> None:
        lat = target.get("latitude")
        lon = target.get("longitude")
        alt = target.get("altitude")
        if lat is not None:
            self.position["latitude"] = self._interpolate(float(self.position.get("latitude", 0.0)), float(lat), self.motion["speed"], interval)
        if lon is not None:
            self.position["longitude"] = self._interpolate(float(self.position.get("longitude", 0.0)), float(lon), self.motion["speed"], interval)
        if alt is not None:
            self.position["altitude"] = self._interpolate(
                float(self.position.get("altitude", 0.0)),
                float(alt),
                max(self.motion["speed"], 0.1),
                interval,
                scale=1.0,
            )
        if self._distance_to(target) < 3.0:
            if self.mission_state.get("mode") not in {"hold_position", "abort", "emergency_stop"}:
                self.mission_state["status"] = "target_reached"
            self._advance_route_state(force=True)

    def _drift(self, interval: float) -> None:
        meters = self.motion["speed"] * interval
        self.position["latitude"] = float(self.position.get("latitude", 0.0)) + random.uniform(-1, 1) * meters / 111000
        self.position["longitude"] = float(self.position.get("longitude", 0.0)) + random.uniform(-1, 1) * meters / 111000

    def _interpolate(self, current: float, target: float, speed: float, interval: float, scale: float = 111000.0) -> float:
        delta = target - current
        step = max(0.000001, min(abs(delta), (speed * interval) / scale if scale else speed * interval))
        if delta == 0:
            return current
        direction = 1 if delta > 0 else -1
        return current + (step * direction)

    def _distance_to(self, target: dict[str, Any]) -> float:
        if not self.position:
            return 0.0
        lat = float(target.get("latitude", self.position.get("latitude", 0.0)))
        lon = float(target.get("longitude", self.position.get("longitude", 0.0)))
        dlat = (lat - float(self.position.get("latitude", 0.0))) * 111000
        dlon = (lon - float(self.position.get("longitude", 0.0))) * 111000
        return math.sqrt(dlat * dlat + dlon * dlon)

    def _sensor_values(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for track in self.tracks:
            name = track.get("name")
            if not name:
                continue
            values[name] = {"status": "ok"}
        return values

    def _platform_telemetry(self, state: AgentState) -> dict[str, Any]:
        return {}

    def _apply_common_action(
        self,
        action: str,
        params: dict[str, Any],
        tools: dict[str, Any],
        result: dict[str, Any],
    ) -> bool:
        motor_control = tools.get("motor_control")
        if action in {"route_move", "follow_route"}:
            target = self._resolve_target_position(params)
            if target:
                route_planner = tools.get("route_planner")
                planned_route: list[tuple[float, float]] | list[dict[str, Any]] = [dict(target)]
                if route_planner and hasattr(route_planner, "plan_route"):
                    planned_route = route_planner.plan_route(
                        float(self.position.get("latitude", 0.0)),
                        float(self.position.get("longitude", 0.0)),
                        float(target.get("latitude", self.position.get("latitude", 0.0))),
                        float(target.get("longitude", self.position.get("longitude", 0.0))),
                        float(params.get("step_size_meters") or 100.0),
                    )
                self.mission_state.update(
                    {
                        "mode": "route_move",
                        "status": "navigating",
                        "active_action": action,
                        "target_position": target,
                        "speed_limit": float(params.get("speed_mps") or self.motion["speed"] or 1.0),
                    }
                )
                self._set_route_plan(action, target, planned_route, float(params.get("step_size_meters") or 100.0))
                if route_planner and hasattr(route_planner, "get_current_route"):
                    result["artifacts"].append(
                        {
                            "type": "route_plan",
                            "target": target,
                            "device_mode": action,
                            "route": route_planner.get_current_route(),
                        }
                    )
                else:
                    result["artifacts"].append({"type": "route_plan", "target": target, "device_mode": action})
                result["artifacts"].append({"type": "navigation_update", "target": target})
                if motor_control is not None and hasattr(motor_control, "set_thrust"):
                    motor_control.set_thrust(float(params.get("speed_mps") or 0.6), 0.0)
                return True
        elif action == "hold_position":
            self.motion["speed"] = 0.0
            if motor_control is not None and hasattr(motor_control, "stop"):
                motor_control.stop()
            self.mission_state.update(
                {
                    "mode": "hold_position",
                    "status": "holding",
                    "active_action": action,
                    "target_position": dict(self.position),
                    "speed_limit": 0.0,
                }
            )
            result["artifacts"].append({"type": "station_keep", "position": dict(self.position)})
            return True
        elif action == "return_to_base":
            self.mission_state.update(
                {
                    "mode": "return_to_base",
                    "status": "returning",
                    "active_action": action,
                    "target_position": dict(self.home_position),
                    "speed_limit": float(params.get("speed_mps") or self.motion["speed"] or 1.0),
                }
            )
            result["artifacts"].append({"type": "return_course", "home_position": dict(self.home_position)})
            if motor_control is not None and hasattr(motor_control, "set_thrust"):
                motor_control.set_thrust(float(params.get("speed_mps") or 0.75), 0.0)
            return True
        elif action == "slow_down":
            target_speed = float(params.get("target_speed_mps") or max(0.1, self.motion["speed"] * 0.5))
            self.motion["speed"] = min(self.motion["speed"], target_speed)
            self.mission_state.update(
                {
                    "mode": "slow_down",
                    "status": "slowing",
                    "active_action": action,
                    "speed_limit": target_speed,
                }
            )
            result["artifacts"].append({"type": "speed_update", "target_speed_mps": target_speed})
            if motor_control is not None and hasattr(motor_control, "set_thrust"):
                motor_control.set_thrust(min(1.0, target_speed / 10.0), 0.0)
            return True
        elif action == "follow_target":
            target_id = str(params.get("target_id") or params.get("target_device_id") or "")
            target_position = self._resolve_target_position(params)
            if target_position is None:
                target_position = {
                    "latitude": float(self.position.get("latitude", 0.0)) + random.uniform(-0.0003, 0.0003),
                    "longitude": float(self.position.get("longitude", 0.0)) + random.uniform(-0.0003, 0.0003),
                }
            self.mission_state.update(
                {
                    "mode": "follow_target",
                    "status": "tracking",
                    "active_action": action,
                    "follow_target_id": target_id or None,
                    "target_position": target_position,
                    "speed_limit": float(params.get("speed_mps") or max(self.motion["speed"], 0.5)),
                }
            )
            result["artifacts"].append({"type": "target_track", "target_id": target_id})
            if motor_control is not None and hasattr(motor_control, "set_thrust"):
                motor_control.set_thrust(0.55, 0.05)
            return True
        elif action in {"abort_mission", "emergency_stop"}:
            self.motion["speed"] = 0.0
            if motor_control is not None:
                if hasattr(motor_control, "stop"):
                    motor_control.stop()
                elif hasattr(motor_control, "set_thrust"):
                    motor_control.set_thrust(0.0, 0.0)
            self.mission_state.update(
                {
                    "mode": action,
                    "status": "stopped" if action == "emergency_stop" else "aborted",
                    "active_action": action,
                    "target_position": None,
                    "speed_limit": 0.0,
                }
            )
            result["artifacts"].append({"type": "mission_halt", "mode": action})
            return True
        return False

    def _resolve_target_position(self, params: dict[str, Any]) -> dict[str, Any] | None:
        location = params.get("location") or params.get("target_position") or {}
        if not isinstance(location, dict):
            location = {}
        target = {}
        if "target_lat" in params or "target_lon" in params:
            target["latitude"] = params.get("target_lat")
            target["longitude"] = params.get("target_lon")
        if "latitude" in location or "longitude" in location:
            target["latitude"] = location.get("latitude", target.get("latitude", self.position.get("latitude", 0.0)))
            target["longitude"] = location.get("longitude", target.get("longitude", self.position.get("longitude", 0.0)))
        if "altitude" in location or "target_depth_m" in params or "depth_m" in params:
            target["altitude"] = location.get(
                "altitude",
                params.get("target_depth_m", params.get("depth_m", self.position.get("altitude", 0.0))),
            )
        if target:
            return target
        return None

    def _normalize_route_waypoints(
        self,
        waypoints: list[tuple[float, float]],
        target: dict[str, Any],
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for lat, lon in waypoints:
            normalized.append({"latitude": float(lat), "longitude": float(lon)})
        if normalized:
            if "altitude" in target:
                for waypoint in normalized:
                    waypoint["altitude"] = target.get("altitude")
            return normalized
        return [dict(target)]

    def _set_route_plan(
        self,
        route_mode: str,
        target: dict[str, Any],
        waypoints: list[tuple[float, float]] | list[dict[str, Any]],
        step_size_meters: float,
    ) -> None:
        normalized_waypoints: list[dict[str, Any]] = []
        for waypoint in waypoints:
            if isinstance(waypoint, dict):
                normalized_waypoints.append(dict(waypoint))
            else:
                lat, lon = waypoint
                normalized_waypoints.append({"latitude": float(lat), "longitude": float(lon)})
        if not normalized_waypoints:
            normalized_waypoints = [dict(target)] if target else []
        if "altitude" in target:
            for waypoint in normalized_waypoints:
                waypoint.setdefault("altitude", target.get("altitude"))
        self.mission_state["route"] = {
            "waypoints": normalized_waypoints,
            "current_index": 0,
            "completed": False if normalized_waypoints else True,
            "route_mode": route_mode,
            "step_size_meters": step_size_meters,
            "planned_at": utc_now(),
        }
        if normalized_waypoints:
            self.mission_state["target_position"] = dict(normalized_waypoints[0])

    def _current_route(self) -> dict[str, Any]:
        route = self.mission_state.get("route")
        return route if isinstance(route, dict) else {}

    def _current_route_target(self) -> dict[str, Any] | None:
        route = self._current_route()
        waypoints = route.get("waypoints") or []
        if not isinstance(waypoints, list) or not waypoints:
            return None
        current_index = int(route.get("current_index") or 0)
        if current_index < 0:
            current_index = 0
        if current_index >= len(waypoints):
            return None
        waypoint = waypoints[current_index]
        return dict(waypoint) if isinstance(waypoint, dict) else None

    def _advance_route_state(self, force: bool = False) -> None:
        route = self._current_route()
        waypoints = route.get("waypoints") or []
        if not isinstance(waypoints, list) or not waypoints:
            return
        current_index = int(route.get("current_index") or 0)
        if current_index >= len(waypoints):
            route["completed"] = True
            return
        current_target = waypoints[current_index]
        if not isinstance(current_target, dict):
            current_target = {"latitude": current_target[0], "longitude": current_target[1]}  # type: ignore[index]
        if not force and self._distance_to(current_target) >= 3.0:
            return
        next_index = current_index + 1
        route["current_index"] = next_index
        if next_index < len(waypoints):
            next_target = waypoints[next_index]
            self.mission_state["target_position"] = dict(next_target) if isinstance(next_target, dict) else {"latitude": next_target[0], "longitude": next_target[1]}  # type: ignore[index]
            route["completed"] = False
            self.mission_state["status"] = "navigating"
        else:
            route["completed"] = True
            mode = str(self.mission_state.get("mode") or "")
            if mode == "return_to_base":
                self.mission_state["status"] = "returned"
            elif mode in {"route_move", "follow_route"}:
                self.mission_state["status"] = "target_reached"
            else:
                self.mission_state["status"] = "completed"

    def _apply_platform_action(
        self,
        action: str,
        params: dict[str, Any],
        tools: dict[str, Any],
        result: dict[str, Any],
    ) -> bool:
        return False
