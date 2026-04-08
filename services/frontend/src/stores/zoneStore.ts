import { create } from "zustand";

export interface Zone {
  zone_id: string;
  name: string;
  zone_type: string;
  geometry: {
    type: string;
    coordinates: number[][][];
  };
  rules: Record<string, unknown>;
  active: boolean;
  created_at: string;
  updated_at: string;
}

interface ZoneStore {
  zones: Zone[];
  setZones: (zones: Zone[]) => void;
}

export const useZoneStore = create<ZoneStore>((set) => ({
  zones: [],
  setZones: (zones) => set({ zones }),
}));

// ── 지도 렌더링용 GeoJSON 헬퍼 ─────────────────────────────────────────────

const TYPE_LABEL: Record<string, string> = {
  prohibited: "금지",
  restricted: "제한",
  caution: "주의",
};

/** 폴리곤 좌표 배열의 단순 무게중심 */
export function computeCentroid(coordinates: number[][][]): [number, number] {
  const ring = coordinates?.[0];
  if (!ring || ring.length === 0) return [0, 0];
  let sumLon = 0;
  let sumLat = 0;
  for (const [lon, lat] of ring) {
    sumLon += lon;
    sumLat += lat;
  }
  return [sumLon / ring.length, sumLat / ring.length];
}

/** 활성 zone → polygon FeatureCollection */
export function buildZoneGeoJSON(zones: Zone[], activeOnly = true) {
  const filtered = activeOnly ? zones.filter((z) => z.active) : zones;
  return {
    type: "FeatureCollection" as const,
    features: filtered.map((z) => ({
      type: "Feature" as const,
      id: z.zone_id,
      properties: {
        zone_id: z.zone_id,
        name: z.name,
        zone_type: z.zone_type,
        active: z.active,
      },
      geometry: z.geometry,
    })),
  };
}

/** 활성 zone → 라벨용 Point FeatureCollection (무게중심) */
export function buildZoneLabelGeoJSON(zones: Zone[], activeOnly = true) {
  const filtered = activeOnly ? zones.filter((z) => z.active) : zones;
  return {
    type: "FeatureCollection" as const,
    features: filtered
      .filter((z) => z.geometry?.coordinates)
      .map((z) => ({
        type: "Feature" as const,
        properties: {
          name: z.name,
          type_label: TYPE_LABEL[z.zone_type] ?? z.zone_type,
          zone_type: z.zone_type,
        },
        geometry: {
          type: "Point" as const,
          coordinates: computeCentroid(z.geometry.coordinates),
        },
      })),
  };
}
