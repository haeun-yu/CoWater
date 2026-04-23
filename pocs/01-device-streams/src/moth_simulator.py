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
- Send binary keepalive (b'') every 25 s when idle
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
                            await ws.send(b"")
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
        # Device IDs that were successfully registered (use per-sensor tracks)
        self._registered: Set[str] = set()
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
            }
            for dev_id, device in self.dynamic_devices.items()
        }

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
        logger.info(
            "[%s] Registered → token=%s…  tracks=%d",
            device_id,
            token[:8],
            track_count,
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
                self._publishers[dev_id] = {
                    dev_id: self._make_publisher_fallback(dev_id)
                }
            else:
                logger.warning("[%s] Registration failed; skipping publish", dev_id)

        for dev_id, device in self.dynamic_devices.items():
            tracks = self._tracks_for_dynamic(device)
            result = self._register_device(dev_id, device["name"], tracks)
            if result:
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
                self._publishers[dev_id] = {
                    dev_id: self._make_publisher_fallback(dev_id)
                }
            else:
                logger.warning("[%s] Registration failed; skipping publish", dev_id)

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
        return {
            "stream": stream,
            "device_id": device_id,
            "device_type": device_type,
            "sensor_id": sensor_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": self._source,
            "qos": "best_effort",
            "parent_device_id": parent_device_id,
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

        state["heading"] = (
            state["heading"]
            + random.uniform(
                -device["movement"]["heading_change_max"],
                device["movement"]["heading_change_max"],
            )
        ) % 360

        lo, hi = device["movement"]["speed_range"]
        state["speed"] = max(lo, min(hi, state["speed"] + random.uniform(-0.2, 0.2)))

        state["position"]["latitude"] += (
            state["speed"] / 111000
        ) * math.cos(math.radians(state["heading"]))
        state["position"]["longitude"] += (
            state["speed"] / 111000
        ) * math.sin(math.radians(state["heading"]))

        dlo, dhi = device["movement"]["depth_range"]
        state["position"]["altitude"] = max(
            dlo,
            min(dhi, state["position"]["altitude"] + random.uniform(-2, 2)),
        )

    def _sensor_payload(self, sensor: dict, state: dict) -> dict:
        """Build the data payload for a single sensor reading."""
        st = sensor["sensor_type"]
        sid = sensor["sensor_id"]
        depth = abs(state["position"]["altitude"])

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
            }
        if st == "hd_camera":
            return {
                "sensor_id": sid, "type": "hd_camera",
                "resolution": sensor["resolution"],
                "fps": 30,
                "light_level_lux": (
                    random.uniform(0, 100) if depth > 50 else random.uniform(100, 10000)
                ),
            }
        if st == "led_light":
            return {
                "sensor_id": sid, "type": "led_light",
                "lumens": sensor["lumens"],
                "power_w": random.uniform(100, 150),
                "status": "on" if random.random() > 0.1 else "dimmed",
            }
        if st == "magnetometer":
            return {
                "sensor_id": sid, "type": "magnetometer",
                "field_x_ut": random.uniform(-50000, 50000),
                "field_y_ut": random.uniform(-50000, 50000),
                "field_z_ut": random.uniform(-50000, 50000),
                "heading": state["heading"],
            }
        return {"sensor_id": sid, "type": st}

    async def _tick_dynamic_devices(self) -> None:
        for dev_id, device in self.dynamic_devices.items():
            self._update_position(dev_id)
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
                    await pub.publish(envelope, sensor_payloads[sensor["sensor_id"]])

                # Aggregated telemetry → telemetry TOPIC track
                tel_pub = pubs.get(_TELEMETRY_TRACK_NAME)
                if tel_pub:
                    envelope = self._make_envelope(
                        dev_id, device["device_type"], "telemetry",
                        parent_device_id=parent,
                    )
                    await tel_pub.publish(envelope, {
                        "name": device["name"],
                        "position": state["position"],
                        "motion": {
                            "heading": round(state["heading"], 2),
                            "speed": round(state["speed"], 2),
                        },
                        "sensors": sensor_payloads,
                    })
            else:
                # ── Fallback mode: single combined payload ──────────────────
                pub = pubs.get(dev_id)
                if pub is None:
                    continue
                envelope = self._make_envelope(
                    dev_id, device["device_type"], "telemetry",
                    parent_device_id=parent,
                )
                await pub.publish(envelope, {
                    "name": device["name"],
                    "position": state["position"],
                    "motion": {
                        "heading": round(state["heading"], 2),
                        "speed": round(state["speed"], 2),
                    },
                    "sensors": sensor_payloads,
                })

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
