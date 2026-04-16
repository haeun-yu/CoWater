"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { usePlatformStore } from "@/stores/platformStore";
import { useAlertStore } from "@/stores/alertStore";
import type { PlatformState } from "@/types";
import { formatDistanceToNow } from "date-fns";
import { ko } from "date-fns/locale";
import { countPlatformsByFreshness } from "@/lib/platformStatus";
import PageHeader from "@/components/ui/PageHeader";
import MetricCard from "@/components/ui/MetricCard";
import StatusBadge from "@/components/ui/StatusBadge";
import { DataTable, DataTableEmpty } from "@/components/ui/DataTable";
import FilterChip from "@/components/ui/FilterChip";

const TYPE_ICON: Record<string, string> = {
  vessel: "▲", usv: "◆", rov: "●", auv: "◈", drone: "✦", buoy: "◉",
};
const TYPE_LABEL: Record<string, string> = {
  vessel: "선박", usv: "USV", rov: "ROV", auv: "AUV", drone: "드론", buoy: "부이",
};
const TYPE_COLOR: Record<string, string> = {
  vessel: "#2e8dd4", usv: "#22d3ee", rov: "#a78bfa",
  auv: "#818cf8", drone: "#34d399", buoy: "#fbbf24",
};
const NAV_STATUS_KR: Record<string, string> = {
  underway_engine: "항행 중", at_anchor: "정박",
  not_under_command: "조종 불능", restricted_maneuverability: "조종 제한",
  moored: "계류", aground: "좌초", engaged_fishing: "어로 작업",
  underway_sailing: "항행 중(범선)",
};
const NAV_STATUS_BADGE: Record<string, string> = {
  not_under_command: "text-red-400 bg-red-500/15 border-red-500/30",
  aground:           "text-red-400 bg-red-500/15 border-red-500/30",
  at_anchor:         "text-yellow-400 bg-yellow-500/10 border-yellow-500/20",
  moored:            "text-yellow-400 bg-yellow-500/10 border-yellow-500/20",
  underway_engine:   "text-green-400 bg-green-500/10 border-green-500/20",
};

function formatId(p: PlatformState) { return p.platform_id.replace(/^MMSI-/, ""); }
function formatName(p: PlatformState) {
  if (!p.name || p.name === p.platform_id) return formatId(p);
  return p.name;
}

