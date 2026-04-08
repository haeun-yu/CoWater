"""
Anomaly Rule Agent — 이상 행동 탐지 (Rule 기반).

탐지 항목:
- AIS 신호 소실 (일정 시간 보고 없음)
- 급격한 속도 저하 (표류 의심)
- 비정상 방향 변경 (ROT 급증)

Redis 영속화:
- _last_seen, _ais_lost 상태를 Redis에 저장하여 재시작 시 복구한다.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import redis.asyncio as aioredis

from base import Agent, AlertPayload, PlatformReport
from config import settings

logger = logging.getLogger(__name__)

_STATE_KEY = "agent:anomaly_rule:state"
_STATE_TTL = 3600  # 1시간 — 장기 중단 후 복구 시 stale 상태 방지


class AnomalyRuleAgent(Agent):
    agent_id = "anomaly-rule"
    name = "Anomaly Rule Agent"
    description = "AIS 소실, 급속도 저하, 비정상 선회 등 이상 행동 Rule 기반 탐지"
    agent_type = "rule"

    def __init__(self, redis: aioredis.Redis) -> None:
        super().__init__(redis)
        self._last_seen: dict[str, datetime] = {}
        self._last_sog: dict[str, float] = {}
        self._last_sog_time: dict[str, datetime] = {}   # 시간 간격 체크용
        self._ais_lost: set[str] = set()

    # ── Redis 상태 영속화 ──────────────────────────────────────────────────

    async def restore_state(self) -> None:
        """서비스 시작 시 Redis에서 상태 복구."""
        try:
            raw = await self._redis.get(_STATE_KEY)
            if not raw:
                return
            data = json.loads(raw)
            for pid, ts_str in data.get("last_seen", {}).items():
                dt = datetime.fromisoformat(ts_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                self._last_seen[pid] = dt
            self._ais_lost = set(data.get("ais_lost", []))
            logger.info(
                "AnomalyRuleAgent state restored: %d platforms, %d ais_lost",
                len(self._last_seen), len(self._ais_lost),
            )
        except Exception:
            logger.exception("Failed to restore AnomalyRuleAgent state")

    async def _save_state(self) -> None:
        """현재 상태를 Redis에 저장 (10% 확률 — 매 보고마다 저장하면 오버헤드)."""
        try:
            data = {
                "last_seen": {
                    pid: dt.isoformat()
                    for pid, dt in self._last_seen.items()
                },
                "ais_lost": list(self._ais_lost),
            }
            await self._redis.set(_STATE_KEY, json.dumps(data), ex=_STATE_TTL)
        except Exception:
            logger.warning("Failed to save AnomalyRuleAgent state")

    # ── 이벤트 핸들러 ───────────────────────────────────────────────────────

    async def on_platform_report(self, report: PlatformReport) -> None:
        pid = report.platform_id
        now = datetime.now(tz=timezone.utc)

        # AIS 복구 감지
        if pid in self._ais_lost:
            self._ais_lost.discard(pid)
            await self.emit_alert(AlertPayload(
                alert_type="ais_recovered",
                severity="info",
                message=f"{pid} AIS 신호 복구",
                platform_ids=[pid],
                # dedup_key 없음: 복구는 독립 이벤트, 소실 경보를 덮어쓰지 않음
                resolve_dedup_key=f"ais_off:{pid}",
            ))

        self._last_seen[pid] = now

        # 급속도 저하 — 두 보고 간 시간 간격이 지나치게 길면 비교 스킵
        prev_sog = self._last_sog.get(pid)
        prev_time = self._last_sog_time.get(pid)
        if (
            prev_sog is not None
            and report.sog is not None
            and prev_time is not None
            and (now - prev_time).total_seconds() <= settings.sog_compare_max_gap_sec
        ):
            drop = prev_sog - report.sog
            if drop >= settings.speed_drop_threshold:
                rec = None
                if self.level in ("L2", "L3"):
                    rec = f"{pid} 속도 급감 감지 ({prev_sog:.1f}→{report.sog:.1f}kts). 표류 또는 기관 이상 의심."
                await self.emit_alert(AlertPayload(
                    alert_type="anomaly",
                    severity="warning",
                    message=f"{pid} 급속도 저하: {prev_sog:.1f}→{report.sog:.1f}kts",
                    platform_ids=[pid],
                    recommendation=rec,
                    metadata={"prev_sog": prev_sog, "current_sog": report.sog},
                    dedup_key=f"anomaly:speed:{pid}",
                ))

        if report.sog is not None:
            self._last_sog[pid] = report.sog
            self._last_sog_time[pid] = now

        # 비정상 선회
        if report.rot is not None and abs(report.rot) > settings.rot_threshold:
            rec = None
            if self.level in ("L2", "L3"):
                rec = f"{pid} 비정상 선회율({report.rot:.1f}°/min) 감지. 항로 이탈 또는 기관 이상 확인 요망."
            await self.emit_alert(AlertPayload(
                alert_type="anomaly",
                severity="warning",
                message=f"{pid} 비정상 선회율: {report.rot:.1f}°/min",
                platform_ids=[pid],
                recommendation=rec,
                metadata={"rot": report.rot},
                dedup_key=f"anomaly:rot:{pid}",
            ))

        # 10% 확률로 상태 저장
        import random
        if random.random() < 0.1:
            await self._save_state()

    async def check_ais_timeout(self) -> None:
        """주기적 호출 — AIS 소실 선박 감지."""
        now = datetime.now(tz=timezone.utc)
        state_dirty = False
        for pid, last in list(self._last_seen.items()):
            elapsed = (now - last).total_seconds()
            if elapsed > settings.ais_timeout_sec and pid not in self._ais_lost:
                self._ais_lost.add(pid)
                state_dirty = True
                await self.emit_alert(AlertPayload(
                    alert_type="ais_off",
                    severity="warning",
                    message=f"{pid} AIS 신호 소실 ({int(elapsed)}초 경과)",
                    platform_ids=[pid],
                    recommendation=(
                        f"{pid} AIS 신호 {int(elapsed)}초 미수신. 위치 미상. "
                        f"인접 선박 및 해경에 통보 검토." if self.level in ("L2", "L3") else None
                    ),
                    dedup_key=f"ais_off:{pid}",
                ))
        if state_dirty:
            await self._save_state()
