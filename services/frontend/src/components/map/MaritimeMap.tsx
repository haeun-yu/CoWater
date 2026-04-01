"use client";

import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import { usePlatformStore } from "@/stores/platformStore";
import { useAlertStore } from "@/stores/alertStore";
import type { PlatformState } from "@/types";
import { createShipIcon } from "@/lib/shipIcon";

const PLATFORM_LABELS: Record<string, string> = {
  vessel: "선박", usv: "USV", rov: "ROV",
  auv: "AUV", drone: "드론", buoy: "부이",
};

// 항적: 최대 보관 포인트 수 (초당 1건 기준 ~90초)
const TRAIL_MAX = 90;
// 항적 3밴드 구분 (포인트 인덱스, 뒤에서부터)
const TRAIL_RECENT  = 15;  // 마지막 15포인트 → 불투명
const TRAIL_MID     = 45;  // 그 전 30포인트 → 반투명

type LonLat = [number, number];

type TrailFeature = {
  type: 'Feature';
  geometry: { type: 'LineString'; coordinates: LonLat[] };
  properties: { opacity: number; color: string };
};

/** 항적 GeoJSON FeatureCollection 생성 — 3-opacity 밴드 */
function buildTrailGeoJSON(
  trails: Map<string, LonLat[]>,
  platforms: Record<string, PlatformState>,
  alertIds: Set<string>,
) {
  const features: TrailFeature[] = [];

  const TYPE_COLOR: Record<string, string> = {
    vessel: '#2e8dd4', usv: '#22d3ee', rov: '#a78bfa',
    auv: '#818cf8', drone: '#34d399', buoy: '#fbbf24',
  };

  for (const [pid, pts] of trails) {
    if (pts.length < 2) continue;
    const p     = platforms[pid];
    const color = alertIds.has(pid) ? '#ef4444'
      : (TYPE_COLOR[p?.platform_type ?? 'vessel'] ?? '#2e8dd4');

    const bands: { pts: LonLat[]; opacity: number }[] = [
      { pts: pts.slice(0, -TRAIL_RECENT),                  opacity: 0.12 },
      { pts: pts.slice(-TRAIL_MID, -TRAIL_RECENT),         opacity: 0.38 },
      { pts: pts.slice(-TRAIL_RECENT),                     opacity: 0.82 },
    ];

    for (const band of bands) {
      if (band.pts.length < 2) continue;
      features.push({
        type: 'Feature' as const,
        geometry: { type: 'LineString' as const, coordinates: band.pts },
        properties: { opacity: band.opacity, color },
      });
    }
  }
  return { type: 'FeatureCollection' as const, features } as maplibregl.GeoJSONSourceSpecification['data'] & object;
}

