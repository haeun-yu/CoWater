"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAlertStore } from "@/stores/alertStore";
import { usePlatformStore } from "@/stores/platformStore";
import { useAILogStore } from "@/stores/aiLogStore";
import { useSystemStore } from "@/stores/systemStore";
import { useAuthStore } from "@/stores/authStore";
import { countPlatformsByFreshness } from "@/lib/platformStatus";
import { useEffect, useState, useCallback } from "react";

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
  const actor = useAuthStore((s) => s.actor);
  const role = useAuthStore((s) => s.role);
  const logout = useAuthStore((s) => s.logout);
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

  const [soundEnabled, setSoundEnabled] = useState(true);
  useEffect(() => {
    setSoundEnabled(localStorage.getItem("cowater-alert-sound") !== "false");
  }, []);
  const toggleSound = useCallback(() => {
    setSoundEnabled((prev) => {
      const next = !prev;
      localStorage.setItem("cowater-alert-sound", String(next));
      return next;
    });
  }, []);

  const platformValues = Object.values(platforms);
  const freshness = countPlatformsByFreshness(platformValues);
  const STREAM_DATA_TIMEOUT_MS = 60_000;
  const allStreamsConnected = Object.values(streams).every(
    (s) =>
      s.status === "connected" &&
      s.lastMessageAt != null &&
      Date.now() - new Date(s.lastMessageAt).getTime() < STREAM_DATA_TIMEOUT_MS,
  );

  const streamSummary = [
    `위치 ${streams.position.status === "connected" ? (streams.position.lastMessageAt ? "정상" : "대기") : "주의"}`,
    `경보 ${streams.alert.status === "connected" ? (streams.alert.lastMessageAt ? "정상" : "대기") : "주의"}`,
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
         <button
            onClick={toggleSound}
           title={soundEnabled ? "경보음 켜짐 — 클릭하여 끄기" : "경보음 꺼짐 — 클릭하여 켜기"}
           aria-pressed={soundEnabled}
           className={`text-sm transition-colors ${soundEnabled ? "text-ocean-300 hover:text-ocean-100" : "text-ocean-600 hover:text-ocean-400"}`}
          >
            {soundEnabled ? "🔔" : "🔕"}
          </button>
          {actor && role && (
            <div className="hidden lg:flex items-center gap-2 rounded border border-ocean-800 px-2 py-1 text-[11px]">
              <span className="text-ocean-300">{actor}</span>
              <span className="text-ocean-600">·</span>
              <span className="text-ocean-500 uppercase">{role}</span>
            </div>
          )}
          <button
            onClick={logout}
            className="text-[11px] text-slate-400 hover:text-red-300 transition-colors"
          >
            로그아웃
          </button>
          <span className="text-ocean-400 font-mono hidden lg:block">{now}</span>
        </div>
      </header>
  );
}
