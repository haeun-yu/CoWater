"""
Anomaly Rule Agent — 이상 행동 탐지 (Rule 기반).

탐지 항목:
- AIS 신호 소실 (일정 시간 보고 없음)
- 급격한 속도 저하 (표류 의심)
- 비정상 방향 변경 (ROT 급증)
"""

from __future__ import annotations

from datetime import datetime, timezone

import redis.asyncio as aioredis

from base import Agent, AlertPayload, PlatformReport
from config import settings


class AnomalyRuleAgent(Agent):
    agent_id = "anomaly-rule"
    name = "Anomaly Rule Agent"
    description = "AIS 소실, 급속도 저하, 비정상 선회 등 이상 행동 Rule 기반 탐지"
    agent_type = "rule"

    def __init__(self, redis: aioredis.Redis) -> None:
        super().__init__(redis)
        self._last_seen: dict[str, datetime] = {}
        self._last_sog: dict[str, float] = {}
        self._ais_lost: set[str] = set()

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
                # dedup_key 없음: 복구는 독립 이벤트로 발행하여 소실 경보를 덮어쓰지 않음
            ))

        self._last_seen[pid] = now

        # 급속도 저하
        prev_sog = self._last_sog.get(pid)
        if prev_sog is not None and report.sog is not None:
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

    async def check_ais_timeout(self) -> None:
        """주기적 호출 — AIS 소실 선박 감지."""
        now = datetime.now(tz=timezone.utc)
        for pid, last in list(self._last_seen.items()):
            elapsed = (now - last).total_seconds()
            if elapsed > settings.ais_timeout_sec and pid not in self._ais_lost:
                self._ais_lost.add(pid)
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
