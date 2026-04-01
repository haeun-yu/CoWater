"use client";

import { useState } from "react";
import { useAlertStore } from "@/stores/alertStore";
import { usePlatformStore } from "@/stores/platformStore";
import type { Alert, AlertSeverity, AlertStatus } from "@/types";
import { formatDistanceToNow, format, isAfter, subHours } from "date-fns";
import { ko } from "date-fns/locale";

const SEVERITY_LABEL: Record<AlertSeverity, string> = {
  critical: "위험", warning: "주의", info: "정보",
};
const SEVERITY_STYLE: Record<AlertSeverity, { border: string; bg: string; text: string; pill: string }> = {
  critical: { border: "border-red-500/50",    bg: "bg-red-500/8",     text: "text-red-400",    pill: "bg-red-500/20 text-red-300 border-red-500/40" },
  warning:  { border: "border-yellow-500/50", bg: "bg-yellow-500/8",  text: "text-yellow-400", pill: "bg-yellow-500/20 text-yellow-300 border-yellow-500/40" },
  info:     { border: "border-blue-500/40",   bg: "bg-blue-500/6",    text: "text-blue-400",   pill: "bg-blue-500/20 text-blue-300 border-blue-500/40" },
};
const ALERT_TYPE_KR: Record<string, string> = {
  cpa: "충돌 위험", zone_intrusion: "구역 침입", anomaly: "이상 행동",
  ais_off: "AIS 소실", distress: "조난", compliance: "상황 보고", traffic: "교통 혼잡",
};
const STATUS_LABEL: Record<AlertStatus, string> = {
  new: "미확인", acknowledged: "확인됨", resolved: "해결됨",
};

type TimeFilter = "all" | "1h" | "6h" | "24h";

