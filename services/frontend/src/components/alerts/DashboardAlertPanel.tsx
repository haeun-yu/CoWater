"use client";

import { useState } from "react";
import { useAlertStore } from "@/stores/alertStore";
import { usePlatformStore } from "@/stores/platformStore";
import type { Alert, AlertSeverity } from "@/types";
import { formatDistanceToNow } from "date-fns";
import { ko } from "date-fns/locale";
import Link from "next/link";

const SEVERITY_LABEL: Record<AlertSeverity, string> = {
  critical: "위험",
  warning:  "주의",
  info:     "정보",
};

const SEVERITY_DOT: Record<AlertSeverity, string> = {
  critical: "bg-red-400",
  warning:  "bg-yellow-400",
  info:     "bg-blue-400",
};

const SEVERITY_TEXT: Record<AlertSeverity, string> = {
  critical: "text-red-400",
  warning:  "text-yellow-400",
  info:     "text-blue-400",
};

const ALERT_TYPE_KR: Record<string, string> = {
  cpa:           "충돌 위험",
  zone_intrusion:"구역 침입",
  anomaly:       "이상 행동",
  ais_off:       "AIS 소실",
  distress:      "조난",
  compliance:    "상황 보고",
  traffic:       "교통 혼잡",
};

export default function DashboardAlertPanel() {
  const alerts = useAlertStore((s) => s.alerts);
  const acknowledge = useAlertStore((s) => s.acknowledge);
  const platforms = usePlatformStore((s) => s.platforms);
  const [expanded, setExpanded] = useState<string | null>(null);

  const newAlerts = alerts.filter((a) => a.status === "new");
  const critical = newAlerts.filter((a) => a.severity === "critical").length;
  const warning  = newAlerts.filter((a) => a.severity === "warning").length;
  const info     = newAlerts.filter((a) => a.severity === "info").length;

  // 대시보드: 미확인만, 최신 30건
  const displayed = newAlerts.slice(0, 30);

  function getPlatformName(id: string) {
    const p = platforms[id];
    if (!p) return id.replace(/^MMSI-/, "");
    return p.name && p.name !== p.platform_id ? p.name : id.replace(/^MMSI-/, "");
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* 헤더 */}
      <div className="flex-shrink-0 px-3 py-2.5 border-b border-ocean-800">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-bold text-ocean-200 tracking-wider">실시간 경보</span>
          <Link href="/alerts" className="text-xs text-ocean-500 hover:text-ocean-300 transition-colors">
            전체 보기 →
          </Link>
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
      </div>

      {/* 경보 목록 */}
      <div className="flex-1 overflow-y-auto">
        {displayed.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 gap-2 text-ocean-600">
            <span className="text-lg">✓</span>
            <span className="text-xs">미확인 경보 없음</span>
          </div>
        ) : (
          displayed.map((alert) => {
            const isExpanded = expanded === alert.alert_id;
            return (
              <div key={alert.alert_id} className="border-b border-ocean-900/80">
                <button
                  className="w-full text-left px-3 py-2.5 hover:bg-ocean-800/30 transition-colors"
                  onClick={() => setExpanded(isExpanded ? null : alert.alert_id)}
                >
                  <div className="flex items-start gap-2">
                    <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 mt-1 ${SEVERITY_DOT[alert.severity]} ${alert.severity === "critical" ? "animate-pulse" : ""}`} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5 mb-0.5">
                        <span className={`text-xs font-bold ${SEVERITY_TEXT[alert.severity]}`}>
                          {SEVERITY_LABEL[alert.severity]}
                        </span>
                        <span className="text-xs text-ocean-600">
                          {ALERT_TYPE_KR[alert.alert_type] ?? alert.alert_type}
                        </span>
                      </div>
                      <div className="text-xs text-ocean-300 leading-snug line-clamp-2">
                        {alert.message}
                      </div>
                      <div className="text-xs text-ocean-600 mt-0.5">
                        {formatDistanceToNow(new Date(alert.created_at), { addSuffix: true, locale: ko })}
                      </div>
                    </div>
                  </div>
                </button>

                {isExpanded && (
                  <div className="px-3 pb-2.5 space-y-2">
                    {alert.platform_ids.length > 0 && (
                      <div className="flex gap-1 flex-wrap">
                        {alert.platform_ids.map((id) => (
                          <span key={id} className="text-xs px-1.5 py-0.5 bg-ocean-800 text-ocean-300 rounded font-mono">
                            {getPlatformName(id)}
                          </span>
                        ))}
                      </div>
                    )}
                    {alert.recommendation && (
                      <div className="text-xs text-ocean-300 bg-ocean-900/60 rounded p-2 leading-relaxed border border-ocean-800 line-clamp-4">
                        {alert.recommendation}
                      </div>
                    )}
                    <button
                      onClick={() => acknowledge(alert.alert_id)}
                      className="text-xs px-2.5 py-1 bg-ocean-700 hover:bg-ocean-600 text-ocean-200 rounded transition-colors"
                    >
                      인지 처리
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
