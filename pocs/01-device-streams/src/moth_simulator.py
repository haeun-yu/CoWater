#!/usr/bin/env python3
"""
Moth Server Simulator - Multi-device real-time data streaming

Startup flow (when registration_server.enabled = true):
  1. Register each device with PoC 03 registration server (POST /devices)
  2. Receive per-device token + per-sensor track endpoints
  3. Publish each sensor's data to the server-provided track endpoints
  Falls back to the original single-track-per-device mode on failure.

Moth protocol rules:
- Registered mode: connect to the track endpoint returned by PoC 03
- Fallback mode: /pang/ws/pub?channel=<type>&name=<fallback>&source=base&track=<device_id>&mode=single
- Connect → send MIME text frame first → send binary payload frames
- Send binary keepalive (b"ping") every 25 s when idle
- ping_interval=None (Moth does not respond to WebSocket pings)
- Never recv() on a pub connection
"""

import asyncio
import json
import math
import logging
import random
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set
from urllib.parse import urlencode

import websockets
from websockets.exceptions import ConnectionClosedError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

_MIME = "application/vnd.cowater.device-stream+json"
_KEEPALIVE_INTERVAL = 25.0
_KEEPALIVE_PAYLOAD = b"ping"

# Maps sensor_type (from config) → registration server track type
SENSOR_TO_TRACK_TYPE: Dict[str, str] = {
    "gps":             "GPS",
    "imu":             "ODOMETRY",
    "pressure":        "TOPIC",
    "temperature":     "TOPIC",
    "sonar":           "TOPIC",
    "side_scan_sonar": "TOPIC",
    "profiling_sonar": "TOPIC",
    "hd_camera":       "VIDEO",
    "led_light":       "TOPIC",
    "magnetometer":    "TOPIC",
}

# Track used for static-device position data
_POSITION_TRACK_NAME = "gps"
_POSITION_TRACK_TYPE = "GPS"

# Aggregated telemetry track (always registered alongside per-sensor tracks)
_TELEMETRY_TRACK_NAME = "telemetry"


# ── Publisher ────────────────────────────────────────────────────────────────


class DevicePublisher:
    """
    Single Moth pub connection for one track of one device.

    Registered mode:  ws_url = track endpoint from registration server
    Fallback mode:    channel_name = shared channel, track_name = device_id
    """

    def __init__(
        self,
        label: str,
        ws_url: str,
    ) -> None:
        self.label = label
        self._ws_url = ws_url
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=64)

    def _build_url(self) -> str:
        return self._ws_url

    async def publish(self, envelope: dict, payload: dict) -> None:
        message = {"envelope": envelope, "payload": payload}
        try:
            self._queue.put_nowait(message)
        except asyncio.QueueFull:
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(message)
            except asyncio.QueueEmpty:
                pass

    async def run(self, running_ref: list) -> None:
        url = self._build_url()
        logger.info("[%s] Connecting → %s", self.label, url)

        while running_ref[0]:
            # Discard stale backlog before reconnecting
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

            try:
                async with websockets.connect(url, ping_interval=None) as ws:
                    logger.info("[%s] Connected", self.label)
                    await ws.send(_MIME)
                    last_sent_at = asyncio.get_running_loop().time()

                    while running_ref[0]:
                        now = asyncio.get_running_loop().time()
                        if now - last_sent_at >= _KEEPALIVE_INTERVAL:
                            await ws.send(_KEEPALIVE_PAYLOAD)
                            last_sent_at = now
                            logger.debug("[%s] keepalive sent", self.label)

                        if not self._queue.empty():
                            msg = self._queue.get_nowait()
                            raw = json.dumps(msg, separators=(",", ":")).encode("utf-8")
                            await ws.send(raw)
                            last_sent_at = asyncio.get_running_loop().time()
                        else:
                            await asyncio.sleep(0.05)

            except ConnectionClosedError as e:
                logger.warning("[%s] Closed (%s) — reconnecting in 5 s", self.label, e)
            except Exception:
                logger.exception("[%s] Error — reconnecting in 5 s", self.label)

            if running_ref[0]:
                await asyncio.sleep(5)

        logger.info("[%s] Stopped", self.label)


