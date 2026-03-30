"use client";

import { useAlertStore } from "@/stores/alertStore";
import { usePlatformStore } from "@/stores/platformStore";

export default function TopBar() {
  const platforms = usePlatformStore((s) => s.platforms);
  const alerts = useAlertStore((s) => s.alerts);
  const criticalCount = alerts.filter(
    (a) => a.severity === "critical" && a.status === "new"
  ).length;

  const now = new Date().toISOString().replace("T", " ").slice(0, 19) + " UTC";

  return (
    <header className="h-10 flex items-center justify-between px-4 border-b border-ocean-800 bg-ocean-900 flex-shrink-0">
      {/* 로고 */}
      <div className="flex items-center gap-3">
        <span className="text-ocean-400 font-bold tracking-widest text-sm">
          CO<span className="text-ocean-200">WATER</span>
        </span>
        <span className="text-ocean-700 text-xs">연안 해양 통합 관제</span>
      </div>

      {/* 상태 요약 */}
      <div className="flex items-center gap-6 text-xs">
        <div className="flex items-center gap-1.5">
          <span className="text-ocean-400">플랫폼</span>
          <span className="text-ocean-200 font-mono">{Object.keys(platforms).length}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-ocean-400">경보</span>
          <span
            className={`font-mono font-bold ${
              criticalCount > 0 ? "text-red-400 animate-pulse" : "text-ocean-200"
            }`}
          >
            {criticalCount > 0 ? `CRITICAL ${criticalCount}` : alerts.filter(a => a.status === "new").length}
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
          <span className="text-ocean-400">LIVE</span>
        </div>
      </div>

      {/* 시각 */}
      <div className="text-xs text-ocean-500 font-mono">{now}</div>
    </header>
  );
}
