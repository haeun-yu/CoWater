"use client";

import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import { usePlatformStore } from "@/stores/platformStore";
import { useAlertStore } from "@/stores/alertStore";
import type { PlatformState } from "@/types";

const PLATFORM_COLORS: Record<string, string> = {
  vessel: "#2e8dd4",
  usv:    "#22d3ee",
  rov:    "#a78bfa",
  auv:    "#818cf8",
  drone:  "#34d399",
  buoy:   "#fbbf24",
};

const PLATFORM_LABELS: Record<string, string> = {
  vessel: "선박",
  usv:    "USV",
  rov:    "ROV",
  auv:    "AUV",
  drone:  "드론",
  buoy:   "부이",
};

// 위쪽(북) 방향 화살표 — 캔버스에서 직접 픽셀 그리기, SDF용 흰색
function createArrowImage(): ImageData {
  const size = 32;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = "white";
  ctx.beginPath();
  ctx.moveTo(16, 2);
  ctx.lineTo(7, 28);
  ctx.lineTo(16, 21);
  ctx.lineTo(25, 28);
  ctx.closePath();
  ctx.fill();
  return ctx.getImageData(0, 0, size, size);
}

function toGeoJSON(
  platforms: Record<string, PlatformState>,
  alertPlatformIds: Set<string>,
) {
  return {
    type: "FeatureCollection" as const,
    features: Object.values(platforms)
      .filter((p) => p.lat != null && p.lon != null)
      .map((p) => ({
        type: "Feature" as const,
        geometry: { type: "Point" as const, coordinates: [p.lon, p.lat] },
        properties: {
          id:       p.platform_id,
          name:     formatName(p),
          type:     p.platform_type ?? "vessel",
          heading:  p.heading ?? p.cog ?? 0,
          sog:      p.sog ?? 0,
          color:    PLATFORM_COLORS[p.platform_type ?? "vessel"] ?? "#2e8dd4",
          alert:    alertPlatformIds.has(p.platform_id) ? 1 : 0,
        },
      })),
  };
}

function formatName(p: PlatformState): string {
  if (!p.name || p.name === p.platform_id) return p.platform_id.replace(/^MMSI-/, "");
  return p.name;
}

