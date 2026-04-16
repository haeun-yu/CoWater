"use client";

import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import { useAlertStore } from "@/stores/alertStore";
import { usePlatformStore } from "@/stores/platformStore";
import { useAILogStore } from "@/stores/aiLogStore";
import { useSystemStore } from "@/stores/systemStore";
import { useAuthStore } from "@/stores/authStore";
import { countPlatformsByFreshness } from "@/lib/platformStatus";
import { useEffect, useState, useCallback } from "react";
import { useKeyboard } from "@/hooks/useKeyboard";
import ThemeToggle from "@/components/ui/ThemeToggle";
import KeyboardShortcutHint from "@/components/ui/KeyboardShortcutHint";
import LiveDot from "@/components/ui/LiveDot";

const NAV = [
  { href: "/", label: "대시보드", icon: "◈" },
  { href: "/platforms", label: "플랫폼", icon: "▲" },
  { href: "/zones", label: "구역", icon: "▦" },
  { href: "/alerts", label: "경보", icon: "⚡" },
  { href: "/agents", label: "에이전트", icon: "⬡" },
  { href: "/reports", label: "리포트", icon: "📋" },
  { href: "/events", label: "이벤트", icon: "📊" },
];

export default function NavBar() {
  const router = useRouter();
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

  // 단축키 오버레이 상태
  const [showShortcuts, setShowShortcuts] = useState(false);

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

  // 단축키 시스템
  useKeyboard({
    onOpenShortcuts: () => setShowShortcuts(true),
    onNavigateToPage: (pageIndex) => {
      const pages = ["/", "/platforms", "/alerts", "/agents", "/reports"];
      const target = pages[pageIndex - 1];
      if (target) router.push(target);
    },
  });

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
    <>
      <header className="flex min-h-14 flex-shrink-0 flex-wrap items-center gap-3 border-b border-ocean-800/80 bg-[linear-gradient(180deg,rgba(4,20,40,0.96),rgba(4,20,40,0.82))] px-3 py-2 backdrop-blur-sm lg:flex-nowrap lg:gap-6 lg:px-4">
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
      <nav className="order-3 flex w-full items-center gap-1 overflow-x-auto rounded-full border border-ocean-800/80 bg-ocean-950/45 px-1 py-1 lg:order-none lg:w-auto" aria-label="주요 메뉴">
        {NAV.map(({ href, label, icon }) => {
          const isActive =
            href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs transition-colors ${
                isActive
                  ? "bg-ocean-700 text-ocean-100 shadow-[0_8px_24px_rgba(2,13,26,0.24)]"
                  : "text-ocean-500 hover:text-ocean-300 hover:bg-ocean-800/50"
              }`}
            >
              <span>{icon}</span>
              <span className="whitespace-nowrap">{label}</span>
              {href === "/alerts" && newAlerts > 0 && (
                <span
                  className={`ml-0.5 px-1 rounded-full text-xs font-bold animate-pulse-slow ${
                    criticalCount > 0
                      ? "bg-red-500 text-white shadow-[0_0_8px_rgba(239,68,68,0.6)]"
                      : "bg-amber-500/90 text-black"
                  }`}
                >
                  {newAlerts}
                </span>
              )}
              {href === "/agents" && aiLogs.length > 0 && (
                <span className="ml-0.5 w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block animate-pulse-slow" />
              )}
            </Link>
          );
        })}
      </nav>

      {/* 우측 상태 */}
        <div className="ml-auto flex items-center gap-2 text-xs lg:gap-3">
          <div className="hidden xl:flex items-center gap-2 rounded-full border border-ocean-800/80 bg-ocean-950/45 px-3 py-1.5 text-ocean-400">
             <span className="font-mono text-ocean-200">
              {platformValues.length}
             </span>
            <span>척 관제</span>
          </div>
          {freshness.stale > 0 && (
            <div className="hidden lg:block text-amber-300">지연 {freshness.stale}</div>
          )}
          {freshness.lost > 0 && (
            <div className="hidden lg:block text-red-300">유실 {freshness.lost}</div>
          )}
          {criticalCount > 0 && (
            <div className="flex items-center gap-1 rounded-full border border-red-500/25 bg-red-500/10 px-3 py-1 text-red-400 font-bold animate-pulse-slow">
              <span>⚠</span>
              <span>CRITICAL {criticalCount}</span>
            </div>
          )}
          <div className="hidden sm:flex items-center gap-1.5 rounded-full border border-ocean-800/80 bg-ocean-950/45 px-3 py-1.5" title={streamSummary} aria-label={streamSummary}>
            {allStreamsConnected ? (
              <LiveDot color="emerald" size="sm" />
            ) : (
              <div className="w-1.5 h-1.5 rounded-full bg-amber-400" />
            )}
            <span className="text-ocean-400">{allStreamsConnected ? "LIVE" : "DEGRADED"}</span>
          </div>
         <button
            onClick={toggleSound}
           title={soundEnabled ? "경보음 켜짐 — 클릭하여 끄기" : "경보음 꺼짐 — 클릭하여 켜기"}
           aria-pressed={soundEnabled}
           className={`text-sm p-2 rounded-lg hover:bg-ocean-800/50 transition-colors ${soundEnabled ? "text-ocean-300 hover:text-ocean-100" : "text-ocean-600 hover:text-ocean-400"}`}
          >
            {soundEnabled ? "🔔" : "🔕"}
          </button>
          <ThemeToggle compact />
          <button
            onClick={() => setShowShortcuts(true)}
            title="단축키 보기 (? 또는 누르기)"
            className="text-sm p-2 rounded-lg hover:bg-ocean-800/50 transition-colors text-ocean-300 hover:text-ocean-100"
          >
            ⌨️
          </button>
          {actor && role && (
             <div className="hidden lg:flex items-center gap-2 rounded-full border border-ocean-800/80 bg-ocean-950/45 px-3 py-1.5 text-[11px]">
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
          <span className="text-ocean-400 font-mono hidden xl:block">{now}</span>
        </div>
      </header>

      {/* 단축키 오버레이 */}
      <KeyboardShortcutHint
        isOpen={showShortcuts}
        onClose={() => setShowShortcuts(false)}
      />
    </>
  );
}
