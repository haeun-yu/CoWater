"use client";

import { useMemo, useState } from "react";
import { usePlatformStore } from "@/stores/platformStore";
import { useAlertStore } from "@/stores/alertStore";
import { useSystemStore } from "@/stores/systemStore";
import { countPlatformsByFreshness, formatLastSeen, getPlatformFreshness } from "@/lib/platformStatus";
import type { PlatformState } from "@/types";
import StatusBadge from "@/components/ui/StatusBadge";
import FilterChip from "@/components/ui/FilterChip";
import EmptyState from "@/components/ui/EmptyState";

const TYPE_ICON: Record<string, string> = {
  vessel: "▲",
  usv:    "◆",
  rov:    "●",
  auv:    "◈",
  drone:  "✦",
  buoy:   "◉",
};

const TYPE_LABEL: Record<string, string> = {
  vessel: "선박",
  usv:    "USV",
  rov:    "ROV",
  auv:    "AUV",
  drone:  "드론",
  buoy:   "부이",
};

const TYPE_COLOR: Record<string, string> = {
  vessel: "#2e8dd4",
  usv:    "#22d3ee",
  rov:    "#a78bfa",
  auv:    "#818cf8",
  drone:  "#34d399",
  buoy:   "#fbbf24",
};

const NAV_STATUS_KR: Record<string, string> = {
  underway_engine:            "항행 중 (기관)",
  at_anchor:                  "정박",
  not_under_command:          "조종 불능 ⚠",
  restricted_maneuverability: "조종 제한",
  moored:                     "계류",
  aground:                    "좌초 ⚠",
  engaged_fishing:            "어로 작업",
  underway_sailing:           "항행 중 (범선)",
  undefined:                  "미상",
};

const NAV_STATUS_COLOR: Record<string, string> = {
  not_under_command: "text-red-400",
  aground:           "text-red-400",
  at_anchor:         "text-yellow-400",
  moored:            "text-yellow-400",
};

function formatId(p: PlatformState): string {
  return p.platform_id.replace(/^MMSI-/, "");
}

function formatDisplayName(p: PlatformState): string {
  if (!p.name || p.name === p.platform_id) return formatId(p);
  return p.name;
}

export default function PlatformSidebar() {
  const platforms = usePlatformStore((s) => s.platforms);
  const selectedId = usePlatformStore((s) => s.selectedId);
  const select = usePlatformStore((s) => s.select);
  const alerts = useAlertStore((s) => s.alerts);
  const platformLoad = useSystemStore((s) => s.initialData.platforms);
  const platformList = Object.values(platforms);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | "alert" | "stale">("all");

  const selected = selectedId ? platforms[selectedId] : null;

  const activePlatformIds = useMemo(
    () => new Set(alerts.filter((a) => a.status === "new").flatMap((a) => a.platform_ids)),
    [alerts],
  );
  const freshness = useMemo(() => countPlatformsByFreshness(platformList), [platformList]);
  const filteredCount = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return platformList.filter((platform) => {
      const matchesQuery =
        normalizedQuery.length === 0
        || formatDisplayName(platform).toLowerCase().includes(normalizedQuery)
        || formatId(platform).toLowerCase().includes(normalizedQuery);
      if (!matchesQuery) return false;
      if (filter === "alert") return activePlatformIds.has(platform.platform_id);
      if (filter === "stale") return getPlatformFreshness(platform.last_seen) !== "live";
      return true;
    }).length;
  }, [activePlatformIds, filter, platformList, query]);

  return (
    <div className="flex flex-1 flex-col overflow-hidden border-b border-ocean-800/80">
      <div className="flex-shrink-0 border-b border-ocean-800/80 px-4 py-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-ocean-400">탐색 패널</div>
            <div className="mt-1 text-sm font-semibold text-ocean-100">플랫폼</div>
            <div className="mt-1 text-xs text-ocean-500">경보 및 수신 상태 기준으로 빠르게 대상을 좁혀볼 수 있습니다.</div>
          </div>
          {selected && (
            <button
              onClick={() => select(null)}
              className="rounded-full border border-ocean-700 px-2.5 py-1 text-[11px] text-ocean-400 transition-colors hover:border-ocean-500 hover:text-ocean-200"
            >
              선택 해제
            </button>
          )}
        </div>

        <div className="mt-4 grid grid-cols-3 gap-2 text-[11px]">
          <StatusPill label="정상" value={freshness.live} tone="neutral" />
          <StatusPill label="지연" value={freshness.stale} tone="warning" />
          <StatusPill label="유실" value={freshness.lost} tone="critical" />
        </div>

        {!selected && (
          <>
            <div className="mt-4">
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="이름 또는 MMSI 검색"
                className="w-full rounded-xl border border-ocean-700/80 bg-ocean-900/60 px-3 py-2 text-sm text-ocean-100 outline-none placeholder:text-ocean-500 focus:border-ocean-500"
              />
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {([
                ["all", `전체 ${platformList.length}`],
                ["alert", `경보 ${activePlatformIds.size}`],
                ["stale", `지연/유실 ${freshness.stale + freshness.lost}`],
              ] as const).map(([value, label]) => (
                <FilterChip
                  key={value}
                  onClick={() => setFilter(value)}
                  active={filter === value}
                >
                  {label}
                </FilterChip>
              ))}
            </div>
            <div className="mt-3 text-[11px] text-ocean-500">표시 중 {filteredCount}척</div>
          </>
        )}
      </div>

      {selected ? (
        <PlatformDetail platform={selected} alerts={alerts.filter(
          (a) => a.platform_ids.includes(selected.platform_id) && a.status === "new"
        )} />
      ) : (
        <PlatformList
          platforms={platformList}
          onSelect={select}
          activePlatformIds={activePlatformIds}
          loadStatus={platformLoad.status}
          query={query}
          filter={filter}
        />
      )}
    </div>
  );
}

