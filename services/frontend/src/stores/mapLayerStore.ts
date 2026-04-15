import { create } from "zustand";

export interface MapLayerState {
  // 기본 레이어
  showSeamark: boolean;
  showZones: boolean;
  showPlatforms: boolean;
  showTrails: boolean;
  showNavAids: boolean;

  // 플랫폼 타입별 가시성
  visiblePlatformTypes: Record<string, boolean>;

  // 구역 타입별 가시성
  visibleZoneTypes: Record<string, boolean>;

  // 항적 길이 (포인트 개수)
  trailLength: number;

  // Actions
  toggleLayer: (layer: "seamark" | "zones" | "platforms" | "trails" | "navAids") => void;
  togglePlatformType: (type: string) => void;
  toggleZoneType: (type: string) => void;
  setTrailLength: (length: number) => void;
  resetToDefaults: () => void;
}

export const useMapLayerStore = create<MapLayerState>((set) => ({
  showSeamark: true,
  showZones: true,
  showPlatforms: true,
  showTrails: true,
  showNavAids: false,

  visiblePlatformTypes: {
    vessel: true,
    usv: true,
    rov: true,
    auv: true,
    drone: true,
    buoy: true,
  },

  visibleZoneTypes: {
    prohibited: true,
    restricted: true,
    caution: true,
  },

  trailLength: 50,

  toggleLayer: (layer) =>
    set((state) => {
      const layerMap = {
        seamark: "showSeamark",
        zones: "showZones",
        platforms: "showPlatforms",
        trails: "showTrails",
        navAids: "showNavAids",
      };
      return {
        [layerMap[layer]]: !state[layerMap[layer] as keyof MapLayerState],
      };
    }),

  togglePlatformType: (type) =>
    set((state) => ({
      visiblePlatformTypes: {
        ...state.visiblePlatformTypes,
        [type]: !state.visiblePlatformTypes[type],
      },
    })),

  toggleZoneType: (type) =>
    set((state) => ({
      visibleZoneTypes: {
        ...state.visibleZoneTypes,
        [type]: !state.visibleZoneTypes[type],
      },
    })),

  setTrailLength: (length) => set({ trailLength: Math.max(10, Math.min(200, length)) }),

  resetToDefaults: () =>
    set({
      showSeamark: true,
      showZones: true,
      showPlatforms: true,
      showTrails: true,
      showNavAids: false,
      visiblePlatformTypes: {
        vessel: true,
        usv: true,
        rov: true,
        auv: true,
        drone: true,
        buoy: true,
      },
      visibleZoneTypes: {
        prohibited: true,
        restricted: true,
        caution: true,
      },
      trailLength: 50,
    }),
}));
