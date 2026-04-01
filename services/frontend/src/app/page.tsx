"use client";

import dynamic from "next/dynamic";
import PlatformSidebar from "@/components/platforms/PlatformSidebar";
import DashboardAlertPanel from "@/components/alerts/DashboardAlertPanel";

const MaritimeMap = dynamic(() => import("@/components/map/MaritimeMap"), {
  ssr: false,
  loading: () => (
    <div className="flex-1 flex items-center justify-center bg-ocean-950 text-ocean-400 text-sm">
      해도 로딩 중...
    </div>
  ),
});

export default function DashboardPage() {
  return (
    <div className="h-full flex overflow-hidden">
      {/* 좌측: 플랫폼 사이드바 */}
      <div className="w-64 flex-shrink-0 border-r border-ocean-800 overflow-hidden flex flex-col">
        <PlatformSidebar />
      </div>

      {/* 중앙: 해도 */}
      <div className="flex-1 relative min-w-0">
        <MaritimeMap />
      </div>

      {/* 우측: 경보 패널 */}
      <div className="w-72 flex-shrink-0 border-l border-ocean-800 overflow-hidden flex flex-col">
        <DashboardAlertPanel />
      </div>
    </div>
  );
}
