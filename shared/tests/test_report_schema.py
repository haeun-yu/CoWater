from __future__ import annotations

import unittest
from datetime import datetime, timezone

from shared.schemas.report import PlatformReport, REPORT_SCHEMA_VERSION


class PlatformReportSchemaTests(unittest.TestCase):
    def test_to_dict_round_trip_preserves_optional_raw_payload_fields(self) -> None:
        report = PlatformReport(
            platform_id="vessel-1",
            timestamp=datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc),
            lat=37.1,
            lon=126.9,
            sog=12.3,
            cog=270.0,
            source_protocol="ais",
            raw_payload_b64="YWJj",
            raw_payload_cache_key="raw:1",
            raw_payload_truncated=True,
        )

        payload = report.to_dict()
        hydrated = PlatformReport.from_dict(payload)

        self.assertEqual(hydrated.platform_id, report.platform_id)
        self.assertEqual(hydrated.timestamp, report.timestamp)
        self.assertEqual(hydrated.raw_payload_b64, "YWJj")
        self.assertEqual(hydrated.raw_payload_cache_key, "raw:1")
        self.assertTrue(hydrated.raw_payload_truncated)
        self.assertEqual(hydrated.schema_version, REPORT_SCHEMA_VERSION)

    def test_from_dict_normalizes_naive_timestamp_to_utc(self) -> None:
        report = PlatformReport.from_dict(
            {
                "platform_id": "vessel-2",
                "timestamp": "2026-04-10T12:34:56",
                "lat": 35.0,
                "lon": 129.0,
            }
        )

        self.assertEqual(report.timestamp.tzinfo, timezone.utc)
        self.assertEqual(report.timestamp.isoformat(), "2026-04-10T12:34:56+00:00")


if __name__ == "__main__":
    unittest.main()
