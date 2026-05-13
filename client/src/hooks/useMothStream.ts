import { useEffect, useRef, useState, useCallback } from 'react';

export interface DeviceStreamData {
  device_id: string | number;
  agent_id?: string;
  status?: string;
  battery_percent?: number | null;
  latitude?: number | null;
  longitude?: number | null;
  layer?: string;
  timestamp?: string;
  last_updated: number;
}

export type DeviceStreamMap = Map<string, DeviceStreamData>;

const MOTH_URL = 'wss://cobot.center:8287/pang/ws/meb?channel=instant&name=agents&source=browser&track=browser';
const PING_INTERVAL_MS = 10_000;
const PING_BYTES = new Uint8Array([0x70, 0x69, 0x6e, 0x67]); // "ping"

export function useMothStream() {
  const [streamMap, setStreamMap] = useState<DeviceStreamMap>(new Map());
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const pingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const parsePayload = useCallback((raw: unknown): DeviceStreamData | null => {
    try {
      const msg = typeof raw === 'string' ? JSON.parse(raw) : raw;
      if (!msg || msg.type !== 'publish') return null;

      let payload = msg.payload;
      // Handle DEVICE_HEALTHCHECK wrapper
      if (payload?.event_type === 'DEVICE_HEALTHCHECK') {
        payload = payload.payload;
      }
      if (!payload?.device_id) return null;

      return {
        device_id: payload.device_id,
        agent_id: payload.agent_id,
        status: payload.status,
        battery_percent: payload.battery_percent ?? null,
        latitude: payload.latitude ?? null,
        longitude: payload.longitude ?? null,
        layer: payload.layer,
        timestamp: payload.timestamp,
        last_updated: Date.now(),
      };
    } catch {
      return null;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    const connect = () => {
      if (cancelled) return;
      const ws = new WebSocket(MOTH_URL);
      ws.binaryType = 'arraybuffer';
      wsRef.current = ws;

      ws.onopen = () => {
        if (cancelled) { ws.close(); return; }
        setConnected(true);
        ws.send(JSON.stringify({
          type: 'subscribe',
          channel: 'agents',
          channel_type: 'meb',
        }));
        pingRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(PING_BYTES);
          }
        }, PING_INTERVAL_MS);
      };

      ws.onmessage = (event) => {
        if (typeof event.data !== 'string') return;
        const data = parsePayload(event.data);
        if (!data) return;
        const key = String(data.device_id);
        setStreamMap(prev => {
          const next = new Map(prev);
          next.set(key, { ...prev.get(key), ...data });
          return next;
        });
      };

      ws.onclose = () => {
        setConnected(false);
        if (pingRef.current) clearInterval(pingRef.current);
        if (!cancelled) setTimeout(connect, 3_000);
      };

      ws.onerror = () => ws.close();
    };

    connect();

    return () => {
      cancelled = true;
      if (pingRef.current) clearInterval(pingRef.current);
      wsRef.current?.close();
    };
  }, [parsePayload]);

  return { streamMap, connected };
}
