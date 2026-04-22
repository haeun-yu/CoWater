"""
시나리오 실행기.

YAML 시나리오를 로드하여 VesselSimulator 집합을 생성하고,
정해진 시각에 이벤트를 주입하며 AIS 인코딩 → Moth 퍼블리시까지 담당.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
import yaml

from config import settings
from core.ais_encoder import encode_position_report
from core.vessel import NavStatus, VesselSimulator, VesselState, Waypoint
from core.weather import WeatherGenerator
from moth_publisher import MothPublisher
from shared.schemas.device_stream import DeviceStreamMessage, StreamEnvelope

logger = logging.getLogger(__name__)


@dataclass
class ScenarioEvent:
    at_s: float         # 시나리오 시작 후 몇 초 후
    mmsi: str           # 대상 선박 MMSI (또는 "MMSI-{mmsi}")
    event_type: str
    params: dict = field(default_factory=dict)
    _fired: bool = False


class ScenarioRunner:
    def __init__(
        self,
        scenario_path: str,
        publishers: list,
        stream_publishers: list | None = None,
    ) -> None:
        self._publishers = publishers
        self._stream_publishers = stream_publishers or []
        self._vessels: dict[str, VesselSimulator] = {}
        self._events: list[ScenarioEvent] = []
        self._weather = WeatherGenerator()
        self._elapsed_s: float = 0.0
        self._last_stream_at: dict[tuple[str, str], float] = {}
        self._load(scenario_path)

    def _load(self, path: str) -> None:
        with open(path) as f:
            cfg = yaml.safe_load(f)

        for v in cfg.get("vessels", []):
            mmsi_key = v["mmsi"] if v["mmsi"].startswith("MMSI-") else f"MMSI-{v['mmsi']}"
            waypoints = [
                Waypoint(lat=wp["lat"], lon=wp["lon"],
                         speed_knots=wp.get("speed"))
                for wp in v.get("waypoints", [])
            ]
            state = VesselState(
                mmsi=mmsi_key,
                name=v["name"],
                lat=v["lat"],
                lon=v["lon"],
                heading=v.get("heading", 0.0),
                cog=v.get("heading", 0.0),
                sog=v.get("speed", 8.0),
                max_speed_knots=v.get("max_speed", 15.0),
                max_rot_deg_per_min=v.get("max_rot", 10.0),
                nav_status=NavStatus.UNDERWAY_ENGINE,
                waypoints=waypoints,
            )
            self._vessels[mmsi_key] = VesselSimulator(state)
            logger.info("Loaded vessel: %s (%s) at (%.4f, %.4f)", v["name"], mmsi_key, v["lat"], v["lon"])

        for e in cfg.get("events", []):
            mmsi = e["mmsi"] if e["mmsi"].startswith("MMSI-") else f"MMSI-{e['mmsi']}"
            self._events.append(ScenarioEvent(
                at_s=float(e["at"]),
                mmsi=mmsi,
                event_type=e["type"],
                params={k: v for k, v in e.items() if k not in ("at", "mmsi", "type")},
            ))
        self._events.sort(key=lambda e: e.at_s)
        logger.info("Loaded %d vessel(s), %d event(s)", len(self._vessels), len(self._events))

    async def register_platforms(self) -> None:
        """시나리오 선박을 Core API에 등록 (이름·유형 설정). 이미 있으면 이름만 업데이트."""
        async with httpx.AsyncClient(base_url=settings.core_api_url, timeout=10) as client:
            for mmsi_key, sim in self._vessels.items():
                name = sim.state.name
                try:
                    # 존재 확인
                    resp = await client.get(f"/platforms/{mmsi_key}")
                    if resp.status_code == 404:
                        await client.post("/platforms", json={
                            "platform_id": mmsi_key,
                            "platform_type": "vessel",
                            "name": name,
                            "source_protocol": "ais",
                            "capabilities": ["position", "heading"],
                            "metadata": {},
                        })
                        logger.info("Registered platform: %s (%s)", name, mmsi_key)
                    elif resp.status_code == 200:
                        await client.patch(f"/platforms/{mmsi_key}", json={"name": name})
                        logger.info("Updated platform name: %s (%s)", name, mmsi_key)
                except Exception:
                    logger.warning("Failed to register platform %s — Core API unavailable", mmsi_key)

    async def run(self) -> None:
        # Core API에 플랫폼 등록 시도 (실패해도 시뮬레이션 계속)
        try:
            await self.register_platforms()
        except Exception:
            logger.warning("Platform registration skipped")

        tick_interval = 1.0 / settings.tick_rate_hz
        real_interval = tick_interval / settings.time_scale
        dt_sim = tick_interval  # 시뮬레이션 내 경과 시간

        while True:
            await asyncio.sleep(real_interval)
            self._elapsed_s += dt_sim
            self._weather.tick(dt_sim)

            # 이벤트 발사
            for event in self._events:
                if not event._fired and self._elapsed_s >= event.at_s:
                    vessel = self._vessels.get(event.mmsi)
                    if vessel:
                        vessel.inject_event(event.event_type, **event.params)
                    else:
                        logger.warning("Event target not found: %s", event.mmsi)
                    event._fired = True

            # 모든 선박 틱 + AIS 퍼블리시 (매 틱마다 1개 이상 문장 보내기)
            sentence_count = 0
            for vessel in self._vessels.values():
                vessel.tick(dt_sim)
                sentence = encode_position_report(vessel.state)
                if sentence:
                    for publisher in self._publishers:
                        await publisher.publish(sentence)
                    sentence_count += 1
                await self._publish_device_streams(vessel)

            if int(self._elapsed_s) % 30 == 0 and self._elapsed_s > 0:
                logger.info(
                    "t=%.0fs vessels=%d weather=wind%.1fkts sentences=%d/tick",
                    self._elapsed_s,
                    len(self._vessels),
                    self._weather.current_state().wind_speed_knots,
                    sentence_count,
                )

    async def _publish_device_streams(self, vessel: VesselSimulator) -> None:
        if not self._stream_publishers:
            return

        stream_defs = [
            ("telemetry.position", 1.0, self._position_payload, "latest"),
            ("telemetry.status", 5.0, self._status_payload, "best_effort"),
            ("sensor.sonar", 2.0, self._sonar_payload, "sampled"),
            ("telemetry.task", 5.0, self._task_payload, "best_effort"),
            ("telemetry.network", 3.0, self._network_payload, "best_effort"),
        ]
        for stream, interval_s, payload_factory, qos in stream_defs:
            key = (vessel.state.mmsi, stream)
            last_at = self._last_stream_at.get(key)
            if last_at is not None and self._elapsed_s - last_at < interval_s:
                continue
            self._last_stream_at[key] = self._elapsed_s
            await self._publish_stream(vessel, stream, payload_factory(vessel), qos)

    async def _publish_stream(
        self,
        vessel: VesselSimulator,
        stream: str,
        payload: dict,
        qos: str,
    ) -> None:
        message = DeviceStreamMessage(
            envelope=StreamEnvelope(
                stream=stream,
                timestamp=datetime.now(timezone.utc).isoformat(),
                source="simulator",
                device_id=vessel.state.mmsi,
                device_type="vessel",
                qos=qos,
            ),
            payload=payload,
        )
        for publisher in self._stream_publishers:
            await publisher.publish_stream(message)

    def _position_payload(self, vessel: VesselSimulator) -> dict:
        state = vessel.state
        return {
            "lat": state.lat,
            "lon": state.lon,
            "sog": state.sog,
            "cog": state.cog,
            "heading": state.heading,
            "rot": state.rot,
            "nav_status": state.nav_status.name.lower(),
            "name": state.name,
            "source_protocol": "custom",
        }

    def _status_payload(self, vessel: VesselSimulator) -> dict:
        state = vessel.state
        battery_pct = max(20.0, 100.0 - (self._elapsed_s / 1800.0 * 100.0))
        return {
            "name": state.name,
            "operational_state": "underway",
            "mode": "autonomous",
            "battery_pct": round(battery_pct, 1),
            "health": "nominal",
            "capabilities": ["position", "status", "network", "task", "sonar"],
        }

    def _sonar_payload(self, vessel: VesselSimulator) -> dict:
        state = vessel.state
        contact_strength = 0.35 + ((int(self._elapsed_s) % 10) / 100.0)
        return {
            "ping_id": f"{state.mmsi}-{int(self._elapsed_s)}",
            "range_m": 120.0,
            "bearing_deg": (state.heading + 35.0) % 360.0,
            "contacts": [
                {
                    "contact_id": f"sim-contact-{state.mmsi}",
                    "classification": "unknown_object",
                    "confidence": round(contact_strength, 2),
                    "range_m": 84.0,
                    "bearing_deg": (state.heading + 18.0) % 360.0,
                }
            ],
        }

    def _task_payload(self, vessel: VesselSimulator) -> dict:
        progress = min(100.0, (self._elapsed_s / 300.0) * 100.0)
        return {
            "task_id": f"sim-task-{vessel.state.mmsi}",
            "task_type": "patrol",
            "phase": "survey",
            "progress_pct": round(progress, 1),
        }

    def _network_payload(self, vessel: VesselSimulator) -> dict:
        latency_ms = 80 + (int(self._elapsed_s) % 5) * 20
        packet_loss_pct = 0.0 if int(self._elapsed_s) % 10 else 10.0
        return {
            "link": "moth",
            "connected": True,
            "latency_ms": latency_ms,
            "packet_loss_pct": packet_loss_pct,
            "rssi_dbm": -62,
        }