export default function MaritimeMap() {
  const mapRef       = useRef<maplibregl.Map | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const followRef    = useRef(false);

  const platforms  = usePlatformStore((s) => s.platforms);
  const select     = usePlatformStore((s) => s.select);
  const selectedId = usePlatformStore((s) => s.selectedId);
  const alerts     = useAlertStore((s) => s.alerts);
  const [mapLoaded, setMapLoaded] = useState(false);

  const alertPlatformIds = new Set(
    alerts
      .filter((a) => a.status === "new" && a.severity === "critical")
      .flatMap((a) => a.platform_ids),
  );

  // ── 지도 초기화 (마운트 1회) ─────────────────────────────────
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
          { id: "osm-layer",     type: "raster", source: "osm",     paint: { "raster-opacity": 0.35 } },
          { id: "seamark-layer", type: "raster", source: "seamark" },
        ],
        // 라벨용 글리프 — 없으면 symbol 레이어 전체가 zoom 중 숨겨질 수 있음
        glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
      },
      center: [126.55, 34.75],
      zoom: 8,
      attributionControl: false,
    });

    map.addControl(new maplibregl.NavigationControl(), "bottom-right");
    map.addControl(new maplibregl.ScaleControl({ unit: "nautical" }), "bottom-left");

    map.on("load", () => {
      // 화살표 SDF 이미지 (캔버스에서 직접 생성 — 비동기 없음)
      map.addImage("platform-arrow", createArrowImage(), { sdf: true });

      // ── GeoJSON 소스 ──────────────────────────────────────────
      map.addSource("platforms", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });

      // ── LAYER 1: 위험 경보 글로우 (circle) ───────────────────
      // circle 레이어는 zoom·글리프와 무관하게 항상 렌더링됨
      map.addLayer({
        id: "platform-alert-glow",
        type: "circle",
        source: "platforms",
        filter: ["==", ["get", "alert"], 1],
        paint: {
          "circle-radius": 26,
          "circle-color": "#ef4444",
          "circle-opacity": 0.20,
          "circle-blur": 0.5,
        },
      });

      // ── LAYER 2: 배경 글로우 (circle) ────────────────────────
      map.addLayer({
        id: "platform-glow",
        type: "circle",
        source: "platforms",
        paint: {
          "circle-radius": 13,
          "circle-color": ["get", "color"],
          "circle-opacity": 0.18,
        },
      });

      // ── LAYER 3: 실제 위치 도트 (circle) — 항상 표시됨 ──────
      // symbol 레이어가 zoom 중 사라져도 이 레이어는 반드시 유지됨
      map.addLayer({
        id: "platform-dot",
        type: "circle",
        source: "platforms",
        paint: {
          "circle-radius": [
            "interpolate", ["linear"], ["zoom"],
            6, 3,
            10, 4.5,
            14, 6,
          ],
          "circle-color": ["get", "color"],
          "circle-opacity": 1,
          "circle-stroke-width": 1,
          "circle-stroke-color": "#0a1628",
          "circle-stroke-opacity": 0.6,
        },
      });

      // ── LAYER 4: 방향 화살표 (symbol) ────────────────────────
      // zoom 중 잠깐 사라질 수 있지만 도트(3)가 항상 대체함
      map.addLayer({
        id: "platform-arrows",
        type: "symbol",
        source: "platforms",
        layout: {
          "icon-image": "platform-arrow",
          "icon-size": ["interpolate", ["linear"], ["zoom"], 6, 0.55, 10, 0.80, 14, 1.0],
          "icon-rotate": ["get", "heading"],
          "icon-rotation-alignment": "map",
          "icon-pitch-alignment": "map",
          "icon-allow-overlap": true,
          "icon-ignore-placement": true,
        },
        paint: {
          "icon-color": ["get", "color"],
          "icon-opacity": ["interpolate", ["linear"], ["zoom"], 7, 0.0, 8, 1.0],
        },
      });

      // ── LAYER 5: 이름 라벨 (symbol) ──────────────────────────
      map.addLayer({
        id: "platform-labels",
        type: "symbol",
        source: "platforms",
        minzoom: 9,   // zoom 9 이상에서만 표시
        layout: {
          "text-field": ["get", "name"],
          "text-size": 10,
          "text-offset": [0, 1.6],
          "text-anchor": "top",
          "text-optional": true,         // 라벨 표시 실패해도 아이콘 유지
          "text-allow-overlap": false,
          "text-font": ["Open Sans Bold", "Arial Unicode MS Bold"],
        },
        paint: {
          "text-color": ["get", "color"],
          "text-halo-color": "#020d1a",
          "text-halo-width": 1.5,
          "text-opacity": ["interpolate", ["linear"], ["zoom"], 9, 0.0, 10, 1.0],
        },
      });

      // ── LAYER 6: 선택 강조 링 (circle) ───────────────────────
      map.addLayer({
        id: "platform-selected",
        type: "circle",
        source: "platforms",
        filter: ["==", ["get", "id"], ""],
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 6, 12, 10, 16, 14, 20],
          "circle-color": "transparent",
          "circle-stroke-width": 2,
          "circle-stroke-color": "#ffffff",
          "circle-stroke-opacity": 0.85,
        },
      });

      // ── 클릭 핸들러 ───────────────────────────────────────────
      // dot 레이어에 걸어야 zoom 중에도 클릭 가능
      for (const layerId of ["platform-dot", "platform-arrows"]) {
        map.on("click", layerId, (e) => {
          const feature = e.features?.[0];
          if (feature?.properties?.id) {
            followRef.current = true;
            select(feature.properties.id as string);
          }
        });
        map.on("mouseenter", layerId, () => { map.getCanvas().style.cursor = "pointer"; });
        map.on("mouseleave", layerId, () => { map.getCanvas().style.cursor = ""; });
      }

      // 드래그 시 follow 해제
      map.on("dragstart", () => { followRef.current = false; });

      setMapLoaded(true);
    });

    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
      setMapLoaded(false);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── 플랫폼 데이터 동기화 ─────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;
    const source = map.getSource("platforms") as maplibregl.GeoJSONSource | undefined;
    source?.setData(toGeoJSON(platforms, alertPlatformIds));
  }, [platforms, alerts, mapLoaded]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── 선택 강조 + Follow ───────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;

    map.setFilter("platform-selected", ["==", ["get", "id"], selectedId ?? ""]);

    if (selectedId) {
      followRef.current = true;
      const p = platforms[selectedId];
      if (p?.lat != null && p?.lon != null) {
        map.flyTo({ center: [p.lon, p.lat], zoom: Math.max(map.getZoom(), 11), duration: 800, essential: true });
      }
    }
  }, [selectedId, mapLoaded]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── 선택된 선박 실시간 추적 (follow 활성 시) ─────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded || !selectedId || !followRef.current) return;
    const p = platforms[selectedId];
    if (p?.lat != null && p?.lon != null) {
      map.easeTo({ center: [p.lon, p.lat], duration: 300 });
    }
  }, [platforms, selectedId, mapLoaded]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── select 함수 변경 시 클릭 핸들러 갱신 ────────────────────
  // (useEffect dep 배열에서 select를 빼고 이벤트 위임으로 처리하므로 불필요)

  const platformCount = Object.keys(platforms).length;
  const criticalCount = alerts.filter((a) => a.severity === "critical" && a.status === "new").length;

  return (
    <div className="relative w-full h-full">
      <div ref={containerRef} className="w-full h-full" />

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
      </div>

      {/* 범례 */}
      <div className="absolute bottom-10 right-12 panel p-2.5 rounded text-xs space-y-1.5 pointer-events-none">
        {Object.entries(PLATFORM_LABELS).map(([type, label]) => (
          <div key={type} className="flex items-center gap-2">
            <span className="inline-block w-2 h-2 rounded-full" style={{ background: PLATFORM_COLORS[type] }} />
            <span className="text-ocean-300">{label}</span>
          </div>
        ))}
        <div className="flex items-center gap-2 border-t border-ocean-800 pt-1.5 mt-0.5">
          <span className="inline-block w-2 h-2 rounded-full bg-red-500/60" />
          <span className="text-red-400">위험 경보</span>
        </div>
      </div>
    </div>
  );
}
