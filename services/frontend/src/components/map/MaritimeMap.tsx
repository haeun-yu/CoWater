"use client";

import { memo, useEffect, useMemo, useRef, useState } from "react";
import maplibregl, { type GeoJSONSource } from "maplibre-gl";
import {
  buffer as turfBuffer,
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
import type { PlatformState } from "@/types";
import { getCoreApiUrl } from "@/lib/publicUrl";
import {
  ALERT_HIGHLIGHT_SEVERITY,
  ALERT_TRAIL_COLOR,
  MAP_CENTER,
  MAP_CLUSTER_MAX_ZOOM,
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

function toFeatureCollection(features: Array<PointFeature | PolygonFeature>) {
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

function buildSelectedSpatialData(platform: PlatformState | null) {
  if (!platform || platform.lat == null || platform.lon == null) {
    return {
      safetyBuffer: emptyFeatureCollection(),
      headingSector: emptyFeatureCollection(),
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
  const safetyRadiusNm = clamp(
    Math.max(MAP_SELECTED_SAFETY_BUFFER_BASE_NM, hullFootprintNm + speedAdvanceNm),
    MAP_SELECTED_SAFETY_BUFFER_BASE_NM,
    3.5,
  );
  const headingSectorRadiusNm = clamp(
    Math.max(safetyRadiusNm * MAP_SELECTED_HEADING_SECTOR_RADIUS_MULTIPLIER, metersToNm(dimensions.length * 2)),
    safetyRadiusNm,
    4.5,
  );

  const safetyBuffer = turfBuffer(center, nmToKm(safetyRadiusNm), { units: "kilometers" });

  const headingSector = normalizedHeading == null
    ? emptyFeatureCollection()
    : turfSector(
        center,
        nmToKm(headingSectorRadiusNm),
        normalizeBearing(normalizedHeading - MAP_SELECTED_HEADING_SECTOR_ANGLE_DEG / 2),
        normalizeBearing(normalizedHeading + MAP_SELECTED_HEADING_SECTOR_ANGLE_DEG / 2),
        { units: "kilometers" },
      );

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
    headingSector: headingSector as maplibregl.GeoJSONSourceSpecification["data"] & object,
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

async function fetchNauticalOverlays(bounds: maplibregl.LngLatBounds) {
  const south = bounds.getSouth();
  const west = bounds.getWest();
  const north = bounds.getNorth();
  const east = bounds.getEast();

  const query = `[out:json][timeout:20];(
    node["seamark:type"~"lighthouse|beacon_lateral|beacon_cardinal|buoy_lateral|buoy_cardinal"](${south},${west},${north},${east});
    way["waterway"="fairway"](${south},${west},${north},${east});
  );out body geom;`;

  const response = await fetch(OVERPASS_API_URL, {
    method: "POST",
    headers: { "Content-Type": "text/plain;charset=UTF-8" },
    body: query,
  });
  if (!response.ok) {
    throw new Error(`Overpass request failed: ${response.status}`);
  }
  const data = (await response.json()) as { elements?: OverpassElement[] };
  const elements = data.elements ?? [];

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
    fairways: { type: "FeatureCollection" as const, features: fairwayFeatures },
  };
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
  const [safetyBufferVisible, setSafetyBufferVisible] = useState(true);
  const [headingSectorVisible, setHeadingSectorVisible] = useState(true);
  const [predictionVisible, setPredictionVisible] = useState(true);

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
            clusterRadius: 46,
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
          "selected-heading-sector": {
            type: "geojson",
            data: { type: "FeatureCollection", features: [] },
          },
          "selected-prediction": {
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
        glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
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
          "line-color": "#0f172a",
          "line-width": 4,
          "line-opacity": 0.5,
        },
      });

      map.addLayer({
        id: "history-trail-line",
        type: "line",
        source: "history-trail",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": "#fbbf24",
          "line-width": 2,
          "line-opacity": 0.65,
          "line-dasharray": [3, 2],
        },
      });

      map.addLayer({
        id: "selected-safety-buffer-fill",
        type: "fill",
        source: "selected-safety-buffer",
        paint: {
          "fill-color": "#38bdf8",
          "fill-opacity": 0.08,
        },
      });

      map.addLayer({
        id: "selected-safety-buffer-line",
        type: "line",
        source: "selected-safety-buffer",
        paint: {
          "line-color": "#38bdf8",
          "line-width": 1.4,
          "line-opacity": 0.55,
          "line-dasharray": [3, 2],
        },
      });

      map.addLayer({
        id: "selected-heading-sector-fill",
        type: "fill",
        source: "selected-heading-sector",
        paint: {
          "fill-color": "#f59e0b",
          "fill-opacity": 0.12,
        },
      });

      map.addLayer({
        id: "selected-heading-sector-line",
        type: "line",
        source: "selected-heading-sector",
        paint: {
          "line-color": "#fbbf24",
          "line-width": 1.2,
          "line-opacity": 0.65,
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
        layout: { visibility: "none", "line-cap": "round", "line-join": "round" },
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
            16,
            10,
            20,
            30,
            24,
            100,
            30,
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
          "text-field": [
            "case",
            ["==", ["get", "selected"], true],
            ["get", "name"],
            ["==", ["get", "alert"], true],
            ["get", "name"],
            [">=", ["zoom"], 12],
            ["get", "name"],
            "",
          ],
          "text-size": 11,
          "text-offset": [0, 1.8],
          "text-anchor": "top",
          "text-font": ["Open Sans Regular", "Arial Unicode MS Regular"],
        },
        paint: {
          "text-color": "#e2e8f0",
          "text-halo-color": "#020617",
          "text-halo-width": 1.2,
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
          "line-dasharray": [
            "case",
            ["==", ["get", "zone_type"], "prohibited"],
            ["literal", [1, 0]],
            ["literal", [4, 2]],
          ],
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
        followRef.current = true;
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
          const bounds = map.getBounds();
          const key = `${bounds.getSouth().toFixed(2)}:${bounds.getWest().toFixed(2)}:${bounds.getNorth().toFixed(2)}:${bounds.getEast().toFixed(2)}`;
          if (lastOverlayBoundsRef.current === key) return;
          lastOverlayBoundsRef.current = key;

          const cached = overlayCacheRef.current.get(key);
          if (cached) {
            (map.getSource("nav-aids") as GeoJSONSource | undefined)?.setData(cached.navAids);
            (map.getSource("fairways") as GeoJSONSource | undefined)?.setData(cached.fairways);
            return;
          }

          try {
            const overlayData = await fetchNauticalOverlays(bounds);
            overlayCacheRef.current.set(key, overlayData);
            if (overlayCacheRef.current.size > 12) {
              const oldestKey = overlayCacheRef.current.keys().next().value;
              if (oldestKey) overlayCacheRef.current.delete(oldestKey);
            }
            (map.getSource("nav-aids") as GeoJSONSource | undefined)?.setData(overlayData.navAids);
            (map.getSource("fairways") as GeoJSONSource | undefined)?.setData(overlayData.fairways);
          } catch (error) {
            console.error("[map] failed to fetch nautical overlays", error);
          }
        }, 250);
      });

      setMapLoaded(true);
    });

    map.on("dragstart", () => {
      followRef.current = false;
    });

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
  }, [platforms, alerts, mapLoaded]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!mapLoaded || !mapRef.current) return;

    if (selectedId) {
      followRef.current = true;
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
    const selectedPlatform = selectedId ? (platforms[selectedId] ?? null) : null;
    const spatialData = buildSelectedSpatialData(selectedPlatform);
    (mapRef.current.getSource("selected-safety-buffer") as GeoJSONSource | undefined)?.setData(spatialData.safetyBuffer);
    (mapRef.current.getSource("selected-heading-sector") as GeoJSONSource | undefined)?.setData(spatialData.headingSector);
    (mapRef.current.getSource("selected-prediction") as GeoJSONSource | undefined)?.setData(spatialData.predictedPath);
  }, [platforms, selectedId, mapLoaded]);

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
        const points = (await res.json()) as Array<{ lon: number; lat: number }>;
        if (controller.signal.aborted) return;
        if (points.length < 2) {
          src.setData({ type: "FeatureCollection", features: [] });
          return;
        }
        const simplifiedCoordinates = simplifyHistoryLine(points);
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
    for (const id of ["zones-fill", "zones-border", "zones-label"]) {
      mapRef.current.setLayoutProperty(id, "visibility", vis);
    }
  }, [zoneVisible, mapLoaded]);

  useEffect(() => {
    if (!mapLoaded || !mapRef.current) return;
    const vis = safetyBufferVisible ? "visible" : "none";
    for (const id of ["selected-safety-buffer-fill", "selected-safety-buffer-line"]) {
      mapRef.current.setLayoutProperty(id, "visibility", vis);
    }
  }, [safetyBufferVisible, mapLoaded]);

  useEffect(() => {
    if (!mapLoaded || !mapRef.current) return;
    const vis = headingSectorVisible ? "visible" : "none";
    for (const id of ["selected-heading-sector-fill", "selected-heading-sector-line"]) {
      mapRef.current.setLayoutProperty(id, "visibility", vis);
    }
  }, [headingSectorVisible, mapLoaded]);

  useEffect(() => {
    if (!mapLoaded || !mapRef.current) return;
    mapRef.current.setLayoutProperty(
      "selected-prediction-line",
      "visibility",
      predictionVisible ? "visible" : "none",
    );
  }, [predictionVisible, mapLoaded]);

  const platformCount = Object.keys(platforms).length;
  const criticalCount = alerts.filter(
    (a) => a.severity === "critical" && a.status === "new",
  ).length;
  const activeNauticalLayerCount = Number(navAidVisible) + Number(fairwayVisible) + Number(seamarkVisible);
  const activeSelectedOverlayCount = Number(safetyBufferVisible) + Number(headingSectorVisible) + Number(predictionVisible);

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

      {/* 레이어 토글 */}
      <div className="absolute top-3 right-12 z-10 flex flex-col items-end gap-2">
        <div className="flex flex-wrap justify-end gap-2">
          <button
            onClick={() => setZoneVisible((v) => !v)}
            title="설정된 금지·제한·주의 구역 표시"
            aria-pressed={zoneVisible}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-colors border ${
              zoneVisible
                ? "panel border-ocean-600/60 text-ocean-200 hover:border-ocean-500"
                : "bg-ocean-900/40 border-ocean-800/40 text-ocean-400 hover:text-ocean-300"
            }`}
          >
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" className="flex-shrink-0">
              <polygon points="6,1 11,10 1,10" fill="none" stroke="currentColor" strokeWidth="1.2" opacity="0.8"/>
              <line x1="6" y1="4" x2="6" y2="7" stroke="currentColor" strokeWidth="1.2"/>
              <circle cx="6" cy="8.5" r="0.7" fill="currentColor"/>
            </svg>
            구역
            <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${zoneVisible ? "bg-amber-400" : "bg-ocean-700"}`} />
          </button>

          <button
            onClick={() => setNavAidVisible((v) => !v)}
            title="주요 부표·등대·표지만 간추려 표시"
            aria-pressed={navAidVisible}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-colors border ${
              navAidVisible
                ? "panel border-ocean-600/60 text-ocean-200 hover:border-ocean-500"
                : "bg-ocean-900/40 border-ocean-800/40 text-ocean-400 hover:text-ocean-300"
            }`}
          >
            <span className={`w-2 h-2 rounded-full ${navAidVisible ? "bg-cyan-300" : "bg-ocean-700"}`} />
            주요 표지
          </button>

          <button
            onClick={() => setFairwayVisible((v) => !v)}
            title="항로 감각을 돕는 fairway 보조 레이어"
            aria-pressed={fairwayVisible}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-colors border ${
              fairwayVisible
                ? "panel border-ocean-600/60 text-ocean-200 hover:border-ocean-500"
                : "bg-ocean-900/40 border-ocean-800/40 text-ocean-400 hover:text-ocean-300"
            }`}
          >
            <span className={`w-2 h-2 rounded-full ${fairwayVisible ? "bg-emerald-300" : "bg-ocean-700"}`} />
            Fairway
          </button>

          <button
            onClick={() => setSeamarkVisible((v) => !v)}
            title="OpenSeaMap 전체 seamark 오버레이 (세부 정보 많음)"
            aria-pressed={seamarkVisible}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-colors border ${
              seamarkVisible
                ? "panel border-ocean-600/60 text-ocean-200 hover:border-ocean-500"
                : "bg-ocean-900/40 border-ocean-800/40 text-ocean-400 hover:text-ocean-400"
            }`}
          >
            <svg
              width="12"
              height="12"
              viewBox="0 0 12 12"
              fill="none"
              className="flex-shrink-0"
            >
              <rect
                x="4.5"
                y="0"
                width="3"
                height="2"
                rx="0.5"
                fill="currentColor"
                opacity="0.8"
              />
              <path d="M4 2h4l1 8H3L4 2Z" fill="currentColor" opacity="0.5" />
              <rect
                x="3"
                y="10"
                width="6"
                height="2"
                rx="0.5"
                fill="currentColor"
              />
            </svg>
            전체 seamark
            <span
              className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${seamarkVisible ? "bg-cyan-400" : "bg-ocean-700"}`}
            />
          </button>

          <button
            onClick={() => setSafetyBufferVisible((v) => !v)}
            title="선택 선박 안전 반경 표시"
            aria-pressed={safetyBufferVisible}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-colors border ${
              safetyBufferVisible
                ? "panel border-ocean-600/60 text-ocean-200 hover:border-ocean-500"
                : "bg-ocean-900/40 border-ocean-800/40 text-ocean-400 hover:text-ocean-300"
            }`}
          >
            <span className={`w-2 h-2 rounded-full ${safetyBufferVisible ? "bg-sky-300" : "bg-ocean-700"}`} />
            안전 반경
          </button>

          <button
            onClick={() => setHeadingSectorVisible((v) => !v)}
            title="선택 선박 진행 방향 부채꼴 표시"
            aria-pressed={headingSectorVisible}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-colors border ${
              headingSectorVisible
                ? "panel border-ocean-600/60 text-ocean-200 hover:border-ocean-500"
                : "bg-ocean-900/40 border-ocean-800/40 text-ocean-400 hover:text-ocean-300"
            }`}
          >
            <span className={`w-2 h-2 rounded-full ${headingSectorVisible ? "bg-amber-300" : "bg-ocean-700"}`} />
            진행 방향 부채꼴
          </button>

          <button
            onClick={() => setPredictionVisible((v) => !v)}
            title="선택 선박 예상 진행선 표시"
            aria-pressed={predictionVisible}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-colors border ${
              predictionVisible
                ? "panel border-ocean-600/60 text-ocean-200 hover:border-ocean-500"
                : "bg-ocean-900/40 border-ocean-800/40 text-ocean-400 hover:text-ocean-300"
            }`}
          >
            <span className={`w-2 h-2 rounded-full ${predictionVisible ? "bg-green-300" : "bg-ocean-700"}`} />
            예측 경로
          </button>
        </div>

        <div className="panel max-w-[240px] rounded px-3 py-2 text-[11px] leading-4 text-ocean-300">
          <div className="flex items-center justify-between gap-3 text-ocean-100">
            <span className="font-medium">해양 레이어</span>
            <span className="font-mono text-[10px] text-ocean-400">{activeNauticalLayerCount}/3 활성</span>
          </div>
          <div className="mt-1 text-ocean-400">
            주요 표지·Fairway는 <span className="font-mono">zoom {MAP_NAV_AID_FETCH_MIN_ZOOM}+</span>에서 자동 조회됩니다.
          </div>
          <div className="mt-2 flex items-center justify-between gap-3 text-ocean-100">
            <span className="font-medium">선택 선박 오버레이</span>
            <span className="font-mono text-[10px] text-ocean-400">{activeSelectedOverlayCount}/3 활성</span>
          </div>
          <div className="mt-1 text-ocean-400">
            선박 크기·속도 기반 안전 반경, 진행 방향 부채꼴, {MAP_SELECTED_PREDICTION_MINUTES}분 예측 경로를 표시합니다.
          </div>
        </div>
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
          <span className="inline-block w-3 h-2 rounded-sm border border-sky-400/70 bg-sky-400/20" />
          <span className="text-sky-200">안전 반경</span>
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
