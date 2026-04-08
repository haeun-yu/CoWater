"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAlertStore } from "@/stores/alertStore";
import { usePlatformStore } from "@/stores/platformStore";
import { useAILogStore } from "@/stores/aiLogStore";
import { useSystemStore } from "@/stores/systemStore";
import { countPlatformsByFreshness } from "@/lib/platformStatus";
import { useEffect, useState } from "react";

const NAV = [
  { href: "/", label: "대시보드", icon: "◈" },
  { href: "/platforms", label: "플랫폼", icon: "▲" },
  { href: "/zones", label: "구역", icon: "▦" },
  { href: "/alerts", label: "경보", icon: "⚡" },
  { href: "/agents", label: "에이전트", icon: "⬡" },
];

export default function NavBar() {
  const pathname = usePathname();
  const alerts = useAlertStore((s) => s.alerts);
  const platforms = usePlatformStore((s) => s.platforms);
  const aiLogs = useAILogStore((s) => s.logs);
  const streams = useSystemStore((s) => s.streams);
  const newAlerts = alerts.filter((a) => a.status === "new").length;
  const criticalCount = alerts.filter(
    (a) => a.severity === "critical" && a.status === "new",
  ).length;

  const [now, setNow] = useState("");
  useEffect(() => {
    const fmt = () =>
      setNow(new Date().toISOString().replace("T", " ").slice(0, 19) + " UTC");
    fmt();
    const id = setInterval(fmt, 1000);
    return () => clearInterval(id);
  }, []);

  const platformValues = Object.values(platforms);
  const freshness = countPlatformsByFreshness(platformValues);
  const allStreamsConnected = Object.values(streams).every((stream) => stream.status === "connected");

  const streamSummary = [
    `위치 ${streams.position.status === "connected" ? "정상" : "주의"}`,
    `경보 ${streams.alert.status === "connected" ? "정상" : "주의"}`,
  ].join(" · ");

  return (
    <header className="h-11 flex-shrink-0 flex items-center border-b border-ocean-800 bg-ocean-900 px-4 gap-6">
      {/* 로고 */}
      <div className="flex items-center gap-2 flex-shrink-0">
        <span className="text-ocean-400 font-bold tracking-widest text-sm">
          CO<span className="text-ocean-200">WATER</span>
        </span>
        <span className="text-ocean-500 text-xs hidden md:block">
          연안 해양 통합 관제
        </span>
      </div>

      {/* 네비게이션 */}
      <nav className="flex items-center gap-1" aria-label="주요 메뉴">
        {NAV.map(({ href, label, icon }) => {
          const isActive =
            href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-1.5 px-3 py-1 rounded text-xs transition-colors ${
                isActive
                  ? "bg-ocean-700 text-ocean-100"
                  : "text-ocean-500 hover:text-ocean-300 hover:bg-ocean-800/50"
              }`}
            >
              <span>{icon}</span>
              <span>{label}</span>
              {href === "/alerts" && newAlerts > 0 && (
                <span
                  className={`ml-0.5 px-1 rounded-full text-xs font-bold ${
                    criticalCount > 0
                      ? "bg-red-500 text-white"
                      : "bg-yellow-500/80 text-black"
                  }`}
                >
                  {newAlerts}
                </span>
              )}
              {href === "/agents" && aiLogs.length > 0 && (
                <span className="ml-0.5 w-1.5 h-1.5 rounded-full bg-green-400 inline-block" />
              )}
            </Link>
          );
        })}
      </nav>

      {/* 우측 상태 */}
       <div className="ml-auto flex items-center gap-5 text-xs">
         <div className="flex items-center gap-1.5 text-ocean-400">
            <span className="font-mono text-ocean-200">
             {platformValues.length}
            </span>
           <span>척 관제</span>
         </div>
         {freshness.stale > 0 && (
           <div className="text-amber-300">지연 {freshness.stale}</div>
         )}
         {freshness.lost > 0 && (
           <div className="text-red-300">유실 {freshness.lost}</div>
         )}
         {criticalCount > 0 && (
           <div className="flex items-center gap-1 text-red-400 font-bold animate-pulse">
             <span>⚠</span>
             <span>CRITICAL {criticalCount}</span>
           </div>
         )}
         <div className="flex items-center gap-1.5" title={streamSummary} aria-label={streamSummary}>
           <span className={`w-1.5 h-1.5 rounded-full ${allStreamsConnected ? "bg-green-400 animate-pulse" : "bg-amber-400"}`} />
           <span className="text-ocean-400">{allStreamsConnected ? "LIVE" : "DEGRADED"}</span>
         </div>
         <span className="text-ocean-400 font-mono hidden lg:block">{now}</span>
       </div>
      </header>
  );
}
