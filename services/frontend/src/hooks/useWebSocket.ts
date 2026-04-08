"use client";

import { useEffect, useRef } from "react";
import { getCoreWsUrl, getPositionWsUrl } from "@/lib/publicUrl";
import { usePlatformStore } from "@/stores/platformStore";
import { useAlertStore } from "@/stores/alertStore";
import { useAILogStore, isAIAgent, type ActivityLogEntry } from "@/stores/aiLogStore";
import { useSystemStore, type StreamKey } from "@/stores/systemStore";
import { useToastStore } from "@/stores/toastStore";
import type { WsMessage, PlatformType } from "@/types";
import {
  WS_RECONNECT_DELAY_MS,
  WS_RECONNECT_MAX_DELAY_MS,
  WS_PING_INTERVAL_MS,
} from "@/config";

const AGENT_NAMES: Record<string, string> = {
  "cpa-agent": "CPA/TCPA Agent",
  "zone-monitor": "Zone Monitor",
  "anomaly-rule": "Anomaly Rule",
  "anomaly-ai": "Anomaly AI",
  "distress-agent": "Distress Agent",
  "report-agent": "Report Agent",
};

type ManagedWsHandlers = {
  onMessage: (data: unknown) => void;
  onOpen?: () => void;
  onDisconnect?: (reconnectAttempt: number) => void;
  onError?: (event: Event) => void;
  onParseError?: (raw: string) => void;
};