export default function AlertsPage() {
  const alerts = useAlertStore((s) => s.alerts);
  const acknowledge = useAlertStore((s) => s.acknowledge);
  const platforms = usePlatformStore((s) => s.platforms);
  const [severityFilter, setSeverityFilter] = useState<AlertSeverity | "all">("all");
  const [statusFilter, setStatusFilter]     = useState<"new" | "acknowledged" | "all">("all");
  const [timeFilter, setTimeFilter]         = useState<TimeFilter>("all");
  const [expanded, setExpanded]             = useState<string | null>(null);

  // 시간 필터
  const now = new Date();
  const timeFiltered = alerts.filter((a) => {
    if (timeFilter === "all") return true;
    const hours = timeFilter === "1h" ? 1 : timeFilter === "6h" ? 6 : 24;
    return isAfter(new Date(a.created_at), subHours(now, hours));
  });

  const filtered = timeFiltered
    .filter((a) => severityFilter === "all" || a.severity === severityFilter)
    .filter((a) => statusFilter === "all" || a.status === statusFilter);

  // 요약 통계
  const newAlerts       = alerts.filter((a) => a.status === "new");
  const criticalNew     = newAlerts.filter((a) => a.severity === "critical").length;
  const warningNew      = newAlerts.filter((a) => a.severity === "warning").length;
  const infoNew         = newAlerts.filter((a) => a.severity === "info").length;
  const acknowledgedAll = alerts.filter((a) => a.status === "acknowledged").length;

  // 활성(미확인) / 과거(확인+해결) 분리
  const active = filtered.filter((a) => a.status === "new");
  const past   = filtered.filter((a) => a.status !== "new");

  function getPlatformName(id: string) {
    const p = platforms[id];
    if (!p) return id.replace(/^MMSI-/, "");
    return p.name && p.name !== p.platform_id ? p.name : id.replace(/^MMSI-/, "");
  }

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* 상단 요약 바 */}
      <div className="flex-shrink-0 px-5 py-3 border-b border-ocean-800">
        <div className="flex items-center justify-between mb-3">
          <h1 className="text-base font-bold text-ocean-200 tracking-wider">경보 현황</h1>
          <div className="text-xs text-ocean-500">전체 {alerts.length}건</div>
        </div>

        {/* 통계 카드 */}
        <div className="grid grid-cols-5 gap-2 mb-3">
          <StatCard label="미확인 위험" value={criticalNew} color="text-red-400" urgent={criticalNew > 0} />
          <StatCard label="미확인 주의" value={warningNew}  color="text-yellow-400" />
          <StatCard label="미확인 정보" value={infoNew}     color="text-blue-400" />
          <StatCard label="확인 완료"   value={acknowledgedAll} color="text-ocean-400" />
          <StatCard label="전체 미확인" value={newAlerts.length} color="text-ocean-200" />
        </div>

        {/* 필터 */}
        <div className="flex flex-wrap gap-2">
          {/* 심각도 */}
          <div className="flex gap-1">
            {(["all", "critical", "warning", "info"] as const).map((f) => {
              const s = f !== "all" ? SEVERITY_STYLE[f] : null;
              return (
                <button key={f} onClick={() => setSeverityFilter(f)}
                  className={`text-xs px-2.5 py-1 rounded border transition-colors ${
                    severityFilter === f
                      ? f === "all" ? "bg-ocean-700 text-ocean-100 border-ocean-600" : `${s!.pill} border-current`
                      : "text-ocean-600 border-ocean-800 hover:border-ocean-600"
                  }`}>
                  {f === "all" ? "전체" : SEVERITY_LABEL[f]}
                </button>
              );
            })}
          </div>

          {/* 상태 */}
          <div className="flex gap-1">
            {(["all", "new", "acknowledged"] as const).map((f) => (
              <button key={f} onClick={() => setStatusFilter(f)}
                className={`text-xs px-2.5 py-1 rounded border transition-colors ${
                  statusFilter === f
                    ? "bg-ocean-700 text-ocean-100 border-ocean-600"
                    : "text-ocean-600 border-ocean-800 hover:border-ocean-600"
                }`}>
                {f === "all" ? "전체 상태" : STATUS_LABEL[f as AlertStatus]}
              </button>
            ))}
          </div>

          {/* 시간 */}
          <div className="flex gap-1 ml-auto">
            {(["all", "1h", "6h", "24h"] as const).map((f) => (
              <button key={f} onClick={() => setTimeFilter(f)}
                className={`text-xs px-2.5 py-1 rounded border transition-colors ${
                  timeFilter === f
                    ? "bg-ocean-700 text-ocean-100 border-ocean-600"
                    : "text-ocean-600 border-ocean-800 hover:border-ocean-600"
                }`}>
                {f === "all" ? "전체 시간" : `최근 ${f}`}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* 목록 */}
      <div className="flex-1 overflow-auto px-5 py-3 space-y-4">
        {/* ── 활성 경보 ── */}
        {statusFilter !== "acknowledged" && (
          <section>
            <div className="flex items-center gap-2 mb-2">
              <div className="text-xs font-bold text-ocean-300 tracking-wider uppercase">미확인 경보</div>
              {active.length > 0 && (
                <span className="text-xs px-1.5 py-0.5 bg-red-500/20 text-red-400 rounded font-bold">{active.length}</span>
              )}
            </div>
            {active.length === 0 ? (
              <div className="text-xs text-green-400 py-4">미확인 경보 없음 ✓</div>
            ) : (
              <div className="space-y-1.5">
                {active.map((a) => (
                  <AlertRow
                    key={a.alert_id}
                    alert={a}
                    expanded={expanded === a.alert_id}
                    onToggle={() => setExpanded(expanded === a.alert_id ? null : a.alert_id)}
                    onAck={() => acknowledge(a.alert_id)}
                    getPlatformName={getPlatformName}
                    isActive
                  />
                ))}
              </div>
            )}
          </section>
        )}

        {/* ── 과거 경보 ── */}
        {statusFilter !== "new" && past.length > 0 && (
          <section>
            <div className="flex items-center gap-2 mb-2">
              <div className="text-xs font-bold text-ocean-600 tracking-wider uppercase">확인 / 해결된 경보</div>
              <span className="text-xs px-1.5 py-0.5 bg-ocean-800 text-ocean-500 rounded">{past.length}</span>
            </div>
            <div className="space-y-1">
              {past.map((a) => (
                <AlertRow
                  key={a.alert_id}
                  alert={a}
                  expanded={expanded === a.alert_id}
                  onToggle={() => setExpanded(expanded === a.alert_id ? null : a.alert_id)}
                  onAck={() => acknowledge(a.alert_id)}
                  getPlatformName={getPlatformName}
                  isActive={false}
                />
              ))}
            </div>
          </section>
        )}

        {filtered.length === 0 && (
          <div className="flex items-center justify-center h-40 text-ocean-600 text-sm">
            조건에 맞는 경보 없음
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({ label, value, color, urgent }: { label: string; value: number; color: string; urgent?: boolean }) {
  return (
    <div className={`rounded border px-3 py-2 ${urgent ? "border-red-500/40 bg-red-500/5" : "border-ocean-800 bg-ocean-900/40"}`}>
      <div className={`text-lg font-bold font-mono ${color} ${urgent ? "animate-pulse" : ""}`}>{value}</div>
      <div className="text-xs text-ocean-500 mt-0.5">{label}</div>
    </div>
  );
}

function AlertRow({
  alert, expanded, onToggle, onAck, getPlatformName, isActive,
}: {
  alert: Alert;
  expanded: boolean;
  onToggle: () => void;
  onAck: () => void;
  getPlatformName: (id: string) => string;
  isActive: boolean;
}) {
  const s = SEVERITY_STYLE[alert.severity];

  return (
    <div className={`rounded border transition-all ${s.border} ${isActive ? s.bg : "bg-transparent opacity-55"}`}>
      {/* 요약 행 */}
      <div className="px-3 py-2.5 cursor-pointer flex items-start gap-3" onClick={onToggle}>
        {/* 심각도 */}
        <div className="flex-shrink-0 pt-0.5 flex flex-col items-center gap-1">
          <span className={`text-xs font-bold ${s.text}`}>{SEVERITY_LABEL[alert.severity]}</span>
          {isActive && <span className={`w-1.5 h-1.5 rounded-full ${s.text.replace("text-", "bg-")} ${alert.severity === "critical" ? "animate-pulse" : ""}`} />}
        </div>

        {/* 내용 */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5 flex-wrap">
            <span className="text-xs px-1.5 py-0.5 bg-ocean-800/80 text-ocean-400 rounded">
              {ALERT_TYPE_KR[alert.alert_type] ?? alert.alert_type}
            </span>
            <span className={`text-xs px-1.5 py-0.5 rounded border ${s.pill}`}>
              {STATUS_LABEL[alert.status]}
            </span>
            <span className="text-xs text-ocean-600">{alert.generated_by}</span>
            <span className="text-xs text-ocean-600 ml-auto">
              {formatDistanceToNow(new Date(alert.created_at), { addSuffix: true, locale: ko })}
            </span>
          </div>
          <div className="text-xs text-ocean-200 leading-snug">{alert.message}</div>

          {alert.platform_ids.length > 0 && (
            <div className="flex gap-1 mt-1 flex-wrap">
              {alert.platform_ids.map((id) => (
                <span key={id} className="text-xs px-1.5 py-0.5 bg-ocean-800/70 text-ocean-400 rounded font-mono">
                  {getPlatformName(id)}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 확장 상세 */}
      {expanded && (
        <div className="px-3 pb-3 border-t border-current/15 pt-2.5 space-y-2.5">
          {/* 타임라인 */}
          <div className="grid grid-cols-3 gap-3 text-xs">
            <div>
              <div className="text-ocean-500 mb-0.5">발생</div>
              <div className="text-ocean-300 font-mono">{format(new Date(alert.created_at), "MM/dd HH:mm:ss")}</div>
            </div>
            {alert.acknowledged_at && (
              <div>
                <div className="text-ocean-500 mb-0.5">확인</div>
                <div className="text-ocean-300 font-mono">{format(new Date(alert.acknowledged_at), "MM/dd HH:mm:ss")}</div>
              </div>
            )}
            {alert.resolved_at && (
              <div>
                <div className="text-ocean-500 mb-0.5">해결</div>
                <div className="text-ocean-300 font-mono">{format(new Date(alert.resolved_at), "MM/dd HH:mm:ss")}</div>
              </div>
            )}
          </div>

          {/* AI 권고 */}
          {alert.recommendation ? (
            <div className="bg-ocean-900/70 rounded p-2.5 border border-ocean-800">
              <div className="text-xs text-ocean-500 mb-1.5 flex items-center gap-1.5">
                <span>⬡</span><span>AI 분석 · 권고사항</span>
              </div>
              <div className="text-xs text-ocean-300 leading-relaxed whitespace-pre-wrap">{alert.recommendation}</div>
            </div>
          ) : (
            <div className="text-xs text-ocean-700">AI 권고 없음 (Rule 에이전트 생성)</div>
          )}

          {/* 액션 */}
          {isActive && (
            <button
              onClick={onAck}
              className="text-xs px-3 py-1.5 bg-ocean-700 hover:bg-ocean-600 text-ocean-100 rounded transition-colors"
            >
              인지 처리
            </button>
          )}
        </div>
      )}
    </div>
  );
}
