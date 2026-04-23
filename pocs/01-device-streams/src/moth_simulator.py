#!/usr/bin/env python3
"""
Moth Server Simulator - Multi-device real-time data streaming
Transmits static and dynamic device data to Moth server via WebSocket
"""

import asyncio
import json
import random
import math
import logging
from datetime import datetime, timezone
from pathlib import Path
import websockets
from typing import Any, Dict, List

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class MothSimulator:
    def __init__(self, config_path: str = "config.json"):
        self.config_path = Path(config_path)
        self.config = self._load_config()

        self.moth_url = self.config["moth_server"]["url"]
        self.channel = self.config["moth_server"]["channel"]

        self.static_devices = {dev["device_id"]: dev for dev in self.config["static_devices"]}
        self.dynamic_devices = {dev["device_id"]: dev for dev in self.config["dynamic_devices"]}

        # Track current state of dynamic devices
        self.device_state = self._init_device_state()

        # Track last transmission time for static devices (to send only on change)
        self.static_last_sent = {dev_id: None for dev_id in self.static_devices}
        self.static_last_state = {dev_id: None for dev_id in self.static_devices}

        self.running = False
        self.ws = None

    def _load_config(self) -> Dict:
        """Load configuration from JSON file"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        with open(self.config_path, 'r') as f:
            return json.load(f)

    def _init_device_state(self) -> Dict[str, Dict]:
        """Initialize device state with starting positions"""
        state = {}
        for dev_id, device in self.dynamic_devices.items():
            state[dev_id] = {
                "position": device["start_position"].copy(),
                "heading": random.uniform(0, 360),
                "speed": random.uniform(*device["movement"]["speed_range"]),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        return state

    async def connect(self) -> bool:
        """Connect to Moth server"""
        try:
            logger.info(f"Connecting to Moth server: {self.moth_url}")
            self.ws = await websockets.connect(self.moth_url)
            logger.info("✓ Connected to Moth server")
            return True
        except Exception as e:
            logger.error(f"✗ Failed to connect: {e}")
            return False

    async def disconnect(self):
        """Disconnect from Moth server"""
        if self.ws:
            await self.ws.close()
            logger.info("Disconnected from Moth server")

    async def send_data(self, data: Dict[str, Any]):
        """Send data to Moth server"""
        try:
            message = json.dumps({
                "channel": self.channel,
                "data": data
            })
            await self.ws.send(message)
        except Exception as e:
            logger.error(f"✗ Failed to send data: {e}")
            # Try to reconnect
            if not await self.connect():
                logger.warning("Reconnection failed, will retry...")

    async def send_static_device_data(self):
        """Send static device data (only on change or at interval)"""
        for dev_id, device in self.static_devices.items():
            current_state = {
                "position": device["position"].copy(),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            # Check if state changed or interval elapsed
            should_send = (
                self.static_last_state[dev_id] is None or
                current_state["position"] != self.static_last_state[dev_id]["position"]
            )

            if should_send:
                payload = {
                    "device_id": dev_id,
                    "device_type": device["device_type"],
                    "name": device["name"],
                    "data_type": "position",
                    "timestamp": current_state["timestamp"],
                    "position": current_state["position"]
                }

                await self.send_data(payload)
                self.static_last_state[dev_id] = current_state
                logger.info(f"📍 Sent static device: {device['name']} (lat: {current_state['position']['latitude']:.4f}, lon: {current_state['position']['longitude']:.4f})")

    async def update_dynamic_device_position(self, dev_id: str):
        """Update dynamic device position based on movement model"""
        device = self.dynamic_devices[dev_id]
        state = self.device_state[dev_id]

        # Random walk for heading
        heading_change = random.uniform(
            -device["movement"]["heading_change_max"],
            device["movement"]["heading_change_max"]
        )
        state["heading"] = (state["heading"] + heading_change) % 360

        # Random walk for speed
        speed_change = random.uniform(-0.2, 0.2)
        state["speed"] = max(
            device["movement"]["speed_range"][0],
            min(device["movement"]["speed_range"][1], state["speed"] + speed_change)
        )

        # Update position (in meters per second -> degrees per second, roughly)
        lat_change = (state["speed"] / 111000) * math.cos(math.radians(state["heading"]))
        lon_change = (state["speed"] / 111000) * math.sin(math.radians(state["heading"]))

        state["position"]["latitude"] += lat_change
        state["position"]["longitude"] += lon_change

        # Update depth/altitude
        depth_range = device["movement"]["depth_range"]
        current_depth = state["position"]["altitude"]
        depth_change = random.uniform(-2, 2)
        state["position"]["altitude"] = max(
            depth_range[0],
            min(depth_range[1], current_depth + depth_change)
        )

        state["timestamp"] = datetime.now(timezone.utc).isoformat()

    async def send_dynamic_device_data(self, dev_id: str):
        """Send dynamic device data with sensor readings"""
        device = self.dynamic_devices[dev_id]
        state = self.device_state[dev_id]

        # Update position
        await self.update_dynamic_device_position(dev_id)

        # Create payload with position and sensor data
        payload = {
            "device_id": dev_id,
            "device_type": device["device_type"],
            "name": device["name"],
            "timestamp": state["timestamp"],
            "position": state["position"],
            "motion": {
                "heading": round(state["heading"], 2),
                "speed": round(state["speed"], 2)
            },
            "sensors": {}
        }

        # Add sensor data
        for sensor in device["sensors"]:
            sensor_type = sensor["sensor_type"]

            if sensor_type == "gps":
                payload["sensors"][sensor["sensor_id"]] = {
                    "type": "gps",
                    "accuracy": sensor["accuracy"],
                    "latitude": state["position"]["latitude"],
                    "longitude": state["position"]["longitude"],
                    "altitude": state["position"]["altitude"]
                }

            elif sensor_type == "imu":
                payload["sensors"][sensor["sensor_id"]] = {
                    "type": "imu",
                    "roll": random.uniform(-30, 30),
                    "pitch": random.uniform(-20, 20),
                    "yaw": state["heading"],
                    "acc_x": random.uniform(-2, 2),
                    "acc_y": random.uniform(-2, 2),
                    "acc_z": random.uniform(9.5, 10.5)
                }

            elif sensor_type == "pressure":
                depth = abs(state["position"]["altitude"])
                payload["sensors"][sensor["sensor_id"]] = {
                    "type": "pressure",
                    "pressure_pa": 101325 + depth * 10050,
                    "depth_m": depth
                }

            elif sensor_type == "temperature":
                # Water temperature decreases with depth
                depth = abs(state["position"]["altitude"])
                temp = 20 - (depth * 0.01)
                payload["sensors"][sensor["sensor_id"]] = {
                    "type": "temperature",
                    "temperature_c": round(max(2, temp), 1),
                    "temperature_f": round(max(35.6, temp * 9/5 + 32), 1)
                }

            elif sensor_type in ["sonar", "side_scan_sonar", "profiling_sonar"]:
                payload["sensors"][sensor["sensor_id"]] = {
                    "type": sensor_type,
                    "frequency_hz": sensor.get("frequency", 200000),
                    "range_m": random.uniform(10, 300),
                    "target_detected": random.random() > 0.7,
                    "signal_strength_db": random.uniform(-120, -60)
                }

            elif sensor_type == "hd_camera":
                payload["sensors"][sensor["sensor_id"]] = {
                    "type": "hd_camera",
                    "resolution": sensor["resolution"],
                    "fps": 30,
                    "light_level_lux": random.uniform(0, 100) if depth > 50 else random.uniform(100, 10000)
                }

            elif sensor_type == "led_light":
                payload["sensors"][sensor["sensor_id"]] = {
                    "type": "led_light",
                    "lumens": sensor["lumens"],
                    "power_w": random.uniform(100, 150),
                    "status": "on" if random.random() > 0.1 else "dimmed"
                }

            elif sensor_type == "magnetometer":
                payload["sensors"][sensor["sensor_id"]] = {
                    "type": "magnetometer",
                    "field_x_ut": random.uniform(-50000, 50000),
                    "field_y_ut": random.uniform(-50000, 50000),
                    "field_z_ut": random.uniform(-50000, 50000),
                    "heading": state["heading"]
                }

        await self.send_data(payload)
        logger.debug(f"📡 Sent dynamic device: {device['name']}")

    async def run_simulation(self):
        """Main simulation loop"""
        if not await self.connect():
            logger.error("Cannot start simulation without connection")
            return

        self.running = True
        logger.info("🚀 Starting simulation...")

        try:
            while self.running:
                # Send static device data (on change or at interval)
                await self.send_static_device_data()

                # Send dynamic device data (continuous)
                for dev_id in self.dynamic_devices:
                    await self.send_dynamic_device_data(dev_id)

                # Sleep to maintain reasonable update rate
                await asyncio.sleep(1)

        except KeyboardInterrupt:
            logger.info("🛑 Simulation interrupted by user")
        except Exception as e:
            logger.error(f"✗ Simulation error: {e}")
        finally:
            self.running = False
            await self.disconnect()

    async def start(self):
        """Start the simulator"""
        await self.run_simulation()

    def stop(self):
        """Stop the simulator"""
        self.running = False


async def main():
    simulator = MothSimulator("config.json")
    try:
        await simulator.start()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        simulator.stop()


if __name__ == "__main__":
    asyncio.run(main())
