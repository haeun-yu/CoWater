"use client";

import { useEffect } from "react";
import dynamic from "next/dynamic";
import AlertPanel from "@/components/alerts/AlertPanel";
import PlatformSidebar from "@/components/platforms/PlatformSidebar";
import AgentPanel from "@/components/agents/AgentPanel";
import TopBar from "@/components/layout/TopBar";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useInitialData } from "@/hooks/useInitialData";

// MapLibre는 SSR 불가 — dynamic import
const MaritimeMap = dynamic(() => import("@/components/map/MaritimeMap"), {
  ssr: false,
  loading: () => (
    <div className="flex-1 flex items-center justify-center bg-ocean-950 text-ocean-400">
      해도 로딩 중...
    </div>
  ),
});

export default function Home() {
  useWebSocket();
  useInitialData();

  return (
    <div className="h-screen w-screen flex flex-col overflow-hidden">
      <TopBar />
      <div className="flex flex-1 overflow-hidden">
        {/* 좌측: 경보 패널 */}
        <div className="w-80 flex-shrink-0 flex flex-col border-r border-ocean-800">
          <AlertPanel />
        </div>

        {/* 중앙: 해도 */}
        <div className="flex-1 relative">
          <MaritimeMap />
        </div>

        {/* 우측: 선박 상세 + Agent 패널 */}
        <div className="w-80 flex-shrink-0 flex flex-col border-l border-ocean-800">
          <PlatformSidebar />
          <AgentPanel />
        </div>
      </div>
    </div>
  );
}