function PlatformList({
  platforms,
  onSelect,
  activePlatformIds,
  loadStatus,
  query,
  filter,
}: {
  platforms: PlatformState[];
  onSelect: (id: string) => void;
  activePlatformIds: Set<string>;
  loadStatus: "idle" | "loading" | "ready" | "error";
  query: string;
  filter: "all" | "alert" | "stale";
}) {
  const normalizedQuery = query.trim().toLowerCase();
  const sorted = [...platforms].filter((platform) => {
    const matchesQuery =
      normalizedQuery.length === 0
      || formatDisplayName(platform).toLowerCase().includes(normalizedQuery)
      || formatId(platform).toLowerCase().includes(normalizedQuery);
    if (!matchesQuery) return false;
    if (filter === "alert") return activePlatformIds.has(platform.platform_id);
    if (filter === "stale") return getPlatformFreshness(platform.last_seen) !== "live";
    return true;
  }).sort((a, b) => {
    // 경보 중인 플랫폼 우선
    const aAlert = activePlatformIds.has(a.platform_id) ? 0 : 1;
    const bAlert = activePlatformIds.has(b.platform_id) ? 0 : 1;
    if (aAlert !== bAlert) return aAlert - bAlert;

    const freshnessOrder = { live: 0, stale: 1, lost: 2 };
    return freshnessOrder[getPlatformFreshness(a.last_seen)] - freshnessOrder[getPlatformFreshness(b.last_seen)];
  });

  return (
    <div className="flex-1 overflow-y-auto">
      {sorted.length === 0 ? (
        <EmptyState
          title={query.trim() || filter !== "all"
            ? "조건에 맞는 플랫폼이 없습니다"
            : loadStatus === "loading"
            ? "플랫폼 로딩 중..."
            : loadStatus === "error"
              ? "플랫폼 로드 실패"
              : "수신 대기 중..."}
          description={query.trim() || filter !== "all"
            ? "검색어 또는 필터를 조정해보세요"
            : loadStatus === "error"
              ? "실시간 스트림으로 회복될 수 있습니다"
              : "시뮬레이터 또는 실제 데이터 필요"}
        />
      ) : (
        sorted.map((p) => {
          const hasAlert = activePlatformIds.has(p.platform_id);
          const freshness = getPlatformFreshness(p.last_seen);
          const color = TYPE_COLOR[p.platform_type ?? "vessel"] ?? "#ffffff";
          const icon = TYPE_ICON[p.platform_type ?? "vessel"] ?? "?";
          return (
            <button
              key={p.platform_id}
              onClick={() => { onSelect(p.platform_id); }}
              title={`${formatDisplayName(p)} 선택`}
              aria-label={`${formatDisplayName(p)} 플랫폼 선택`}
              className={`w-full border-b border-ocean-900/80 px-4 py-3 text-left transition-colors hover:bg-ocean-800/50 ${
                hasAlert ? "bg-red-500/6" : ""
              }`}
            >
              <div className="flex items-start gap-3">
                <div className={`mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-xl border border-ocean-700/70 bg-ocean-900/60 text-sm ${hasAlert ? "shadow-[0_0_0_1px_rgba(239,68,68,0.25)]" : ""}`} style={{ color }}>
                  {icon}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <span className="truncate text-sm font-medium text-ocean-100">
                      {formatDisplayName(p)}
                    </span>
                    {hasAlert && (
                      <StatusBadge tone="critical">경보</StatusBadge>
                    )}
                    {freshness !== "live" && (
                      <StatusBadge tone={freshness === "stale" ? "warning" : "critical"}>
                        {freshness === "stale" ? "지연" : "유실"}
                      </StatusBadge>
                    )}
                  </div>
                  <div className="mt-1 text-[11px] font-mono text-ocean-500">{formatId(p)}</div>
                  <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] font-mono text-ocean-300">
                    <span>{p.sog != null ? `${p.sog.toFixed(1)}kt` : "--"}</span>
                    <span>{p.cog != null ? `${p.cog.toFixed(0)}°` : "—"}</span>
                    <span className={NAV_STATUS_COLOR[p.nav_status ?? ""] ?? "text-ocean-500"}>
                      {NAV_STATUS_KR[p.nav_status ?? ""] ?? p.nav_status ?? "상태 미상"}
                    </span>
                  </div>
                </div>
                <div className="text-right text-[11px] text-ocean-500">
                  {formatLastSeen(p.last_seen)}
                </div>
              </div>
            </button>
          );
        })
      )}
    </div>
  );
}

