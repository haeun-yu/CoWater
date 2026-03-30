"use client";

import { useEffect } from "react";
import { usePlatformStore } from "@/stores/platformStore";
import { useAlertStore } from "@/stores/alertStore";
import type { Alert, PlatformState } from "@/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function useInitialData() {
  const setAll = usePlatformStore((s) => s.setAll);
  const setAlerts = useAlertStore((s) => s.setAll);

  useEffect(() => {
    // 초기 플랫폼 목록 로드
    fetch(`${API_URL}/platforms`)
      .then((r) => r.json())
      .then((data: PlatformState[]) => setAll(data))
      .catch(() => {});

    // 초기 경보 목록 로드
    fetch(`${API_URL}/alerts?status=new&limit=50`)
      .then((r) => r.json())
      .then((data: Alert[]) => setAlerts(data))
      .catch(() => {});
  }, [setAll, setAlerts]);
}