class AgentSessionPublisher:
    """
    JSON WebSocket session for one device Agent.

    The Agent server receives identity first, then the same envelope/payload
    stream used by the simulator.
    """

    def __init__(self, label: str, ws_url: str, hello: dict, on_command=None) -> None:
        self.label = label
        self._ws_url = ws_url
        self._hello = hello
        self._on_command = on_command
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=64)

    async def publish(self, envelope: dict, payload: dict) -> None:
        message = {"kind": "stream", "envelope": envelope, "payload": payload}
        try:
            self._queue.put_nowait(message)
        except asyncio.QueueFull:
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(message)
            except asyncio.QueueEmpty:
                pass

    async def run(self, running_ref: list) -> None:
        logger.info("[%s] Connecting Agent → %s", self.label, self._ws_url)

        while running_ref[0]:
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

            try:
                async with websockets.connect(self._ws_url, ping_interval=None) as ws:
                    logger.info("[%s] Agent connected", self.label)
                    await ws.send(json.dumps(self._hello, separators=(",", ":")))
                    recv_task = None

                    async def recv_loop() -> None:
                        try:
                            while running_ref[0]:
                                raw = await ws.recv()
                                if raw is None:
                                    continue
                                if isinstance(raw, bytes):
                                    try:
                                        raw = raw.decode("utf-8")
                                    except Exception:
                                        continue
                                try:
                                    message = json.loads(raw)
                                except Exception:
                                    logger.debug("[%s] Agent message ignored: %s", self.label, raw)
                                    continue
                                if isinstance(message, dict) and message.get("kind") == "command":
                                    if self._on_command:
                                        await self._on_command(message)
                        except ConnectionClosedError:
                            return
                        except asyncio.CancelledError:
                            return
                        except Exception:
                            logger.exception("[%s] Agent receive loop error", self.label)

                    recv_task = asyncio.create_task(recv_loop())

                    try:
                        while running_ref[0]:
                            if not self._queue.empty():
                                msg = self._queue.get_nowait()
                                await ws.send(json.dumps(msg, separators=(",", ":")))
                            else:
                                await asyncio.sleep(0.05)
                    finally:
                        if recv_task:
                            recv_task.cancel()
                            try:
                                await recv_task
                            except BaseException:
                                pass

            except ConnectionClosedError as e:
                logger.warning("[%s] Agent closed (%s) — reconnecting in 5 s", self.label, e)
            except Exception:
                logger.exception("[%s] Agent error — reconnecting in 5 s", self.label)

            if running_ref[0]:
                await asyncio.sleep(5)

        logger.info("[%s] Agent stopped", self.label)


# ── HTTP helper ──────────────────────────────────────────────────────────────


