"use client";

import { useEffect } from "react";
import { usePlatformStore } from "@/stores/platformStore";
import { useAlertStore } from "@/stores/alertStore";
import type { Alert, PlatformState } from "@/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function useInitialData() {
  const upsert = usePlatformStore((s) => s.upsert);
  const setAlerts = useAlertStore((s) => s.setAll);

  useEffect(() => {
    // 초기 플랫폼 메타데이터 로드 — setAll 대신 upsert로 병합
    // (WS로 이미 들어온 lat/lon/sog 등 위치 데이터를 덮어쓰지 않기 위함)
    fetch(`${API_URL}/platforms`)
      .then((r) => r.json())
      .then((data: PlatformState[]) => {
        for (const p of data) upsert(p);
      })
      .catch(() => {});

    // 초기 경보 목록 로드
    fetch(`${API_URL}/alerts?status=new&limit=50`)
      .then((r) => r.json())
      .then((data: Alert[]) => setAlerts(data))
      .catch(() => {});
  }, [upsert, setAlerts]);
}
