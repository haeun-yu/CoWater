"use client";

import { useWebSocket } from "@/hooks/useWebSocket";
import { useInitialData } from "@/hooks/useInitialData";
import NavBar from "@/components/layout/NavBar";

export default function AppProvider({ children }: { children: React.ReactNode }) {
  useWebSocket();
  useInitialData();
  return (
    <>
      <NavBar />
      <main className="flex-1 overflow-hidden">
        {children}
      </main>
    </>
  );
}
