"use client";

import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import { usePlatformStore } from "@/stores/platformStore";
import type { PlatformState } from "@/types";

const PLATFORM_COLORS: Record<string, string> = {
  vessel: "#2e8dd4",
  usv:    "#22d3ee",
  rov:    "#a78bfa",
  auv:    "#818cf8",
  drone:  "#34d399",
  buoy:   "#fbbf24",
};

export default function MaritimeMap() {
  const mapRef = useRef<maplibregl.Map | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const markersRef = useRef<Map<string, maplibregl.Marker>>(new Map());
  const platforms = usePlatformStore((s) => s.platforms);
  const select = usePlatformStore((s) => s.select);
  // 지도 스타일 로딩 완료 여부 — 이 상태가 변경되면 플랫폼 마커 useEffect가 재실행됨
  const [mapLoaded, setMapLoaded] = useState(false);

  // 지도 초기화
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
            paint: { "raster-opacity": 0.3 },
          },
          {
            id: "seamark-layer",
            type: "raster",
            source: "seamark",
          },
        ],
        glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
      },
      center: [126.55, 34.75], // 한국 남해안 중심
      zoom: 8,
      attributionControl: false,
    });

    map.addControl(new maplibregl.NavigationControl(), "bottom-right");
    map.addControl(new maplibregl.ScaleControl({ unit: "nautical" }), "bottom-left");
    // 스타일 로딩 완료 시 state 갱신 → 마커 useEffect 재실행 보장
    map.on("load", () => setMapLoaded(true));
    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
      setMapLoaded(false);
    };
  }, []);

  // 플랫폼 마커 동기화 — mapLoaded를 의존성에 포함하여 스타일 로드 후 반드시 실행
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;

    const currentIds = new Set(Object.keys(platforms));

    // 제거된 플랫폼 마커 삭제
    for (const [id, marker] of markersRef.current.entries()) {
      if (!currentIds.has(id)) {
        marker.remove();
        markersRef.current.delete(id);
      }
    }

    // 추가/갱신
    for (const platform of Object.values(platforms)) {
      if (platform.lat == null || platform.lon == null) continue;
      updateMarker(map, platform, markersRef.current, select);
    }
  }, [platforms, select, mapLoaded]);

  return (
    <div className="relative w-full h-full">
      <div ref={containerRef} className="w-full h-full" />

      {/* 줌 레벨 표시 */}
      <div className="absolute top-3 left-3 panel px-2 py-1 text-xs text-ocean-300 rounded">
        {Object.keys(platforms).length}척 관제 중
      </div>

      {/* 범례 */}
      <div className="absolute bottom-10 right-12 panel p-2 rounded text-xs space-y-1">
        {Object.entries(PLATFORM_COLORS).map(([type, color]) => (
          <div key={type} className="flex items-center gap-2">
            <span style={{ color }} className="text-base">▲</span>
            <span className="text-ocean-300 uppercase">{type}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── 마커 생성/갱신 헬퍼 ───────────────────────────────────────────────────

function updateMarker(
  map: maplibregl.Map,
  platform: PlatformState,
  markers: Map<string, maplibregl.Marker>,
  select: (id: string | null) => void
) {
  const color = PLATFORM_COLORS[platform.platform_type] ?? "#ffffff";
  const heading = platform.heading ?? 0;

  const existing = markers.get(platform.platform_id);

  if (existing) {
    existing.setLngLat([platform.lon, platform.lat]);
    // 방향 갱신
    const el = existing.getElement();
    const arrow = el.querySelector<HTMLElement>(".vessel-arrow");
    if (arrow) arrow.style.transform = `rotate(${heading}deg)`;
    return;
  }

  // 새 마커 생성
  const el = document.createElement("div");
  el.className = "vessel-marker cursor-pointer";
  el.style.cssText = `
    width: 28px; height: 28px;
    display: flex; align-items: center; justify-content: center;
    position: relative;
  `;

  const arrow = document.createElement("div");
  arrow.className = "vessel-arrow";
  arrow.style.cssText = `
    width: 0; height: 0;
    border-left: 6px solid transparent;
    border-right: 6px solid transparent;
    border-bottom: 18px solid ${color};
    transform: rotate(${heading}deg);
    filter: drop-shadow(0 0 4px ${color}88);
    transition: transform 0.3s ease;
  `;
  el.appendChild(arrow);

  // 이름 라벨
  if (platform.name) {
    const label = document.createElement("div");
    label.style.cssText = `
      position: absolute; top: 100%; left: 50%;
      transform: translateX(-50%);
      font-size: 10px; color: ${color};
      white-space: nowrap; pointer-events: none;
      text-shadow: 0 0 4px #000;
      font-family: 'JetBrains Mono', monospace;
    `;
    label.textContent = platform.name;
    el.appendChild(label);
  }

  el.addEventListener("click", () => select(platform.platform_id));

  const marker = new maplibregl.Marker({ element: el, anchor: "center" })
    .setLngLat([platform.lon, platform.lat])
    .addTo(map);

  markers.set(platform.platform_id, marker);
}
