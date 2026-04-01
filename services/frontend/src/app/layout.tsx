import type { Metadata } from "next";
import "./globals.css";
import AppProvider from "@/components/AppProvider";

export const metadata: Metadata = {
  title: "CoWater — Maritime Operations",
  description: "연안 해양 통합 관제 플랫폼",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko" suppressHydrationWarning>
      <body suppressHydrationWarning className="h-screen flex flex-col overflow-hidden">
        <AppProvider>{children}</AppProvider>
      </body>
    </html>
  );
}
