"use client";

import dynamic from "next/dynamic";
import { useState } from "react";
import PlatformSidebar from "@/components/platforms/PlatformSidebar";
import DashboardAlertPanel from "@/components/alerts/DashboardAlertPanel";
import { useAlertStore } from "@/stores/alertStore";
import { useSystemStore } from "@/stores/systemStore";

const MaritimeMap = dynamic(() => import("@/components/map/MaritimeMap"), {
  ssr: false,
  loading: () => (
    <div className="flex-1 flex items-center justify-center bg-ocean-950 text-ocean-400 text-sm">
      해도 로딩 중...
    </div>
  ),
});

export default function DashboardPage() {
  const alerts = useAlertStore((s) => s.alerts);
  const initialData = useSystemStore((s) => s.initialData);
  const newAlerts = alerts.filter((a) => a.status === "new");
  const criticalCount = newAlerts.filter((a) => a.severity === "critical").length;

  const [leftOpen, setLeftOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(true);

  return (
    <div className="h-full flex flex-col overflow-hidden bg-ocean-950">
      {/* 초기 데이터 오류 배너 */}
      {Object.values(initialData).some((r) => r.status === "error") && (
        <div className="border-b border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-xs text-amber-200 shrink-0">
          일부 초기 데이터를 불러오지 못했습니다. 실시간 스트림은 계속 수신됩니다.
        </div>
      )}

      {/* 메인 레이아웃 */}
      <div className="relative flex-1 min-h-0 flex">
        {/* ── 왼쪽 사이드바 ── */}
        <aside
          className={`flex-shrink-0 flex flex-col border-r border-ocean-800/80 bg-ocean-950/90 backdrop-blur-sm transition-all duration-200 overflow-hidden ${leftOpen ? "w-72" : "w-0"}`}
          aria-label="플랫폼 패널"
        >
          <PlatformSidebar />
        </aside>

        {/* ── 지도 (중앙 전체) ── */}
        <section className="relative flex-1 min-w-0 min-h-0" aria-label="해도">
          <MaritimeMap />

          {/* 왼쪽 토글 버튼 */}
          <button
            onClick={() => setLeftOpen((v) => !v)}
            title={leftOpen ? "플랫폼 패널 닫기" : "플랫폼 패널 열기"}
            className="absolute left-2 top-2 z-20 flex h-7 w-7 items-center justify-center rounded-md border border-ocean-700/70 bg-ocean-900/80 text-ocean-300 backdrop-blur-sm hover:bg-ocean-800/90 hover:text-ocean-100 transition-colors"
          >
            {leftOpen ? "◀" : "▶"}
          </button>

          {/* 오른쪽 토글 버튼 */}
          <button
            onClick={() => setRightOpen((v) => !v)}
            title={rightOpen ? "경보 패널 닫기" : "경보 패널 열기"}
            className="absolute right-2 top-2 z-20 flex h-7 w-7 items-center justify-center rounded-md border border-ocean-700/70 bg-ocean-900/80 text-ocean-300 backdrop-blur-sm hover:bg-ocean-800/90 hover:text-ocean-100 transition-colors"
          >
            {rightOpen ? "▶" : "◀"}
          </button>

          {/* critical 배지 (경보 패널 닫혔을 때만 표시) */}
          {!rightOpen && criticalCount > 0 && (
            <button
              onClick={() => setRightOpen(true)}
              className="absolute right-2 top-11 z-20 flex items-center gap-1 rounded-md border border-red-500/40 bg-red-500/20 px-2 py-1 text-[11px] font-bold text-red-300 animate-pulse-slow backdrop-blur-sm"
            >
              ⚠ {criticalCount}
            </button>
          )}
        </section>

        {/* ── 오른쪽 사이드바 ── */}
        <aside
          className={`flex-shrink-0 flex flex-col border-l border-ocean-800/80 bg-ocean-950/90 backdrop-blur-sm transition-all duration-200 overflow-hidden ${rightOpen ? "w-80" : "w-0"}`}
          aria-label="경보 패널"
        >
          <DashboardAlertPanel />
        </aside>
      </div>
    </div>
  );
}
