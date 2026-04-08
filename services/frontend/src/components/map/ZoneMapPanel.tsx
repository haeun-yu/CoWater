"use client";

import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import { MAP_CENTER, MAP_OSM_OPACITY, MAP_ZOOM } from "@/config";
import { buildZoneGeoJSON, buildZoneLabelGeoJSON, type Zone } from "@/stores/zoneStore";

const TYPE_LABEL: Record<string, string> = {
  prohibited: "금지",
  restricted: "제한",
  caution: "주의",
};

const TYPE_COLOR: Record<string, { fill: string; text: string }> = {
  prohibited: { fill: "#ef4444", text: "text-red-300" },
  restricted: { fill: "#f59e0b", text: "text-amber-300" },
  caution: { fill: "#3b82f6", text: "text-blue-300" },
};

interface ZoneMapPanelProps {
  zones: Zone[];
  selectedZoneId: string | null;
  onSelectZone: (id: string | null) => void;
}

export default function ZoneMapPanel({
  zones,
  selectedZoneId,
  onSelectZone,
}: ZoneMapPanelProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [mapLoaded, setMapLoaded] = useState(false);
  const [zoneVisible, setZoneVisible] = useState(true);

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
            attribution: "© OpenStreetMap",
          },
        },
        layers: [
          {
            id: "osm-layer",
            type: "raster",
            source: "osm",
            paint: { "raster-opacity": MAP_OSM_OPACITY },
          },
        ],
        glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
      },
      center: MAP_CENTER,
      zoom: MAP_ZOOM - 1,
      attributionControl: false,
    });

    map.addControl(new maplibregl.NavigationControl(), "bottom-right");

    map.on("load", () => {
      map.addSource("zones", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addSource("zone-labels", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });

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
          "fill-opacity": ["case", ["==", ["get", "zone_id"], ""], 0.08, 0.18],
        },
      });

      map.addLayer({
        id: "zones-fill-selected",
        type: "fill",
        source: "zones",
        filter: ["==", ["get", "zone_id"], ""],
        paint: {
          "fill-color": [
            "match", ["get", "zone_type"],
            "prohibited", "#ef4444",
            "restricted", "#f59e0b",
            "caution", "#3b82f6",
            "#64748b",
          ],
          "fill-opacity": 0.35,
        },
      });

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
          "line-width": ["case", ["==", ["get", "zone_id"], ""], 1.5, 2.2],
          "line-opacity": 0.85,
        },
      });

      map.addLayer({
        id: "zones-label",
        type: "symbol",
        source: "zone-labels",
        layout: {
          "text-field": ["concat", ["get", "name"], "\n", ["get", "type_label"]],
          "text-size": 13,
          "text-anchor": "center",
          "text-justify": "center",
          "text-font": ["Open Sans Regular", "Arial Unicode MS Regular"],
          "text-max-width": 12,
        },
        paint: {
          "text-color": "#f1f5f9",
          "text-halo-color": "#0f172a",
          "text-halo-width": 1.8,
        },
      });

      map.on("click", "zones-fill", (event) => {
        const feature = event.features?.[0];
        const zoneId = feature?.properties?.zone_id as string | undefined;
        onSelectZone(zoneId ?? null);
      });

      map.on("mouseenter", "zones-fill", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "zones-fill", () => {
        map.getCanvas().style.cursor = "";
      });

      setMapLoaded(true);
    });

    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
      setMapLoaded(false);
    };
  }, [onSelectZone]);

  useEffect(() => {
    if (!mapLoaded || !mapRef.current) return;
    const map = mapRef.current;
    (map.getSource("zones") as maplibregl.GeoJSONSource | undefined)
      ?.setData(buildZoneGeoJSON(zones, false) as Parameters<maplibregl.GeoJSONSource["setData"]>[0]);
    (map.getSource("zone-labels") as maplibregl.GeoJSONSource | undefined)
      ?.setData(buildZoneLabelGeoJSON(zones, false) as Parameters<maplibregl.GeoJSONSource["setData"]>[0]);
  }, [zones, mapLoaded]);

  useEffect(() => {
    if (!mapLoaded || !mapRef.current) return;
    const map = mapRef.current;

    map.setFilter(
      "zones-fill-selected",
      selectedZoneId
        ? ["==", ["get", "zone_id"], selectedZoneId]
        : ["==", ["get", "zone_id"], ""],
    );

    if (!selectedZoneId) return;

    const zone = zones.find((item) => item.zone_id === selectedZoneId);
    if (!zone?.geometry?.coordinates?.[0]?.length) return;

    let minLon = Infinity;
    let maxLon = -Infinity;
    let minLat = Infinity;
    let maxLat = -Infinity;

    for (const [lon, lat] of zone.geometry.coordinates[0]) {
      minLon = Math.min(minLon, lon);
      maxLon = Math.max(maxLon, lon);
      minLat = Math.min(minLat, lat);
      maxLat = Math.max(maxLat, lat);
    }

    map.fitBounds(
      [[minLon, minLat], [maxLon, maxLat]],
      { padding: 80, duration: 600, maxZoom: 14 },
    );
  }, [selectedZoneId, zones, mapLoaded]);

  useEffect(() => {
    if (!mapLoaded || !mapRef.current) return;
    const visibility = zoneVisible ? "visible" : "none";
    for (const layerId of ["zones-fill", "zones-fill-selected", "zones-border", "zones-label"]) {
      mapRef.current.setLayoutProperty(layerId, "visibility", visibility);
    }
  }, [zoneVisible, mapLoaded]);

  const activeCount = zones.filter((zone) => zone.active).length;

  return (
    <div className="relative w-full h-full rounded overflow-hidden border border-ocean-800">
      <div ref={containerRef} className="w-full h-full" />

      <div className="absolute top-3 right-3 z-10 flex gap-2">
        <button
          onClick={() => setZoneVisible((visible) => !visible)}
          title="구역 시각화 토글"
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-colors border ${
            zoneVisible
              ? "panel border-ocean-600/60 text-ocean-200 hover:border-ocean-500"
              : "bg-ocean-900/40 border-ocean-800/40 text-ocean-400 hover:text-ocean-300"
          }`}
        >
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" className="flex-shrink-0">
            <polygon points="6,1 11,10 1,10" fill="none" stroke="currentColor" strokeWidth="1.2" opacity="0.8" />
            <line x1="6" y1="4" x2="6" y2="7" stroke="currentColor" strokeWidth="1.2" />
            <circle cx="6" cy="8.5" r="0.7" fill="currentColor" />
          </svg>
          구역
          <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${zoneVisible ? "bg-amber-400" : "bg-ocean-700"}`} />
        </button>
      </div>

      <div className="absolute top-3 left-3 flex flex-col gap-1.5 pointer-events-none">
        <div className="panel px-2.5 py-1 text-xs text-ocean-300 rounded flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-green-400 inline-block" />
          <span className="font-mono">활성 {activeCount} / 전체 {zones.length}개</span>
        </div>
        {selectedZoneId && (
          <div className="panel px-2.5 py-1 text-xs text-ocean-200 rounded border border-ocean-600/60">
            {zones.find((zone) => zone.zone_id === selectedZoneId)?.name ?? selectedZoneId}
          </div>
        )}
      </div>

      {zoneVisible && (
        <div className="absolute bottom-8 left-3 panel p-2 rounded text-xs space-y-1 pointer-events-none">
          {(["prohibited", "restricted", "caution"] as const).map((type) => (
            <div key={type} className="flex items-center gap-1.5">
              <span
                className="inline-block w-3 h-2 rounded-sm border"
                style={{ background: `${TYPE_COLOR[type].fill}33`, borderColor: TYPE_COLOR[type].fill }}
              />
              <span className={TYPE_COLOR[type].text}>{TYPE_LABEL[type]}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
