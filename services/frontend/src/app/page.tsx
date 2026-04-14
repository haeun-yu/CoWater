"use client";

import dynamic from "next/dynamic";
import { useMemo } from "react";
import PlatformSidebar from "@/components/platforms/PlatformSidebar";
import DashboardAlertPanel from "@/components/alerts/DashboardAlertPanel";
import { useAlertStore } from "@/stores/alertStore";
import { usePlatformStore } from "@/stores/platformStore";
import { useSystemStore } from "@/stores/systemStore";
import { countPlatformsByFreshness } from "@/lib/platformStatus";
import MetricCard from "@/components/ui/MetricCard";

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
  const selectedId = usePlatformStore((s) => s.selectedId);
  const alerts = useAlertStore((s) => s.alerts);
  const streams = useSystemStore((s) => s.streams);
  const initialData = useSystemStore((s) => s.initialData);

  const platformValues = Object.values(platforms);
  const freshness = useMemo(
    () => countPlatformsByFreshness(platformValues),
    [platformValues],
  );
  const newAlerts = alerts.filter((alert) => alert.status === "new");
  const criticalCount = newAlerts.filter(
    (alert) => alert.severity === "critical",
  ).length;
  const streamStatusSummary = [streams.position.status, streams.alert.status];
  const allStreamsHealthy = streamStatusSummary.every(
    (status) => status === "connected",
  );
  const degradedStreams = streamStatusSummary.filter(
    (status) => status !== "connected",
  ).length;

  return (
    <div className="h-full flex flex-col overflow-hidden bg-[radial-gradient(circle_at_top,#0b2f57_0%,#051427_42%,#020d1a_100%)]">
      {Object.values(initialData).some(
        (resource) => resource.status === "error",
      ) && (
        <div className="border-b border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
          일부 초기 데이터를 불러오지 못했습니다. 실시간 스트림은 계속 수신될 수
          있습니다.
        </div>
      )}
      <section
        className="border-b border-ocean-800/80 bg-ocean-950/60 px-4 py-3 backdrop-blur-sm"
        aria-label="실시간 운영 요약"
      >
        <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
          <div></div>
          <div
            className={`rounded-full border px-3 py-1 text-[11px] font-medium ${allStreamsHealthy ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-200" : "border-amber-400/30 bg-amber-400/10 text-amber-200"}`}
          >
            {allStreamsHealthy
              ? "실시간 스트림 정상"
              : `스트림 주의 ${degradedStreams}건`}
          </div>
        </div>

        <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard
            label="관제 대상"
            value={`${platformValues.length}척`}
            detail="현재 지도 및 패널 기준"
          />
          <MetricCard
            label="긴급 대응"
            value={`${criticalCount}건`}
            detail="즉시 확인이 필요한 경보"
            tone={criticalCount > 0 ? "critical" : "neutral"}
          />
          <MetricCard
            label="활성 경보"
            value={`${newAlerts.length}건`}
            detail="우측 패널에서 우선순위 정렬"
            tone={newAlerts.length > 0 ? "warning" : "neutral"}
          />
          <MetricCard
            label="정상 수신"
            value={`${freshness.live}척`}
            detail={`지연 ${freshness.stale} · 유실 ${freshness.lost}`}
            tone={
              freshness.stale > 0 || freshness.lost > 0 ? "warning" : "neutral"
            }
          />
        </div>
      </section>

      <div className="grid flex-1 min-h-0 gap-px bg-ocean-950 xl:grid-cols-[320px_minmax(0,1fr)_360px]">
        <aside
          className="min-h-0 overflow-hidden border-r border-ocean-800/80 bg-ocean-950/75 backdrop-blur-sm flex flex-col"
          aria-label="플랫폼 패널"
        >
          <PlatformSidebar />
        </aside>

        <section
          className="flex min-h-0 min-w-0 flex-col bg-ocean-950/35"
          aria-label="해도 패널"
        >
          <div className="border-b border-ocean-800/80 px-4 py-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-ocean-400">
                  운영 시야
                </div>
                <div className="mt-1 text-sm text-ocean-100">
                  지도는 상황 인지 전용, 세부 데이터는 좌우 패널에서 분리해
                  확인합니다.
                </div>
              </div>
              <div className="flex flex-wrap gap-2 text-[11px]">
                <MapChip
                  label="정상"
                  value={`${freshness.live}`}
                  tone="neutral"
                />
                <MapChip
                  label="지연"
                  value={`${freshness.stale}`}
                  tone={freshness.stale > 0 ? "warning" : "neutral"}
                />
                <MapChip
                  label="유실"
                  value={`${freshness.lost}`}
                  tone={freshness.lost > 0 ? "critical" : "neutral"}
                />
                <MapChip
                  label="활성 경보"
                  value={`${newAlerts.length}`}
                  tone={newAlerts.length > 0 ? "warning" : "neutral"}
                />
              </div>
            </div>
          </div>
          <div className="relative min-h-0 flex-1">
            <MaritimeMap />
          </div>
        </section>

        <aside
          className="min-h-0 overflow-hidden border-l border-ocean-800/80 bg-ocean-950/80 backdrop-blur-sm flex flex-col"
          aria-label="경보 패널"
        >
          <DashboardAlertPanel />
        </aside>
      </div>
    </div>
  );
}

function MapChip({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "neutral" | "warning" | "critical";
}) {
  const toneClass =
    tone === "critical"
      ? "border-red-400/25 bg-red-400/10 text-red-200"
      : tone === "warning"
        ? "border-amber-400/25 bg-amber-400/10 text-amber-200"
        : "border-ocean-700/80 bg-ocean-900/55 text-ocean-200";

  return (
    <div className={`rounded-full border px-3 py-1.5 ${toneClass}`}>
      <span className="text-ocean-400">{label}</span>
      <span className="ml-1 font-mono">{value}</span>
    </div>
  );
}