function createManagedWs(url: string, handlers: ManagedWsHandlers) {
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
      handlers.onOpen?.();
      console.log(`[WS] connected: ${url}`);
      pingTimer = setInterval(() => {
        if (ws?.readyState === WebSocket.OPEN) ws.send("ping");
      }, WS_PING_INTERVAL_MS);
    };
    ws.onerror = (event) => {
      handlers.onError?.(event);
      console.error(`[WS] error: ${url}`, event);
    };
    ws.onclose = () => {
      clearPing();
      if (!disposed) {
        handlers.onDisconnect?.(reconnectAttempt + 1);
        console.warn(`[WS] disconnected: ${url}, reconnecting...`);
        scheduleReconnect();
      }
    };
    ws.onmessage = (event) => {
      try {
        handlers.onMessage(JSON.parse(event.data));
      } catch {
        handlers.onParseError?.(String(event.data));
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
  const upsert = usePlatformStore((s) => s.upsert);
  const addAlert = useAlertStore((s) => s.addAlert);
  const updateAlert = useAlertStore((s) => s.updateAlert);
  const addLog = useAILogStore((s) => s.addLog);
  const updateLog = useAILogStore((s) => s.updateLog);
  const setStreamStatus = useSystemStore((s) => s.setStreamStatus);
  const markStreamMessage = useSystemStore((s) => s.markStreamMessage);
  const toastPush = useToastStore((s) => s.push);
  const positionIssueShown = useRef(false);
  const alertIssueShown = useRef(false);
  const positionParseShown = useRef(false);
  const alertParseShown = useRef(false);

  useEffect(() => {
    const setConnected = (stream: StreamKey) => {
      setStreamStatus(stream, "connected", { reconnectAttempt: 0, error: null });
    };

    const setDisconnected = (stream: StreamKey, reconnectAttempt: number) => {
      setStreamStatus(stream, "reconnecting", { reconnectAttempt });
    };

    const setErrored = (stream: StreamKey, message: string) => {
      setStreamStatus(stream, "error", { error: message });
    };

    const notifyIssue = (kind: "position" | "alert", message: string) => {
      const ref = kind === "position" ? positionIssueShown : alertIssueShown;
      if (ref.current) return;
      ref.current = true;
      toastPush({
        severity: "warning",
        agentName: "시스템",
        alertType: kind === "position" ? "위치 스트림" : "경보 스트림",
        message,
        platformIds: [],
      });
    };

    const notifyParseIssue = (kind: "position" | "alert") => {
      const ref = kind === "position" ? positionParseShown : alertParseShown;
      if (ref.current) return;
      ref.current = true;
      toastPush({
        severity: "warning",
        agentName: "시스템",
        alertType: kind === "position" ? "위치 스트림" : "경보 스트림",
        message: `${kind === "position" ? "위치" : "경보"} WebSocket 메시지를 해석하지 못했습니다.`,
        platformIds: [],
      });
    };

    const disposePosition = createManagedWs(`${getPositionWsUrl()}/ws/positions`, {
      onOpen: () => {
        positionIssueShown.current = false;
        positionParseShown.current = false;
        setConnected("position");
      },
      onDisconnect: (reconnectAttempt) => {
        setDisconnected("position", reconnectAttempt);
        notifyIssue("position", "위치 스트림 연결이 끊어졌습니다. 자동으로 재연결합니다.");
      },
      onError: () => {
        setErrored("position", "위치 스트림 연결 오류");
        notifyIssue("position", "위치 스트림 연결에 문제가 발생했습니다.");
      },
      onParseError: () => {
        console.error("[ws] failed to parse position payload");
        notifyParseIssue("position");
      },
      onMessage: (data) => {
        const msg = data as {
          type: string;
          platform_id: string;
          platform_type?: PlatformType;
          name?: string;
          timestamp: string;
          lat: number;
          lon: number;
          sog: number | null;
          cog: number | null;
          heading: number | null;
          nav_status: string | null;
        };
        if (msg.type !== "position_update") return;
        markStreamMessage("position");
        upsert({
          platform_id: msg.platform_id,
          ...(msg.platform_type && { platform_type: msg.platform_type }),
          ...(msg.name && { name: msg.name }),
          lat: msg.lat,
          lon: msg.lon,
          sog: msg.sog,
          cog: msg.cog,
          heading: msg.heading,
          nav_status: msg.nav_status,
          last_seen: msg.timestamp,
        });
      },
    });

    const disposeAlerts = createManagedWs(`${getCoreWsUrl()}/ws/alerts`, {
      onOpen: () => {
        alertIssueShown.current = false;
        alertParseShown.current = false;
        setConnected("alert");
      },
      onDisconnect: (reconnectAttempt) => {
        setDisconnected("alert", reconnectAttempt);
        notifyIssue("alert", "경보 스트림 연결이 끊어졌습니다. 자동으로 재연결합니다.");
      },
      onError: () => {
        setErrored("alert", "경보 스트림 연결 오류");
        notifyIssue("alert", "경보 스트림 연결에 문제가 발생했습니다.");
      },
      onParseError: () => {
        console.error("[ws] failed to parse alert payload");
        notifyParseIssue("alert");
      },
      onMessage: (data) => {
        const msg = data as WsMessage;
        if (msg.type !== "alert_created" && msg.type !== "alert_updated") return;
        markStreamMessage("alert");

        const alertData = {
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
        };

        if (msg.type === "alert_created") {
          addAlert(alertData);
        } else {
          updateAlert(alertData);
        }

        const meta = (msg.metadata ?? {}) as Record<string, unknown>;
        const logEntry: ActivityLogEntry = {
          id: msg.alert_id,
          timestamp: msg.created_at,
          agent_id: msg.generated_by,
          agent_name: AGENT_NAMES[msg.generated_by] ?? msg.generated_by,
          agent_type: isAIAgent(msg.generated_by) ? "ai" : "rule",
          alert_type: msg.alert_type,
          severity: msg.severity,
          message: msg.message,
          recommendation: msg.recommendation ?? null,
          platform_ids: msg.platform_ids,
          model: (meta.ai_model as string) ?? null,
          metadata: meta,
        };

        if (msg.type === "alert_created") {
          addLog(logEntry);
          toastPush({
            severity: msg.severity as "critical" | "warning" | "info",
            agentName: AGENT_NAMES[msg.generated_by] ?? msg.generated_by,
            alertType: msg.alert_type,
            message: msg.message,
            platformIds: msg.platform_ids,
          });
        } else {
          updateLog(logEntry);
        }
      },
    });

    return () => {
      disposePosition();
      disposeAlerts();
    };
  }, [upsert, addAlert, updateAlert, addLog, updateLog, toastPush, setStreamStatus, markStreamMessage]);
}
