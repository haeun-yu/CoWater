"use client";

import { memo, useEffect, useMemo, useRef, useState } from "react";
import maplibregl, { type GeoJSONSource } from "maplibre-gl";
import {
  destination as turfDestination,
  lineString as turfLineString,
  point as turfPoint,
  sector as turfSector,
  simplify as turfSimplify,
} from "@turf/turf";
import { usePlatformStore } from "@/stores/platformStore";
import { useAlertStore } from "@/stores/alertStore";
import { useSystemStore } from "@/stores/systemStore";
import { useZoneStore, buildZoneGeoJSON, buildZoneLabelGeoJSON } from "@/stores/zoneStore";
import type { Alert, PlatformState } from "@/types";
import { getCoreApiUrl } from "@/lib/publicUrl";
import {
  ALERT_HIGHLIGHT_SEVERITY,
  ALERT_TRAIL_COLOR,
  MAP_CENTER,
  MAP_CLUSTER_MAX_ZOOM,
  MAP_GLYPHS_URL,
  MAP_NAV_AID_FETCH_MIN_ZOOM,
  MAP_OPENSEAMAP_ATTRIBUTION,
  MAP_OPENSEAMAP_SEAMARK_TILE_URL,
  MAP_OSM_ATTRIBUTION,
  MAP_OSM_OPACITY,
  MAP_OSM_TILE_URL,
  MAP_SELECT_FLY_DURATION,
  MAP_SELECTED_HEADING_SECTOR_ANGLE_DEG,
  MAP_SELECTED_HEADING_SECTOR_RADIUS_MULTIPLIER,
  MAP_SELECT_MIN_ZOOM,
  MAP_SELECTED_PREDICTION_MINUTES,
  MAP_SELECTED_SAFETY_BUFFER_BASE_NM,
  MAP_SELECTED_SAFETY_SPEED_LOOKAHEAD_MIN,
  MAP_SHIP_LAYER_MIN_ZOOM,
  MAP_TRACK_EASE_DURATION,
  MAP_ZOOM,
  MAP_HISTORY_SIMPLIFY_TOLERANCE_DEGREES,
  OVERPASS_API_URL,
  PLATFORM_COLORS,
  PLATFORM_RENDER_METERS,
  TRAIL_CASING_COLOR,
  TRAIL_CASING_OPACITY_FACTOR,
  TRAIL_CASING_WIDTH,
  TRAIL_LINE_WIDTH,
  TRAIL_MAX,
  TRAIL_MID,
  TRAIL_OPACITY,
  TRAIL_RECENT,
} from "@/config";

const PLATFORM_LABELS: Record<string, string> = {
  vessel: "선박",
  usv: "USV",
  rov: "ROV",
  auv: "AUV",
  drone: "드론",
  buoy: "부이",
};

type LonLat = [number, number];
type PointFeature = {
  type: "Feature";
  geometry: { type: "Point"; coordinates: LonLat };
  properties: Record<string, string | number | boolean | null>;
};
type PolygonFeature = {
  type: "Feature";
  geometry: { type: "Polygon"; coordinates: LonLat[][] };
  properties: Record<string, string | number | boolean | null>;
};

type TrailFeature = {
  type: "Feature";
  geometry: { type: "LineString"; coordinates: LonLat[] };
  properties: { opacity: number; color: string };
};

type LineFeature = {
  type: "Feature";
  geometry: { type: "LineString"; coordinates: LonLat[] };
  properties: Record<string, string | number | boolean | null>;
};

type EncounterOverlayItem = {
  alertId: string;
  counterpartId: string;
  counterpartName: string;
  severity: Alert["severity"];
  cpaNm: number | null;
  tcpaMin: number | null;
  createdAt: string;
};

type EncounterRiskState = {
  severity: Alert["severity"];
  cpaNm: number | null;
  tcpaMin: number | null;
  scale: number;
};

type EncounterProjection = {
  point: LonLat;
  tcpaMin: number;
  cpaNm: number;
};

/** 항적 GeoJSON FeatureCollection 생성 — 3-opacity 밴드
 *
 *  구간 구분 (뒤에서부터):
 *   recent  : 마지막 TRAIL_RECENT개  → opacity 0.82 (불투명)
 *   mid     : 그 이전 구간까지       → opacity 0.38 (반투명)
 *   old     : 나머지 전체            → opacity 0.12 (흐림)
 *
 *  각 밴드 경계에 연결점 1개씩 포함시켜 선이 끊기지 않게 한다.
 */
function buildTrailGeoJSON(
  trails: Map<string, LonLat[]>,
  platforms: Record<string, PlatformState>,
  alertIds: Set<string>,
) {
  const features: TrailFeature[] = [];

  for (const [pid, pts] of trails) {
    if (pts.length < 2) continue;
    const p = platforms[pid];
    const typeColor = PLATFORM_COLORS[p?.platform_type ?? "vessel"]?.top ?? PLATFORM_COLORS.vessel.top;
    const color = alertIds.has(pid) ? ALERT_TRAIL_COLOR : typeColor;

    const len = pts.length;
    // 경계 인덱스 (clamp to valid range)
    const midEnd = Math.max(0, len - TRAIL_RECENT); // recent 시작점
    const oldEnd = Math.max(0, len - TRAIL_MID); // mid 시작점

    // 경계점을 1개씩 포함해 밴드 간 끊김 방지
    const bands: { pts: LonLat[]; opacity: number }[] = [
      { pts: pts.slice(0, oldEnd + 1), opacity: TRAIL_OPACITY.old },
      { pts: pts.slice(oldEnd, midEnd + 1), opacity: TRAIL_OPACITY.mid },
      { pts: pts.slice(midEnd), opacity: TRAIL_OPACITY.recent },
    ];

    for (const band of bands) {
      if (band.pts.length < 2) continue;
      features.push({
        type: "Feature" as const,
        geometry: { type: "LineString" as const, coordinates: band.pts },
        properties: { opacity: band.opacity, color },
      });
    }
  }
  return {
    type: "FeatureCollection" as const,
    features,
  } as maplibregl.GeoJSONSourceSpecification["data"] & object;
}

const NAV_AID_LABELS: Record<string, string> = {
  lighthouse: "등대",
  beacon_lateral: "표지",
  beacon_cardinal: "방위표지",
  buoy_lateral: "부표",
  buoy_cardinal: "방위부표",
};

function toFeatureCollection(features: Array<PointFeature | PolygonFeature | LineFeature>) {
  return { type: "FeatureCollection" as const, features };
}

function emptyFeatureCollection() {
  return { type: "FeatureCollection" as const, features: [] };
}

function nmToKm(value: number) {
  return value * 1.852;
}

function metersToNm(value: number) {
  return value / 1852;
}

