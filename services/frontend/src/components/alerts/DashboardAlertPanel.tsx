"use client";

import { useMemo, useState } from "react";
import { getCoreApiUrl } from "@/lib/publicUrl";
import { useAlertStore } from "@/stores/alertStore";
import { usePlatformStore } from "@/stores/platformStore";
import { useSystemStore } from "@/stores/systemStore";
import type { Alert, AlertSeverity } from "@/types";
import { formatDistanceToNow } from "date-fns";
import { ko } from "date-fns/locale";
import Link from "next/link";

const SEVERITY_LABEL: Record<AlertSeverity, string> = {
  critical: "위험",
  warning: "주의",
  info: "정보",
};

const SEVERITY_DOT: Record<AlertSeverity, string> = {
  critical: "bg-red-400",
  warning: "bg-yellow-400",
  info: "bg-blue-400",
};

const SEVERITY_TEXT: Record<AlertSeverity, string> = {
  critical: "text-red-400",
  warning: "text-yellow-400",
  info: "text-blue-400",
};

const ALERT_TYPE_KR: Record<string, string> = {
  cpa: "충돌 위험",
  zone_intrusion: "구역 침입",
  anomaly: "이상 행동",
  ais_off: "AIS 소실",
  distress: "조난",
  compliance: "상황 보고",
  traffic: "교통 혼잡",
};

