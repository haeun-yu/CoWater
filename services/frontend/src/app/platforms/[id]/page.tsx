"use client";

import { use } from "react";
import { useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import { usePlatformStore } from "@/stores/platformStore";
import { useAlertStore } from "@/stores/alertStore";
import type { Alert, AlertSeverity } from "@/types";
import { formatDistanceToNow, format } from "date-fns";
import { ko } from "date-fns/locale";

const MaritimeMap = dynamic(() => import("@/components/map/MaritimeMap"), {
  ssr: false,
  loading: () => (
    <div className="w-full h-full flex items-center justify-center bg-ocean-950 text-ocean-400 text-sm">
      해도 로딩 중...
    </div>
  ),
});

const TYPE_ICON: Record<string, string> = {
  vessel: "▲", usv: "◆", rov: "●", auv: "◈", drone: "✦", buoy: "◉",
};
const TYPE_COLOR: Record<string, string> = {
  vessel: "#2e8dd4", usv: "#22d3ee", rov: "#a78bfa",
  auv: "#818cf8", drone: "#34d399", buoy: "#fbbf24",
};
const TYPE_LABEL: Record<string, string> = {
  vessel: "선박", usv: "USV", rov: "ROV", auv: "AUV", drone: "드론", buoy: "부이",
};
const NAV_STATUS_KR: Record<string, string> = {
  underway_engine: "항행 중", at_anchor: "정박",
  not_under_command: "조종 불능 ⚠", restricted_maneuverability: "조종 제한",
  moored: "계류", aground: "좌초 ⚠", engaged_fishing: "어로 작업",
  underway_sailing: "항행 중(범선)",
};
const SEVERITY_STYLE: Record<AlertSeverity, { border: string; bg: string; text: string; badge: string }> = {
  critical: { border: "border-red-500/40",    bg: "bg-red-500/8",    text: "text-red-400",    badge: "bg-red-500/20 text-red-300" },
  warning:  { border: "border-yellow-500/40", bg: "bg-yellow-500/8", text: "text-yellow-400", badge: "bg-yellow-500/20 text-yellow-300" },
  info:     { border: "border-blue-500/40",   bg: "bg-blue-500/8",   text: "text-blue-400",   badge: "bg-blue-500/20 text-blue-300" },
};
const ALERT_TYPE_KR: Record<string, string> = {
  cpa: "충돌 위험", zone_intrusion: "구역 침입", anomaly: "이상 행동",
  ais_off: "AIS 소실", distress: "조난", compliance: "상황 보고", traffic: "교통 혼잡",
};

function formatId(id: string) { return id.replace(/^MMSI-/, ""); }

export default function PlatformDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const platformId = decodeURIComponent(id);

  const platforms = usePlatformStore((s) => s.platforms);
  const select = usePlatformStore((s) => s.select);
  const alerts = useAlertStore((s) => s.alerts);
  const acknowledge = useAlertStore((s) => s.acknowledge);

  const p = platforms[platformId];
  const allAlerts = alerts.filter((a) => a.platform_ids.includes(platformId));
  const activeAlerts = allAlerts.filter((a) => a.status === "new");
  const pastAlerts = allAlerts.filter((a) => a.status !== "new");

  // 주변 선박 (5nm 이내 — 간단히 좌표 차이로 근사)
  const nearbyPlatforms = p ? Object.values(platforms).filter((other) => {
    if (other.platform_id === platformId) return false;
    if (other.lat == null || other.lon == null || p.lat == null || p.lon == null) return false;
    const dlat = Math.abs(other.lat - p.lat);
    const dlon = Math.abs(other.lon - p.lon);
    return dlat < 0.08 && dlon < 0.08; // ~5nm 근사
  }).slice(0, 8) : [];

  // 지도에서 이 선박 선택
  if (p) {
    setTimeout(() => select(platformId), 100);
  }

  if (!p) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-4 text-ocean-500">
        <div className="text-4xl opacity-20">▲</div>
        <div className="text-sm">플랫폼 데이터 없음</div>
        <div className="text-xs text-ocean-400">{platformId}</div>
        <button onClick={() => router.back()} className="text-xs px-3 py-1.5 bg-ocean-800 rounded hover:bg-ocean-700 text-ocean-300 transition-colors">
          ← 목록으로
        </button>
      </div>
    );
  }

  const type = p.platform_type ?? "vessel";
  const color = TYPE_COLOR[type] ?? "#2e8dd4";
  const isDistress = p.nav_status === "not_under_command" || p.nav_status === "aground";

  return (
    <div className="h-full flex overflow-hidden">
      {/* 좌측: 선박 상세 정보 */}
      <div className="w-80 flex-shrink-0 border-r border-ocean-800 flex flex-col overflow-hidden">
        {/* 선박 헤더 */}
        <div className="flex-shrink-0 px-4 py-3 border-b border-ocean-800">
          <button
            onClick={() => router.push("/platforms")}
            className="text-xs text-ocean-500 hover:text-ocean-300 mb-2 transition-colors"
          >
            ← 플랫폼 목록
          </button>
          <div className="flex items-center gap-3">
            <span style={{ color }} className="text-2xl">{TYPE_ICON[type] ?? "?"}</span>
            <div className="flex-1 min-w-0">
              <div className="font-bold text-ocean-100 text-sm truncate">{p.name && p.name !== p.platform_id ? p.name : formatId(p.platform_id)}</div>
              <div className="text-xs text-ocean-500 font-mono">{formatId(p.platform_id)}</div>
            </div>
            <span
              className="text-xs px-2 py-0.5 rounded border flex-shrink-0"
              style={{ color, background: `${color}18`, borderColor: `${color}44` }}
            >
              {TYPE_LABEL[type]}
            </span>
          </div>
          {isDistress && (
            <div className="mt-2 px-2.5 py-1.5 bg-red-500/15 border border-red-500/40 rounded text-xs text-red-400 font-bold animate-pulse">
              ⚠ 조난 상황 — 즉각 대응 필요
            </div>
          )}
        </div>

        <div className="flex-1 overflow-y-auto">
          {/* 운항 정보 */}
          <section className="px-4 py-3 border-b border-ocean-900">
            <div className="text-xs font-medium text-ocean-500 mb-2 tracking-wider uppercase">운항 정보</div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
              <InfoRow label="속도(SOG)" value={p.sog != null ? `${p.sog.toFixed(1)} kt` : "—"} />
              <InfoRow label="침로(COG)" value={p.cog != null ? `${p.cog.toFixed(0)}°` : "—"} />
              <InfoRow label="선수" value={p.heading != null ? `${p.heading.toFixed(0)}°` : "—"} />
              <InfoRow label="위도" value={p.lat?.toFixed(5) ?? "—"} mono />
              <InfoRow label="경도" value={p.lon?.toFixed(5) ?? "—"} mono />
              <InfoRow label="국적" value={p.flag ?? "—"} />
            </div>
            <div className={`mt-2 text-xs font-medium ${isDistress ? "text-red-400" : "text-ocean-300"}`}>
              <span className="text-ocean-500 font-normal">상태 </span>
              {NAV_STATUS_KR[p.nav_status ?? ""] ?? p.nav_status ?? "미상"}
            </div>
            {p.last_seen && (
              <div className="text-xs text-ocean-400 mt-1">
                최근 수신 {formatDistanceToNow(new Date(p.last_seen), { addSuffix: true, locale: ko })}
              </div>
            )}
          </section>

          {/* 활성 경보 */}
          <section className="px-4 py-3 border-b border-ocean-900">
            <div className="flex items-center justify-between mb-2">
              <div className="text-xs font-medium text-ocean-500 tracking-wider uppercase">활성 경보</div>
              {activeAlerts.length > 0 && (
                <span className="text-xs text-red-400 font-bold">{activeAlerts.length}건</span>
              )}
            </div>
            {activeAlerts.length === 0 ? (
              <div className="text-xs text-green-400">정상 ✓</div>
            ) : (
              <div className="space-y-2">
                {activeAlerts.map((a) => (
                  <AlertCard key={a.alert_id} alert={a} onAck={() => acknowledge(a.alert_id)} />
                ))}
              </div>
            )}
          </section>

          {/* 주변 선박 */}
          {nearbyPlatforms.length > 0 && (
            <section className="px-4 py-3 border-b border-ocean-900">
              <div className="text-xs font-medium text-ocean-500 mb-2 tracking-wider uppercase">주변 선박 (~5nm)</div>
              <div className="space-y-1.5">
                {nearbyPlatforms.map((np) => {
                  const ntype = np.platform_type ?? "vessel";
                  const ncolor = TYPE_COLOR[ntype] ?? "#2e8dd4";
                  const nAlerts = alerts.filter((a) => a.status === "new" && a.platform_ids.includes(np.platform_id)).length;
                  return (
                    <button
                      key={np.platform_id}
                      onClick={() => router.push(`/platforms/${encodeURIComponent(np.platform_id)}`)}
                      className="w-full text-left flex items-center gap-2 px-2 py-1.5 rounded hover:bg-ocean-800/50 transition-colors"
                    >
                      <span style={{ color: ncolor }} className="text-sm flex-shrink-0">{TYPE_ICON[ntype]}</span>
                      <div className="flex-1 min-w-0">
                        <div className="text-xs text-ocean-200 truncate">
                          {np.name && np.name !== np.platform_id ? np.name : formatId(np.platform_id)}
                        </div>
                        <div className="text-xs text-ocean-400 font-mono">
                          {np.sog != null ? `${np.sog.toFixed(1)}kt` : "—"}
                        </div>
                      </div>
                      {nAlerts > 0 && (
                        <span className="text-xs text-red-400 font-bold">{nAlerts}</span>
                      )}
                    </button>
                  );
                })}
              </div>
            </section>
          )}

          {/* 과거 경보 이력 */}
          {pastAlerts.length > 0 && (
            <section className="px-4 py-3">
              <div className="text-xs font-medium text-ocean-500 mb-2 tracking-wider uppercase">
                경보 이력 ({pastAlerts.length}건)
              </div>
              <div className="space-y-1.5">
                {pastAlerts.slice(0, 10).map((a) => {
                  const s = SEVERITY_STYLE[a.severity];
                  return (
                    <div key={a.alert_id} className={`text-xs px-2.5 py-1.5 rounded border opacity-60 ${s.border} ${s.bg}`}>
                      <div className={`font-medium ${s.text}`}>{ALERT_TYPE_KR[a.alert_type]}</div>
                      <div className="text-ocean-400 line-clamp-1">{a.message}</div>
                      <div className="text-ocean-400 mt-0.5">
                        {a.status === "acknowledged" ? "확인됨" : "해결됨"} ·{" "}
                        {format(new Date(a.created_at), "MM/dd HH:mm")}
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>
          )}
        </div>
      </div>

      {/* 우측: 지도 관제 뷰 */}
      <div className="flex-1 relative min-w-0">
        <MaritimeMap />
        {/* 선박 이름 오버레이 */}
        <div className="absolute top-3 left-1/2 -translate-x-1/2 pointer-events-none">
          <div className="panel px-3 py-1.5 rounded text-xs flex items-center gap-2">
            <span style={{ color }}>{TYPE_ICON[type]}</span>
            <span className="text-ocean-200 font-medium">
              {p.name && p.name !== p.platform_id ? p.name : formatId(p.platform_id)} 관제
            </span>
            {isDistress && <span className="text-red-400 font-bold animate-pulse">⚠ 조난</span>}
          </div>
        </div>
      </div>
    </div>
  );
}

function InfoRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <span className="text-ocean-500">{label} </span>
      <span className={`text-ocean-200 ${mono ? "font-mono" : ""}`}>{value}</span>
    </div>
  );
}

function AlertCard({ alert, onAck }: { alert: Alert; onAck: () => void }) {
  const s = SEVERITY_STYLE[alert.severity];
  return (
    <div className={`rounded border p-2.5 ${s.border} ${s.bg}`}>
      <div className="flex items-center gap-2 mb-1">
        <span className={`text-xs font-bold ${s.text}`}>{ALERT_TYPE_KR[alert.alert_type]}</span>
        <span className="text-ocean-400 text-xs ml-auto">
          {formatDistanceToNow(new Date(alert.created_at), { addSuffix: true, locale: ko })}
        </span>
      </div>
      <div className="text-xs text-ocean-300 leading-snug">{alert.message}</div>
      {alert.recommendation && (
        <div className="mt-1.5 text-xs text-ocean-400 leading-relaxed line-clamp-3 bg-ocean-900/50 rounded p-1.5">
          {alert.recommendation}
        </div>
      )}
      <button
        onClick={onAck}
        className={`mt-2 text-xs px-2 py-0.5 rounded transition-colors ${s.badge} hover:opacity-80`}
      >
        인지 처리
      </button>
    </div>
  );
}
