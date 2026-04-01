"""
CPA/TCPA Agent — 선박 간 최근접거리/시간 계산 및 충돌 위험 경보.

COLREGS 기반:
- CPA < warning_nm  AND TCPA < warning_min  → WARNING
- CPA < critical_nm AND TCPA < critical_min → CRITICAL
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone

import redis.asyncio as aioredis

from base import Agent, AlertPayload, PlatformReport


class CPAAgent(Agent):
    agent_id = "cpa-agent"
    name = "CPA/TCPA Agent"
    description = "선박 간 최근접거리(CPA)와 최근접시간(TCPA)을 계산하여 충돌 위험 경보 생성"
    agent_type = "rule"

    # 기본 임계값 (config로 오버라이드 가능)
    _DEFAULT_CONFIG = {
        "warning_cpa_nm": 0.5,
        "warning_tcpa_min": 30,
        "critical_cpa_nm": 0.2,
        "critical_tcpa_min": 10,
    }

    def __init__(self, redis: aioredis.Redis) -> None:
        super().__init__(redis)
        self.config = dict(self._DEFAULT_CONFIG)
        # platform_id → 최근 보고 캐시
        self._reports: dict[str, PlatformReport] = {}
        # 이미 경보된 쌍 (중복 방지) — key: frozenset({id1, id2})
        self._alerted_critical: set[frozenset] = set()
        self._alerted_warning: set[frozenset] = set()

    async def on_platform_report(self, report: PlatformReport) -> None:
        self._reports[report.platform_id] = report
        await self._check_all(report.platform_id)

    async def _check_all(self, changed_id: str) -> None:
        r1 = self._reports[changed_id]
        for other_id, r2 in self._reports.items():
            if other_id == changed_id:
                continue
            cpa, tcpa = _compute_cpa_tcpa(r1, r2)
            if cpa is None or tcpa is None or tcpa < 0:
                continue
            await self._evaluate(r1, r2, cpa, tcpa)

    async def _evaluate(
        self, r1: PlatformReport, r2: PlatformReport, cpa: float, tcpa: float
    ) -> None:
        cfg = self.config
        pair = frozenset({r1.platform_id, r2.platform_id})

        # dedup_key: 쌍 기반 (정렬하여 방향 무관)
        ids = sorted([r1.platform_id, r2.platform_id])
        dedup_key = f"cpa:{ids[0]}:{ids[1]}"

        if cpa < cfg["critical_cpa_nm"] and tcpa < cfg["critical_tcpa_min"]:
            self._alerted_warning.discard(pair)
            rec = None
            if self.level in ("L2", "L3"):
                rec = (
                    f"{r1.platform_id}와 {r2.platform_id}의 CPA={cpa:.2f}NM, TCPA={tcpa:.1f}분. "
                    f"COLREGS Rule 16에 따라 피항선은 즉시 변침 또는 감속하십시오."
                )
            await self.emit_alert(AlertPayload(
                alert_type="cpa",
                severity="critical",
                message=(
                    f"충돌 위험 CRITICAL: {r1.platform_id} ↔ {r2.platform_id} "
                    f"CPA={cpa:.2f}NM TCPA={tcpa:.1f}분"
                ),
                platform_ids=[r1.platform_id, r2.platform_id],
                recommendation=rec,
                metadata={"cpa_nm": round(cpa, 3), "tcpa_min": round(tcpa, 1)},
                dedup_key=dedup_key,
            ))

        elif cpa < cfg["warning_cpa_nm"] and tcpa < cfg["warning_tcpa_min"]:
            if pair not in self._alerted_critical:
                rec = None
                if self.level in ("L2", "L3"):
                    rec = (
                        f"주의 요망: {r1.platform_id}와 {r2.platform_id} 접근 중. "
                        f"CPA={cpa:.2f}NM TCPA={tcpa:.1f}분. 상대 동향 지속 감시."
                    )
                await self.emit_alert(AlertPayload(
                    alert_type="cpa",
                    severity="warning",
                    message=(
                        f"충돌 위험 WARNING: {r1.platform_id} ↔ {r2.platform_id} "
                        f"CPA={cpa:.2f}NM TCPA={tcpa:.1f}분"
                    ),
                    platform_ids=[r1.platform_id, r2.platform_id],
                    recommendation=rec,
                    metadata={"cpa_nm": round(cpa, 3), "tcpa_min": round(tcpa, 1)},
                    dedup_key=dedup_key,
                ))

        else:
            # 위험 해소
            self._alerted_critical.discard(pair)
            self._alerted_warning.discard(pair)


# ── CPA/TCPA 계산 (벡터 방식) ────────────────────────────────────────────

_NM_PER_DEG_LAT = 60.0      # 위도 1° ≈ 60 NM
_KNOTS_TO_NM_PER_MIN = 1 / 60


def _compute_cpa_tcpa(
    r1: PlatformReport, r2: PlatformReport
) -> tuple[float | None, float | None]:
    """
    두 선박의 위치/속도 벡터로 CPA(NM)와 TCPA(분)를 계산.
    SOG/COG가 없으면 None 반환.
    """
    if r1.sog is None or r2.sog is None or r1.cog is None or r2.cog is None:
        return None, None

    # NM 단위 상대 위치
    avg_lat = (r1.lat + r2.lat) / 2
    cos_lat = math.cos(math.radians(avg_lat))

    dx = (r2.lon - r1.lon) * cos_lat * _NM_PER_DEG_LAT
    dy = (r2.lat - r1.lat) * _NM_PER_DEG_LAT

    # 속도 벡터 (NM/min)
    def vel(sog, cog):
        rad = math.radians(cog)
        return sog * math.sin(rad) * _KNOTS_TO_NM_PER_MIN, \
               sog * math.cos(rad) * _KNOTS_TO_NM_PER_MIN

    vx1, vy1 = vel(r1.sog, r1.cog)
    vx2, vy2 = vel(r2.sog, r2.cog)

    # 상대 속도
    dvx = vx2 - vx1
    dvy = vy2 - vy1

    dv2 = dvx ** 2 + dvy ** 2
    if dv2 < 1e-9:
        # 같은 속도/방향 — 현재 거리가 CPA
        cpa = math.hypot(dx, dy)
        return cpa, float("inf")

    tcpa = -(dx * dvx + dy * dvy) / dv2   # minutes

    cpa_x = dx + dvx * tcpa
    cpa_y = dy + dvy * tcpa
    cpa = math.hypot(cpa_x, cpa_y)

    return cpa, tcpa
