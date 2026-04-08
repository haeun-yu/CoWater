import { create } from "zustand";
import type { PlatformState } from "@/types";

type LonLat = [number, number];

interface HistoryOverride {
  platformId: string;
  points: LonLat[];
  from: string;
  to: string;
}

interface PlatformStore {
  platforms: Record<string, PlatformState>;
  selectedId: string | null;
  historyOverride: HistoryOverride | null;

  upsert: (update: Partial<PlatformState> & { platform_id: string }) => void;
  select: (id: string | null) => void;
  setAll: (platforms: PlatformState[]) => void;
  setHistoryOverride: (o: HistoryOverride | null) => void;
}

export const usePlatformStore = create<PlatformStore>((set) => ({
  platforms: {},
  selectedId: null,
  historyOverride: null,

  upsert: (update) =>
    set((state) => ({
      platforms: {
        ...state.platforms,
        [update.platform_id]: {
          ...(state.platforms[update.platform_id] ?? {}),
          ...update,
        } as PlatformState,
      },
    })),

  select: (id) => set({ selectedId: id }),

  setAll: (platforms) =>
    set({
      platforms: Object.fromEntries(platforms.map((p) => [p.platform_id, p])),
    }),

  setHistoryOverride: (o) => set({ historyOverride: o }),
}));
