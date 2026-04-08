"use client";

import { useEffect } from "react";
import { usePlatformStore } from "@/stores/platformStore";
import { useAlertStore } from "@/stores/alertStore";
import { useZoneStore, type Zone } from "@/stores/zoneStore";
import type { Alert, PlatformState } from "@/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7700";

export function useInitialData() {
  const upsert = usePlatformStore((s) => s.upsert);
  const setAlerts = useAlertStore((s) => s.setAll);
  const setZones = useZoneStore((s) => s.setZones);

  useEffect(() => {
    // 초기 플랫폼 메타데이터 로드 — setAll 대신 upsert로 병합
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

    // 구역 목록 로드 (활성+비활성 모두)
    fetch(`${API_URL}/zones?active_only=false`)
      .then((r) => r.json())
      .then((data: Zone[]) => setZones(data))
      .catch(() => {});
  }, [upsert, setAlerts, setZones]);
}