def _http_post_json(url: str, body: dict, timeout: int = 10) -> Optional[dict]:
    """Blocking HTTP POST with JSON body. Returns parsed response or None."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = json.loads(exc.read()).get("detail", "")
        except Exception:
            pass
        logger.error("HTTP %d from %s — %s", exc.code, url, detail)
        return None
    except Exception as exc:
        logger.error("Request to %s failed: %s", url, exc)
        return None


# ── Simulator ────────────────────────────────────────────────────────────────


class MothSimulator:
    def __init__(self, config_path: str = "config.json") -> None:
        self.config_path = Path(config_path)
        self.config = self._load_config()

        moth = self.config["moth_server"]
        self._base_url = moth["url"]
        self._channel_type = moth.get("channel_type", "instant")
        self._fallback_channel_name = moth.get("channel_name", "cowater-sim-device-streams")
        self._source = moth.get("source", "base")
        self._mode = moth.get("mode", "single")

        reg = self.config.get("registration_server", {})
        self._reg_enabled: bool = reg.get("enabled", False)
        self._reg_url: str = reg.get("url", "http://localhost:8003").rstrip("/")
        self._reg_secret: str = reg.get("secret_key", "server-secret")
        self._reg_fallback_on_failure: bool = reg.get("fallback_on_failure", False)

        self.static_devices = {d["device_id"]: d for d in self.config["static_devices"]}
        self.dynamic_devices = {d["device_id"]: d for d in self.config["dynamic_devices"]}

        self.device_state = self._init_device_state()
        self.static_last_state: Dict[str, Optional[dict]] = {
            k: None for k in self.static_devices
        }

        # {device_id: {track_name: DevicePublisher}}
        self._publishers: Dict[str, Dict[str, DevicePublisher]] = {}
        # {device_id: AgentSessionPublisher}
        self._agent_publishers: Dict[str, AgentSessionPublisher] = {}
        # Device IDs that were successfully registered (use per-sensor tracks)
        self._registered: Set[str] = set()
        # Registration responses keyed by device id
        self._registrations: Dict[str, dict] = {}
        self._running = [True]

    def _load_config(self) -> dict:
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config not found: {self.config_path}")
        with open(self.config_path) as f:
            return json.load(f)

    def _init_device_state(self) -> Dict[str, dict]:
        return {
            dev_id: {
                "position": device["start_position"].copy(),
                "heading": random.uniform(0, 360),
                "speed": random.uniform(*device["movement"]["speed_range"]),
                "battery_percent": random.uniform(60, 100),
                "command": {
                    "mode": "idle",
                    "route": [],
                    "route_index": 0,
                    "target_position": None,
                    "target_speed": None,
                    "home_position": device["start_position"].copy(),
                    "light_on": False,
                    "camera_mode": "default",
                    "scan_mode": "normal",
                    "hold_depth": None,
                    "last_command": None,
                },
            }
            for dev_id, device in self.dynamic_devices.items()
        }

    def _get_position_for_device(self, device_id: str) -> Optional[dict]:
        if device_id in self.static_devices:
            device = self.static_devices[device_id]
            return device["position"].copy()
        if device_id in self.device_state:
            return self.device_state[device_id]["position"].copy()
        return None

    @staticmethod
    def _distance_m(a: dict, b: dict) -> float:
        lat = (a["latitude"] - b["latitude"]) * 111000
        lon = (a["longitude"] - b["longitude"]) * 111000
        alt = a.get("altitude", 0.0) - b.get("altitude", 0.0)
        return math.sqrt(lat * lat + lon * lon + alt * alt)

    @staticmethod
    def _step_toward(current: dict, target: dict, meters: float) -> dict:
        delta_lat = target["latitude"] - current["latitude"]
        delta_lon = target["longitude"] - current["longitude"]
        delta_alt = target.get("altitude", 0.0) - current.get("altitude", 0.0)
        distance = math.sqrt((delta_lat * 111000) ** 2 + (delta_lon * 111000) ** 2 + delta_alt ** 2)
        if distance <= 0 or meters <= 0:
            return current.copy()
        ratio = min(1.0, meters / distance)
        return {
            "latitude": current["latitude"] + delta_lat * ratio,
            "longitude": current["longitude"] + delta_lon * ratio,
            "altitude": current.get("altitude", 0.0) + delta_alt * ratio,
        }

    def _set_device_command(self, dev_id: str, command: dict) -> None:
        state = self.device_state.get(dev_id)
        if state is None:
            return
        command_state = state["command"]
        action = str(command.get("action") or "").strip()
        params = command.get("params") or {}
        command_state["mode"] = action or "idle"
        command_state["last_command"] = {
            "at": datetime.now(timezone.utc).isoformat(),
            "command": command,
        }

        if action in {"patrol_route", "route_move"}:
            command_state["hold_depth"] = None
            route = params.get("route") or []
            normalized_route = []
            for waypoint in route:
                if isinstance(waypoint, dict) and "latitude" in waypoint and "longitude" in waypoint:
                    normalized_route.append({
                        "latitude": float(waypoint["latitude"]),
                        "longitude": float(waypoint["longitude"]),
                        "altitude": float(waypoint.get("altitude", state["position"].get("altitude", 0.0))),
                    })
            command_state["route"] = normalized_route
            command_state["route_index"] = 0
            command_state["target_position"] = normalized_route[0] if normalized_route else state["position"].copy()
        elif action in {"move_to_device", "follow_target"}:
            command_state["hold_depth"] = None
            target_device_id = params.get("device_id") or params.get("target_device_id")
            target_position = params.get("target_position")
            if isinstance(target_position, dict) and "latitude" in target_position and "longitude" in target_position:
                command_state["target_position"] = {
                    "latitude": float(target_position["latitude"]),
                    "longitude": float(target_position["longitude"]),
                    "altitude": float(target_position.get("altitude", state["position"].get("altitude", 0.0))),
                }
            elif target_device_id:
                command_state["target_position"] = self._get_position_for_device(str(target_device_id)) or state["position"].copy()
            else:
                command_state["target_position"] = state["position"].copy()
        elif action == "return_to_base":
            command_state["hold_depth"] = None
            command_state["target_position"] = command_state.get("home_position") or state["position"].copy()
        elif action == "charge_at_tower":
            command_state["hold_depth"] = None
            target = self._get_position_for_device("ocean-power-tower-01")
            command_state["target_position"] = target or state["position"].copy()
        elif action == "hold_position":
            command_state["hold_depth"] = None
            command_state["target_position"] = state["position"].copy()
            command_state["target_speed"] = 0.0
        elif action == "hold_depth":
            command_state["hold_depth"] = float(params.get("depth", state["position"].get("altitude", 0.0)))
        elif action == "surface":
            command_state["hold_depth"] = None
            command_state["target_position"] = {
                "latitude": state["position"]["latitude"],
                "longitude": state["position"]["longitude"],
                "altitude": 0.0,
            }
        elif action == "light_on":
            command_state["light_on"] = True
        elif action == "light_off":
            command_state["light_on"] = False
        elif action == "slow_down":
            target_speed = params.get("target_speed_mps")
            if target_speed is None:
                target_speed = max(0.1, state["speed"] * 0.5)
            command_state["target_speed"] = float(target_speed)
        elif action == "camera_mode_switch":
            command_state["camera_mode"] = str(params.get("mode") or params.get("camera_mode") or "default")
        elif action == "sonar_scan_plan":
            command_state["scan_mode"] = str(params.get("mode") or "scan")

        logger.info("[%s] Agent command applied: %s", dev_id, action or "unknown")

    async def _apply_agent_command(self, dev_id: str, command: dict) -> None:
        self._set_device_command(dev_id, command)

    # ── Registration ─────────────────────────────────────────────────────────

    def _tracks_for_static(self) -> List[dict]:
        return [{"type": _POSITION_TRACK_TYPE, "name": _POSITION_TRACK_NAME}]

    def _tracks_for_dynamic(self, device: dict) -> List[dict]:
        seen: Set[str] = set()
        tracks: List[dict] = []
        for sensor in device.get("sensors", []):
            st = sensor["sensor_type"]
            if st not in seen:
                seen.add(st)
                tracks.append({
                    "type": SENSOR_TO_TRACK_TYPE.get(st, "TOPIC"),
                    "name": st,  # track name == sensor_type
                })
        # Aggregated telemetry track (for backward-compat with the dashboard)
        tracks.append({"type": "TOPIC", "name": _TELEMETRY_TRACK_NAME})
        return tracks

    def _register_device(
        self, device_id: str, device_name: str, tracks: List[dict]
    ) -> Optional[dict]:
        """POST /devices → returns the registration response on success, None on failure."""
        result = _http_post_json(
            f"{self._reg_url}/devices",
            {
                "secretKey": self._reg_secret,
                "name": device_name,
                "tracks": tracks,
            },
        )
        if result is None:
            return None
        token: str = result.get("token", "")
        track_count = len(result.get("tracks") or [])
        if not token:
            logger.error("[%s] Registration response missing token", device_id)
            return None
        agent_endpoint = (result.get("agent") or {}).get("endpoint", "")
        logger.info(
            "[%s] Registered → token=%s…  tracks=%d  agent=%s",
            device_id,
            token[:8],
            track_count,
            agent_endpoint or "-",
        )
        return result

    def _make_publisher(
        self, device_id: str, track_name: str, endpoint: str
    ) -> DevicePublisher:
        ws_url = f"{self._base_url.rstrip('/')}{endpoint}"
        return DevicePublisher(
            label=f"{device_id}/{track_name}",
            ws_url=ws_url,
        )

    def _make_publisher_fallback(self, device_id: str) -> DevicePublisher:
        """Original single-track-per-device (no registration)."""
        params = {
            "channel": self._channel_type,
            "name": self._fallback_channel_name,
            "source": self._source,
            "track": device_id,
            "mode": self._mode,
        }
        return DevicePublisher(
            label=f"{device_id}/fallback",
            ws_url=f"{self._base_url.rstrip('/')}/pang/ws/pub?{urlencode(params)}",
        )

    def _register_all_devices(self) -> None:
        logger.info("🔗 Registering devices with %s …", self._reg_url)

        for dev_id, device in self.static_devices.items():
            tracks = self._tracks_for_static()
            result = self._register_device(dev_id, device["name"], tracks)
            if result:
                self._registrations[dev_id] = result
                agent_endpoint = (result.get("agent") or {}).get("endpoint", "")
                if agent_endpoint:
                    self._agent_publishers[dev_id] = AgentSessionPublisher(
                        label=f"{dev_id}/agent",
                        ws_url=agent_endpoint,
                        hello={
                            "kind": "hello",
                            "token": result.get("token"),
                            "device_id": result.get("id") or dev_id,
                            "device_name": device["name"],
                            "device_type": device["device_type"],
                            "registry_id": result.get("id"),
                        },
                        on_command=lambda message, device_id=dev_id: self._apply_agent_command(device_id, message),
                    )
                track_map = {t["name"]: t for t in (result.get("tracks") or [])}
                self._publishers[dev_id] = {
                    t["name"]: self._make_publisher(
                        dev_id,
                        t["name"],
                        track_map.get(t["name"], {}).get("endpoint", ""),
                    )
                    for t in tracks
                    if track_map.get(t["name"], {}).get("endpoint")
                }
                self._registered.add(dev_id)
            elif self._reg_fallback_on_failure:
                logger.warning("[%s] Using fallback track", dev_id)
                self._registrations.pop(dev_id, None)
                self._agent_publishers.pop(dev_id, None)
                self._publishers[dev_id] = {
                    dev_id: self._make_publisher_fallback(dev_id)
                }
            else:
                logger.warning("[%s] Registration failed; skipping publish", dev_id)
                self._registrations.pop(dev_id, None)
                self._agent_publishers.pop(dev_id, None)

        for dev_id, device in self.dynamic_devices.items():
            tracks = self._tracks_for_dynamic(device)
            result = self._register_device(dev_id, device["name"], tracks)
            if result:
                self._registrations[dev_id] = result
                agent_endpoint = (result.get("agent") or {}).get("endpoint", "")
                if agent_endpoint:
                    self._agent_publishers[dev_id] = AgentSessionPublisher(
                        label=f"{dev_id}/agent",
                        ws_url=agent_endpoint,
                        hello={
                            "kind": "hello",
                            "token": result.get("token"),
                            "device_id": result.get("id") or dev_id,
                            "device_name": device["name"],
                            "device_type": device["device_type"],
                            "registry_id": result.get("id"),
                        },
                        on_command=lambda message, device_id=dev_id: self._apply_agent_command(device_id, message),
                    )
                track_map = {t["name"]: t for t in (result.get("tracks") or [])}
                self._publishers[dev_id] = {
                    t["name"]: self._make_publisher(
                        dev_id,
                        t["name"],
                        track_map.get(t["name"], {}).get("endpoint", ""),
                    )
                    for t in tracks
                    if track_map.get(t["name"], {}).get("endpoint")
                }
                self._registered.add(dev_id)
            elif self._reg_fallback_on_failure:
                logger.warning("[%s] Using fallback track", dev_id)
                self._registrations.pop(dev_id, None)
                self._agent_publishers.pop(dev_id, None)
                self._publishers[dev_id] = {
                    dev_id: self._make_publisher_fallback(dev_id)
                }
            else:
                logger.warning("[%s] Registration failed; skipping publish", dev_id)
                self._registrations.pop(dev_id, None)
                self._agent_publishers.pop(dev_id, None)

    def _init_publishers_fallback(self) -> None:
        for dev_id in list(self.static_devices) + list(self.dynamic_devices):
            self._publishers[dev_id] = {
                dev_id: self._make_publisher_fallback(dev_id)
            }

    # ── Envelope ─────────────────────────────────────────────────────────────

    def _make_envelope(
        self,
        device_id: str,
        device_type: str,
        stream: str,
        sensor_id: Optional[str] = None,
        parent_device_id: Optional[str] = None,
    ) -> dict:
        registration = self._registrations.get(device_id, {})
        agent_endpoint = (registration.get("agent") or {}).get("endpoint")
        return {
            "stream": stream,
            "device_id": device_id,
            "device_type": device_type,
            "sensor_id": sensor_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": self._source,
            "qos": "best_effort",
            "parent_device_id": parent_device_id,
            "agent_endpoint": agent_endpoint,
            "flow_id": str(uuid.uuid4()),
            "message_id": str(uuid.uuid4()),
            "schema_version": 1,
        }

    # ── Tick: static devices ─────────────────────────────────────────────────

    async def _tick_static_devices(self) -> None:
        for dev_id, device in self.static_devices.items():
            position = device["position"].copy()
            state = {"position": position}
            if self.static_last_state[dev_id] == state:
                continue
            self.static_last_state[dev_id] = state

            pubs = self._publishers.get(dev_id, {})
            envelope = self._make_envelope(dev_id, device["device_type"], "position")
            payload = {"name": device["name"], "position": position}

            # Registered: publish to the GPS track; fallback: publish to device track
            pub = pubs.get(_POSITION_TRACK_NAME) or pubs.get(dev_id)
            if pub:
                await pub.publish(envelope, payload)
                agent_pub = self._agent_publishers.get(dev_id)
                if agent_pub:
                    await agent_pub.publish(envelope, payload)
                logger.info(
                    "📍 Static: %s  lat=%.4f  lon=%.4f",
                    device["name"],
                    position["latitude"],
                    position["longitude"],
                )

    # ── Tick: dynamic devices ────────────────────────────────────────────────

    def _update_position(self, dev_id: str) -> None:
        device = self.dynamic_devices[dev_id]
        state = self.device_state[dev_id]
        command_state = state.get("command", {})

        target_position = command_state.get("target_position")
        hold_depth = command_state.get("hold_depth")
        mode = command_state.get("mode", "idle")

        lo, hi = device["movement"]["speed_range"]
        state["speed"] = max(lo, min(hi, state["speed"] + random.uniform(-0.2, 0.2)))

        target_speed = command_state.get("target_speed")
        if target_speed is not None:
            target_speed = float(target_speed)
            if abs(state["speed"] - target_speed) < 0.05:
                command_state["target_speed"] = None
            else:
                state["speed"] += max(-0.25, min(0.25, target_speed - state["speed"]))
                state["speed"] = max(lo, min(hi, state["speed"]))

        if target_position:
            if mode in {"hold_position"}:
                state["speed"] = 0.0
            else:
                step_m = max(0.5, state["speed"] * 1.5)
                next_position = self._step_toward(state["position"], target_position, step_m)
                delta_lat = next_position["latitude"] - state["position"]["latitude"]
                delta_lon = next_position["longitude"] - state["position"]["longitude"]
                if delta_lat or delta_lon:
                    state["heading"] = (math.degrees(math.atan2(delta_lon, delta_lat)) + 360) % 360
                state["position"] = next_position

            if self._distance_m(state["position"], target_position) < 8.0:
                if mode in {"patrol_route", "route_move"}:
                    route = command_state.get("route") or []
                    index = int(command_state.get("route_index") or 0)
                    if route:
                        index = (index + 1) % len(route)
                        command_state["route_index"] = index
                        command_state["target_position"] = route[index]
                elif mode == "move_to_device":
                    command_state["target_position"] = None
                elif mode == "follow_target":
                    target_device_id = (command_state.get("last_command") or {}).get("command", {}).get("params", {}).get("device_id")
                    if target_device_id:
                        command_state["target_position"] = self._get_position_for_device(str(target_device_id)) or target_position
                elif mode == "charge_at_tower":
                    command_state["target_position"] = target_position
        else:
            state["heading"] = (
                state["heading"]
                + random.uniform(
                    -device["movement"]["heading_change_max"],
                    device["movement"]["heading_change_max"],
                )
            ) % 360

            state["position"]["latitude"] += (
                state["speed"] / 111000
            ) * math.cos(math.radians(state["heading"]))
            state["position"]["longitude"] += (
                state["speed"] / 111000
            ) * math.sin(math.radians(state["heading"]))

        dlo, dhi = device["movement"]["depth_range"]
        if hold_depth is not None:
            state["position"]["altitude"] = max(dlo, min(dhi, float(hold_depth)))
        else:
            state["position"]["altitude"] = max(
                dlo,
                min(dhi, state["position"]["altitude"] + random.uniform(-2, 2)),
            )

    def _update_battery(self, dev_id: str) -> None:
        device = self.dynamic_devices[dev_id]
        state = self.device_state[dev_id]
        command_state = state.get("command", {})
        battery = float(state.get("battery_percent", 100.0))

        if command_state.get("mode") == "charge_at_tower":
            tower_position = self._get_position_for_device("ocean-power-tower-01")
            if tower_position and self._distance_m(state["position"], tower_position) < 20.0:
                battery += random.uniform(2.0, 5.0)
            else:
                battery -= random.uniform(0.1, 0.3)
        else:
            drain = 0.12 + (float(state.get("speed", 0.0)) * 0.04)
            if command_state.get("light_on"):
                drain += 0.03
            if command_state.get("camera_mode") not in {None, "default"}:
                drain += 0.02
            if command_state.get("scan_mode") not in {None, "normal"}:
                drain += 0.03
            battery -= drain

        state["battery_percent"] = max(0.0, min(100.0, battery))

    def _sensor_payload(self, sensor: dict, state: dict) -> dict:
        """Build the data payload for a single sensor reading."""
        st = sensor["sensor_type"]
        sid = sensor["sensor_id"]
        depth = abs(state["position"]["altitude"])
        command_state = state.get("command", {})

        if st == "gps":
            return {
                "sensor_id": sid, "type": "gps",
                "accuracy": sensor["accuracy"],
                "latitude": state["position"]["latitude"],
                "longitude": state["position"]["longitude"],
                "altitude": state["position"]["altitude"],
            }
        if st == "imu":
            return {
                "sensor_id": sid, "type": "imu",
                "roll": random.uniform(-30, 30),
                "pitch": random.uniform(-20, 20),
                "yaw": state["heading"],
                "acc_x": random.uniform(-2, 2),
                "acc_y": random.uniform(-2, 2),
                "acc_z": random.uniform(9.5, 10.5),
            }
        if st == "pressure":
            return {
                "sensor_id": sid, "type": "pressure",
                "pressure_pa": 101325 + depth * 10050,
                "depth_m": depth,
            }
        if st == "temperature":
            temp = 20 - depth * 0.01
            return {
                "sensor_id": sid, "type": "temperature",
                "temperature_c": round(max(2.0, temp), 1),
                "temperature_f": round(max(35.6, temp * 9 / 5 + 32), 1),
            }
        if st in ("sonar", "side_scan_sonar", "profiling_sonar"):
            return {
                "sensor_id": sid, "type": st,
                "frequency_hz": sensor.get("frequency", 200000),
                "range_m": random.uniform(10, 300),
                "target_detected": random.random() > 0.7,
                "signal_strength_db": random.uniform(-120, -60),
                "scan_mode": command_state.get("scan_mode", "normal"),
            }
        if st == "hd_camera":
            return {
                "sensor_id": sid, "type": "hd_camera",
                "resolution": sensor["resolution"],
                "fps": 30,
                "light_level_lux": (
                    random.uniform(0, 100) if depth > 50 else random.uniform(100, 10000)
                ),
                "camera_mode": command_state.get("camera_mode", "default"),
            }
        if st == "led_light":
            return {
                "sensor_id": sid, "type": "led_light",
                "lumens": sensor["lumens"],
                "power_w": random.uniform(100, 150),
                "status": "on" if command_state.get("light_on") else "off",
            }
        if st == "magnetometer":
            return {
                "sensor_id": sid, "type": "magnetometer",
                "field_x_ut": random.uniform(-50000, 50000),
                "field_y_ut": random.uniform(-50000, 50000),
                "field_z_ut": random.uniform(-50000, 50000),
                "heading": state["heading"],
            }
        if st in ("sonar", "side_scan_sonar", "profiling_sonar"):
            return {
                "sensor_id": sid, "type": st,
                "frequency_hz": sensor.get("frequency", 200000),
                "range_m": random.uniform(10, 300),
                "target_detected": random.random() > 0.5,
                "signal_strength_db": random.uniform(-120, -60),
                "scan_mode": command_state.get("scan_mode", "normal"),
            }
        return {"sensor_id": sid, "type": st}

    async def _tick_dynamic_devices(self) -> None:
        for dev_id, device in self.dynamic_devices.items():
            self._update_position(dev_id)
            self._update_battery(dev_id)
            state = self.device_state[dev_id]
            pubs = self._publishers.get(dev_id, {})
            parent = device.get("parent_device_id")

            # Pre-compute all sensor payloads once (reused for both per-sensor
            # tracks and the aggregated telemetry track)
            sensor_payloads = {
                sensor["sensor_id"]: self._sensor_payload(sensor, state)
                for sensor in device.get("sensors", [])
            }

            if dev_id in self._registered:
                # ── Registered mode: one track per sensor ──────────────────
                for sensor in device.get("sensors", []):
                    track_name = sensor["sensor_type"]
                    pub = pubs.get(track_name)
                    if pub is None:
                        continue
                    envelope = self._make_envelope(
                        dev_id,
                        device["device_type"],
                        sensor["sensor_type"],
                        sensor_id=sensor["sensor_id"],
                        parent_device_id=parent,
                    )
                    payload = sensor_payloads[sensor["sensor_id"]]
                    await pub.publish(envelope, payload)
                    agent_pub = self._agent_publishers.get(dev_id)
                    if agent_pub:
                        await agent_pub.publish(envelope, payload)

                # Aggregated telemetry → telemetry TOPIC track
                tel_pub = pubs.get(_TELEMETRY_TRACK_NAME)
                if tel_pub:
                    command_snapshot = {
                        key: state["command"].get(key)
                        for key in ("mode", "light_on", "camera_mode", "scan_mode", "route_index", "target_position", "target_speed")
                    }
                    envelope = self._make_envelope(
                        dev_id, device["device_type"], "telemetry",
                        parent_device_id=parent,
                    )
                    payload = {
                        "name": device["name"],
                        "position": state["position"],
                        "motion": {
                            "heading": round(state["heading"], 2),
                            "speed": round(state["speed"], 2),
                        },
                        "command": command_snapshot,
                        "power": {
                            "battery_percent": round(float(state.get("battery_percent", 0.0)), 1),
                            "charging": state["command"].get("mode") == "charge_at_tower",
                        },
                        "sensors": sensor_payloads,
                    }
                    await tel_pub.publish(envelope, payload)
                    agent_pub = self._agent_publishers.get(dev_id)
                    if agent_pub:
                        await agent_pub.publish(envelope, payload)
            else:
                # ── Fallback mode: single combined payload ──────────────────
                pub = pubs.get(dev_id)
                if pub is None:
                    continue
                envelope = self._make_envelope(
                    dev_id, device["device_type"], "telemetry",
                    parent_device_id=parent,
                )
                payload = {
                    "name": device["name"],
                    "position": state["position"],
                    "motion": {
                        "heading": round(state["heading"], 2),
                        "speed": round(state["speed"], 2),
                    },
                    "command": {
                        key: state["command"].get(key)
                        for key in ("mode", "light_on", "camera_mode", "scan_mode", "route_index", "target_position", "target_speed")
                    },
                    "power": {
                        "battery_percent": round(float(state.get("battery_percent", 0.0)), 1),
                        "charging": state["command"].get("mode") == "charge_at_tower",
                    },
                    "sensors": sensor_payloads,
                }
                await pub.publish(envelope, payload)
                agent_pub = self._agent_publishers.get(dev_id)
                if agent_pub:
                    await agent_pub.publish(envelope, payload)

    # ── Main loop ─────────────────────────────────────────────────────────────

    async def _simulation_loop(self) -> None:
        while self._running[0]:
            try:
                await self._tick_static_devices()
                await self._tick_dynamic_devices()
            except Exception:
                logger.exception("Simulation loop error")
            await asyncio.sleep(1)

    async def run(self) -> None:
        self._running[0] = True

        if self._reg_enabled:
            self._register_all_devices()
        else:
            logger.info("Registration disabled — using direct Moth tracks")
            self._init_publishers_fallback()

        total_tracks = sum(len(v) for v in self._publishers.values())
        registered_count = len(self._registered)
        logger.info(
            "🚀 Starting — %d devices (%d registered, %d fallback) | %d total tracks",
            len(self._publishers),
            registered_count,
            len(self._publishers) - registered_count,
            total_tracks,
        )

        tasks = [asyncio.ensure_future(self._simulation_loop())]
        for track_pubs in self._publishers.values():
            for pub in track_pubs.values():
                tasks.append(asyncio.ensure_future(pub.run(self._running)))
        for agent_pub in self._agent_publishers.values():
            tasks.append(asyncio.ensure_future(agent_pub.run(self._running)))

        try:
            await asyncio.gather(*tasks)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            self._running[0] = False
            for t in tasks:
                t.cancel()
            logger.info("🛑 Simulation stopped")

    def stop(self) -> None:
        self._running[0] = False


async def main() -> None:
    simulator = MothSimulator("config.json")
    try:
        await simulator.run()
    except KeyboardInterrupt:
        logger.info("Shutting down…")
        simulator.stop()


if __name__ == "__main__":
    asyncio.run(main())
