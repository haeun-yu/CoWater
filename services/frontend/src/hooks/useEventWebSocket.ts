"use client";

import { useEffect } from "react";
import { getCoreWsUrl } from "@/lib/publicUrl";
import { useEventStore } from "@/stores/eventStore";
import { useSystemStore } from "@/stores/systemStore";
import { useToastStore } from "@/stores/toastStore";
import {
  WS_RECONNECT_DELAY_MS,
  WS_RECONNECT_MAX_DELAY_MS,
  WS_PING_INTERVAL_MS,
} from "@/config";

type ManagedWsHandlers = {
  onMessage: (data: unknown) => void;
  onOpen?: () => void;
  onDisconnect?: (reconnectAttempt: number) => void;
  onError?: (event: Event) => void;
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
      console.log(`[WS] events connected: ${url}`);
      pingTimer = setInterval(() => {
        if (ws?.readyState === WebSocket.OPEN) ws.send("ping");
      }, WS_PING_INTERVAL_MS);
    };
    ws.onerror = (event) => {
      handlers.onError?.(event);
      console.error(`[WS] events error: ${url}`, event);
    };
    ws.onclose = () => {
      clearPing();
      if (!disposed) {
        handlers.onDisconnect?.(reconnectAttempt + 1);
        console.warn(`[WS] events disconnected: ${url}, reconnecting...`);
        scheduleReconnect();
      }
    };
    ws.onmessage = (event) => {
      if (typeof event.data !== "string") return;

      try {
        const message = JSON.parse(event.data);
        handlers.onMessage(message);
      } catch (error) {
        console.error("[WS] failed to parse event:", error);
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

export function useEventWebSocket() {
  const addEvent = useEventStore((s) => s.addEvent);
  const toastPush = useToastStore((s) => s.push);

  useEffect(() => {
    const dispose = createManagedWs(`${getCoreWsUrl()}/ws/events`, {
      onOpen: () => {
        console.log("[WS] Event stream connected");
      },
      onDisconnect: (reconnectAttempt) => {
        console.warn(`[WS] Event stream disconnected (attempt ${reconnectAttempt})`);
      },
      onError: () => {
        console.error("[WS] Event stream error");
      },
      onMessage: (data) => {
        try {
          const msg = data as {
            type: string;
            channel: string;
            event?: Record<string, unknown>;
          };

          if (msg.type === "event" && msg.event) {
            const event = msg.event as {
              flow_id: string;
              event_id: string;
              type: string;
              agent_id: string;
              payload?: Record<string, unknown>;
              causation_id?: string;
              timestamp?: number;
            };

            addEvent({
              id: event.event_id || Math.random().toString(36),
              channel: msg.channel || "",
              type: event.type || "",
              timestamp: event.timestamp || Date.now(),
              flow_id: event.flow_id || "",
              event_id: event.event_id || "",
              agent_id: event.agent_id || "",
              payload: event.payload || {},
              causation_id: event.causation_id,
            });

            // Show toast for critical events
            if (
              event.type?.includes("detect") &&
              event.payload?.severity === "critical"
            ) {
              const platform = event.payload?.platform_name || "Unknown";
              toastPush({
                severity: "critical",
                agentName: event.agent_id || "Detection",
                alertType: event.type,
                message: `Critical event: ${platform}`,
                platformIds: [],
              });
            }
          }
        } catch (error) {
          console.error("[event-ws] message handling error:", error);
        }
      },
    });

    return () => {
      dispose();
    };
  }, [addEvent, toastPush]);
}