function normalizeBearing(value: number) {
  return ((value % 360) + 360) % 360;
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function getPlatformDimensions(platform: PlatformState) {
  const fallback = PLATFORM_RENDER_METERS[platform.platform_type ?? "vessel"] ?? PLATFORM_RENDER_METERS.vessel;
  const length = platform.dimensions?.length_m != null && platform.dimensions.length_m > 0
    ? platform.dimensions.length_m
    : fallback.length;
  const beam = platform.dimensions?.beam_m != null && platform.dimensions.beam_m > 0
    ? platform.dimensions.beam_m
    : fallback.beam;

  return { length, beam };
}

function metersToLon(meters: number, latitude: number) {
  const latRad = (latitude * Math.PI) / 180;
  const metersPerDegreeLon = 111_320 * Math.cos(latRad);
  return meters / Math.max(metersPerDegreeLon, 1);
}

function metersToLat(meters: number) {
  return meters / 110_540;
}

function buildShipPolygon(platform: PlatformState, heading: number, scale = 1) {
  const dimensions = getPlatformDimensions(platform);
  const length = dimensions.length * scale;
  const beam = dimensions.beam * scale;
  const bow = length * 0.5;
  const stern = length * 0.5;
  const halfBeam = beam * 0.5;
  const rad = (heading * Math.PI) / 180;
  const forwardX = Math.sin(rad);
  const forwardY = Math.cos(rad);
  const starboardX = Math.cos(rad);
  const starboardY = -Math.sin(rad);

  const localPoints = [
    { forward: bow, starboard: 0 },
    { forward: bow * 0.2, starboard: halfBeam },
    { forward: -stern, starboard: halfBeam * 0.75 },
    { forward: -stern, starboard: -halfBeam * 0.75 },
    { forward: bow * 0.2, starboard: -halfBeam },
    { forward: bow, starboard: 0 },
  ];

  return localPoints.map((point) => {
    const dxMeters = forwardX * point.forward + starboardX * point.starboard;
    const dyMeters = forwardY * point.forward + starboardY * point.starboard;
    return [
      platform.lon + metersToLon(dxMeters, platform.lat),
      platform.lat + metersToLat(dyMeters),
    ] as LonLat;
  });
}

function buildBridgePolygon(platform: PlatformState, heading: number) {
  const dimensions = getPlatformDimensions(platform);
  const bridgeLength = dimensions.length * 0.18;
  const bridgeBeam = dimensions.beam * 0.42;
  const offsetForward = dimensions.length * 0.02;
  const rad = (heading * Math.PI) / 180;
  const forwardX = Math.sin(rad);
  const forwardY = Math.cos(rad);
  const starboardX = Math.cos(rad);
  const starboardY = -Math.sin(rad);

  const localPoints = [
    { forward: offsetForward + bridgeLength, starboard: bridgeBeam },
    { forward: offsetForward + bridgeLength, starboard: -bridgeBeam },
    { forward: offsetForward, starboard: -bridgeBeam },
    { forward: offsetForward, starboard: bridgeBeam },
    { forward: offsetForward + bridgeLength, starboard: bridgeBeam },
  ];

  return localPoints.map((point) => {
    const dxMeters = forwardX * point.forward + starboardX * point.starboard;
    const dyMeters = forwardY * point.forward + starboardY * point.starboard;
    return [
      platform.lon + metersToLon(dxMeters, platform.lat),
      platform.lat + metersToLat(dyMeters),
    ] as LonLat;
  });
}

function projectOffset(platform: PlatformState, heading: number, forwardMeters: number, starboardMeters: number) {
  const rad = (heading * Math.PI) / 180;
  const forwardX = Math.sin(rad);
  const forwardY = Math.cos(rad);
  const starboardX = Math.cos(rad);
  const starboardY = -Math.sin(rad);
  const dxMeters = forwardX * forwardMeters + starboardX * starboardMeters;
  const dyMeters = forwardY * forwardMeters + starboardY * starboardMeters;

  return [
    platform.lon + metersToLon(dxMeters, platform.lat),
    platform.lat + metersToLat(dyMeters),
  ] as LonLat;
}

function buildShipDomainPolygon(
  platform: PlatformState,
  heading: number,
  extents: { forwardNm: number; aftNm: number; lateralNm: number },
) {
  const coordinates: LonLat[] = [];
  const steps = 48;

  for (let index = 0; index <= steps; index += 1) {
    const theta = (index / steps) * Math.PI * 2;
    const cosTheta = Math.cos(theta);
    const sinTheta = Math.sin(theta);
    const forwardNm = cosTheta >= 0 ? extents.forwardNm * cosTheta : extents.aftNm * cosTheta;
    const starboardNm = extents.lateralNm * sinTheta;
    coordinates.push(projectOffset(platform, heading, forwardNm * 1852, starboardNm * 1852));
  }

  return coordinates;
}

function getAlertSeverityRank(severity: Alert["severity"]) {
  if (severity === "critical") return 3;
  if (severity === "warning") return 2;
  return 1;
}

function getNumericMeta(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function projectEncounterCpaPoint(selected: PlatformState, counterpart: PlatformState) {
  const selectedCog = selected.cog;
  const counterpartCog = counterpart.cog;
  if (
    selected.sog == null
    || counterpart.sog == null
    || selectedCog == null
    || counterpartCog == null
  ) {
    return null;
  }

  const avgLat = (selected.lat + counterpart.lat) / 2;
  const cosLat = Math.cos((avgLat * Math.PI) / 180);
  const dx = (counterpart.lon - selected.lon) * cosLat * 60;
  const dy = (counterpart.lat - selected.lat) * 60;
  const vel = (sog: number, cog: number) => {
    const rad = (cog * Math.PI) / 180;
    return { x: sog * Math.sin(rad) / 60, y: sog * Math.cos(rad) / 60 };
  };

  const v1 = vel(selected.sog, selectedCog);
  const v2 = vel(counterpart.sog, counterpartCog);
  const dvx = v2.x - v1.x;
  const dvy = v2.y - v1.y;
  const dv2 = dvx ** 2 + dvy ** 2;
  if (dv2 < 1e-9) return null;

  const tcpaMin = -((dx * dvx) + (dy * dvy)) / dv2;
  if (!Number.isFinite(tcpaMin) || tcpaMin <= 0) return null;

  const selectedCpaX = v1.x * tcpaMin;
  const selectedCpaY = v1.y * tcpaMin;
  const counterpartCpaX = dx + v2.x * tcpaMin;
  const counterpartCpaY = dy + v2.y * tcpaMin;
  const midpointX = (selectedCpaX + counterpartCpaX) / 2;
  const midpointY = (selectedCpaY + counterpartCpaY) / 2;

  return {
    point: [
      selected.lon + midpointX / Math.max(cosLat * 60, 1e-6),
      selected.lat + midpointY / 60,
    ],
    tcpaMin,
    cpaNm: Math.hypot(counterpartCpaX - selectedCpaX, counterpartCpaY - selectedCpaY),
  } satisfies EncounterProjection;
}

function buildSelectedEncounterItems(
  selectedId: string | null,
  alerts: Alert[],
  platforms: Record<string, PlatformState>,
) {
  if (!selectedId) return [] as EncounterOverlayItem[];

  const deduped = new Map<string, EncounterOverlayItem>();

  for (const alert of alerts) {
    if (alert.alert_type !== "cpa" || alert.status === "resolved" || !alert.platform_ids.includes(selectedId)) {
      continue;
    }

    const counterpartId = alert.platform_ids.find((platformId) => platformId !== selectedId);
    if (!counterpartId) continue;

    const meta = alert.metadata ?? {};
    const item: EncounterOverlayItem = {
      alertId: alert.alert_id,
      counterpartId,
      counterpartName: platforms[counterpartId]?.name || counterpartId,
      severity: alert.severity,
      cpaNm: getNumericMeta(meta.cpa_nm),
      tcpaMin: getNumericMeta(meta.tcpa_min),
      createdAt: alert.created_at,
    };

    const existing = deduped.get(counterpartId);
    if (!existing) {
      deduped.set(counterpartId, item);
      continue;
    }

    const isHigherSeverity = getAlertSeverityRank(item.severity) > getAlertSeverityRank(existing.severity);
    const isNewer = new Date(item.createdAt).getTime() > new Date(existing.createdAt).getTime();
    if (isHigherSeverity || (getAlertSeverityRank(item.severity) === getAlertSeverityRank(existing.severity) && isNewer)) {
      deduped.set(counterpartId, item);
    }
  }

  return [...deduped.values()].sort((left, right) => {
    const severityDelta = getAlertSeverityRank(right.severity) - getAlertSeverityRank(left.severity);
    if (severityDelta !== 0) return severityDelta;
    const leftTcpa = left.tcpaMin ?? Number.POSITIVE_INFINITY;
    const rightTcpa = right.tcpaMin ?? Number.POSITIVE_INFINITY;
    if (leftTcpa !== rightTcpa) return leftTcpa - rightTcpa;
    return right.createdAt.localeCompare(left.createdAt);
  });
}

function buildSelectedEncounterData(
  selectedPlatform: PlatformState | null,
  encounters: EncounterOverlayItem[],
  platforms: Record<string, PlatformState>,
) {
  if (!selectedPlatform) {
    return {
      lines: emptyFeatureCollection(),
      points: emptyFeatureCollection(),
      cpaProjection: emptyFeatureCollection(),
    };
  }

  const lineFeatures: LineFeature[] = [];
  const pointFeatures: PointFeature[] = [];
  const cpaProjectionFeatures: PointFeature[] = [];

  for (const [index, encounter] of encounters.entries()) {
    const counterpart = platforms[encounter.counterpartId];
    if (!counterpart || counterpart.lat == null || counterpart.lon == null) continue;
    const isPrimary = index === 0;

    lineFeatures.push({
      type: "Feature",
      geometry: {
        type: "LineString",
        coordinates: [
          [selectedPlatform.lon, selectedPlatform.lat],
          [counterpart.lon, counterpart.lat],
        ],
      },
      properties: {
        severity: encounter.severity,
        counterpartId: encounter.counterpartId,
        isPrimary,
      },
    });

    pointFeatures.push({
      type: "Feature",
      geometry: { type: "Point", coordinates: [counterpart.lon, counterpart.lat] },
      properties: {
        severity: encounter.severity,
        counterpartId: encounter.counterpartId,
        counterpartName: encounter.counterpartName,
        isPrimary,
      },
    });

    if (isPrimary) {
      const projection = projectEncounterCpaPoint(selectedPlatform, counterpart);
      if (projection) {
        cpaProjectionFeatures.push({
          type: "Feature",
          geometry: { type: "Point", coordinates: projection.point },
          properties: {
            severity: encounter.severity,
            cpa_nm: Number(projection.cpaNm.toFixed(3)),
            tcpa_min: Number(projection.tcpaMin.toFixed(1)),
          },
        });
      }
    }
  }

  return {
    lines: toFeatureCollection(lineFeatures),
    points: toFeatureCollection(pointFeatures),
    cpaProjection: toFeatureCollection(cpaProjectionFeatures),
  };
}

function buildEncounterRiskState(encounters: EncounterOverlayItem[]) {
  if (encounters.length === 0) return null;

  const sorted = [...encounters].sort((left, right) => {
    const severityDelta = getAlertSeverityRank(right.severity) - getAlertSeverityRank(left.severity);
    if (severityDelta !== 0) return severityDelta;
    const leftTcpa = left.tcpaMin ?? Number.POSITIVE_INFINITY;
    const rightTcpa = right.tcpaMin ?? Number.POSITIVE_INFINITY;
    if (leftTcpa !== rightTcpa) return leftTcpa - rightTcpa;
    const leftCpa = left.cpaNm ?? Number.POSITIVE_INFINITY;
    const rightCpa = right.cpaNm ?? Number.POSITIVE_INFINITY;
    return leftCpa - rightCpa;
  });

  const worst = sorted[0];
  const tcpaFactor = worst.tcpaMin == null
    ? 1
    : worst.tcpaMin <= 10
      ? 1.28
      : worst.tcpaMin <= 20
        ? 1.18
        : 1.08;
  const cpaFactor = worst.cpaNm == null
    ? 1
    : worst.cpaNm <= 0.2
      ? 1.24
      : worst.cpaNm <= 0.5
        ? 1.12
        : 1.04;
  const severityBase = worst.severity === "critical" ? 1.26 : 1.12;

  return {
    severity: worst.severity,
    cpaNm: worst.cpaNm,
    tcpaMin: worst.tcpaMin,
    scale: clamp(severityBase * tcpaFactor * cpaFactor, 1.08, 1.75),
  } satisfies EncounterRiskState;
}

function buildSelectedSpatialData(platform: PlatformState | null, encounterRisk: EncounterRiskState | null) {
  if (!platform || platform.lat == null || platform.lon == null) {
    return {
      safetyBuffer: emptyFeatureCollection(),
      dangerBuffer: emptyFeatureCollection(),
      predictedPath: emptyFeatureCollection(),
    };
  }

  const center = turfPoint([platform.lon, platform.lat], { platform_id: platform.platform_id });
  const heading = platform.heading ?? platform.cog;
  const normalizedHeading = heading == null ? null : normalizeBearing(heading);
  const dimensions = getPlatformDimensions(platform);
  const speedKnots = Math.max(platform.sog ?? 0, 0);
  const hullFootprintNm = metersToNm(dimensions.length * 1.2 + dimensions.beam * 0.8);
  const speedAdvanceNm = speedKnots * (MAP_SELECTED_SAFETY_SPEED_LOOKAHEAD_MIN / 60);
  const forwardDomainNm = clamp(
    Math.max(
      MAP_SELECTED_SAFETY_BUFFER_BASE_NM,
      hullFootprintNm + speedAdvanceNm * 1.35 + metersToNm(dimensions.length * 0.35),
    ),
    MAP_SELECTED_SAFETY_BUFFER_BASE_NM,
    4.2,
  );
  const lateralDomainNm = clamp(
    Math.max(
      MAP_SELECTED_SAFETY_BUFFER_BASE_NM * 0.42,
      metersToNm(dimensions.beam * 1.6 + dimensions.length * 0.12) + speedAdvanceNm * 0.28,
    ),
    MAP_SELECTED_SAFETY_BUFFER_BASE_NM * 0.35,
    1.6,
  );
  const aftDomainNm = clamp(
    Math.max(
      MAP_SELECTED_SAFETY_BUFFER_BASE_NM * 0.3,
      metersToNm(dimensions.length * 0.55) + speedAdvanceNm * 0.5,
    ),
    MAP_SELECTED_SAFETY_BUFFER_BASE_NM * 0.28,
    forwardDomainNm * 0.72,
  );

  const safetyBuffer = normalizedHeading == null
    ? emptyFeatureCollection()
    : toFeatureCollection([
        {
          type: "Feature",
          geometry: {
            type: "Polygon",
            coordinates: [[
              ...buildShipDomainPolygon(platform, normalizedHeading, {
                forwardNm: forwardDomainNm,
                aftNm: aftDomainNm,
                lateralNm: lateralDomainNm,
              }),
            ]],
          },
          properties: {
            forward_nm: Number(forwardDomainNm.toFixed(2)),
            lateral_nm: Number(lateralDomainNm.toFixed(2)),
            aft_nm: Number(aftDomainNm.toFixed(2)),
          },
        },
      ]);

  const dangerBuffer = normalizedHeading == null || encounterRisk == null
    ? emptyFeatureCollection()
    : toFeatureCollection([
        {
          type: "Feature",
          geometry: {
            type: "Polygon",
            coordinates: [[
              ...buildShipDomainPolygon(platform, normalizedHeading, {
                forwardNm: forwardDomainNm * encounterRisk.scale,
                aftNm: aftDomainNm * Math.max(1.02, encounterRisk.scale * 0.9),
                lateralNm: lateralDomainNm * Math.max(1.04, encounterRisk.scale * 0.94),
              }),
            ]],
          },
          properties: {
            severity: encounterRisk.severity,
            cpa_nm: encounterRisk.cpaNm != null ? Number(encounterRisk.cpaNm.toFixed(3)) : null,
            tcpa_min: encounterRisk.tcpaMin != null ? Number(encounterRisk.tcpaMin.toFixed(1)) : null,
            scale: Number(encounterRisk.scale.toFixed(2)),
          },
        },
      ]);

  const predictedPath = normalizedHeading == null || !platform.sog || platform.sog <= 0
    ? emptyFeatureCollection()
    : turfLineString([
        [platform.lon, platform.lat],
        turfDestination(
          center,
          nmToKm(platform.sog * (MAP_SELECTED_PREDICTION_MINUTES / 60)),
          normalizedHeading,
          { units: "kilometers" },
        ).geometry.coordinates as LonLat,
      ]);

  return {
    safetyBuffer: safetyBuffer as maplibregl.GeoJSONSourceSpecification["data"] & object,
    dangerBuffer: dangerBuffer as maplibregl.GeoJSONSourceSpecification["data"] & object,
    predictedPath: predictedPath as maplibregl.GeoJSONSourceSpecification["data"] & object,
  };
}

function simplifyHistoryLine(points: Array<{ lon: number; lat: number }>) {
  if (points.length < 3) return points.map((p) => [p.lon, p.lat] as LonLat);
  const simplified = turfSimplify(
    turfLineString(points.map((p) => [p.lon, p.lat] as LonLat)),
    { tolerance: MAP_HISTORY_SIMPLIFY_TOLERANCE_DEGREES, highQuality: false },
  );
  return simplified.geometry.coordinates as LonLat[];
}

function buildPlatformSources(
  platforms: Record<string, PlatformState>,
  selectedId: string | null,
  alertIds: Set<string>,
) {
  const pointFeatures: PointFeature[] = [];
  const hullFeatures: PolygonFeature[] = [];
  const bridgeFeatures: PolygonFeature[] = [];

  for (const platform of Object.values(platforms)) {
    if (platform.lat == null || platform.lon == null) continue;
    const selected = platform.platform_id === selectedId;
    const alert = alertIds.has(platform.platform_id);
    const heading = platform.heading ?? platform.cog ?? 0;
    const colors = PLATFORM_COLORS[platform.platform_type ?? "vessel"] ?? PLATFORM_COLORS.vessel;
    const commonProps = {
      platform_id: platform.platform_id,
      platform_type: platform.platform_type ?? "vessel",
      name: platform.name ?? platform.platform_id,
      selected,
      alert,
      heading,
      hullColor: selected ? "#f59e0b" : colors.top,
      bridgeColor: selected ? "#fbbf24" : colors.bridge,
      outlineColor: alert ? "#ef4444" : selected ? "#fbbf24" : colors.side,
    };

    pointFeatures.push({
      type: "Feature",
      geometry: { type: "Point", coordinates: [platform.lon, platform.lat] },
      properties: commonProps,
    });

    hullFeatures.push({
      type: "Feature",
      geometry: { type: "Polygon", coordinates: [buildShipPolygon(platform, heading)] },
      properties: commonProps,
    });

    bridgeFeatures.push({
      type: "Feature",
      geometry: { type: "Polygon", coordinates: [buildBridgePolygon(platform, heading)] },
      properties: commonProps,
    });
  }

  return {
    points: toFeatureCollection(pointFeatures),
    hulls: toFeatureCollection(hullFeatures),
    bridges: toFeatureCollection(bridgeFeatures),
  };
}

type OverpassElement = {
  type: "node" | "way";
  id: number;
  lat?: number;
  lon?: number;
  tags?: Record<string, string>;
  geometry?: Array<{ lat: number; lon: number }>;
};

const OVERPASS_FETCH_DEBOUNCE_MS = 600;
const OVERPASS_RATE_LIMIT_COOLDOWN_MS = 60_000;

class OverpassRequestError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "OverpassRequestError";
  }
}

