"use client";

import { useEffect, useRef } from "react";
import { usePlatformStore } from "@/stores/platformStore";
import { useAlertStore } from "@/stores/alertStore";
import { useAILogStore, isAIAgent, type ActivityLogEntry } from "@/stores/aiLogStore";
import type { WsMessage, PlatformType } from "@/types";

const POSITION_WS_URL = process.env.NEXT_PUBLIC_POSITION_WS_URL ?? "ws://localhost:7703";
const CORE_WS_URL     = process.env.NEXT_PUBLIC_WS_URL           ?? "ws://localhost:7700";

const RECONNECT_DELAY_MS = 3000;

const AGENT_NAMES: Record<string, string> = {
  "cpa-agent":      "CPA/TCPA Agent",
  "zone-monitor":   "Zone Monitor",
  "anomaly-rule":   "Anomaly Rule",
  "anomaly-ai":     "Anomaly AI",
  "distress-agent": "Distress Agent",
  "report-agent":   "Report Agent",
};

function createWs(url: string, onMessage: (data: unknown) => void) {
  const ws = new WebSocket(url);
  ws.onopen  = () => console.log(`[WS] connected: ${url}`);
  ws.onclose = () => {
    console.warn(`[WS] disconnected: ${url}, reconnecting...`);
    setTimeout(() => createWs(url, onMessage), RECONNECT_DELAY_MS);
  };
  ws.onerror   = (e) => console.error(`[WS] error: ${url}`, e);
  ws.onmessage = (e) => {
    try { onMessage(JSON.parse(e.data)); } catch { /* ignore */ }
  };
  const ping = setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) ws.send("ping");
  }, 20_000);
  ws.addEventListener("close", () => clearInterval(ping));
  return ws;
}

export function useWebSocket() {
  const upsert      = usePlatformStore((s) => s.upsert);
  const addAlert    = useAlertStore((s) => s.addAlert);
  const updateAlert = useAlertStore((s) => s.updateAlert);
  const addLog      = useAILogStore((s) => s.addLog);
  const updateLog   = useAILogStore((s) => s.updateLog);
  const initialized = useRef(false);

  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;

    // 위치 스트림 — moth-bridge 직접
    createWs(POSITION_WS_URL + "/ws/positions", (data) => {
      const msg = data as {
        type: string; platform_id: string; platform_type?: PlatformType;
        name?: string; timestamp: string; lat: number; lon: number;
        sog: number | null; cog: number | null; heading: number | null; nav_status: string | null;
      };
      if (msg.type === "position_update") {
        upsert({
          platform_id: msg.platform_id,
          ...(msg.platform_type && { platform_type: msg.platform_type }),
          ...(msg.name && { name: msg.name }),
          lat: msg.lat, lon: msg.lon, sog: msg.sog,
          cog: msg.cog, heading: msg.heading,
          nav_status: msg.nav_status, last_seen: msg.timestamp,
        });
      }
    });

    // 경보 스트림 — core
    createWs(CORE_WS_URL + "/ws/alerts", (data) => {
      const msg = data as WsMessage;
      if (msg.type !== "alert_created" && msg.type !== "alert_updated") return;

      const alertData = {
        alert_id:       msg.alert_id,
        alert_type:     msg.alert_type,
        severity:       msg.severity,
        status:         msg.status,
        platform_ids:   msg.platform_ids,
        zone_id:        msg.zone_id,
        generated_by:   msg.generated_by,
        message:        msg.message,
        recommendation: msg.recommendation,
        metadata:       msg.metadata,
        created_at:     msg.created_at,
        acknowledged_at: msg.acknowledged_at,
        resolved_at:    msg.resolved_at,
      };

      if (msg.type === "alert_created") {
        addAlert(alertData);
      } else {
        updateAlert(alertData);
      }

      // 모든 에이전트 활동 로그 (Rule + AI 모두)
      const meta = msg.metadata as Record<string, string> | null ?? {};
      const logEntry: ActivityLogEntry = {
        id:           msg.alert_id,
        timestamp:    msg.created_at,
        agent_id:     msg.generated_by,
        agent_name:   AGENT_NAMES[msg.generated_by] ?? msg.generated_by,
        agent_type:   isAIAgent(msg.generated_by) ? "ai" : "rule",
        alert_type:   msg.alert_type,
        severity:     msg.severity,
        message:      msg.message,
        recommendation: msg.recommendation ?? null,
        platform_ids: msg.platform_ids,
        model:        meta.ai_model ?? null,
      };

      if (msg.type === "alert_created") {
        addLog(logEntry);
      } else {
        updateLog(logEntry);
      }
    });
  }, [upsert, addAlert, updateAlert, addLog, updateLog]);
}
