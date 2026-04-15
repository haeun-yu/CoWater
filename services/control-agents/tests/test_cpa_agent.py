from __future__ import annotations

import math
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone

# CPAAgent imports redis.asyncio only for its Redis client type/runtime dependency.
# Unit tests stub it so the pure math and threshold logic can run without installing Redis.
redis_module = types.ModuleType("redis")
redis_asyncio_module = types.ModuleType("redis.asyncio")
redis_asyncio_module.Redis = object
redis_module.asyncio = redis_asyncio_module
sys.modules.setdefault("redis", redis_module)
sys.modules.setdefault("redis.asyncio", redis_asyncio_module)

pydantic_settings_module = types.ModuleType("pydantic_settings")


class _BaseSettings:
    def __init__(self, **kwargs):
        for name, value in self.__class__.__dict__.items():
            if name.startswith("_") or callable(value):
                continue
            setattr(self, name, kwargs.get(name, value))


def _settings_config_dict(**kwargs):
    return kwargs


pydantic_settings_module.BaseSettings = _BaseSettings
pydantic_settings_module.SettingsConfigDict = _settings_config_dict
sys.modules.setdefault("pydantic_settings", pydantic_settings_module)

CPA_AGENT_PATH = Path(__file__).resolve().parents[1] / "rule" / "cpa_agent.py"
spec = importlib.util.spec_from_file_location("test_cpa_agent_module", CPA_AGENT_PATH)
assert spec is not None and spec.loader is not None
cpa_agent_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cpa_agent_module)

CPAAgent = cpa_agent_module.CPAAgent
_compute_cpa_tcpa = cpa_agent_module._compute_cpa_tcpa
from shared.schemas.report import PlatformReport


def make_report(
    platform_id: str,
    *,
    lat: float,
    lon: float,
    sog: float | None,
    cog: float | None,
    nav_status: str | None = "underway_engine",
    timestamp: datetime | None = None,
) -> PlatformReport:
    return PlatformReport(
        platform_id=platform_id,
        timestamp=timestamp or datetime.now(tz=timezone.utc),
        lat=lat,
        lon=lon,
        sog=sog,
        cog=cog,
        nav_status=nav_status,
        source_protocol="ais",
    )


class CPAComputationTests(unittest.TestCase):
    def test_head_on_collision_course_returns_zero_cpa_and_positive_tcpa(self) -> None:
        r1 = make_report("A", lat=0.0, lon=0.0, sog=10.0, cog=90.0)
        r2 = make_report("B", lat=0.0, lon=1 / 60, sog=10.0, cog=270.0)

        cpa, tcpa = _compute_cpa_tcpa(r1, r2)

        self.assertIsNotNone(cpa)
        self.assertIsNotNone(tcpa)
        assert cpa is not None
        assert tcpa is not None
        self.assertAlmostEqual(cpa, 0.0, places=6)
        self.assertAlmostEqual(tcpa, 3.0, places=6)

    def test_diverging_targets_return_negative_tcpa(self) -> None:
        r1 = make_report("A", lat=0.0, lon=0.0, sog=10.0, cog=90.0)
        r2 = make_report("B", lat=0.0, lon=1 / 60, sog=20.0, cog=90.0)

        cpa, tcpa = _compute_cpa_tcpa(r1, r2)

        self.assertIsNotNone(cpa)
        self.assertIsNotNone(tcpa)
        assert cpa is not None
        assert tcpa is not None
        self.assertAlmostEqual(cpa, 0.0, places=6)
        self.assertLess(tcpa, 0.0)

    def test_parallel_same_speed_returns_current_distance_and_infinite_tcpa(self) -> None:
        r1 = make_report("A", lat=0.0, lon=0.0, sog=12.0, cog=90.0)
        r2 = make_report("B", lat=1 / 60, lon=0.0, sog=12.0, cog=90.0)

        cpa, tcpa = _compute_cpa_tcpa(r1, r2)

        self.assertIsNotNone(cpa)
        self.assertIsNotNone(tcpa)
        assert cpa is not None
        assert tcpa is not None
        self.assertAlmostEqual(cpa, 1.0, places=6)
        self.assertTrue(math.isinf(tcpa))

    def test_missing_motion_fields_return_none(self) -> None:
        r1 = make_report("A", lat=0.0, lon=0.0, sog=None, cog=90.0)
        r2 = make_report("B", lat=0.0, lon=1 / 60, sog=10.0, cog=270.0)

        cpa, tcpa = _compute_cpa_tcpa(r1, r2)

        self.assertIsNone(cpa)
        self.assertIsNone(tcpa)


class CPAAgentBehaviorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.agent = CPAAgent(redis=object())
        self.emitted_payloads = []

        async def capture_emit_alert(payload):
            self.emitted_payloads.append(payload)

        self.agent.emit_alert = capture_emit_alert  # type: ignore[method-assign]

    def test_is_active_filters_non_maneuvering_targets(self) -> None:
        anchored = make_report("A", lat=0.0, lon=0.0, sog=2.0, cog=90.0, nav_status="at_anchor")
        stopped = make_report("B", lat=0.0, lon=0.0, sog=0.0, cog=90.0)
        missing_cog = make_report("C", lat=0.0, lon=0.0, sog=2.0, cog=None)
        active = make_report("D", lat=0.0, lon=0.0, sog=2.0, cog=90.0)

        self.assertFalse(self.agent._is_active(anchored))
        self.assertFalse(self.agent._is_active(stopped))
        self.assertFalse(self.agent._is_active(missing_cog))
        self.assertTrue(self.agent._is_active(active))

    async def test_evaluate_emits_warning_inside_warning_threshold(self) -> None:
        r1 = make_report("A", lat=0.0, lon=0.0, sog=10.0, cog=90.0)
        r2 = make_report("B", lat=0.0, lon=1 / 60, sog=10.0, cog=270.0)

        await self.agent._evaluate(r1, r2, cpa=0.4, tcpa=20.0)

        self.assertEqual(len(self.emitted_payloads), 1)
        payload = self.emitted_payloads[0]
        self.assertEqual(payload.severity, "warning")
        self.assertEqual(payload.alert_type, "cpa")
        self.assertEqual(payload.metadata["cpa_nm"], 0.4)
        self.assertEqual(payload.metadata["tcpa_min"], 20.0)

    async def test_evaluate_emits_critical_inside_critical_threshold(self) -> None:
        r1 = make_report("A", lat=0.0, lon=0.0, sog=10.0, cog=90.0)
        r2 = make_report("B", lat=0.0, lon=1 / 60, sog=10.0, cog=270.0)

        await self.agent._evaluate(r1, r2, cpa=0.1, tcpa=5.0)

        self.assertEqual(len(self.emitted_payloads), 1)
        self.assertEqual(self.emitted_payloads[0].severity, "critical")

    async def test_evaluate_does_not_emit_on_exact_boundary_values(self) -> None:
        r1 = make_report("A", lat=0.0, lon=0.0, sog=10.0, cog=90.0)
        r2 = make_report("B", lat=0.0, lon=1 / 60, sog=10.0, cog=270.0)

        await self.agent._evaluate(
            r1,
            r2,
            cpa=self.agent.config["warning_cpa_nm"],
            tcpa=self.agent.config["warning_tcpa_min"],
        )

        self.assertEqual(self.emitted_payloads, [])

    async def test_evaluate_auto_resolves_previously_alerted_pair_when_risk_clears(self) -> None:
        r1 = make_report("A", lat=0.0, lon=0.0, sog=10.0, cog=90.0)
        r2 = make_report("B", lat=0.0, lon=1 / 60, sog=10.0, cog=270.0)

        await self.agent._evaluate(r1, r2, cpa=0.4, tcpa=20.0)
        await self.agent._evaluate(r1, r2, cpa=1.2, tcpa=20.0)

        self.assertEqual(len(self.emitted_payloads), 2)
        payload = self.emitted_payloads[1]
        self.assertEqual(payload.alert_type, "cpa_cleared")
        self.assertEqual(payload.resolve_dedup_key, "cpa:A:B")
        self.assertTrue(payload.metadata["resolve_only"])

    async def test_check_all_auto_resolves_when_tcpa_turns_negative(self) -> None:
        r1 = make_report("A", lat=0.0, lon=0.0, sog=10.0, cog=90.0)
        r2 = make_report("B", lat=0.0, lon=1 / 60, sog=10.0, cog=270.0)
        await self.agent._evaluate(r1, r2, cpa=0.4, tcpa=20.0)

        r2_diverging = make_report("B", lat=0.0, lon=1 / 60, sog=20.0, cog=90.0)
        self.agent._reports = {r1.platform_id: r1, r2_diverging.platform_id: r2_diverging}

        await self.agent._check_all(r1.platform_id)

        self.assertEqual(len(self.emitted_payloads), 2)
        payload = self.emitted_payloads[1]
        self.assertEqual(payload.alert_type, "cpa_cleared")
        self.assertEqual(payload.metadata["reason"], "risk_cleared")

    async def test_check_all_skips_stale_reports(self) -> None:
        now = datetime.now(tz=timezone.utc)
        fresh = make_report("A", lat=0.0, lon=0.0, sog=10.0, cog=90.0, timestamp=now)
        stale = make_report(
            "B",
            lat=0.0,
            lon=1 / 60,
            sog=10.0,
            cog=270.0,
            timestamp=now - timedelta(seconds=301),
        )

        self.agent._reports = {fresh.platform_id: fresh, stale.platform_id: stale}

        await self.agent._check_all(fresh.platform_id)

        self.assertEqual(self.emitted_payloads, [])

    async def test_purge_stale_reports_auto_resolves_existing_pair(self) -> None:
        now = datetime.now(tz=timezone.utc)
        fresh = make_report("A", lat=0.0, lon=0.0, sog=10.0, cog=90.0, timestamp=now)
        stale = make_report(
            "B",
            lat=0.0,
            lon=1 / 60,
            sog=10.0,
            cog=270.0,
            timestamp=now - timedelta(seconds=301),
        )
        await self.agent._evaluate(fresh, stale, cpa=0.4, tcpa=20.0)
        self.agent._reports = {fresh.platform_id: fresh, stale.platform_id: stale}

        await self.agent._purge_stale_reports()

        self.assertEqual(len(self.emitted_payloads), 2)
        payload = self.emitted_payloads[1]
        self.assertEqual(payload.alert_type, "cpa_cleared")
        self.assertEqual(payload.metadata["reason"], "stale_report")


if __name__ == "__main__":
    unittest.main()