function isTemporaryOverpassFailure(error: unknown) {
  return error instanceof OverpassRequestError && [429, 502, 503, 504].includes(error.status);
}

async function fetchNauticalOverlays(bounds: maplibregl.LngLatBounds) {
  const south = bounds.getSouth();
  const west = bounds.getWest();
  const north = bounds.getNorth();
  const east = bounds.getEast();

  const query = `[out:json][timeout:25];(
    node["seamark:type"~"lighthouse|beacon_lateral|beacon_cardinal|buoy_lateral|buoy_cardinal"](${south},${west},${north},${east});
    way["waterway"="fairway"](${south},${west},${north},${east});
  );out body geom;`;

  // 재시도 로직 (최대 3회)
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      const response = await fetch(OVERPASS_API_URL, {
        method: "POST",
        headers: { "Content-Type": "text/plain;charset=UTF-8" },
        body: query,
      });
      if (!response.ok) {
        throw new OverpassRequestError(`Overpass request failed: ${response.status}`, response.status);
      }
      const data = (await response.json()) as { elements?: OverpassElement[] };
      const elements = data.elements ?? [];

      // 조기 반환 - 성공
      const navAidFeatures: PointFeature[] = [];
      const fairwayFeatures: Array<{ type: "Feature"; geometry: { type: "LineString"; coordinates: LonLat[] }; properties: Record<string, string> }> = [];

      for (const element of elements) {
        if (element.type === "node" && element.lat != null && element.lon != null) {
          const seamarkType = element.tags?.["seamark:type"];
          if (!seamarkType) continue;
          navAidFeatures.push({
            type: "Feature",
            geometry: { type: "Point", coordinates: [element.lon, element.lat] },
            properties: {
              seamark_type: seamarkType,
              label: NAV_AID_LABELS[seamarkType] ?? seamarkType,
              name: element.tags?.name ?? NAV_AID_LABELS[seamarkType] ?? seamarkType,
            },
          });
          continue;
        }

        if (element.type === "way" && element.geometry?.length) {
          fairwayFeatures.push({
            type: "Feature",
            geometry: {
              type: "LineString",
              coordinates: element.geometry.map((point) => [point.lon, point.lat] as LonLat),
            },
            properties: {
              name: element.tags?.name ?? "Fairway",
            },
          });
        }
      }

      return {
        navAids: toFeatureCollection(navAidFeatures),
        fairways: toFeatureCollection(fairwayFeatures as LineFeature[]),
      };
    } catch (error) {
      if (!isTemporaryOverpassFailure(error) || attempt === 3) {
        throw error;
      }
      // 임시 실패면 1초 대기 후 재시도
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  }

  throw new Error("Overpass fetch failed after 3 attempts");
}

