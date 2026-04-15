"use client";

import { useEffect } from "react";
import { usePlatformStore } from "@/stores/platformStore";
import { useAlertStore } from "@/stores/alertStore";
import { useZoneStore, type Zone } from "@/stores/zoneStore";
import { useSystemStore, type InitialDataKey } from "@/stores/systemStore";
import { useToastStore } from "@/stores/toastStore";
import { getCoreApiUrl } from "@/lib/publicUrl";
import { waitForCoreReady } from "@/lib/coreReady";
import type { Alert, PlatformState } from "@/types";

export function useInitialData() {
  const upsert = usePlatformStore((s) => s.upsert);
  const setAlerts = useAlertStore((s) => s.setAll);
  const setZones = useZoneStore((s) => s.setZones);
  const setInitialDataStatus = useSystemStore((s) => s.setInitialDataStatus);
  const toastPush = useToastStore((s) => s.push);

  useEffect(() => {
    const controller = new AbortController();
    const apiUrl = getCoreApiUrl();
    const load = async <T,>(
      path: string,
      label: string,
      key: InitialDataKey,
    ): Promise<T | null> => {
      setInitialDataStatus(key, "loading", { error: null });
      try {
        for (let attempt = 0; attempt < 3; attempt += 1) {
          const response = await fetch(`${apiUrl}${path}`, {
            cache: "no-store",
            signal: controller.signal,
          });

          if (response.ok) {
            const payload = await (response.json() as Promise<T>);
            setInitialDataStatus(key, "ready", { error: null });
            return payload;
          }

          if (attempt === 2) {
            throw new Error(`${label} request failed: ${response.status}`);
          }

          await new Promise((resolve) => window.setTimeout(resolve, 1000 * (attempt + 1)));
        }

        return null;
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return null;
        }

        console.error(`[initial-data] ${label} load failed`, error);
        setInitialDataStatus(
          key,
          "error",
          { error: error instanceof Error ? error.message : `${label} load failed` },
        );
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

    void (async () => {
      try {
        await waitForCoreReady(controller.signal);
      } catch (error) {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          console.warn("[initial-data] core health check did not complete", error);
        }
        return;
      }

      void load<PlatformState[]>("/platforms", "플랫폼", "platforms").then((data) => {
        if (!data) return;
        for (const platform of data) upsert(platform);
      });

      void load<Alert[]>("/alerts?status=new&limit=50", "경보", "alerts").then((data) => {
        if (data) setAlerts(data);
      });

      void load<Zone[]>("/zones?active_only=false", "구역", "zones").then((data) => {
        if (data) setZones(data);
      });
    })();

    return () => {
      controller.abort();
    };
  }, [upsert, setAlerts, setZones, toastPush, setInitialDataStatus]);
}