export default function MaritimeMap() {
  const mapRef       = useRef<maplibregl.Map | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // 선박 마커 관리: platform_id → Marker
  const markersRef   = useRef(new Map<string, maplibregl.Marker>());
  // 항적 관리: platform_id → [[lon, lat], ...]
  const trailsRef    = useRef(new Map<string, LonLat[]>());
  // 직전 위치 기록 (중복 포인트 방지용)
  const prevPosRef   = useRef(new Map<string, string>()); // pid → "lon,lat"
  // 현재 zoom
  const zoomRef      = useRef(8);
  const followRef    = useRef(false);

  const platforms    = usePlatformStore((s) => s.platforms);
  const select       = usePlatformStore((s) => s.select);
  const selectedId   = usePlatformStore((s) => s.selectedId);
  const alerts       = useAlertStore((s) => s.alerts);
  const [mapLoaded, setMapLoaded] = useState(false);

  const alertPlatformIds = new Set(
    alerts
      .filter((a) => a.status === "new" && a.severity === "critical")
      .flatMap((a) => a.platform_ids),
  );

  // ── 선박 마커 생성/갱신 ────────────────────────────────────────────────────

  function updateMarker(p: PlatformState, isSelected: boolean, isAlert: boolean) {
    if (p.lat == null || p.lon == null) return;
    const { html, anchorX, anchorY } = createShipIcon(
      p.platform_type ?? 'vessel',
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
      const el = document.createElement('div');
      el.innerHTML = html;
      el.style.cursor = 'pointer';
      el.addEventListener('click', () => {
        followRef.current = true;
        select(p.platform_id);
      });

      const marker = new maplibregl.Marker({
        element: el,
        offset: [anchorX, anchorY], // hull center → coordinate
        anchor: 'top-left',
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
    const src = map.getSource('trails') as maplibregl.GeoJSONSource | undefined;
    src?.setData(buildTrailGeoJSON(trailsRef.current, platforms, alertPlatformIds));
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
            type: 'raster',
            tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
            tileSize: 256,
            attribution: '© OpenStreetMap contributors',
          },
          seamark: {
            type: 'raster',
            tiles: ['https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png'],
            tileSize: 256,
            attribution: '© OpenSeaMap contributors',
          },
        },
        layers: [
          { id: 'osm-layer',     type: 'raster', source: 'osm',     paint: { 'raster-opacity': 0.35 } },
          { id: 'seamark-layer', type: 'raster', source: 'seamark' },
        ],
        glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
      },
      center: [126.55, 34.75],
      zoom: 8,
      attributionControl: false,
    });

    map.addControl(new maplibregl.NavigationControl(), 'bottom-right');
    map.addControl(new maplibregl.ScaleControl({ unit: 'nautical' }), 'bottom-left');

    map.on('load', () => {
      // ── 항적 소스 + 레이어 ────────────────────────────────────────────
      map.addSource('trails', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      });

      // 항적 외곽선 (대비용)
      map.addLayer({
        id: 'trail-casing',
        type: 'line',
        source: 'trails',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': '#020d1a',
          'line-width': 3.5,
          'line-opacity': ['*', ['get', 'opacity'], 0.55],
        },
      });

      // 항적 메인
      map.addLayer({
        id: 'trail-line',
        type: 'line',
        source: 'trails',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': ['get', 'color'],
          'line-width': 2.0,
          'line-opacity': ['get', 'opacity'],
        },
      });

      setMapLoaded(true);
    });

    // zoom 변화 시 모든 마커 아이콘 크기 갱신
    map.on('zoom', () => {
      zoomRef.current = map.getZoom();
      for (const [pid, marker] of markersRef.current) {
        const p = platforms[pid];
        if (!p) continue;
        const { html } = createShipIcon(
          p.platform_type ?? 'vessel',
          p.heading ?? p.cog ?? 0,
          pid === selectedId,
          alertPlatformIds.has(pid),
          zoomRef.current,
        );
        marker.getElement().innerHTML = html;
      }
    });

    map.on('dragstart', () => { followRef.current = false; });

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

    const ids = new Set(Object.keys(platforms));
    removeStaleMarkers(ids);

    for (const p of Object.values(platforms)) {
      updateTrail(p);
      updateMarker(p, p.platform_id === selectedId, alertPlatformIds.has(p.platform_id));
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
        p.platform_type ?? 'vessel',
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
          zoom: Math.max(mapRef.current.getZoom(), 11),
          duration: 800,
          essential: true,
        });
      }
    }
  }, [selectedId, mapLoaded]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── 선택 선박 실시간 추적 ─────────────────────────────────────────────────

  useEffect(() => {
    if (!mapLoaded || !mapRef.current || !selectedId || !followRef.current) return;
    const p = platforms[selectedId];
    if (p?.lat != null && p?.lon != null) {
      mapRef.current.easeTo({ center: [p.lon, p.lat], duration: 300 });
    }
  }, [platforms, selectedId, mapLoaded]); // eslint-disable-line react-hooks/exhaustive-deps

  const platformCount = Object.keys(platforms).length;
  const criticalCount = alerts.filter((a) => a.severity === 'critical' && a.status === 'new').length;

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
        {Object.entries(PLATFORM_LABELS).map(([type, label]) => {
          const colors: Record<string, string> = {
            vessel: '#2e8dd4', usv: '#22d3ee', rov: '#a78bfa',
            auv: '#818cf8', drone: '#34d399', buoy: '#fbbf24',
          };
          return (
            <div key={type} className="flex items-center gap-2">
              <span className="inline-block w-2 h-2 rounded-full" style={{ background: colors[type] }} />
              <span className="text-ocean-300">{label}</span>
            </div>
          );
        })}
        <div className="flex items-center gap-2 border-t border-ocean-800 pt-1.5 mt-0.5">
          <span className="inline-block w-2 h-2 rounded-full bg-red-500/60" />
          <span className="text-red-400">위험 경보</span>
        </div>
      </div>
    </div>
  );
}
