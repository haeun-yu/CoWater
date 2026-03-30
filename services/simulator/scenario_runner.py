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

import yaml

from config import settings
from core.ais_encoder import encode_position_report
from core.vessel import NavStatus, VesselSimulator, VesselState, Waypoint
from core.weather import WeatherGenerator
from moth_publisher import MothPublisher

logger = logging.getLogger(__name__)


@dataclass
class ScenarioEvent:
    at_s: float         # 시나리오 시작 후 몇 초 후
    mmsi: str           # 대상 선박 MMSI (또는 "MMSI-{mmsi}")
    event_type: str
    params: dict = field(default_factory=dict)
    _fired: bool = False


class ScenarioRunner:
    def __init__(self, scenario_path: str, publisher: MothPublisher) -> None:
        self._publisher = publisher
        self._vessels: dict[str, VesselSimulator] = {}
        self._events: list[ScenarioEvent] = []
        self._weather = WeatherGenerator()
        self._elapsed_s: float = 0.0
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

    async def run(self) -> None:
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

            # 모든 선박 틱 + AIS 퍼블리시
            for vessel in self._vessels.values():
                vessel.tick(dt_sim)
                sentence = encode_position_report(vessel.state)
                if sentence:
                    await self._publisher.publish(sentence)

            if int(self._elapsed_s) % 30 == 0 and self._elapsed_s > 0:
                logger.info(
                    "t=%.0fs vessels=%d weather=wind%.1fkts",
                    self._elapsed_s,
                    len(self._vessels),
                    self._weather.current_state().wind_speed_knots,
                )
