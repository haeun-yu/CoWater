"use client";

import { usePlatformStore } from "@/stores/platformStore";
import { useAlertStore } from "@/stores/alertStore";
import type { PlatformState } from "@/types";

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

  const selected = selectedId ? platforms[selectedId] : null;

  const activePlatformIds = new Set(
    alerts.filter((a) => a.status === "new").flatMap((a) => a.platform_ids)
  );

  return (
    <div className="flex flex-col flex-1 overflow-hidden border-b border-ocean-800">
      <div className="px-3 py-2 border-b border-ocean-800 flex-shrink-0 flex items-center justify-between">
        <span className="text-xs font-bold text-ocean-200 tracking-wider">
          플랫폼
          <span className="ml-2 text-ocean-500 font-normal">
            {Object.keys(platforms).length}척
          </span>
        </span>
        {selected && (
          <button
            onClick={() => select(null)}
            className="text-xs text-ocean-500 hover:text-ocean-300 transition-colors"
          >
            ✕ 닫기
          </button>
        )}
      </div>

      {selected ? (
        <PlatformDetail platform={selected} alerts={alerts.filter(
          (a) => a.platform_ids.includes(selected.platform_id) && a.status === "new"
        )} />
      ) : (
        <PlatformList
          platforms={Object.values(platforms)}
          onSelect={select}
          activePlatformIds={activePlatformIds}
        />
      )}
    </div>
  );
}

function PlatformList({
  platforms,
  onSelect,
  activePlatformIds,
}: {
  platforms: PlatformState[];
  onSelect: (id: string) => void;
  activePlatformIds: Set<string>;
}) {
  const sorted = [...platforms].sort((a, b) => {
    // 경보 중인 플랫폼 우선
    const aAlert = activePlatformIds.has(a.platform_id) ? 0 : 1;
    const bAlert = activePlatformIds.has(b.platform_id) ? 0 : 1;
    return aAlert - bAlert;
  });

  return (
    <div className="flex-1 overflow-y-auto">
      {sorted.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-24 text-ocean-600 text-xs gap-1">
          <span>수신 대기 중...</span>
          <span className="text-ocean-700">시뮬레이터 또는 실제 데이터 필요</span>
        </div>
      ) : (
        sorted.map((p) => {
          const hasAlert = activePlatformIds.has(p.platform_id);
          const color = TYPE_COLOR[p.platform_type ?? "vessel"] ?? "#ffffff";
          const icon = TYPE_ICON[p.platform_type ?? "vessel"] ?? "?";
          return (
            <button
              key={p.platform_id}
              onClick={() => { onSelect(p.platform_id); }}
              className={`w-full px-3 py-2 text-left border-b border-ocean-900 hover:bg-ocean-800/60 transition-colors flex items-center gap-2 ${
                hasAlert ? "bg-red-500/5 border-l-2 border-l-red-500/60" : ""
              }`}
            >
              <span style={{ color }} className="text-sm flex-shrink-0">{icon}</span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-ocean-200 truncate font-medium">
                    {formatDisplayName(p)}
                  </span>
                  {hasAlert && (
                    <span className="w-1.5 h-1.5 rounded-full bg-red-400 flex-shrink-0 animate-pulse" />
                  )}
                </div>
                <div className="text-xs text-ocean-600 font-mono flex gap-2">
                  <span>{p.sog != null ? `${p.sog.toFixed(1)}kt` : "--"}</span>
                  <span>{p.cog != null ? `${p.cog.toFixed(0)}°` : ""}</span>
                  {p.nav_status && p.nav_status !== "underway_engine" && (
                    <span className={NAV_STATUS_COLOR[p.nav_status] ?? "text-ocean-500"}>
                      {NAV_STATUS_KR[p.nav_status] ?? p.nav_status}
                    </span>
                  )}
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
      {/* 헤더 */}
      <div className="p-3 border-b border-ocean-900">
        <div className="flex items-center gap-2 mb-1">
          <span style={{ color }} className="text-lg">{TYPE_ICON[type] ?? "?"}</span>
          <div>
            <div className="text-sm font-bold text-ocean-100">
              {formatDisplayName(platform)}
            </div>
            {/* name이 있고 ID와 다를 때만 MMSI를 부제로 표시 */}
            {platform.name && platform.name !== platform.platform_id && (
              <div className="text-xs text-ocean-500 font-mono">{formatId(platform)}</div>
            )}
          </div>
          <span
            className="ml-auto text-xs px-1.5 py-0.5 rounded"
            style={{ color, background: `${color}22`, border: `1px solid ${color}44` }}
          >
            {TYPE_LABEL[type] ?? type}
          </span>
        </div>
      </div>

      {/* 실시간 운항 정보 */}
      <div className="p-3 border-b border-ocean-900">
        <div className="text-xs text-ocean-500 mb-2 tracking-wider">운항 정보</div>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs font-mono">
          <InfoCell label="속도" value={platform.sog != null ? `${platform.sog.toFixed(1)} kt` : "—"} />
          <InfoCell label="침로" value={platform.cog != null ? `${platform.cog.toFixed(1)}°` : "—"} />
          <InfoCell label="선수" value={platform.heading != null ? `${platform.heading.toFixed(1)}°` : "—"} />
          <InfoCell label="위도" value={platform.lat?.toFixed(5) ?? "—"} />
          <InfoCell label="경도" value={platform.lon?.toFixed(5) ?? "—"} />
          <div className={`col-span-2 ${navStatusColor}`}>
            <span className="text-ocean-500">상태 </span>
            {NAV_STATUS_KR[platform.nav_status ?? ""] ?? platform.nav_status ?? "—"}
          </div>
        </div>
      </div>

      {/* 메타 정보 */}
      <div className="p-3 border-b border-ocean-900">
        <div className="text-xs text-ocean-500 mb-2 tracking-wider">메타</div>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs font-mono">
          <InfoCell label="국적" value={platform.flag ?? "—"} />
          <InfoCell label="프로토콜" value={platform.source_protocol ?? "—"} />
          {platform.capabilities?.length > 0 && (
            <div className="col-span-2 text-ocean-400">
              <span className="text-ocean-500">장비 </span>
              {platform.capabilities.join(", ")}
            </div>
          )}
        </div>
        {platform.last_seen && (
          <div className="text-xs text-ocean-600 mt-2">
            최근 수신 {new Date(platform.last_seen).toLocaleTimeString("ko-KR")}
          </div>
        )}
      </div>

      {/* 관련 경보 */}
      {alerts.length > 0 && (
        <div className="p-3">
          <div className="text-xs text-ocean-500 mb-2 tracking-wider">활성 경보</div>
          <div className="space-y-2">
            {alerts.map((a) => (
              <div
                key={a.alert_id}
                className={`text-xs rounded p-2 border ${
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
    <div>
      <span className="text-ocean-500">{label} </span>
      <span className="text-ocean-200">{value}</span>
    </div>
  );
}