function MaritimeMap() {
  const mapRef = useRef<maplibregl.Map | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const trailsRef = useRef(new Map<string, LonLat[]>());
  const prevPosRef = useRef(new Map<string, string>()); // pid → "lon,lat"
  const followRef = useRef(false);
  const lastOverlayBoundsRef = useRef<string | null>(null);
  const overlayCacheRef = useRef(new Map<string, Awaited<ReturnType<typeof fetchNauticalOverlays>>>());
  const overlayFetchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const overlayFetchInFlightRef = useRef(false);
  const overlayCooldownUntilRef = useRef<number>(0);
  const overlayRateLimitLoggedRef = useRef(false);
  const overlayVisibilityRef = useRef({ navAidVisible: true, fairwayVisible: false });

  const platforms = usePlatformStore((s) => s.platforms);
  const select = usePlatformStore((s) => s.select);
  const selectedId = usePlatformStore((s) => s.selectedId);
  const historyOverride = usePlatformStore((s) => s.historyOverride);
  const alerts = useAlertStore((s) => s.alerts);
  const streams = useSystemStore((s) => s.streams);
  const zones = useZoneStore((s) => s.zones);
  const [mapLoaded, setMapLoaded] = useState(false);
  const [seamarkVisible, setSeamarkVisible] = useState(false);
  const [navAidVisible, setNavAidVisible] = useState(true);
  const [fairwayVisible, setFairwayVisible] = useState(false);
  const [zoneVisible, setZoneVisible] = useState(true);
  const [predictionVisible, setPredictionVisible] = useState(true);
  const [encounterVisible, setEncounterVisible] = useState(true);
  const [showLabels, setShowLabels] = useState(true);
  const [showInfoPanels, setShowInfoPanels] = useState(true);
  const [nauticalLayersExpanded, setNauticalLayersExpanded] = useState(true);

  overlayVisibilityRef.current = { navAidVisible, fairwayVisible };

  const alertPlatformIds = useMemo(
    () =>
      new Set(
        alerts
          .filter((a) => a.status === "new" && a.severity === ALERT_HIGHLIGHT_SEVERITY)
          .flatMap((a) => a.platform_ids),
      ),
    [alerts],
  );
  const selectedPlatform = selectedId ? (platforms[selectedId] ?? null) : null;
  const selectedCpaEncounters = useMemo(
    () => buildSelectedEncounterItems(selectedId, alerts, platforms),
    [selectedId, alerts, platforms],
  );
  const selectedEncounterRisk = useMemo(
    () => buildEncounterRiskState(selectedCpaEncounters),
    [selectedCpaEncounters],
  );
  const selectedEncounterData = useMemo(
    () => buildSelectedEncounterData(selectedPlatform, selectedCpaEncounters, platforms),
    [selectedPlatform, selectedCpaEncounters, platforms],
  );

  function updateTrail(p: PlatformState) {
    if (p.lat == null || p.lon == null) return;
    const key = `${p.lon.toFixed(5)},${p.lat.toFixed(5)}`;
    if (prevPosRef.current.get(p.platform_id) === key) return; // 위치 변화 없음
    prevPosRef.current.set(p.platform_id, key);

    const trail = trailsRef.current.get(p.platform_id) ?? [];
    trail.push([p.lon, p.lat]);
    if (trail.length > TRAIL_MAX) trail.shift();
    trailsRef.current.set(p.platform_id, trail);
  }

  function flushTrailSource() {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;
    const src = map.getSource("trails") as GeoJSONSource | undefined;
    src?.setData(
      buildTrailGeoJSON(trailsRef.current, platforms, alertPlatformIds),
    );
  }

  // ── 지도 초기화 (마운트 1회) ──────────────────────────────────────────────

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: {
        version: 8,
        sources: {
          osm: {
            type: "raster",
            tiles: [MAP_OSM_TILE_URL],
            tileSize: 256,
            attribution: MAP_OSM_ATTRIBUTION,
          },
          seamark: {
            type: "raster",
            tiles: [MAP_OPENSEAMAP_SEAMARK_TILE_URL],
            tileSize: 256,
            attribution: MAP_OPENSEAMAP_ATTRIBUTION,
          },
          "platform-points": {
            type: "geojson",
            data: { type: "FeatureCollection", features: [] },
            cluster: true,
            clusterRadius: 58,
            clusterMaxZoom: MAP_CLUSTER_MAX_ZOOM,
          },
          "platform-hulls": {
            type: "geojson",
            data: { type: "FeatureCollection", features: [] },
          },
          "platform-bridges": {
            type: "geojson",
            data: { type: "FeatureCollection", features: [] },
          },
          "nav-aids": {
            type: "geojson",
            data: { type: "FeatureCollection", features: [] },
          },
          fairways: {
            type: "geojson",
            data: { type: "FeatureCollection", features: [] },
          },
          "selected-safety-buffer": {
            type: "geojson",
            data: { type: "FeatureCollection", features: [] },
          },
          "selected-danger-buffer": {
            type: "geojson",
            data: { type: "FeatureCollection", features: [] },
          },
          "selected-prediction": {
            type: "geojson",
            data: { type: "FeatureCollection", features: [] },
          },
          "selected-cpa-lines": {
            type: "geojson",
            data: { type: "FeatureCollection", features: [] },
          },
          "selected-cpa-points": {
            type: "geojson",
            data: { type: "FeatureCollection", features: [] },
          },
          "selected-cpa-projection": {
            type: "geojson",
            data: { type: "FeatureCollection", features: [] },
          },
        },
        layers: [
          {
            id: "osm-layer",
            type: "raster",
            source: "osm",
            paint: { "raster-opacity": MAP_OSM_OPACITY },
          },
          { id: "seamark-layer", type: "raster", source: "seamark", layout: { visibility: "none" } },
        ],
        glyphs: MAP_GLYPHS_URL,
      },
      center: MAP_CENTER,
      zoom: MAP_ZOOM,
      attributionControl: false,
    });

    map.addControl(new maplibregl.NavigationControl(), "bottom-right");
    map.addControl(
      new maplibregl.ScaleControl({ unit: "nautical" }),
      "bottom-left",
    );

    // Suppress vector tile parsing errors (type 4 unimplemented)
    map.on("error", (e) => {
      if (e.error?.message?.includes("Unimplemented type")) {
        // Silently ignore unimplemented vector tile types
        return;
      }
      console.error("[map] Error:", e.error);
    });

    map.on("load", () => {
      // ── 역사적 항적 소스 (선택된 선박 DB 이력) ─────────────────────────
      map.addSource("history-trail", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });

      map.addLayer({
        id: "history-trail-casing",
        type: "line",
        source: "history-trail",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": "#92400e",
          "line-width": TRAIL_CASING_WIDTH,
          "line-opacity": 0.28,
        },
      });

      map.addLayer({
        id: "history-trail-line",
        type: "line",
        source: "history-trail",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": "#f97316",
          "line-width": TRAIL_LINE_WIDTH,
          "line-opacity": 0.65,
        },
      });

      map.addLayer({
        id: "selected-safety-buffer-fill",
        type: "fill",
        source: "selected-safety-buffer",
        paint: {
          "fill-color": "#38bdf8",
          "fill-opacity": 0.05,
        },
      });

      map.addLayer({
        id: "selected-safety-buffer-line",
        type: "line",
        source: "selected-safety-buffer",
        paint: {
          "line-color": "#67e8f9",
          "line-width": 1,
          "line-opacity": 0.42,
          "line-dasharray": [2, 2],
        },
      });

      map.addLayer({
        id: "selected-danger-buffer-fill",
        type: "fill",
        source: "selected-danger-buffer",
        paint: {
          "fill-color": [
            "match",
            ["get", "severity"],
            "critical",
            "#ef4444",
            "warning",
            "#f59e0b",
            "#f59e0b",
          ],
          "fill-opacity": [
            "match",
            ["get", "severity"],
            "critical",
            0.22,
            "warning",
            0.16,
            0.1,
          ],
        },
      });

      map.addLayer({
        id: "selected-danger-buffer-line",
        type: "line",
        source: "selected-danger-buffer",
        paint: {
          "line-color": [
            "match",
            ["get", "severity"],
            "critical",
            "#f87171",
            "warning",
            "#fbbf24",
            "#fbbf24",
          ],
          "line-width": [
            "match",
            ["get", "severity"],
            "critical",
            2.8,
            "warning",
            2.2,
            1.6,
          ],
          "line-opacity": 0.95,
        },
      });


      map.addLayer({
        id: "selected-prediction-line",
        type: "line",
        source: "selected-prediction",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": "#22c55e",
          "line-width": 2,
          "line-opacity": 0.7,
          "line-dasharray": [2, 2],
        },
      });

      map.addLayer({
        id: "selected-cpa-line-primary",
        type: "line",
        source: "selected-cpa-lines",
        filter: ["==", ["get", "isPrimary"], true],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": [
            "match",
            ["get", "severity"],
            "critical",
            "#ef4444",
            "warning",
            "#f59e0b",
            "#38bdf8",
          ],
          "line-width": [
            "match",
            ["get", "severity"],
            "critical",
            3.4,
            "warning",
            2.8,
            2.2,
          ],
          "line-opacity": 0.92,
          "line-dasharray": [2, 1.5],
        },
      });

      map.addLayer({
        id: "selected-cpa-line-secondary",
        type: "line",
        source: "selected-cpa-lines",
        filter: ["!=", ["get", "isPrimary"], true],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": [
            "match",
            ["get", "severity"],
            "critical",
            "#ef4444",
            "warning",
            "#f59e0b",
            "#38bdf8",
          ],
          "line-width": [
            "match",
            ["get", "severity"],
            "critical",
            2.1,
            "warning",
            1.7,
            1.4,
          ],
          "line-opacity": 0.54,
          "line-dasharray": [3, 3],
        },
      });

      map.addLayer({
        id: "selected-cpa-point",
        type: "circle",
        source: "selected-cpa-points",
        paint: {
          "circle-radius": [
            "case",
            ["==", ["get", "isPrimary"], true],
            [
              "match",
              ["get", "severity"],
              "critical",
              10,
              "warning",
              9,
              8,
            ],
            [
              "match",
              ["get", "severity"],
              "critical",
              7,
              "warning",
              6,
              5,
            ],
          ],
          "circle-color": [
            "match",
            ["get", "severity"],
            "critical",
            "#ef4444",
            "warning",
            "#f59e0b",
            "#38bdf8",
          ],
          "circle-opacity": ["case", ["==", ["get", "isPrimary"], true], 0.22, 0.12],
          "circle-stroke-width": ["case", ["==", ["get", "isPrimary"], true], 2.4, 1.4],
          "circle-stroke-color": [
            "match",
            ["get", "severity"],
            "critical",
            "#fca5a5",
            "warning",
            "#fcd34d",
            "#bae6fd",
          ],
        },
      });

      map.addLayer({
        id: "selected-cpa-projection-point",
        type: "circle",
        source: "selected-cpa-projection",
        paint: {
          "circle-radius": 4,
          "circle-color": "#f8fafc",
          "circle-opacity": 0.82,
          "circle-stroke-width": 1.4,
          "circle-stroke-color": "#94a3b8",
        },
      });

      map.addLayer({
        id: "selected-cpa-projection-label",
        type: "symbol",
        source: "selected-cpa-projection",
        layout: {
          "text-field": [
            "concat",
            "최근접 ",
            ["to-string", ["get", "cpa_nm"]],
            "NM / ",
            ["to-string", ["get", "tcpa_min"]],
            "분",
          ],
          "text-size": 10,
          "text-offset": [0, 1.4],
          "text-anchor": "top",
        },
        paint: {
          "text-color": "#e2e8f0",
          "text-halo-color": "#0f172a",
          "text-halo-width": 1.2,
        },
      });

      // ── 실시간 항적 소스 + 레이어 ────────────────────────────────────
      map.addSource("trails", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });

      // 항적 외곽선 (대비용)
      map.addLayer({
        id: "trail-casing",
        type: "line",
        source: "trails",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": TRAIL_CASING_COLOR,
          "line-width": TRAIL_CASING_WIDTH,
          "line-opacity": ["*", ["get", "opacity"], TRAIL_CASING_OPACITY_FACTOR],
        },
      });

      // 항적 메인
      map.addLayer({
        id: "trail-line",
        type: "line",
        source: "trails",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": ["get", "color"],
          "line-width": TRAIL_LINE_WIDTH,
          "line-opacity": ["get", "opacity"],
        },
      });

      map.addLayer({
        id: "fairway-lines",
        type: "line",
        source: "fairways",
        layout: { visibility: "visible", "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": "#67e8f9",
          "line-width": ["interpolate", ["linear"], ["zoom"], 8, 1.2, 12, 3.4],
          "line-opacity": 0.5,
          "line-dasharray": [4, 3],
        },
      });

      map.addLayer({
        id: "platform-clusters",
        type: "circle",
        source: "platform-points",
        filter: ["has", "point_count"],
        paint: {
          "circle-color": "#0f172a",
          "circle-stroke-color": "#38bdf8",
          "circle-stroke-width": 1.5,
          "circle-radius": [
            "step",
            ["get", "point_count"],
            18,
            10,
            24,
            30,
            30,
            100,
            36,
          ],
        },
      });

      map.addLayer({
        id: "platform-cluster-count",
        type: "symbol",
        source: "platform-points",
        filter: ["has", "point_count"],
        layout: {
          "text-field": ["get", "point_count_abbreviated"],
          "text-size": 11,
          "text-font": ["Open Sans Bold", "Arial Unicode MS Bold"],
        },
        paint: {
          "text-color": "#dbeafe",
          "text-halo-color": "#020617",
          "text-halo-width": 1.2,
        },
      });

      map.addLayer({
        id: "platform-point-fallback",
        type: "circle",
        source: "platform-points",
        filter: ["!", ["has", "point_count"]],
        maxzoom: MAP_SHIP_LAYER_MIN_ZOOM,
        paint: {
          "circle-radius": ["case", ["==", ["get", "alert"], true], 7, 5],
          "circle-color": ["get", "hullColor"],
          "circle-stroke-color": ["case", ["==", ["get", "selected"], true], "#fbbf24", "#0f172a"],
          "circle-stroke-width": ["case", ["==", ["get", "selected"], true], 2, 1],
        },
      });

      map.addLayer({
        id: "platform-hulls-fill",
        type: "fill",
        source: "platform-hulls",
        minzoom: MAP_SHIP_LAYER_MIN_ZOOM,
        paint: {
          "fill-color": ["get", "hullColor"],
          "fill-opacity": 0.92,
        },
      });

      map.addLayer({
        id: "platform-hulls-outline",
        type: "line",
        source: "platform-hulls",
        minzoom: MAP_SHIP_LAYER_MIN_ZOOM,
        paint: {
          "line-color": ["get", "outlineColor"],
          "line-width": ["case", ["==", ["get", "selected"], true], 2.6, 1.2],
          "line-opacity": 0.95,
        },
      });

      map.addLayer({
        id: "platform-bridges-fill",
        type: "fill",
        source: "platform-bridges",
        minzoom: MAP_SHIP_LAYER_MIN_ZOOM,
        paint: {
          "fill-color": ["get", "bridgeColor"],
          "fill-opacity": 0.95,
        },
      });

      map.addLayer({
        id: "platform-labels",
        type: "symbol",
        source: "platform-points",
        filter: ["!", ["has", "point_count"]],
        minzoom: MAP_SHIP_LAYER_MIN_ZOOM + 1,
        layout: {
          "text-field": ["get", "name"],
          "text-size": 11,
          "text-offset": [0, 1.8],
          "text-anchor": "top",
          "text-font": ["Open Sans Regular", "Arial Unicode MS Regular"],
        },
        paint: {
          "text-color": "#e2e8f0",
          "text-halo-color": "#020617",
          "text-halo-width": 1.2,
          "text-opacity": [
            "step",
            ["zoom"],
            [
              "case",
              ["==", ["get", "selected"], true],
              1,
              ["==", ["get", "alert"], true],
              1,
              0,
            ],
            12,
            1,
          ],
        },
      });

      map.addLayer({
        id: "nav-aids-circle",
        type: "circle",
        source: "nav-aids",
        layout: { visibility: "visible" },
        paint: {
          "circle-radius": [
            "match",
            ["get", "seamark_type"],
            "lighthouse",
            6,
            "beacon_lateral",
            5,
            "beacon_cardinal",
            5,
            4,
          ],
          "circle-color": [
            "match",
            ["get", "seamark_type"],
            "lighthouse",
            "#f8fafc",
            "beacon_cardinal",
            "#f59e0b",
            "buoy_cardinal",
            "#fbbf24",
            "#38bdf8",
          ],
          "circle-stroke-color": "#082f49",
          "circle-stroke-width": 1,
          "circle-opacity": 0.9,
        },
      });

      map.addLayer({
        id: "nav-aids-label",
        type: "symbol",
        source: "nav-aids",
        minzoom: 11,
        layout: {
          visibility: "visible",
          "text-field": ["get", "label"],
          "text-size": 10,
          "text-offset": [0, 1.2],
          "text-anchor": "top",
        },
        paint: {
          "text-color": "#bae6fd",
          "text-halo-color": "#082f49",
          "text-halo-width": 1,
        },
      });

      // ── 구역 소스 + 레이어 ────────────────────────────────────────────
      map.addSource("zones", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addSource("zone-labels", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });

      // 구역 반투명 fill
      map.addLayer({
        id: "zones-fill",
        type: "fill",
        source: "zones",
        paint: {
          "fill-color": [
            "match", ["get", "zone_type"],
            "prohibited", "#ef4444",
            "restricted", "#f59e0b",
            "caution", "#3b82f6",
            "#64748b",
          ],
          "fill-opacity": 0.12,
        },
      });

      // 구역 테두리
      map.addLayer({
        id: "zones-border",
        type: "line",
        source: "zones",
        filter: ["!=", ["get", "zone_type"], "prohibited"],
        paint: {
          "line-color": [
            "match", ["get", "zone_type"],
            "prohibited", "#ef4444",
            "restricted", "#f59e0b",
            "caution", "#3b82f6",
            "#64748b",
          ],
          "line-width": 1.8,
          "line-opacity": 0.75,
          "line-dasharray": [4, 2],
        },
      });

      map.addLayer({
        id: "zones-border-prohibited",
        type: "line",
        source: "zones",
        filter: ["==", ["get", "zone_type"], "prohibited"],
        paint: {
          "line-color": "#ef4444",
          "line-width": 1.8,
          "line-opacity": 0.9,
        },
      });

      // 구역 라벨 (이름 + 유형)
      map.addLayer({
        id: "zones-label",
        type: "symbol",
        source: "zone-labels",
        layout: {
          "text-field": ["concat", ["get", "name"], "\n", ["get", "type_label"]],
          "text-size": 12,
          "text-anchor": "center",
          "text-justify": "center",
          "text-font": ["Open Sans Regular", "Arial Unicode MS Regular"],
          "text-max-width": 10,
        },
        paint: {
          "text-color": "#f1f5f9",
          "text-halo-color": "#0f172a",
          "text-halo-width": 1.5,
        },
      });

      map.on("click", "platform-clusters", (event) => {
        const feature = event.features?.[0];
        if (!feature) return;
        const clusterId = feature.properties?.cluster_id;
        const source = map.getSource("platform-points") as GeoJSONSource | undefined;
        if (!source || typeof clusterId !== "number") return;
        void source.getClusterExpansionZoom(clusterId).then((zoom) => {
          const geometry = feature.geometry as { coordinates?: LonLat };
          if (!geometry.coordinates) return;
          map.easeTo({ center: geometry.coordinates, zoom, duration: 500 });
        });
      });

      const selectPlatformFromFeature = (event: maplibregl.MapLayerMouseEvent) => {
        const feature = event.features?.[0];
        const platformId = feature?.properties?.platform_id;
        if (typeof platformId !== "string") return;
        followRef.current = false;
        select(platformId);
      };

      map.on("click", "platform-point-fallback", selectPlatformFromFeature);
      map.on("click", "platform-hulls-fill", selectPlatformFromFeature);

      const setInteractiveCursor = () => {
        map.getCanvas().style.cursor = "pointer";
      };
      const resetCursor = () => {
        map.getCanvas().style.cursor = "";
      };

      for (const layerId of ["platform-clusters", "platform-point-fallback", "platform-hulls-fill"]) {
        map.on("mouseenter", layerId, setInteractiveCursor);
        map.on("mouseleave", layerId, resetCursor);
      }

      map.on("moveend", async () => {
        if (overlayFetchTimerRef.current) {
          clearTimeout(overlayFetchTimerRef.current);
        }

        overlayFetchTimerRef.current = setTimeout(async () => {
          const { navAidVisible: navVisible, fairwayVisible: fairwayLayerVisible } = overlayVisibilityRef.current;
          if (!navVisible && !fairwayLayerVisible) return;
          if (map.getZoom() < MAP_NAV_AID_FETCH_MIN_ZOOM) return;
          if (overlayFetchInFlightRef.current) return;

          const now = Date.now();
          if (overlayCooldownUntilRef.current > now) return;

          const bounds = map.getBounds();
          const key = `${bounds.getSouth().toFixed(2)}:${bounds.getWest().toFixed(2)}:${bounds.getNorth().toFixed(2)}:${bounds.getEast().toFixed(2)}`;
          if (lastOverlayBoundsRef.current === key) return;

          const cached = overlayCacheRef.current.get(key);
          if (cached) {
            lastOverlayBoundsRef.current = key;
            (map.getSource("nav-aids") as GeoJSONSource | undefined)?.setData(cached.navAids);
            (map.getSource("fairways") as GeoJSONSource | undefined)?.setData(cached.fairways);
            return;
          }

          overlayFetchInFlightRef.current = true;
          try {
            const overlayData = await fetchNauticalOverlays(bounds);
            lastOverlayBoundsRef.current = key;
            overlayRateLimitLoggedRef.current = false;
            overlayCacheRef.current.set(key, overlayData);
            if (overlayCacheRef.current.size > 12) {
              const oldestKey = overlayCacheRef.current.keys().next().value;
              if (oldestKey) overlayCacheRef.current.delete(oldestKey);
            }
            (map.getSource("nav-aids") as GeoJSONSource | undefined)?.setData(overlayData.navAids);
            (map.getSource("fairways") as GeoJSONSource | undefined)?.setData(overlayData.fairways);
          } catch (error) {
            if (isTemporaryOverpassFailure(error)) {
              overlayCooldownUntilRef.current = Date.now() + OVERPASS_RATE_LIMIT_COOLDOWN_MS;
              if (!overlayRateLimitLoggedRef.current) {
                console.warn("[map] Overpass temporarily unavailable; nautical overlays paused briefly");
                overlayRateLimitLoggedRef.current = true;
              }
              return;
            }

            console.error("[map] failed to fetch nautical overlays", error);
          } finally {
            overlayFetchInFlightRef.current = false;
          }
        }, OVERPASS_FETCH_DEBOUNCE_MS);
      });

      setMapLoaded(true);
    });

      const stopFollow = () => {
        followRef.current = false;
      };

      map.on("dragstart", stopFollow);
      map.on("zoomstart", stopFollow);
      map.on("rotatestart", stopFollow);
      map.on("pitchstart", stopFollow);
      map.on("wheel", stopFollow);
      map.on("touchstart", stopFollow);

    mapRef.current = map;
    return () => {
      if (overlayFetchTimerRef.current) {
        clearTimeout(overlayFetchTimerRef.current);
      }
      map.remove();
      mapRef.current = null;
      setMapLoaded(false);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── 플랫폼 업데이트 → 마커 + 항적 동기화 ─────────────────────────────────

  useEffect(() => {
    if (!mapLoaded || !mapRef.current) return;
    for (const p of Object.values(platforms)) {
      updateTrail(p);
    }
    flushTrailSource();
    const sourceData = buildPlatformSources(platforms, selectedId, alertPlatformIds);
    (mapRef.current.getSource("platform-points") as GeoJSONSource | undefined)?.setData(sourceData.points);
    (mapRef.current.getSource("platform-hulls") as GeoJSONSource | undefined)?.setData(sourceData.hulls);
    (mapRef.current.getSource("platform-bridges") as GeoJSONSource | undefined)?.setData(sourceData.bridges);
  }, [platforms, selectedId, alertPlatformIds, mapLoaded]);

  useEffect(() => {
    if (!mapLoaded || !mapRef.current) return;

    if (selectedId) {
      const p = platforms[selectedId];
      if (p?.lat != null && p?.lon != null) {
        mapRef.current.flyTo({
          center: [p.lon, p.lat],
          zoom: Math.max(mapRef.current.getZoom(), MAP_SELECT_MIN_ZOOM),
          duration: MAP_SELECT_FLY_DURATION,
          essential: true,
        });
      }
    }
  }, [selectedId, mapLoaded]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── 선택 선박 실시간 추적 재개 ───────────────────────────────────────────
  useEffect(() => {
    if (selectedId) {
      followRef.current = true;
    }
  }, [selectedId]);

  // ── 선택 선박 실시간 추적 ─────────────────────────────────────────────────

  useEffect(() => {
    if (!mapLoaded || !mapRef.current || !selectedId || !followRef.current)
      return;
    const p = platforms[selectedId];
    if (p?.lat != null && p?.lon != null) {
      mapRef.current.easeTo({ center: [p.lon, p.lat], duration: MAP_TRACK_EASE_DURATION });
    }
  }, [platforms, selectedId, mapLoaded]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!mapLoaded || !mapRef.current) return;
    const spatialData = buildSelectedSpatialData(selectedPlatform, selectedEncounterRisk);
    (mapRef.current.getSource("selected-safety-buffer") as GeoJSONSource | undefined)?.setData(spatialData.safetyBuffer);
    (mapRef.current.getSource("selected-danger-buffer") as GeoJSONSource | undefined)?.setData(spatialData.dangerBuffer);
    (mapRef.current.getSource("selected-prediction") as GeoJSONSource | undefined)?.setData(spatialData.predictedPath);
    (mapRef.current.getSource("selected-cpa-lines") as GeoJSONSource | undefined)?.setData(selectedEncounterData.lines);
    (mapRef.current.getSource("selected-cpa-points") as GeoJSONSource | undefined)?.setData(selectedEncounterData.points);
    (mapRef.current.getSource("selected-cpa-projection") as GeoJSONSource | undefined)?.setData(selectedEncounterData.cpaProjection);
  }, [selectedPlatform, selectedEncounterRisk, selectedEncounterData, mapLoaded]);

  // ── 선택 선박 역사적 항적 (DB 조회 또는 외부 override) ───────────────────

  useEffect(() => {
    if (!mapLoaded || !mapRef.current) return;
    const map = mapRef.current;
    const src = map.getSource("history-trail") as GeoJSONSource | undefined;
    if (!src) return;

    // historyOverride: 플랫폼 상세 페이지에서 날짜 범위 지정 조회 시 사용
    if (historyOverride && historyOverride.platformId === selectedId && historyOverride.points.length >= 2) {
      src.setData({
        type: "FeatureCollection",
        features: [
          {
            type: "Feature",
            geometry: { type: "LineString", coordinates: historyOverride.points },
            properties: {},
          },
        ],
      });
      return;
    }

    if (!selectedId) {
      src.setData({ type: "FeatureCollection", features: [] });
      return;
    }

    const controller = new AbortController();
    void (async () => {
      try {
        const url = `${getCoreApiUrl()}/platforms/${encodeURIComponent(selectedId)}/track?limit=500`;
        const res = await fetch(url, { signal: controller.signal });
        if (!res.ok) return;
        const allPoints = (await res.json()) as Array<{ time: string; lon: number; lat: number }>;
        if (controller.signal.aborted) return;

        // 최신 5분 데이터만 필터링
        const now = new Date();
        const fiveMinutesAgo = new Date(now.getTime() - 5 * 60 * 1000);
        const recentPoints = allPoints.filter((p) => {
          const pointTime = new Date(p.time);
          return pointTime >= fiveMinutesAgo && pointTime <= now;
        });

        if (recentPoints.length < 2) {
          src.setData({ type: "FeatureCollection", features: [] });
          return;
        }
        const simplifiedCoordinates = simplifyHistoryLine(recentPoints);
        src.setData({
          type: "FeatureCollection",
          features: [
            {
              type: "Feature",
              geometry: {
                type: "LineString",
                coordinates: simplifiedCoordinates,
              },
              properties: {},
            },
          ],
        });
      } catch {
        // 취소 또는 네트워크 오류 — 무시
      }
    })();

    return () => controller.abort();
  }, [selectedId, historyOverride, mapLoaded]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── 해도 심볼(OpenSeaMap) 레이어 표시/숨김 ────────────────────────────────

  useEffect(() => {
    if (!mapLoaded || !mapRef.current) return;
    mapRef.current.setLayoutProperty(
      "seamark-layer",
      "visibility",
      seamarkVisible ? "visible" : "none",
    );
  }, [seamarkVisible, mapLoaded]);

  useEffect(() => {
    if (!mapLoaded || !mapRef.current) return;
    const visibility = navAidVisible ? "visible" : "none";
    mapRef.current.setLayoutProperty("nav-aids-circle", "visibility", visibility);
    mapRef.current.setLayoutProperty("nav-aids-label", "visibility", visibility);
  }, [navAidVisible, mapLoaded]);

  useEffect(() => {
    if (!mapLoaded || !mapRef.current) return;
    mapRef.current.setLayoutProperty(
      "fairway-lines",
      "visibility",
      fairwayVisible ? "visible" : "none",
    );
  }, [fairwayVisible, mapLoaded]);

  // ── 구역 소스 데이터 갱신 ─────────────────────────────────────────────────

  useEffect(() => {
    if (!mapLoaded || !mapRef.current) return;
    const map = mapRef.current;
    (map.getSource("zones") as maplibregl.GeoJSONSource | undefined)
      ?.setData(buildZoneGeoJSON(zones) as Parameters<maplibregl.GeoJSONSource["setData"]>[0]);
    (map.getSource("zone-labels") as maplibregl.GeoJSONSource | undefined)
      ?.setData(buildZoneLabelGeoJSON(zones) as Parameters<maplibregl.GeoJSONSource["setData"]>[0]);
  }, [zones, mapLoaded]);

  // ── 구역 레이어 표시/숨김 ─────────────────────────────────────────────────

  useEffect(() => {
    if (!mapLoaded || !mapRef.current) return;
    const vis = zoneVisible ? "visible" : "none";
    for (const id of ["zones-fill", "zones-border", "zones-border-prohibited", "zones-label"]) {
      if (mapRef.current.getLayer(id)) {
        mapRef.current.setLayoutProperty(id, "visibility", vis);
      }
    }
  }, [zoneVisible, mapLoaded]);


  useEffect(() => {
    if (!mapLoaded || !mapRef.current) return;
    mapRef.current.setLayoutProperty(
      "selected-prediction-line",
      "visibility",
      predictionVisible ? "visible" : "none",
    );
  }, [predictionVisible, mapLoaded]);

  useEffect(() => {
    if (!mapLoaded || !mapRef.current) return;
    const visibility = encounterVisible ? "visible" : "none";
    for (const id of ["selected-cpa-line-primary", "selected-cpa-line-secondary", "selected-cpa-point", "selected-cpa-projection-point", "selected-cpa-projection-label", "selected-danger-buffer-fill", "selected-danger-buffer-line"]) {
      if (mapRef.current.getLayer(id)) {
        mapRef.current.setLayoutProperty(id, "visibility", visibility);
      }
    }
  }, [encounterVisible, mapLoaded]);

  useEffect(() => {
    if (!mapLoaded || !mapRef.current) return;
    const visibility = showLabels ? "visible" : "none";
    for (const id of ["platform-labels", "platform-cluster-count", "nav-aids-label"]) {
      if (mapRef.current.getLayer(id)) {
        mapRef.current.setLayoutProperty(id, "visibility", visibility);
      }
    }
  }, [showLabels, mapLoaded]);

  const platformCount = Object.keys(platforms).length;
  const criticalCount = alerts.filter(
    (a) => a.severity === "critical" && a.status === "new",
  ).length;
  const activeNauticalLayerCount = Number(navAidVisible) + Number(fairwayVisible) + Number(seamarkVisible);
  const activeSelectedOverlayCount = Number(Boolean(selectedPlatform))
    + Number(predictionVisible)
    + Number(encounterVisible && selectedCpaEncounters.length > 0);

  return (
    <div className="relative w-full h-full">
      <div ref={containerRef} className="w-full h-full" role="img" aria-label="실시간 해양 플랫폼 지도" />

      {/* 상태 배지 */}
      <div className="absolute top-3 left-3 flex flex-col gap-1.5 pointer-events-none">
        <div className="panel px-2.5 py-1 text-xs text-ocean-300 rounded flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-green-400 inline-block" />
          <span className="font-mono">{platformCount}척 관제 중</span>
        </div>
        {criticalCount > 0 && (
          <div className="panel px-2.5 py-1 text-xs text-red-400 rounded flex items-center gap-2 border border-red-500/40">
            <span className="w-1.5 h-1.5 rounded-full bg-red-400 inline-block animate-pulse" />
            <span className="font-mono font-bold">위험 {criticalCount}건</span>
          </div>
        )}
        {(streams.position.status !== "connected" || streams.alert.status !== "connected") && (
          <div className="panel px-2.5 py-1 text-xs text-amber-300 rounded border border-amber-500/30">
            스트림 상태: 위치 {streams.position.status === "connected" ? "정상" : "주의"} · 경보 {streams.alert.status === "connected" ? "정상" : "주의"}
          </div>
        )}
      </div>

      {/* 레이어 토글 (Notion toggle 스타일) */}
      <div className="absolute top-3 right-12 z-10 pointer-events-none">
        <div className="pointer-events-auto">
          {/* 해양 레이어 토글 헤더 */}
          <button
            onClick={() => setNauticalLayersExpanded((v) => !v)}
            className="panel flex items-center gap-2 px-3 py-2 rounded text-xs font-medium border border-ocean-600/60 text-ocean-200 hover:border-ocean-500 transition-colors mb-1"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 14 14"
              fill="none"
              className={`flex-shrink-0 transition-transform duration-200 ${nauticalLayersExpanded ? "rotate-90" : ""}`}
            >
              <polyline points="5 2 10 7 5 12" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            해양 레이어
            <span className="ml-auto text-ocean-400 text-[10px]">{activeNauticalLayerCount}개</span>
          </button>

          {/* 토글 내용 */}
          {nauticalLayersExpanded && (
            <div className="panel border border-ocean-600/60 border-t-0 rounded-b px-2 py-2 space-y-1.5">
              <button
                onClick={() => setZoneVisible((v) => !v)}
                className="w-full flex items-center gap-2 px-2 py-1.5 rounded text-xs text-ocean-200 hover:bg-ocean-800/30 transition-colors"
              >
                <svg width="10" height="10" viewBox="0 0 12 12" fill="none" className="flex-shrink-0">
                  <polygon points="6,1 11,10 1,10" fill="none" stroke="currentColor" strokeWidth="1.2" opacity="0.8"/>
                  <line x1="6" y1="4" x2="6" y2="7" stroke="currentColor" strokeWidth="1.2"/>
                  <circle cx="6" cy="8.5" r="0.7" fill="currentColor"/>
                </svg>
                <span className="flex-1 text-left">구역</span>
                <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${zoneVisible ? "bg-amber-400" : "bg-ocean-700"}`} />
              </button>

              <button
                onClick={() => setNavAidVisible((v) => !v)}
                className="w-full flex items-center gap-2 px-2 py-1.5 rounded text-xs text-ocean-200 hover:bg-ocean-800/30 transition-colors"
              >
                <svg width="10" height="10" viewBox="0 0 12 12" fill="none" className="flex-shrink-0" style={{ opacity: navAidVisible ? 1 : 0.5 }}>
                  <circle cx="6" cy="6" r="2" fill="none" stroke="currentColor" strokeWidth="1.2"/>
                  <circle cx="6" cy="6" r="4" fill="none" stroke="currentColor" strokeWidth="0.8" style={{ opacity: navAidVisible ? 0.7 : 0.3 }}/>
                </svg>
                <span className="flex-1 text-left">주요 표지</span>
                <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${navAidVisible ? "bg-cyan-300" : "bg-ocean-700"}`} />
              </button>

              <button
                onClick={() => setFairwayVisible((v) => !v)}
                className="w-full flex items-center gap-2 px-2 py-1.5 rounded text-xs text-ocean-200 hover:bg-ocean-800/30 transition-colors"
              >
                <svg width="10" height="10" viewBox="0 0 12 12" fill="none" className="flex-shrink-0" style={{ opacity: fairwayVisible ? 1 : 0.5 }}>
                  <line x1="2" y1="10" x2="10" y2="2" stroke="currentColor" strokeWidth="1.2"/>
                  <circle cx="6" cy="6" r="0.5" fill="currentColor" style={{ opacity: fairwayVisible ? 0.8 : 0.4 }}/>
                </svg>
                <span className="flex-1 text-left">Fairway</span>
                <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${fairwayVisible ? "bg-emerald-300" : "bg-ocean-700"}`} />
              </button>

              <button
                onClick={() => setSeamarkVisible((v) => !v)}
                className="w-full flex items-center gap-2 px-2 py-1.5 rounded text-xs text-ocean-200 hover:bg-ocean-800/30 transition-colors"
              >
                <svg width="10" height="10" viewBox="0 0 12 12" fill="none" className="flex-shrink-0" style={{ opacity: seamarkVisible ? 1 : 0.5 }}>
                  <rect x="4.5" y="0" width="3" height="2" rx="0.5" fill="currentColor"/>
                  <path d="M4 2h4l1 8H3L4 2Z" fill="currentColor" style={{ opacity: seamarkVisible ? 0.6 : 0.3 }}/>
                  <rect x="3" y="10" width="6" height="2" rx="0.5" fill="currentColor"/>
                </svg>
                <span className="flex-1 text-left">전체 seamark</span>
                <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${seamarkVisible ? "bg-cyan-300" : "bg-ocean-700"}`} />
              </button>
            </div>
          )}

          {/* 텍스트 레이블 토글 */}
          <button
            onClick={() => setShowLabels((v) => !v)}
            className="w-full mt-3 flex items-center gap-2 px-2.5 py-1.5 rounded text-xs font-medium text-ocean-200 hover:bg-ocean-800/30 transition-colors border border-ocean-700/40 hover:border-ocean-600/60"
          >
            <svg width="12" height="12" viewBox="0 0 16 16" fill="none" className="flex-shrink-0">
              <text x="2" y="11" fontSize="8" fill="currentColor" opacity={showLabels ? 1 : 0.5}>텍스트</text>
            </svg>
            <span className="flex-1 text-left">텍스트 레이블</span>
            <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${showLabels ? "bg-blue-300" : "bg-ocean-700"}`} />
          </button>

          {/* 정보 패널 토글 */}
          <button
            onClick={() => setShowInfoPanels((v) => !v)}
            className="w-full mt-1.5 flex items-center gap-2 px-2.5 py-1.5 rounded text-xs font-medium text-ocean-200 hover:bg-ocean-800/30 transition-colors border border-ocean-700/40 hover:border-ocean-600/60"
          >
            <svg width="12" height="12" viewBox="0 0 16 16" fill="none" className="flex-shrink-0" style={{ opacity: showInfoPanels ? 1 : 0.5 }}>
              <rect x="2" y="2" width="12" height="12" rx="1" fill="none" stroke="currentColor" strokeWidth="1.2"/>
              <line x1="2" y1="5" x2="14" y2="5" stroke="currentColor" strokeWidth="0.8" opacity="0.6"/>
              <line x1="4" y1="8" x2="12" y2="8" stroke="currentColor" strokeWidth="0.6" opacity="0.4"/>
              <line x1="4" y1="10" x2="12" y2="10" stroke="currentColor" strokeWidth="0.6" opacity="0.4"/>
            </svg>
            <span className="flex-1 text-left">정보 패널</span>
            <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${showInfoPanels ? "bg-cyan-300" : "bg-ocean-700"}`} />
          </button>

          {/* 선택 선박 오버레이 */}
          <div className="flex flex-col gap-1.5 mt-3 pt-2 border-t border-ocean-700/40">
            <button
              onClick={() => setEncounterVisible((v) => !v)}
              title="선택 선박과 활성 CPA/TCPA 상대선 연결 표시"
              aria-pressed={encounterVisible}
              className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs font-medium transition-all border ${
                encounterVisible
                  ? "panel border-red-500/40 text-red-200 hover:border-red-400 hover:bg-red-500/10"
                  : "bg-ocean-900/40 border-ocean-800/40 text-ocean-400 hover:bg-ocean-800/50 hover:text-ocean-200"
              }`}
            >
              <span className={`w-2.5 h-2.5 rounded-full transition-colors ${encounterVisible ? "bg-red-400" : "bg-ocean-700"}`} />
              CPA/TCPA 조우선
            </button>

            <button
              onClick={() => setPredictionVisible((v) => !v)}
              title="선택 선박 예상 진행선 표시"
              aria-pressed={predictionVisible}
              className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs font-medium transition-all border ${
                predictionVisible
                  ? "panel border-emerald-500/40 text-emerald-200 hover:border-emerald-400 hover:bg-emerald-500/10"
                  : "bg-ocean-900/40 border-ocean-800/40 text-ocean-400 hover:bg-ocean-800/50 hover:text-ocean-200"
              }`}
            >
              <span className={`w-2.5 h-2.5 rounded-full transition-colors ${predictionVisible ? "bg-emerald-400" : "bg-ocean-700"}`} />
              예측 경로
            </button>
          </div>
        </div>

        {showInfoPanels && (
          <div className="panel max-w-[280px] rounded px-3 py-2.5 text-[11px] leading-relaxed text-ocean-300 pointer-events-none select-none space-y-2.5">
            <div>
              <div className="flex items-center justify-between gap-3 text-ocean-100 mb-1">
                <span className="font-semibold text-sm">해양 레이어</span>
                <span className="font-mono text-[10px] text-ocean-400 bg-ocean-900/40 px-2 py-0.5 rounded">{activeNauticalLayerCount}/3</span>
              </div>
              <div className="text-ocean-400 text-[10px]">
                주요 표지·Fairway는 지도 확대 레벨 {MAP_NAV_AID_FETCH_MIN_ZOOM} 이상에서 자동으로 표시됩니다.
              </div>
            </div>
            <div className="border-t border-ocean-700/50 pt-2">
              <div className="flex items-center justify-between gap-3 text-ocean-100 mb-1">
                <span className="font-semibold text-sm">선택 선박 오버레이</span>
                <span className="font-mono text-[10px] text-ocean-400 bg-ocean-900/40 px-2 py-0.5 rounded">{activeSelectedOverlayCount}/4</span>
              </div>
              <div className="text-ocean-400 text-[10px] space-y-1">
                <p>• 파란 점선: 참고 기동 영역</p>
                <p>• 황색/적색: 실제 위험 도메인</p>
                <p>• CPA/TCPA: 최근접거리·시간</p>
              </div>
            </div>
          </div>
        )}

        {showInfoPanels && selectedId && (
          <div className="panel max-w-[320px] rounded px-3 py-2 text-[11px] leading-4 text-ocean-300 pointer-events-none select-none">
            <div className="flex items-center justify-between gap-3 text-ocean-100">
              <span className="font-medium">안전 영역 기준 안내</span>
              <span className="font-mono text-[10px] text-ocean-400">실시간</span>
            </div>
            <div className="mt-1 space-y-1 text-ocean-400">
              <p>파란 점선 도메인: 선박 크기·속도·heading/COG 기반 참고 기동 여유 영역</p>
              <p>황색/적색 위험 도메인: 활성 CPA/TCPA 경보가 있을 때만 표시되는 실제 위험 상태 강조</p>
              <p>흰색 점: 현재 속력·침로를 유지할 경우 가장 가까워지는 최근접 예상 위치</p>
              <p className="text-ocean-500">현재 경보 기준: warning CPA&lt;0.5NM · TCPA&lt;30분 / critical CPA&lt;0.2NM · TCPA&lt;10분</p>
            </div>
          </div>
        )}

        {showInfoPanels && selectedId && selectedCpaEncounters.length > 0 && (
          <div className="panel max-w-[300px] rounded px-3 py-2 text-[11px] leading-4 text-ocean-300 pointer-events-none select-none">
            <div className="flex items-center justify-between gap-3 text-ocean-100">
              <span className="font-medium">활성 CPA/TCPA 조우</span>
              <span className="font-mono text-[10px] text-ocean-400">{selectedCpaEncounters.length}건</span>
            </div>
            {selectedCpaEncounters[0] && (
              <div className={`mt-2 rounded border px-2.5 py-2 ${selectedCpaEncounters[0].severity === "critical" ? "border-red-500/45 bg-red-500/12 text-red-100" : "border-amber-500/45 bg-amber-500/12 text-amber-100"}`}>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[10px] font-semibold uppercase tracking-[0.18em] opacity-80">Primary encounter</span>
                  <span className="font-mono text-[10px] uppercase tracking-wide opacity-90">{selectedCpaEncounters[0].severity}</span>
                </div>
                <div className="mt-1 text-sm font-semibold">{selectedCpaEncounters[0].counterpartName}</div>
                <div className="mt-2 grid grid-cols-2 gap-2 text-[10px]">
                  <div className="rounded bg-black/15 px-2 py-1">
                    <div className="opacity-70">CPA</div>
                    <div className="font-mono text-[12px]">{selectedCpaEncounters[0].cpaNm !== null ? `${selectedCpaEncounters[0].cpaNm.toFixed(3)} NM` : "—"}</div>
                  </div>
                  <div className="rounded bg-black/15 px-2 py-1">
                    <div className="opacity-70">TCPA</div>
                    <div className="font-mono text-[12px]">{selectedCpaEncounters[0].tcpaMin !== null ? `${selectedCpaEncounters[0].tcpaMin.toFixed(1)}분` : "—"}</div>
                  </div>
                </div>
                {selectedEncounterRisk && (
                  <div className="mt-2 text-[10px] opacity-80">
                    위험 도메인 배율 ×{selectedEncounterRisk.scale.toFixed(2)}
                  </div>
                )}
              </div>
            )}
            <div className="mt-2 space-y-2">
              {selectedCpaEncounters.map((encounter, index) => {
                const tone = encounter.severity === "critical"
                  ? "border-red-500/40 bg-red-500/10 text-red-200"
                  : "border-amber-500/35 bg-amber-500/10 text-amber-100";
                return (
                  <div key={encounter.alertId} className={`rounded border px-2 py-1.5 ${tone} ${index === 0 ? "hidden" : "opacity-90"}`}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium">{encounter.counterpartName}</span>
                      <span className="font-mono text-[10px] uppercase tracking-wide opacity-80">
                        {encounter.severity}
                      </span>
                    </div>
                    <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-current/90">
                      <span>CPA {encounter.cpaNm !== null ? `${encounter.cpaNm.toFixed(3)} NM` : "—"}</span>
                      <span>TCPA {encounter.tcpaMin !== null ? `${encounter.tcpaMin.toFixed(1)}분` : "—"}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* 범례 */}
      <div className="absolute bottom-10 right-12 panel p-2.5 rounded text-xs space-y-1.5 pointer-events-none">
        {Object.entries(PLATFORM_LABELS).map(([type, label]) => {
          const colors: Record<string, string> = {
            vessel: "#2e8dd4",
            usv: "#22d3ee",
            rov: "#a78bfa",
            auv: "#818cf8",
            drone: "#34d399",
            buoy: "#fbbf24",
          };
          return (
            <div key={type} className="flex items-center gap-2">
              <span
                className="inline-block w-2 h-2 rounded-full"
                style={{ background: colors[type] }}
              />
              <span className="text-ocean-300">{label}</span>
            </div>
          );
        })}
        <div className="flex items-center gap-2 border-t border-ocean-800 pt-1.5 mt-0.5">
          <span className="inline-block w-2 h-2 rounded-full bg-red-500/60" />
          <span className="text-red-400">위험 경보</span>
        </div>
        <div className="border-t border-ocean-800 pt-1.5 mt-0.5 text-ocean-500 text-[10px] uppercase tracking-wider">항로 보조</div>
        <div className="flex items-center gap-2">
          <span className="inline-block w-2 h-2 rounded-full bg-cyan-300" />
          <span className="text-cyan-200">주요 부표/등대/표지</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-block w-3 h-px bg-emerald-300" />
          <span className="text-emerald-200">Fairway 보조선</span>
        </div>
        <div className="border-t border-ocean-800 pt-1.5 mt-0.5 text-ocean-500 text-[10px] uppercase tracking-wider">선택 선박</div>
        <div className="flex items-center gap-2">
          <span className="inline-block w-3 h-2 rounded-sm border border-sky-400/50 bg-sky-400/10" />
          <span className="text-sky-200">참고 기동 도메인</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-block w-3 h-2 rounded-sm border border-red-400/70 bg-red-400/20" />
          <span className="text-red-300">CPA/TCPA 위험 도메인</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-block w-3 h-px bg-red-400" />
          <span className="text-red-300">CPA/TCPA 조우선</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-block w-2 h-2 rounded-full border-2 border-red-400 bg-white" />
          <span className="text-slate-100">최근접 예상 지점</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-block w-3 h-2 rounded-sm border border-amber-400/70 bg-amber-400/20" />
          <span className="text-amber-200">진행 방향 부채꼴</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-block w-3 h-px bg-green-300" />
          <span className="text-green-200">예측 경로</span>
        </div>
        {zoneVisible && (
          <>
            <div className="border-t border-ocean-800 pt-1.5 mt-0.5 text-ocean-500 text-[10px] uppercase tracking-wider">구역</div>
            <div className="flex items-center gap-2">
              <span className="inline-block w-3 h-2 rounded-sm border border-red-400/70 bg-red-500/20" />
              <span className="text-red-300">금지</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="inline-block w-3 h-2 rounded-sm border border-amber-400/70 bg-amber-500/20" />
              <span className="text-amber-300">제한</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="inline-block w-3 h-2 rounded-sm border border-blue-400/70 bg-blue-500/20" />
              <span className="text-blue-300">주의</span>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default memo(MaritimeMap);
