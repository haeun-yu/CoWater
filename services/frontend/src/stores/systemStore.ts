import { create } from "zustand";

export type StreamKey = "position" | "alert";
export type StreamStatus = "connecting" | "connected" | "reconnecting" | "error";
export type InitialDataKey = "platforms" | "alerts" | "zones";
export type InitialDataStatus = "idle" | "loading" | "ready" | "error";

export interface StreamState {
  status: StreamStatus;
  reconnectAttempt: number;
  lastMessageAt: string | null;
  lastConnectedAt: string | null;
  lastError: string | null;
}

export interface InitialDataState {
  status: InitialDataStatus;
  lastLoadedAt: string | null;
  lastError: string | null;
}

interface SystemStore {
  streams: Record<StreamKey, StreamState>;
  initialData: Record<InitialDataKey, InitialDataState>;
  setStreamStatus: (
    key: StreamKey,
    status: StreamStatus,
    options?: { reconnectAttempt?: number; error?: string | null },
  ) => void;
  markStreamMessage: (key: StreamKey) => void;
  setInitialDataStatus: (
    key: InitialDataKey,
    status: InitialDataStatus,
    options?: { error?: string | null },
  ) => void;
}

const createInitialStreamState = (): StreamState => ({
  status: "connecting",
  reconnectAttempt: 0,
  lastMessageAt: null,
  lastConnectedAt: null,
  lastError: null,
});

const createInitialDataState = (): InitialDataState => ({
  status: "idle",
  lastLoadedAt: null,
  lastError: null,
});

export const useSystemStore = create<SystemStore>((set) => ({
  streams: {
    position: createInitialStreamState(),
    alert: createInitialStreamState(),
  },
  initialData: {
    platforms: createInitialDataState(),
    alerts: createInitialDataState(),
    zones: createInitialDataState(),
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

  setInitialDataStatus: (key, status, options) =>
    set((state) => ({
      initialData: {
        ...state.initialData,
        [key]: {
          ...state.initialData[key],
          status,
          lastLoadedAt:
            status === "ready" ? new Date().toISOString() : state.initialData[key].lastLoadedAt,
          lastError:
            options && "error" in options ? options.error ?? null : state.initialData[key].lastError,
        },
      },
    })),
}));
