"use client";

import { useEffect, useRef } from "react";
import { usePlatformStore } from "@/stores/platformStore";
import { useAlertStore } from "@/stores/alertStore";
import type { WsMessage } from "@/types";

const WS_URL =
  process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";

const RECONNECT_DELAY_MS = 3000;

function createWs(path: string, onMessage: (msg: WsMessage) => void) {
  const ws = new WebSocket(`${WS_URL}${path}`);

  ws.onopen = () => console.log(`[WS] connected: ${path}`);
  ws.onclose = () => {
    console.warn(`[WS] disconnected: ${path}, reconnecting...`);
    setTimeout(() => createWs(path, onMessage), RECONNECT_DELAY_MS);
  };
  ws.onerror = (e) => console.error(`[WS] error: ${path}`, e);
  ws.onmessage = (e) => {
    try {
      const msg: WsMessage = JSON.parse(e.data);
      onMessage(msg);
    } catch {
      // ignore malformed
    }
  };

  // keep-alive ping
  const ping = setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) ws.send("ping");
  }, 20_000);
  ws.addEventListener("close", () => clearInterval(ping));

  return ws;
}

export function useWebSocket() {
  const upsert = usePlatformStore((s) => s.upsert);
  const addAlert = useAlertStore((s) => s.addAlert);
  const initialized = useRef(false);

  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;

    // 플랫폼 위치 스트림
    createWs("/ws/platforms", (msg) => {
      if (msg.type === "position_update") {
        upsert({
          platform_id: msg.platform_id,
          lat: msg.lat,
          lon: msg.lon,
          sog: msg.sog,
          cog: msg.cog,
          heading: msg.heading,
          nav_status: msg.nav_status,
          last_seen: msg.timestamp,
        });
      }
    });

    // 경보 스트림
    createWs("/ws/alerts", (msg) => {
      if (msg.type === "alert_created") {
        addAlert({
          alert_id: msg.alert_id,
          alert_type: msg.alert_type,
          severity: msg.severity,
          status: msg.status,
          platform_ids: msg.platform_ids,
          zone_id: msg.zone_id,
          generated_by: msg.generated_by,
          message: msg.message,
          recommendation: msg.recommendation,
          metadata: msg.metadata,
          created_at: msg.created_at,
          acknowledged_at: msg.acknowledged_at,
          resolved_at: msg.resolved_at,
        });
      }
    });
  }, [upsert, addAlert]);
}
