"use client";

import { useWebSocket } from "@/hooks/useWebSocket";
import { useInitialData } from "@/hooks/useInitialData";
import NavBar from "@/components/layout/NavBar";
import AppErrorBoundary from "@/components/system/AppErrorBoundary";
import ToastOverlay from "@/components/ui/ToastOverlay";
import ChatDrawer from "@/components/chat/ChatDrawer";

export default function AppProvider({ children }: { children: React.ReactNode }) {
  useWebSocket();
  useInitialData();
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
