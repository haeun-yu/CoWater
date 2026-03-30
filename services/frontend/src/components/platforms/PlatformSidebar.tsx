"use client";

import { usePlatformStore } from "@/stores/platformStore";
import type { PlatformState } from "@/types";

const TYPE_ICON: Record<string, string> = {
  vessel: "▲",
  usv:    "◆",
  rov:    "●",
  auv:    "◈",
  drone:  "✦",
  buoy:   "◉",
};

const NAV_STATUS_KR: Record<string, string> = {
  underway_engine:           "항행 중 (기관)",
  at_anchor:                 "정박",
  not_under_command:         "조종 불능",
  restricted_maneuverability:"조종 제한",
  moored:                    "계류",
  aground:                   "좌초",
  engaged_fishing:           "어로 작업",
  underway_sailing:          "항행 중 (범선)",
  undefined:                 "미상",
};

export default function PlatformSidebar() {
  const platforms = usePlatformStore((s) => s.platforms);
  const selectedId = usePlatformStore((s) => s.selectedId);
  const select = usePlatformStore((s) => s.select);

  const selected = selectedId ? platforms[selectedId] : null;

  return (
    <div className="flex flex-col flex-1 overflow-hidden border-b border-ocean-800">
      {/* 헤더 */}
      <div className="px-3 py-2 border-b border-ocean-800 flex-shrink-0 flex items-center justify-between">
        <span className="text-xs font-bold text-ocean-200 tracking-wider">플랫폼</span>
        {selected && (
          <button
            onClick={() => select(null)}
            className="text-xs text-ocean-500 hover:text-ocean-300"
          >
            닫기
          </button>
        )}
      </div>

      {selected ? (
        <PlatformDetail platform={selected} />
      ) : (
        <PlatformList platforms={Object.values(platforms)} onSelect={select} />
      )}
    </div>
  );
}

function PlatformList({
  platforms,
  onSelect,
}: {
  platforms: PlatformState[];
  onSelect: (id: string) => void;
}) {
  return (
    <div className="flex-1 overflow-y-auto">
      {platforms.length === 0 ? (
        <div className="flex items-center justify-center h-24 text-ocean-600 text-xs">
          수신 대기 중...
        </div>
      ) : (
        platforms.map((p) => (
          <button
            key={p.platform_id}
            onClick={() => onSelect(p.platform_id)}
            className="w-full px-3 py-2 text-left border-b border-ocean-900 hover:bg-ocean-800 transition-colors flex items-center gap-2"
          >
            <span className="text-ocean-400 text-sm">{TYPE_ICON[p.platform_type] ?? "?"}</span>
            <div className="flex-1 min-w-0">
              <div className="text-xs text-ocean-200 truncate">{p.name || p.platform_id}</div>
              <div className="text-xs text-ocean-600 font-mono">
                {p.sog != null ? `${p.sog.toFixed(1)}kts` : "--"}{" "}
                {p.cog != null ? `${p.cog.toFixed(0)}°` : ""}
              </div>
            </div>
          </button>
        ))
      )}
    </div>
  );
}

function PlatformDetail({ platform }: { platform: PlatformState }) {
  const rows: [string, string][] = [
    ["ID", platform.platform_id],
    ["유형", `${TYPE_ICON[platform.platform_type]} ${platform.platform_type.toUpperCase()}`],
    ["국적", platform.flag ?? "—"],
    ["프로토콜", platform.source_protocol],
    ["위도", platform.lat?.toFixed(5) ?? "—"],
    ["경도", platform.lon?.toFixed(5) ?? "—"],
    ["SOG", platform.sog != null ? `${platform.sog.toFixed(1)} kts` : "—"],
    ["COG", platform.cog != null ? `${platform.cog.toFixed(1)}°` : "—"],
    ["침로", platform.heading != null ? `${platform.heading.toFixed(1)}°` : "—"],
    ["상태", platform.nav_status ? (NAV_STATUS_KR[platform.nav_status] ?? platform.nav_status) : "—"],
    ["최근 수신", platform.last_seen ? new Date(platform.last_seen).toLocaleTimeString("ko-KR") : "—"],
  ];

  if (platform.capabilities?.length > 0) {
    rows.push(["장비", platform.capabilities.join(", ")]);
  }

  return (
    <div className="flex-1 overflow-y-auto p-3">
      <div className="text-sm font-bold text-ocean-200 mb-3 truncate">{platform.name || platform.platform_id}</div>
      <table className="w-full text-xs">
        <tbody>
          {rows.map(([label, value]) => (
            <tr key={label} className="border-b border-ocean-900">
              <td className="py-1.5 text-ocean-500 w-20 font-mono">{label}</td>
              <td className="py-1.5 text-ocean-200 font-mono break-all">{value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
