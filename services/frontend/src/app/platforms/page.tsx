"use client";

import { useRouter } from "next/navigation";
import { usePlatformStore } from "@/stores/platformStore";
import { useAlertStore } from "@/stores/alertStore";
import type { PlatformState } from "@/types";
import { formatDistanceToNow } from "date-fns";
import { ko } from "date-fns/locale";

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
  const platforms = Object.values(usePlatformStore((s) => s.platforms));
  const alerts = useAlertStore((s) => s.alerts);

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

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* 헤더 */}
      <div className="flex-shrink-0 px-5 py-3 border-b border-ocean-800">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-base font-bold text-ocean-200 tracking-wider">플랫폼 현황</h1>
            <p className="text-xs text-ocean-500 mt-0.5">선박 클릭 시 개별 관제 페이지로 이동</p>
          </div>
          <div className="flex gap-4 text-xs">
            <div className="text-center">
              <div className="text-ocean-200 font-bold text-base">{platforms.length}</div>
              <div className="text-ocean-500">관제 중</div>
            </div>
            <div className="text-center">
              <div className={`font-bold text-base ${totalAlerts > 0 ? "text-red-400" : "text-green-400"}`}>{totalAlerts}</div>
              <div className="text-ocean-500">미확인 경보</div>
            </div>
            <div className="text-center">
              <div className="text-ocean-200 font-bold text-base">
                {platforms.filter((p) => p.nav_status === "underway_engine").length}
              </div>
              <div className="text-ocean-500">항행 중</div>
            </div>
          </div>
        </div>
      </div>

      {/* 테이블 */}
      <div className="flex-1 overflow-auto px-5">
        <table className="w-full text-xs border-collapse">
          <thead className="sticky top-0 bg-ocean-950 z-10">
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
              <tr>
                <td colSpan={9} className="py-16 text-center text-ocean-600">
                  수신된 플랫폼 없음 — 시뮬레이터를 시작하세요
                </td>
              </tr>
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
                      alertInfo?.maxSeverity === "critical" ? "bg-red-500/5" :
                      alertInfo?.maxSeverity === "warning"  ? "bg-yellow-500/3" : ""
                    }`}
                  >
                    <td className="py-2.5 pr-3">
                      <span style={{ color }} title={TYPE_LABEL[type]}>{TYPE_ICON[type] ?? "?"}</span>
                    </td>
                    <td className="py-2.5 pr-3">
                      <div className="font-medium text-ocean-200">{formatName(p)}</div>
                      <div className="text-ocean-600 font-mono">{formatId(p)}</div>
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
                      <span className={`px-1.5 py-0.5 rounded border text-xs ${navBadge}`}>
                        {NAV_STATUS_KR[p.nav_status ?? ""] ?? p.nav_status ?? "—"}
                        {isDistress && " ⚠"}
                      </span>
                    </td>
                    <td className="py-2.5 pr-3 text-ocean-500">{p.flag ?? "—"}</td>
                    <td className="py-2.5 pr-3 text-ocean-600 font-mono">
                      {p.last_seen
                        ? formatDistanceToNow(new Date(p.last_seen), { addSuffix: true, locale: ko })
                        : "—"}
                    </td>
                    <td className="py-2.5">
                      {alertInfo ? (
                        <span className={`px-1.5 py-0.5 rounded font-bold border ${
                          alertInfo.maxSeverity === "critical"
                            ? "bg-red-500/20 text-red-400 border-red-500/30"
                            : "bg-yellow-500/20 text-yellow-400 border-yellow-500/30"
                        }`}>
                          {alertInfo.count}
                        </span>
                      ) : (
                        <span className="text-ocean-700">—</span>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
