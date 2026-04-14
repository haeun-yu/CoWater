"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useEventWebSocket } from "@/hooks/useEventWebSocket";
import { useInitialData } from "@/hooks/useInitialData";
import { useAlertNotifications } from "@/hooks/useAlertNotifications";
import NavBar from "@/components/layout/NavBar";
import AppErrorBoundary from "@/components/system/AppErrorBoundary";
import ToastOverlay from "@/components/ui/ToastOverlay";
import ChatDrawer from "@/components/chat/ChatDrawer";
import { useAuthStore } from "@/stores/authStore";

export default function AppProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const status = useAuthStore((s) => s.status);
  const initialized = useAuthStore((s) => s.initialized);
  const initialize = useAuthStore((s) => s.initialize);

  useWebSocket();
  useEventWebSocket();
  useInitialData();
  useAlertNotifications();

  useEffect(() => {
    void initialize();
  }, [initialize]);

  useEffect(() => {
    if (!initialized) return;
    if (status === "unauthenticated" && pathname !== "/login") {
      router.replace("/login");
    }
    if (status === "authenticated" && pathname === "/login") {
      router.replace("/");
    }
  }, [initialized, pathname, router, status]);

  if (pathname === "/login") {
    return <>{children}</>;
  }

  if (!initialized || status !== "authenticated") {
    return (
      <div className="flex min-h-screen flex-1 items-center justify-center bg-[radial-gradient(circle_at_top,rgba(11,47,87,0.35),rgba(2,13,26,0.96)_55%)] text-slate-300">
        <div className="rounded-2xl border border-ocean-800/70 bg-ocean-950/60 px-6 py-5 text-center shadow-[0_18px_50px_rgba(0,0,0,0.32)]">
          <div className="page-kicker">System access</div>
          <div className="mt-2 text-sm text-ocean-100">권한을 확인하는 중입니다...</div>
          <div className="mt-1 text-xs text-ocean-400">세션과 운영 권한을 동기화하고 있습니다.</div>
        </div>
      </div>
    );
  }

  return (
    <>
      <NavBar />
      <main className="flex-1 overflow-hidden" role="main" aria-label="해양 관제 메인 화면">
        <AppErrorBoundary>{children}</AppErrorBoundary>
      </main>
      <ToastOverlay />
      <ChatDrawer />
    </>
  );
}
