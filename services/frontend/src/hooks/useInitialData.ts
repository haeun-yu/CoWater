"use client";

import { useEffect } from "react";
import { usePlatformStore } from "@/stores/platformStore";
import { useAlertStore } from "@/stores/alertStore";
import { useZoneStore, type Zone } from "@/stores/zoneStore";
import { useToastStore } from "@/stores/toastStore";
import { getCoreApiUrl } from "@/lib/publicUrl";
import type { Alert, PlatformState } from "@/types";

export function useInitialData() {
  const upsert = usePlatformStore((s) => s.upsert);
  const setAlerts = useAlertStore((s) => s.setAll);
  const setZones = useZoneStore((s) => s.setZones);
  const toastPush = useToastStore((s) => s.push);

  useEffect(() => {
    const apiUrl = getCoreApiUrl();
    const load = async <T,>(path: string, label: string): Promise<T | null> => {
      try {
        const response = await fetch(`${apiUrl}${path}`);
        if (!response.ok) {
          throw new Error(`${label} request failed: ${response.status}`);
        }
        return response.json() as Promise<T>;
      } catch (error) {
        console.error(`[initial-data] ${label} load failed`, error);
        toastPush({
          severity: "warning",
          agentName: "시스템",
          alertType: label,
          message: `${label} 초기 데이터를 불러오지 못했습니다.`,
          platformIds: [],
        });
        return null;
      }
    };

    void load<PlatformState[]>("/platforms", "플랫폼").then((data) => {
      if (!data) return;
      for (const platform of data) upsert(platform);
    });

    void load<Alert[]>("/alerts?status=new&limit=50", "경보").then((data) => {
      if (data) setAlerts(data);
    });

    void load<Zone[]>("/zones?active_only=false", "구역").then((data) => {
      if (data) setZones(data);
    });
  }, [upsert, setAlerts, setZones, toastPush]);
}
