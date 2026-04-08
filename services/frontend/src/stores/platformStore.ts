import { create } from "zustand";
import type { PlatformState } from "@/types";

interface PlatformStore {
  platforms: Record<string, PlatformState>;
  selectedId: string | null;

  upsert: (update: Partial<PlatformState> & { platform_id: string }) => void;
  select: (id: string | null) => void;
  setAll: (platforms: PlatformState[]) => void;
}

export const usePlatformStore = create<PlatformStore>((set) => ({
  platforms: {},
  selectedId: null,

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
}));