function PlatformDetail({
  platform,
  alerts,
}: {
  platform: PlatformState;
  alerts: import("@/types").Alert[];
}) {
  const type = platform.platform_type ?? "vessel";
  const color = TYPE_COLOR[type] ?? "#ffffff";
  const navStatusColor = NAV_STATUS_COLOR[platform.nav_status ?? ""] ?? "text-ocean-200";

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="border-b border-ocean-900/80 p-4">
        <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-ocean-400">선택된 대상</div>
        <div className="mt-3 flex items-center gap-3">
          <span style={{ color }} className="flex h-10 w-10 items-center justify-center rounded-xl border border-ocean-700/70 bg-ocean-900/60 text-lg">{TYPE_ICON[type] ?? "?"}</span>
          <div>
            <div className="text-base font-semibold text-ocean-100">
              {formatDisplayName(platform)}
            </div>
            {platform.name && platform.name !== platform.platform_id && (
              <div className="text-xs text-ocean-500 font-mono">{formatId(platform)}</div>
            )}
          </div>
          <span
            className="ml-auto rounded-full px-2.5 py-1 text-[11px]"
            style={{ color, background: `${color}22`, border: `1px solid ${color}44` }}
          >
            {TYPE_LABEL[type] ?? type}
          </span>
        </div>
      </div>

      <div className="border-b border-ocean-900/80 p-4">
        <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.28em] text-ocean-400">운항 정보</div>
        <div className="grid grid-cols-2 gap-2 text-xs font-mono">
          <InfoCell label="속도" value={platform.sog != null ? `${platform.sog.toFixed(1)} kt` : "—"} />
          <InfoCell label="침로" value={platform.cog != null ? `${platform.cog.toFixed(1)}°` : "—"} />
          <InfoCell label="선수" value={platform.heading != null ? `${platform.heading.toFixed(1)}°` : "—"} />
          <InfoCell label="위도" value={platform.lat?.toFixed(5) ?? "—"} />
          <InfoCell label="경도" value={platform.lon?.toFixed(5) ?? "—"} />
          <div className={`col-span-2 rounded-xl border border-ocean-800/70 bg-ocean-900/55 px-3 py-2 ${navStatusColor}`}>
            <span className="text-ocean-500">상태 </span>
            {NAV_STATUS_KR[platform.nav_status ?? ""] ?? platform.nav_status ?? "—"}
          </div>
        </div>
      </div>

      <div className="border-b border-ocean-900/80 p-4">
        <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.28em] text-ocean-400">메타</div>
        <div className="grid grid-cols-2 gap-2 text-xs font-mono">
          <InfoCell label="국적" value={platform.flag ?? "—"} />
          <InfoCell label="프로토콜" value={platform.source_protocol ?? "—"} />
          {platform.capabilities?.length > 0 && (
            <div className="col-span-2 rounded-xl border border-ocean-800/70 bg-ocean-900/55 px-3 py-2 text-ocean-400">
              <span className="text-ocean-500">장비 </span>
              {platform.capabilities.join(", ")}
            </div>
          )}
        </div>
        {platform.last_seen && (
          <div className="text-xs text-ocean-400 mt-2">
            최근 수신 {new Date(platform.last_seen).toLocaleTimeString("ko-KR")} · {formatLastSeen(platform.last_seen)}
          </div>
        )}
      </div>

      {alerts.length > 0 && (
        <div className="p-4">
          <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.28em] text-ocean-400">활성 경보</div>
          <div className="space-y-2">
            {alerts.map((a) => (
              <div
                key={a.alert_id}
                className={`rounded-xl border p-3 text-xs ${
                  a.severity === "critical"
                    ? "bg-red-500/10 border-red-500/30 text-red-300"
                    : "bg-yellow-500/10 border-yellow-500/30 text-yellow-300"
                }`}
              >
                <div className="font-medium">{a.message}</div>
                {a.recommendation && (
                  <div className="text-ocean-400 mt-1 text-xs">{a.recommendation}</div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function InfoCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-ocean-800/70 bg-ocean-900/55 px-3 py-2">
      <div className="text-[10px] uppercase tracking-[0.16em] text-ocean-500">{label}</div>
      <div className="mt-1 text-sm text-ocean-100">{value}</div>
    </div>
  );
}

function StatusPill({ label, value, tone }: { label: string; value: number; tone: "neutral" | "warning" | "critical" }) {
  return (
    <div className="rounded-xl border border-ocean-800/70 bg-ocean-900/55 px-3 py-2">
      <div className="text-[10px] uppercase tracking-[0.16em] opacity-80">{label}</div>
      <div className="mt-1 flex items-center justify-between gap-2">
        <div className="font-mono text-sm text-ocean-100">{value}</div>
        <StatusBadge tone={tone === "critical" ? "critical" : tone === "warning" ? "warning" : "neutral"}>{label}</StatusBadge>
      </div>
    </div>
  );
}
