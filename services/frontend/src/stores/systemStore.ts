import { create } from "zustand";

export type StreamKey = "position" | "alert";
export type StreamStatus = "connecting" | "connected" | "reconnecting" | "error";

export interface StreamState {
  status: StreamStatus;
  reconnectAttempt: number;
  lastMessageAt: string | null;
  lastConnectedAt: string | null;
  lastError: string | null;
}

interface SystemStore {
  streams: Record<StreamKey, StreamState>;
  setStreamStatus: (
    key: StreamKey,
    status: StreamStatus,
    options?: { reconnectAttempt?: number; error?: string | null },
  ) => void;
  markStreamMessage: (key: StreamKey) => void;
}

const createInitialStreamState = (): StreamState => ({
  status: "connecting",
  reconnectAttempt: 0,
  lastMessageAt: null,
  lastConnectedAt: null,
  lastError: null,
});

export const useSystemStore = create<SystemStore>((set) => ({
  streams: {
    position: createInitialStreamState(),
    alert: createInitialStreamState(),
  },

  setStreamStatus: (key, status, options) =>
    set((state) => ({
      streams: {
        ...state.streams,
        [key]: {
          ...state.streams[key],
          status,
          reconnectAttempt: options?.reconnectAttempt ?? state.streams[key].reconnectAttempt,
          lastConnectedAt:
            status === "connected"
              ? new Date().toISOString()
              : state.streams[key].lastConnectedAt,
          lastError:
            options && "error" in options ? options.error ?? null : state.streams[key].lastError,
        },
      },
    })),

  markStreamMessage: (key) =>
    set((state) => ({
      streams: {
        ...state.streams,
        [key]: {
          ...state.streams[key],
          lastMessageAt: new Date().toISOString(),
        },
      },
    })),
}));