export default function DashboardAlertPanel() {
  const alerts = useAlertStore((s) => s.alerts);
  const updateAlert = useAlertStore((s) => s.updateAlert);
  const platforms = usePlatformStore((s) => s.platforms);
  const alertStream = useSystemStore((s) => s.streams.alert);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [filter, setFilter] = useState<AlertSeverity | "all">("all");
  const [pendingAlertId, setPendingAlertId] = useState<string | null>(null);

  const newAlerts = useMemo(() => alerts.filter((a) => a.status === "new"), [alerts]);
  const critical = newAlerts.filter((a) => a.severity === "critical").length;
  const warning = newAlerts.filter((a) => a.severity === "warning").length;
  const info = newAlerts.filter((a) => a.severity === "info").length;

  // 대시보드: 미확인만, 최신 30건
  const displayed = useMemo(
    () =>
      (filter === "all" ? newAlerts : newAlerts.filter((alert) => alert.severity === filter)).slice(0, 30),
    [filter, newAlerts],
  );

  async function acknowledge(alertId: string) {
    setPendingAlertId(alertId);
    try {
      const res = await fetch(`${getCoreApiUrl()}/alerts/${alertId}/action`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "acknowledge" }),
      });
      if (!res.ok) {
        throw new Error(`acknowledge failed: ${res.status}`);
      }
      const updated = (await res.json()) as Alert;
      updateAlert(updated);
    } catch (error) {
      console.error("[alerts] acknowledge failed", error);
    } finally {
      setPendingAlertId((current) => (current === alertId ? null : current));
    }
  }

  function getPlatformName(id: string) {
    const p = platforms[id];
    if (!p) return id.replace(/^MMSI-/, "");
    return p.name && p.name !== p.platform_id
      ? p.name
      : id.replace(/^MMSI-/, "");
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* 헤더 */}
      <div className="flex-shrink-0 px-3 py-2.5 border-b border-ocean-800">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-bold text-ocean-200 tracking-wider">
            실시간 경보
          </span>
          <Link
            href="/alerts"
            className="text-xs text-ocean-500 hover:text-ocean-300 transition-colors"
          >
            전체 보기 →
          </Link>
        </div>
        <div className="mb-2 text-[11px] text-ocean-500">
          경보 스트림: {alertStream.status === "connected" ? "정상" : alertStream.status === "reconnecting" ? "재연결 중" : alertStream.status === "error" ? "오류" : "연결 중"}
        </div>
        {/* 카운트 배지 */}
        <div className="flex gap-2">
          {critical > 0 && (
            <span className="flex items-center gap-1 text-xs text-red-400 bg-red-500/10 border border-red-500/30 px-2 py-0.5 rounded">
              <span className="w-1.5 h-1.5 rounded-full bg-red-400 animate-pulse inline-block" />
              위험 {critical}
            </span>
          )}
          {warning > 0 && (
            <span className="flex items-center gap-1 text-xs text-yellow-400 bg-yellow-500/10 border border-yellow-500/30 px-2 py-0.5 rounded">
              주의 {warning}
            </span>
          )}
          {info > 0 && (
            <span className="flex items-center gap-1 text-xs text-blue-400 bg-blue-500/10 border border-blue-500/30 px-2 py-0.5 rounded">
              정보 {info}
            </span>
          )}
          {newAlerts.length === 0 && (
            <span className="text-xs text-green-400">경보 없음 ✓</span>
          )}
        </div>
        {newAlerts.length > 0 && (
          <div className="mt-2 flex gap-1">
            {(["all", "critical", "warning", "info"] as const).map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setFilter(value)}
                className={`rounded px-2 py-0.5 text-[11px] transition-colors ${filter === value ? "bg-ocean-700 text-ocean-100" : "bg-ocean-900/70 text-ocean-500 hover:text-ocean-300"}`}
              >
                {value === "all" ? "전체" : SEVERITY_LABEL[value]}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* 경보 목록 */}
      <div className="flex-1 overflow-y-auto">
        {displayed.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 gap-2 text-ocean-400">
            <span className="text-lg">✓</span>
            <span className="text-xs">미확인 경보 없음</span>
          </div>
        ) : (
          displayed.map((alert) => {
            const isExpanded = expanded === alert.alert_id;
            return (
              <div
                key={alert.alert_id}
                className="border-b border-ocean-900/80"
              >
                <button
                  className="w-full text-left px-3 py-2.5 hover:bg-ocean-800/30 transition-colors"
                  onClick={() =>
                    setExpanded(isExpanded ? null : alert.alert_id)
                  }
                  aria-expanded={isExpanded}
                  aria-controls={`dashboard-alert-${alert.alert_id}`}
                >
                  <div className="flex items-start gap-2">
                    <span
                      className={`w-1.5 h-1.5 rounded-full flex-shrink-0 mt-1 ${SEVERITY_DOT[alert.severity]} ${alert.severity === "critical" ? "animate-pulse" : ""}`}
                    />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5 mb-0.5">
                        <span
                          className={`text-xs font-bold ${SEVERITY_TEXT[alert.severity]}`}
                        >
                          {SEVERITY_LABEL[alert.severity]}
                        </span>
                        <span className="text-xs text-ocean-400">
                          {ALERT_TYPE_KR[alert.alert_type] ?? alert.alert_type}
                        </span>
                      </div>
                      <div className="text-xs text-ocean-300 leading-snug line-clamp-2">
                        {alert.message}
                      </div>
                      <div className="text-xs text-ocean-400 mt-0.5">
                        {formatDistanceToNow(new Date(alert.created_at), {
                          addSuffix: true,
                          locale: ko,
                        })}
                      </div>
                    </div>
                  </div>
                </button>

                {isExpanded && (
                  <div id={`dashboard-alert-${alert.alert_id}`} className="px-3 pb-2.5 space-y-2">
                    {alert.platform_ids.length > 0 && (
                      <div className="flex gap-1 flex-wrap">
                        {alert.platform_ids.map((id) => (
                          <span
                            key={id}
                            className="text-xs px-1.5 py-0.5 bg-ocean-800 text-ocean-300 rounded font-mono"
                          >
                            {getPlatformName(id)}
                          </span>
                        ))}
                      </div>
                    )}
                    {alert.recommendation && (
                      <div className="text-xs text-ocean-300 bg-ocean-900/60 rounded p-2 leading-relaxed border border-ocean-800 line-clamp-4">
                        {Boolean(
                          (alert.metadata as Record<string, unknown> | null)
                            ?.llm_fallback,
                        ) && (
                          <div className="mb-1 text-amber-300">
                            LLM 실패 fallback
                          </div>
                        )}
                        {alert.recommendation}
                      </div>
                    )}
                    <button
                      onClick={() => acknowledge(alert.alert_id)}
                      disabled={pendingAlertId === alert.alert_id}
                      className="text-xs px-2.5 py-1 bg-ocean-700 hover:bg-ocean-600 text-ocean-200 rounded transition-colors"
                    >
                      {pendingAlertId === alert.alert_id ? "처리 중..." : "인지 처리"}
                    </button>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
