"use client";

import dynamic from "next/dynamic";
import { useMemo } from "react";
import PlatformSidebar from "@/components/platforms/PlatformSidebar";
import DashboardAlertPanel from "@/components/alerts/DashboardAlertPanel";
import { useAlertStore } from "@/stores/alertStore";
import { usePlatformStore } from "@/stores/platformStore";
import { useSystemStore } from "@/stores/systemStore";
import { countPlatformsByFreshness } from "@/lib/platformStatus";

const MaritimeMap = dynamic(() => import("@/components/map/MaritimeMap"), {
  ssr: false,
  loading: () => (
    <div className="flex-1 flex items-center justify-center bg-ocean-950 text-ocean-400 text-sm">
      해도 로딩 중...
    </div>
  ),
});

export default function DashboardPage() {
  const platforms = usePlatformStore((s) => s.platforms);
  const alerts = useAlertStore((s) => s.alerts);
  const streams = useSystemStore((s) => s.streams);
  const initialData = useSystemStore((s) => s.initialData);

  const platformValues = Object.values(platforms);
  const freshness = useMemo(() => countPlatformsByFreshness(platformValues), [platformValues]);
  const newAlerts = alerts.filter((alert) => alert.status === "new");
  const criticalCount = newAlerts.filter((alert) => alert.severity === "critical").length;

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {Object.values(initialData).some((resource) => resource.status === "error") && (
        <div className="border-b border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
          일부 초기 데이터를 불러오지 못했습니다. 실시간 스트림은 계속 수신될 수 있습니다.
        </div>
      )}
      <section
        className="grid grid-cols-2 gap-px border-b border-ocean-800 bg-ocean-800/80 px-3 py-2 text-xs text-ocean-300 lg:grid-cols-5"
        aria-label="실시간 운영 요약"
      >
        <SummaryCard label="관제" value={`${platformValues.length}척`} tone="neutral" />
        <SummaryCard label="위험" value={`${criticalCount}건`} tone={criticalCount > 0 ? "critical" : "neutral"} />
        <SummaryCard label="활성" value={`${newAlerts.length}건`} tone={newAlerts.length > 0 ? "warning" : "neutral"} />
        <SummaryCard label="정상" value={`${freshness.live}척`} tone="neutral" />
        <SummaryCard label="지연" value={`${freshness.stale}척`} tone={freshness.stale > 0 ? "warning" : "neutral"} />
      </section>

      <div className="flex flex-1 overflow-hidden">
        <aside className="w-64 flex-shrink-0 border-r border-ocean-800 overflow-hidden flex flex-col" aria-label="플랫폼 패널">
          <PlatformSidebar />
        </aside>

        <section className="flex-1 relative min-w-0" aria-label="해도 패널">
          <MaritimeMap />
        </section>

        <aside className="w-72 flex-shrink-0 border-l border-ocean-800 overflow-hidden flex flex-col" aria-label="경보 패널">
          <DashboardAlertPanel />
        </aside>
      </div>
    </div>
  );
}

function SummaryCard({ label, value, tone }: { label: string; value: string; tone: "neutral" | "warning" | "critical" }) {
  const toneClass =
    tone === "critical"
      ? "text-red-300"
      : tone === "warning"
        ? "text-amber-300"
        : "text-ocean-100";

  return (
    <div className="rounded border border-ocean-800/70 bg-ocean-900/70 px-3 py-2">
      <div className="text-[10px] text-ocean-500 truncate">{label}</div>
      <div className={`mt-1 font-mono text-sm leading-tight ${toneClass}`}>{value}</div>
    </div>
  );
}
