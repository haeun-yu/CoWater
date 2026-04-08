"""
CPA/TCPA Agent — 선박 간 최근접거리/시간 계산 및 충돌 위험 경보.

COLREGS 기반:
- CPA < warning_nm  AND TCPA < warning_min  → WARNING
- CPA < critical_nm AND TCPA < critical_min → CRITICAL

개선 사항:
- 정박/계류 선박(anchor/moored) 및 SOG=0 선박은 계산 대상에서 제외
- 두 보고 간 시간 간격이 max_report_age_sec 이상이면 계산 스킵 (stale data)
- _reports 딕셔너리를 TTL(max_report_age_sec)로 주기적 정리
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone

import redis.asyncio as aioredis

from base import Agent, AlertPayload, PlatformReport
from config import settings

# 정박/계류/조종불능 등 충돌 위험 계산에서 제외할 항법 상태
_SKIP_NAV_STATUSES = frozenset({
    "at_anchor",
    "moored",
    "aground",
    "not_under_command",
    "restricted_maneuverability",
})

# 보고 유효 기간(초) — 이보다 오래된 데이터는 CPA 계산 제외
_MAX_REPORT_AGE_SEC = 300   # 5분


class CPAAgent(Agent):
    agent_id = "cpa-agent"
    name = "CPA/TCPA Agent"
    description = "선박 간 최근접거리(CPA)와 최근접시간(TCPA)을 계산하여 충돌 위험 경보 생성"
    agent_type = "rule"

    def __init__(self, redis: aioredis.Redis) -> None:
        super().__init__(redis)
        # 기본 임계값은 settings에서 읽음 (PATCH /agents/cpa-agent/config 로 런타임 변경 가능)
        self.config = {
            "warning_cpa_nm":  settings.cpa_warning_nm,
            "warning_tcpa_min": settings.cpa_warning_tcpa_min,
            "critical_cpa_nm": settings.cpa_critical_nm,
            "critical_tcpa_min": settings.cpa_critical_tcpa_min,
        }
        # platform_id → 최근 보고 캐시 (메모리 상한: 최대 _MAX_REPORT_AGE_SEC 이내 활성 선박만)
        self._reports: dict[str, PlatformReport] = {}
        # 이미 경보된 쌍 (중복 방지) — key: frozenset({id1, id2})
        self._alerted_critical: set[frozenset] = set()
        self._alerted_warning: set[frozenset] = set()

    def _is_active(self, report: PlatformReport) -> bool:
        """CPA 계산 대상 선박 여부 판단."""
        # 정박·계류 상태 제외
        if report.nav_status in _SKIP_NAV_STATUSES:
            return False
        # SOG 없거나 0 이하인 선박 제외
        if report.sog is None or report.sog <= 0:
            return False
        # COG 없는 선박 제외
        if report.cog is None:
            return False
        return True

    def _purge_stale_reports(self) -> None:
        """오래된 보고 제거하여 메모리 누수 방지."""
        now = datetime.now(tz=timezone.utc)
        stale = [
            pid for pid, r in self._reports.items()
            if (now - r.timestamp).total_seconds() > _MAX_REPORT_AGE_SEC
        ]
        for pid in stale:
            self._reports.pop(pid, None)
            # 이 선박과 관련된 alerted 쌍도 정리
            self._alerted_critical = {
                pair for pair in self._alerted_critical if pid not in pair
            }
            self._alerted_warning = {
                pair for pair in self._alerted_warning if pid not in pair
            }

    async def on_platform_report(self, report: PlatformReport) -> None:
        self._reports[report.platform_id] = report

        # 주기적 메모리 정리 (10% 확률 — 매 보고마다 하면 오버헤드)
        import random
        if random.random() < 0.1:
            self._purge_stale_reports()

        if self._is_active(report):
            await self._check_all(report.platform_id)

    async def _check_all(self, changed_id: str) -> None:
        r1 = self._reports[changed_id]
        now = datetime.now(tz=timezone.utc)

        for other_id, r2 in list(self._reports.items()):
            if other_id == changed_id:
                continue
            # 상대방 선박도 활성 조건 확인
            if not self._is_active(r2):
                continue
            # 상대방 보고가 너무 오래됐으면 스킵
            if (now - r2.timestamp).total_seconds() > _MAX_REPORT_AGE_SEC:
                continue

            cpa, tcpa = _compute_cpa_tcpa(r1, r2)
            if cpa is None or tcpa is None or tcpa < 0 or not math.isfinite(tcpa):
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
            self._alerted_critical.add(pair)
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
            if pair not in self._alerted_warning and pair not in self._alerted_critical:
                self._alerted_warning.add(pair)
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
        # 같은 속도/방향 — 현재 거리가 CPA, TCPA=∞ (충돌 궤적 아님)
        return math.hypot(dx, dy), float("inf")

    tcpa = -(dx * dvx + dy * dvy) / dv2   # minutes

    cpa_x = dx + dvx * tcpa
    cpa_y = dy + dvy * tcpa
    cpa = math.hypot(cpa_x, cpa_y)

    return cpa, tcpa
