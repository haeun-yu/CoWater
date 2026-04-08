"use client";

import { useEffect } from "react";
import { usePlatformStore } from "@/stores/platformStore";
import { useAlertStore } from "@/stores/alertStore";
import { useAILogStore, isAIAgent, type ActivityLogEntry } from "@/stores/aiLogStore";
import { useToastStore } from "@/stores/toastStore";
import type { WsMessage, PlatformType } from "@/types";
import {
  WS_RECONNECT_DELAY_MS,
  WS_RECONNECT_MAX_DELAY_MS,
  WS_PING_INTERVAL_MS,
} from "@/config";

const POSITION_WS_URL = process.env.NEXT_PUBLIC_POSITION_WS_URL ?? "ws://localhost:7703";
const CORE_WS_URL     = process.env.NEXT_PUBLIC_WS_URL           ?? "ws://localhost:7700";

const AGENT_NAMES: Record<string, string> = {
  "cpa-agent":      "CPA/TCPA Agent",
  "zone-monitor":   "Zone Monitor",
  "anomaly-rule":   "Anomaly Rule",
  "anomaly-ai":     "Anomaly AI",
  "distress-agent": "Distress Agent",
  "report-agent":   "Report Agent",
};

function createManagedWs(url: string, onMessage: (data: unknown) => void) {
  let ws: WebSocket | null = null;
  let pingTimer: ReturnType<typeof setInterval> | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let reconnectAttempt = 0;
  let disposed = false;

  const clearPing = () => {
    if (pingTimer !== null) {
      clearInterval(pingTimer);
      pingTimer = null;
    }
  };

  const clearReconnect = () => {
    if (reconnectTimer !== null) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  };

  const scheduleReconnect = () => {
    if (disposed) return;
    const delay = Math.min(
      WS_RECONNECT_DELAY_MS * 2 ** reconnectAttempt,
      WS_RECONNECT_MAX_DELAY_MS,
    );
    reconnectAttempt += 1;
    reconnectTimer = setTimeout(connect, delay);
  };

  const connect = () => {
    if (disposed) return;

    ws = new WebSocket(url);
    ws.onopen = () => {
      reconnectAttempt = 0;
      clearReconnect();
      console.log(`[WS] connected: ${url}`);
      pingTimer = setInterval(() => {
        if (ws?.readyState === WebSocket.OPEN) ws.send("ping");
      }, WS_PING_INTERVAL_MS);
    };
    ws.onerror = (event) => {
      console.error(`[WS] error: ${url}`, event);
    };
    ws.onclose = () => {
      clearPing();
      if (!disposed) {
        console.warn(`[WS] disconnected: ${url}, reconnecting...`);
        scheduleReconnect();
      }
    };
    ws.onmessage = (event) => {
      try {
        onMessage(JSON.parse(event.data));
      } catch {
      }
    };
  };

  connect();

  return () => {
    disposed = true;
    clearReconnect();
    clearPing();
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
      ws.close();
    }
  };
}

export function useWebSocket() {
  const upsert      = usePlatformStore((s) => s.upsert);
  const addAlert    = useAlertStore((s) => s.addAlert);
  const updateAlert = useAlertStore((s) => s.updateAlert);
  const addLog      = useAILogStore((s) => s.addLog);
  const updateLog   = useAILogStore((s) => s.updateLog);
  const toastPush   = useToastStore((s) => s.push);

  useEffect(() => {
    const disposePosition = createManagedWs(POSITION_WS_URL + "/ws/positions", (data) => {
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

    const disposeAlerts = createManagedWs(CORE_WS_URL + "/ws/alerts", (data) => {
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
      const meta = (msg.metadata ?? {}) as Record<string, unknown>;
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
        model:        (meta.ai_model as string) ?? null,
        metadata:     meta,
      };

      if (msg.type === "alert_created") {
        addLog(logEntry);
        // 신규 경보 toast 알림
        toastPush({
          severity:    msg.severity as "critical" | "warning" | "info",
          agentName:   AGENT_NAMES[msg.generated_by] ?? msg.generated_by,
          alertType:   msg.alert_type,
          message:     msg.message,
          platformIds: msg.platform_ids,
        });
      } else {
        updateLog(logEntry);
      }
    });

    return () => {
      disposePosition();
      disposeAlerts();
    };
  }, [upsert, addAlert, updateAlert, addLog, updateLog, toastPush]);
}
