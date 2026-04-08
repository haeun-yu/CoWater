"use client";

import { memo, useEffect, useMemo, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import { usePlatformStore } from "@/stores/platformStore";
import { useAlertStore } from "@/stores/alertStore";
import { useSystemStore } from "@/stores/systemStore";
import { useZoneStore, buildZoneGeoJSON, buildZoneLabelGeoJSON } from "@/stores/zoneStore";
import type { PlatformState } from "@/types";
import { createShipIcon } from "@/lib/shipIcon";
import {
  MAP_CENTER,
  MAP_ZOOM,
  MAP_OSM_OPACITY,
  MAP_SELECT_MIN_ZOOM,
  MAP_SELECT_FLY_DURATION,
  MAP_TRACK_EASE_DURATION,
  TRAIL_MAX,
  TRAIL_RECENT,
  TRAIL_MID,
  TRAIL_OPACITY,
  TRAIL_LINE_WIDTH,
  TRAIL_CASING_WIDTH,
  TRAIL_CASING_COLOR,
  TRAIL_CASING_OPACITY_FACTOR,
  ALERT_HIGHLIGHT_SEVERITY,
  ALERT_TRAIL_COLOR,
  PLATFORM_COLORS,
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

function MaritimeMap() {
  const mapRef = useRef<maplibregl.Map | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // 선박 마커 관리: platform_id → Marker
  const markersRef = useRef(new Map<string, maplibregl.Marker>());
  // 항적 관리: platform_id → [[lon, lat], ...]
  const trailsRef = useRef(new Map<string, LonLat[]>());
  // 직전 위치 기록 (중복 포인트 방지용)
  const prevPosRef = useRef(new Map<string, string>()); // pid → "lon,lat"
  // 현재 zoom
  const zoomRef = useRef(8);
  const followRef = useRef(false);

  const platforms = usePlatformStore((s) => s.platforms);
  const select = usePlatformStore((s) => s.select);
  const selectedId = usePlatformStore((s) => s.selectedId);
  const alerts = useAlertStore((s) => s.alerts);
  const streams = useSystemStore((s) => s.streams);
  const zones = useZoneStore((s) => s.zones);
  const [mapLoaded, setMapLoaded] = useState(false);
  const [seamarkVisible, setSeamarkVisible] = useState(true);
  const [zoneVisible, setZoneVisible] = useState(true);

  const alertPlatformIds = useMemo(
    () =>
      new Set(
        alerts
          .filter((a) => a.status === "new" && a.severity === ALERT_HIGHLIGHT_SEVERITY)
          .flatMap((a) => a.platform_ids),
      ),
    [alerts],
  );

  // zoom 핸들러는 마운트 1회짜리 useEffect 클로저 안에 있어서
  // platforms / selectedId / alertPlatformIds를 직접 참조하면 초기값에 고정된다.
  // ref를 통해 항상 최신 값을 읽도록 동기화한다.
  const platformsRef = useRef(platforms);
  const selectedIdRef = useRef(selectedId);
  const alertIdsRef = useRef(alertPlatformIds);
  platformsRef.current = platforms;
  selectedIdRef.current = selectedId;
  alertIdsRef.current = alertPlatformIds;

  // ── 선박 마커 생성/갱신 ────────────────────────────────────────────────────

  function updateMarker(
    p: PlatformState,
    isSelected: boolean,
    isAlert: boolean,
  ) {
    if (p.lat == null || p.lon == null) return;
    const { html, anchorX, anchorY } = createShipIcon(
      p.platform_type ?? "vessel",
      p.heading ?? p.cog ?? 0,
      isSelected,
      isAlert,
      zoomRef.current,
    );

    const existing = markersRef.current.get(p.platform_id);
    if (existing) {
      // 기존 마커: HTML 업데이트 + 위치 이동
      existing.getElement().innerHTML = html;
      existing.setLngLat([p.lon, p.lat]);
    } else {
      // 신규 마커 생성
      const el = document.createElement("div");
      el.innerHTML = html;
      el.style.cursor = "pointer";
      el.addEventListener("click", () => {
        followRef.current = true;
        select(p.platform_id);
      });

      const marker = new maplibregl.Marker({
        element: el,
        offset: [-anchorX, -anchorY], // hull center → coordinate
        anchor: "top-left",
      })
        .setLngLat([p.lon, p.lat])
        .addTo(mapRef.current!);

      markersRef.current.set(p.platform_id, marker);
    }
  }

  function removeStaleMarkers(currentIds: Set<string>) {
    for (const [pid, marker] of markersRef.current) {
      if (!currentIds.has(pid)) {
        marker.remove();
        markersRef.current.delete(pid);
        trailsRef.current.delete(pid);
        prevPosRef.current.delete(pid);
      }
    }
  }

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
    const src = map.getSource("trails") as maplibregl.GeoJSONSource | undefined;
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
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "© OpenStreetMap contributors",
          },
          seamark: {
            type: "raster",
            tiles: ["https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "© OpenSeaMap contributors",
          },
        },
        layers: [
          {
            id: "osm-layer",
            type: "raster",
            source: "osm",
            paint: { "raster-opacity": MAP_OSM_OPACITY },
          },
          { id: "seamark-layer", type: "raster", source: "seamark" },
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
      // ── 항적 소스 + 레이어 ────────────────────────────────────────────
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

      setMapLoaded(true);
    });

    // zoom 변화 시 모든 마커 아이콘 크기 갱신
    // ref를 통해 최신 platforms / selectedId / alertIds를 읽는다 (클로저 stale 방지)
    map.on("zoom", () => {
      zoomRef.current = map.getZoom();
      for (const [pid, marker] of markersRef.current) {
        const p = platformsRef.current[pid];
        if (!p) continue;
        const { html } = createShipIcon(
          p.platform_type ?? "vessel",
          p.heading ?? p.cog ?? 0,
          pid === selectedIdRef.current,
          alertIdsRef.current.has(pid),
          zoomRef.current,
        );
        marker.getElement().innerHTML = html;
      }
    });

    map.on("dragstart", () => {
      followRef.current = false;
    });

    mapRef.current = map;
    return () => {
      for (const m of markersRef.current.values()) m.remove();
      markersRef.current.clear();
      map.remove();
      mapRef.current = null;
      setMapLoaded(false);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── 플랫폼 업데이트 → 마커 + 항적 동기화 ─────────────────────────────────

  useEffect(() => {
    if (!mapLoaded || !mapRef.current) return;

    const visibleIds = new Set(
      Object.values(platforms)
        .filter((platform) => platform.lat != null && platform.lon != null)
        .map((platform) => platform.platform_id),
    );
    removeStaleMarkers(visibleIds);

    for (const p of Object.values(platforms)) {
      updateTrail(p);
      updateMarker(
        p,
        p.platform_id === selectedId,
        alertPlatformIds.has(p.platform_id),
      );
    }
    flushTrailSource();
  }, [platforms, alerts, mapLoaded]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── 선택 변경 → 마커 재렌더 + Follow ──────────────────────────────────────

  useEffect(() => {
    if (!mapLoaded || !mapRef.current) return;

    // 이전 선택 해제 (리셋)
    for (const [pid, marker] of markersRef.current) {
      const p = platforms[pid];
      if (!p) continue;
      const wasSelected = pid === selectedId;
      const { html } = createShipIcon(
        p.platform_type ?? "vessel",
        p.heading ?? p.cog ?? 0,
        wasSelected,
        alertPlatformIds.has(pid),
        zoomRef.current,
      );
      marker.getElement().innerHTML = html;
    }

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

  // ── 해도 심볼(OpenSeaMap) 레이어 표시/숨김 ────────────────────────────────

  useEffect(() => {
    if (!mapLoaded || !mapRef.current) return;
    mapRef.current.setLayoutProperty(
      "seamark-layer",
      "visibility",
      seamarkVisible ? "visible" : "none",
    );
  }, [seamarkVisible, mapLoaded]);

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

  const platformCount = Object.keys(platforms).length;
  const criticalCount = alerts.filter(
    (a) => a.severity === "critical" && a.status === "new",
  ).length;

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

      {/* 구역 레이어 토글 */}
      <div className="absolute top-3 right-12 z-10 flex gap-2">
        <button
          onClick={() => setZoneVisible((v) => !v)}
          title="설정된 금지·제한·주의 구역 표시"
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

      {/* 해도 심볼 토글 */}
        <button
          onClick={() => setSeamarkVisible((v) => !v)}
          title="OpenSeaMap 해도 심볼 (등대·부표·침선 등 실제 항로표지)"
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-colors border ${
            seamarkVisible
              ? "panel border-ocean-600/60 text-ocean-200 hover:border-ocean-500"
              : "bg-ocean-900/40 border-ocean-800/40 text-ocean-400 hover:text-ocean-400"
          }`}
        >
          {/* 등대 아이콘 (SVG) */}
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
          해도 심볼
          <span
            className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${seamarkVisible ? "bg-cyan-400" : "bg-ocean-700"}`}
          />
        </button>
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
