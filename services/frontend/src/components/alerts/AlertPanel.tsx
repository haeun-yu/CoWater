"use client";

import { useState } from "react";
import { useAlertStore } from "@/stores/alertStore";
import { usePlatformStore } from "@/stores/platformStore";
import type { Alert, AlertSeverity } from "@/types";
import { formatDistanceToNow } from "date-fns";
import { ko } from "date-fns/locale";

const SEVERITY_LABEL: Record<AlertSeverity, string> = {
  critical: "위험",
  warning:  "주의",
  info:     "정보",
};

export default function AlertPanel({ compact }: { compact?: boolean }) {
  const alerts = useAlertStore((s) => s.alerts);
  const acknowledge = useAlertStore((s) => s.acknowledge);
  const [filter, setFilter] = useState<AlertSeverity | "all">("all");
  const [expanded, setExpanded] = useState<string | null>(null);
  const select = usePlatformStore((s) => s.select);

  const newCount = alerts.filter((a) => a.status === "new").length;
  const criticalCount = alerts.filter((a) => a.severity === "critical" && a.status === "new").length;

  // In compact mode, show only new alerts, prioritize critical
  const filtered = alerts
    .filter((a) => filter === "all" || a.severity === filter)
    .filter((a) => !compact || a.status === "new");

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* 헤더 */}
      <div className="px-3 py-2 border-b border-ocean-800 flex-shrink-0">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-bold text-ocean-200 tracking-wider">경보 현황</span>
          <div className="flex gap-2 text-xs">
            <span className="text-ocean-500">{newCount} 신규</span>
            {criticalCount > 0 && (
              <span className="text-red-400 font-bold animate-pulse">{criticalCount} 위험</span>
            )}
          </div>
        </div>
        {/* 필터 탭 */}
        <div className="flex gap-1">
          {(["all", "critical", "warning", "info"] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`text-xs px-2 py-0.5 rounded transition-colors ${
                filter === f
                  ? f === "all"
                    ? "bg-ocean-700 text-ocean-100"
                    : `bg-severity-${f} text-white border`
                  : "text-ocean-500 hover:text-ocean-300"
              }`}
            >
              {f === "all" ? "전체" : SEVERITY_LABEL[f]}
            </button>
          ))}
        </div>
      </div>

      {/* 경보 목록 */}
      <div className="flex-1 overflow-y-auto">
        {filtered.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-ocean-600 text-xs">
            경보 없음
          </div>
        ) : (
          filtered.map((alert) => (
            <AlertRow
              key={alert.alert_id}
              alert={alert}
              expanded={expanded === alert.alert_id}
              onToggle={() =>
                setExpanded(expanded === alert.alert_id ? null : alert.alert_id)
              }
              onAck={() => acknowledge(alert.alert_id)}
              onSelectPlatform={(id) => select(id)}
            />
          ))
        )}
      </div>
    </div>
  );
}

function AlertRow({
  alert,
  expanded,
  onToggle,
  onAck,
  onSelectPlatform,
}: {
  alert: Alert;
  expanded: boolean;
  onToggle: () => void;
  onAck: () => void;
  onSelectPlatform: (id: string) => void;
}) {
  const isNew = alert.status === "new";

  return (
    <div
      className={`border-b border-ocean-900 ${isNew ? `bg-severity-${alert.severity}` : "opacity-60"}`}
    >
      {/* 요약 행 */}
      <div
        className="px-3 py-2 cursor-pointer flex items-start gap-2"
        onClick={onToggle}
      >
        <span className={`text-xs font-bold mt-0.5 severity-${alert.severity} flex-shrink-0`}>
          {SEVERITY_LABEL[alert.severity]}
        </span>
        <div className="flex-1 min-w-0">
          <div className="text-xs text-ocean-200 leading-snug line-clamp-2">
            {alert.message}
          </div>
          <div className="text-xs text-ocean-600 mt-0.5">
            {formatDistanceToNow(new Date(alert.created_at), { addSuffix: true, locale: ko })}
            {" · "}
            <span className="text-ocean-500">{alert.generated_by}</span>
          </div>
        </div>
        {isNew && (
          <span className="w-1.5 h-1.5 rounded-full bg-current flex-shrink-0 mt-1.5 animate-pulse" />
        )}
      </div>

      {/* 확장 상세 */}
      {expanded && (
        <div className="px-3 pb-2 space-y-2">
          {/* 관련 선박 */}
          {alert.platform_ids.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {alert.platform_ids.map((id) => (
                <button
                  key={id}
                  onClick={() => onSelectPlatform(id)}
                  className="text-xs px-1.5 py-0.5 bg-ocean-800 text-ocean-300 rounded hover:bg-ocean-700"
                >
                  {id}
                </button>
              ))}
            </div>
          )}

          {/* AI 권고사항 */}
          {alert.recommendation && (
            <div className="text-xs text-ocean-300 bg-ocean-900 rounded p-2 leading-relaxed border border-ocean-700">
              <span className="text-ocean-500 text-xs block mb-1">AI 권고</span>
              {alert.recommendation}
            </div>
          )}

          {/* 인지 버튼 */}
          {alert.status === "new" && (
            <button
              onClick={onAck}
              className="text-xs px-2 py-1 bg-ocean-700 hover:bg-ocean-600 text-ocean-200 rounded transition-colors"
            >
              인지 처리
            </button>
          )}
        </div>
      )}
    </div>
  );
}