export default function PlatformsPage() {
  const router = useRouter();
  const [viewMode, setViewMode] = useState<"table" | "card">("table");
  const platforms = Object.values(usePlatformStore((s) => s.platforms));
  const alerts = useAlertStore((s) => s.alerts);

  // 타입별 분포 계산
  const typeDistribution = platforms.reduce<Record<string, number>>((acc, p) => {
    const type = p.platform_type ?? "vessel";
    acc[type] = (acc[type] ?? 0) + 1;
    return acc;
  }, {});

  const alertsByPlatform = alerts
    .filter((a) => a.status === "new")
    .reduce<Record<string, { count: number; maxSeverity: string }>>((acc, a) => {
      a.platform_ids.forEach((id) => {
        if (!acc[id]) acc[id] = { count: 0, maxSeverity: "info" };
        acc[id].count++;
        if (a.severity === "critical") acc[id].maxSeverity = "critical";
        else if (a.severity === "warning" && acc[id].maxSeverity !== "critical") acc[id].maxSeverity = "warning";
      });
      return acc;
    }, {});

  const sorted = [...platforms].sort((a, b) => {
    const aS = alertsByPlatform[a.platform_id]?.maxSeverity === "critical" ? 0 : alertsByPlatform[a.platform_id]?.maxSeverity === "warning" ? 1 : alertsByPlatform[a.platform_id] ? 2 : 3;
    const bS = alertsByPlatform[b.platform_id]?.maxSeverity === "critical" ? 0 : alertsByPlatform[b.platform_id]?.maxSeverity === "warning" ? 1 : alertsByPlatform[b.platform_id] ? 2 : 3;
    return aS - bS;
  });

  const totalAlerts = alerts.filter((a) => a.status === "new").length;
  const freshness = countPlatformsByFreshness(platforms);

  return (
    <div className="page-shell">
      <PageHeader
        title="플랫폼 현황"
        stats={[
          <MetricCard key="tracked" label="관제 중" value={platforms.length} />,
          <MetricCard key="alerts" label="미확인 경보" value={totalAlerts} tone={totalAlerts > 0 ? "critical" : "neutral"} />,
          <MetricCard key="live" label="정상 수신" value={freshness.live} />,
          <MetricCard key="issues" label="지연·유실" value={freshness.stale + freshness.lost} tone={freshness.stale + freshness.lost > 0 ? "warning" : "neutral"} />,
        ]}
      />

      {/* 타입별 분포 + 뷰 전환 */}
      <div className="border-b border-ocean-800/80 bg-ocean-950/60 px-5 py-3 backdrop-blur-sm flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        {/* 타입별 분포 */}
        <div className="flex flex-wrap gap-2">
          {Object.entries(typeDistribution)
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([type, count]) => (
              <div key={type} className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-ocean-700 bg-ocean-900/40 text-xs">
                <span style={{ color: TYPE_COLOR[type] ?? "#2e8dd4" }} className="text-sm">
                  {TYPE_ICON[type] ?? "?"}
                </span>
                <span className="text-ocean-300">{TYPE_LABEL[type]}</span>
                <span className="text-ocean-500 font-mono">{count}</span>
              </div>
            ))}
        </div>

        {/* 뷰 전환 */}
        <div className="flex items-center gap-1 rounded-full border border-ocean-700 bg-ocean-900/40 p-1">
          <FilterChip
            onClick={() => setViewMode("table")}
            active={viewMode === "table"}
            className="text-xs"
          >
            📋 테이블
          </FilterChip>
          <FilterChip
            onClick={() => setViewMode("card")}
            active={viewMode === "card"}
            className="text-xs"
          >
            🎴 카드
          </FilterChip>
        </div>
      </div>

      {/* 목록 */}
      <div className="flex-1 overflow-auto p-5">
        {viewMode === "table" ? (
          <TableView />
        ) : (
          <CardView />
        )}
      </div>
    </div>
  );

  function TableView() {
    return (
      <DataTable>
        <table className="w-full text-xs border-collapse">
          <thead className="sticky top-0 bg-ocean-950/95 z-10 backdrop-blur-sm">
            <tr className="border-b border-ocean-800 text-ocean-500 text-left">
              <th className="py-2.5 pr-3 font-medium w-8">유형</th>
              <th className="py-2.5 pr-3 font-medium">이름 / ID</th>
              <th className="py-2.5 pr-3 font-medium">위치</th>
              <th className="py-2.5 pr-3 font-medium">속도</th>
              <th className="py-2.5 pr-3 font-medium">침로</th>
              <th className="py-2.5 pr-3 font-medium">항법 상태</th>
              <th className="py-2.5 pr-3 font-medium">국적</th>
              <th className="py-2.5 pr-3 font-medium">최근 수신</th>
              <th className="py-2.5 font-medium">경보</th>
            </tr>
          </thead>
          <tbody>
            {sorted.length === 0 ? (
              <DataTableEmpty colSpan={9}>수신된 플랫폼 없음 — 시뮬레이터를 시작하세요</DataTableEmpty>
            ) : (
              sorted.map((p) => {
                const type = p.platform_type ?? "vessel";
                const color = TYPE_COLOR[type] ?? "#2e8dd4";
                const alertInfo = alertsByPlatform[p.platform_id];
                const navBadge = NAV_STATUS_BADGE[p.nav_status ?? ""] ?? "text-ocean-500 bg-ocean-800/50 border-ocean-700/50";
                const isDistress = p.nav_status === "not_under_command" || p.nav_status === "aground";

                return (
                  <tr
                    key={p.platform_id}
                    onClick={() => router.push(`/platforms/${encodeURIComponent(p.platform_id)}`)}
                    className={`border-b border-ocean-900 cursor-pointer transition-colors hover:bg-ocean-800/40 ${
                      alertInfo?.maxSeverity === "critical"
                        ? "border-l-2 border-l-red-500/60 bg-red-500/7"
                        : alertInfo?.maxSeverity === "warning"
                          ? "border-l-2 border-l-amber-500/35 bg-amber-500/3"
                          : ""
                    }`}
                  >
                    <td className="py-2.5 pr-3">
                      <span style={{ color }} title={TYPE_LABEL[type]}>{TYPE_ICON[type] ?? "?"}</span>
                    </td>
                    <td className="py-2.5 pr-3">
                      <div className="font-medium text-ocean-200">{formatName(p)}</div>
                      <div className="text-ocean-400 font-mono">{formatId(p)}</div>
                    </td>
                    <td className="py-2.5 pr-3 font-mono text-ocean-400">
                      {p.lat != null && p.lon != null
                        ? `${p.lat.toFixed(3)}°N ${p.lon.toFixed(3)}°E`
                        : "—"}
                    </td>
                    <td className="py-2.5 pr-3 font-mono">
                      {p.sog != null ? `${p.sog.toFixed(1)} kt` : "—"}
                    </td>
                    <td className="py-2.5 pr-3 font-mono">
                      {p.cog != null ? `${p.cog.toFixed(0)}°` : "—"}
                    </td>
                    <td className="py-2.5 pr-3">
                      <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] ${navBadge}`}>
                        {NAV_STATUS_KR[p.nav_status ?? ""] ?? p.nav_status ?? "—"}
                        {isDistress && " ⚠"}
                      </span>
                    </td>
                    <td className="py-2.5 pr-3 text-ocean-500">{p.flag ?? "—"}</td>
                    <td className="py-2.5 pr-3 text-ocean-400 font-mono">
                      {p.last_seen
                        ? formatDistanceToNow(new Date(p.last_seen), { addSuffix: true, locale: ko })
                        : "—"}
                    </td>
                    <td className="py-2.5">
                      {alertInfo ? (
                        <StatusBadge tone={alertInfo.maxSeverity === "critical" ? "critical" : "warning"} className="font-bold">
                          {alertInfo.count}
                        </StatusBadge>
                      ) : (
                        <span className="text-ocean-500">—</span>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
        </DataTable>
    );
  }

  function CardView() {
    return (
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
        {sorted.length === 0 ? (
          <div className="col-span-full py-8 text-center text-ocean-500 text-sm">
            수신된 플랫폼 없음 — 시뮬레이터를 시작하세요
          </div>
        ) : (
          sorted.map((p) => {
            const type = p.platform_type ?? "vessel";
            const color = TYPE_COLOR[type] ?? "#2e8dd4";
            const alertInfo = alertsByPlatform[p.platform_id];
            const navBadge = NAV_STATUS_BADGE[p.nav_status ?? ""] ?? "text-ocean-500 bg-ocean-800/50 border-ocean-700/50";

            return (
              <div
                key={p.platform_id}
                onClick={() => router.push(`/platforms/${encodeURIComponent(p.platform_id)}`)}
                className={`rounded-lg border p-3 cursor-pointer transition-all hover:bg-ocean-800/50 ${
                  alertInfo?.maxSeverity === "critical"
                    ? "border-red-500/50 bg-red-500/10"
                    : alertInfo?.maxSeverity === "warning"
                      ? "border-amber-500/30 bg-amber-500/5"
                      : "border-ocean-700/40 bg-ocean-900/30"
                }`}
              >
                {/* 타입 아이콘 + 이름 */}
                <div className="flex items-start justify-between mb-2">
                  <div>
                    <div className="text-2xl" style={{ color }} title={TYPE_LABEL[type]}>
                      {TYPE_ICON[type] ?? "?"}
                    </div>
                    <div className="mt-1 font-semibold text-sm text-ocean-100 truncate">
                      {formatName(p)}
                    </div>
                    <div className="text-xs text-ocean-500 font-mono truncate">
                      {formatId(p)}
                    </div>
                  </div>

                  {/* 경보 뱃지 */}
                  {alertInfo && (
                    <StatusBadge tone={alertInfo.maxSeverity === "critical" ? "critical" : "warning"}>
                      {alertInfo.count}
                    </StatusBadge>
                  )}
                </div>

                {/* 위치 */}
                {p.lat != null && p.lon != null && (
                  <div className="text-[11px] text-ocean-400 font-mono mb-2">
                    {p.lat.toFixed(2)}° / {p.lon.toFixed(2)}°
                  </div>
                )}

                {/* 속도 + 침로 */}
                <div className="flex gap-3 text-xs mb-2">
                  {p.sog != null && (
                    <div>
                      <div className="text-ocean-600">속도</div>
                      <div className="font-mono text-ocean-200">{p.sog.toFixed(1)} kt</div>
                    </div>
                  )}
                  {p.cog != null && (
                    <div>
                      <div className="text-ocean-600">침로</div>
                      <div className="font-mono text-ocean-200">{p.cog.toFixed(0)}°</div>
                    </div>
                  )}
                </div>

                {/* 항법 상태 */}
                {p.nav_status && (
                  <div className="text-[10px] mb-2">
                    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 ${navBadge}`}>
                      {NAV_STATUS_KR[p.nav_status] ?? p.nav_status}
                    </span>
                  </div>
                )}

                {/* 국적 + 최근 수신 */}
                <div className="border-t border-ocean-700/30 pt-2 text-[10px] space-y-0.5">
                  {p.flag && (
                    <div className="flex justify-between">
                      <span className="text-ocean-600">국적</span>
                      <span className="text-ocean-300">{p.flag}</span>
                    </div>
                  )}
                  {p.last_seen && (
                    <div className="flex justify-between">
                      <span className="text-ocean-600">수신</span>
                      <span className="text-ocean-400 font-mono">
                        {formatDistanceToNow(new Date(p.last_seen), { addSuffix: false, locale: ko })}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    );
  }
}
