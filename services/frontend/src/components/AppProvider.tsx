"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useWebSocket } from "@/hooks/useWebSocket";
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
      <div className="flex-1 min-h-screen flex items-center justify-center bg-slate-950 text-slate-300 text-sm">
        권한을 확인하는 중입니다...
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
