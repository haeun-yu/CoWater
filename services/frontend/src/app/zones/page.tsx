"use client";

import { useEffect, useState } from "react";
import type { MultiPolygon, Polygon } from "geojson";
import { area as turfArea, bbox as turfBbox, booleanValid as turfBooleanValid, feature, pointOnFeature } from "@turf/turf";
import ZoneMapPanel from "@/components/map/ZoneMapPanel";
import { getCoreApiUrl } from "@/lib/publicUrl";
import { useZoneStore, type Zone } from "@/stores/zoneStore";

type ZoneType = "prohibited" | "restricted" | "caution";

const TYPE_LABEL: Record<string, string> = {
  prohibited: "금지",
  restricted: "제한",
  caution: "주의",
};

const TYPE_COLOR: Record<string, { fill: string; border: string; text: string; badge: string }> = {
  prohibited: { fill: "#ef4444", border: "border-red-500/40",   text: "text-red-300",   badge: "bg-red-500/15 text-red-300 border-red-500/30" },
  restricted: { fill: "#f59e0b", border: "border-amber-500/40", text: "text-amber-300", badge: "bg-amber-500/15 text-amber-300 border-amber-500/30" },
  caution:    { fill: "#3b82f6", border: "border-blue-500/40",  text: "text-blue-300",  badge: "bg-blue-500/15 text-blue-300 border-blue-500/30" },
};

// ── 메인 페이지 ───────────────────────────────────────────────────────────────

export default function ZonesPage() {
  const zonesFromStore = useZoneStore((s) => s.zones);
  const setZonesInStore = useZoneStore((s) => s.setZones);

  const [name, setName] = useState("");
  const [zoneType, setZoneType] = useState<ZoneType>("restricted");
  const [geometryText, setGeometryText] = useState(
    '{"type":"Polygon","coordinates":[[[126.37,34.77],[126.39,34.77],[126.39,34.79],[126.37,34.79],[126.37,34.77]]]}',
  );
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedZoneId, setSelectedZoneId] = useState<string | null>(null);

  let geometryPreview: {
    valid: boolean;
    areaKm2: number | null;
    bboxText: string | null;
    centroidText: string | null;
    error: string | null;
  } = {
    valid: false,
    areaKm2: null,
    bboxText: null,
    centroidText: null,
    error: null,
  };

  try {
    const geometry = JSON.parse(geometryText) as Zone["geometry"];
    const zoneFeature = feature(geometry as Polygon | MultiPolygon);
    const isValid = turfBooleanValid(zoneFeature);
    const [minLon, minLat, maxLon, maxLat] = turfBbox(zoneFeature);
    const centroid = pointOnFeature(zoneFeature);
    geometryPreview = {
      valid: isValid,
      areaKm2: turfArea(zoneFeature) / 1_000_000,
      bboxText: `${minLon.toFixed(4)}, ${minLat.toFixed(4)} → ${maxLon.toFixed(4)}, ${maxLat.toFixed(4)}`,
      centroidText: `${centroid.geometry.coordinates[1].toFixed(4)}, ${centroid.geometry.coordinates[0].toFixed(4)}`,
      error: isValid ? null : "GeoJSON 형상은 파싱되지만 self-intersection 등으로 유효하지 않을 수 있습니다.",
    };
  } catch (previewError) {
    geometryPreview = {
      valid: false,
      areaKm2: null,
      bboxText: null,
      centroidText: null,
      error: previewError instanceof Error ? previewError.message : "GeoJSON 파싱 실패",
    };
  }

  // store의 zones를 로컬 상태로 사용 (페이지 내 변경도 store에 반영)
  const zones = zonesFromStore;

  async function loadZones() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${getCoreApiUrl()}/zones?active_only=false`);
      if (!res.ok) throw new Error(`zones load failed (${res.status})`);
      const data = (await res.json()) as Zone[];
      setZonesInStore(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "구역 목록 로드 실패");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    // store에 이미 데이터 있으면 추가 fetch 생략
    if (zones.length === 0) loadZones();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function createZone() {
    setCreating(true);
    setError(null);
    try {
      const geometry = JSON.parse(geometryText);
      const res = await fetch(`${getCoreApiUrl()}/zones`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, zone_type: zoneType, geometry, rules: {} }),
      });
      if (!res.ok) throw new Error(`zone create failed (${res.status})`);
      setName("");
      await loadZones();
    } catch (e) {
      setError(e instanceof Error ? e.message : "구역 생성 실패");
    } finally {
      setCreating(false);
    }
  }

  async function deactivateZone(zoneId: string) {
    try {
      const res = await fetch(`${getCoreApiUrl()}/zones/${zoneId}/deactivate`, { method: "PATCH" });
      if (!res.ok) throw new Error(`zone deactivate failed (${res.status})`);
      await loadZones();
    } catch (e) {
      setError(e instanceof Error ? e.message : "구역 비활성화 실패");
    }
  }

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* 헤더 */}
      <div className="px-5 py-3 border-b border-ocean-800 flex items-center justify-between flex-shrink-0">
        <div>
          <h1 className="text-base font-bold text-ocean-200 tracking-wider">구역 관리</h1>
          <p className="text-xs text-ocean-500 mt-0.5">
            Zone Monitor가 참조하는 금지·제한·주의 구역을 관리합니다.
          </p>
        </div>
        <button
          onClick={loadZones}
          disabled={loading}
          className="text-xs px-3 py-1.5 border border-ocean-700 rounded text-ocean-300 hover:border-ocean-500 disabled:opacity-40"
        >
          {loading ? "로딩 중..." : "새로고침"}
        </button>
      </div>

      {/* 본문: 왼쪽(폼+목록) | 오른쪽(지도) */}
      <div className="flex-1 min-h-0 grid grid-cols-1 xl:grid-cols-[340px_minmax(0,1fr)] gap-3 p-4">

        {/* ── 왼쪽: 생성 폼 + 구역 목록 ─────────────────────────────────────── */}
        <div className="flex flex-col gap-3 min-h-0 overflow-hidden">

          {/* 생성 폼 */}
          <section className="rounded border border-ocean-800 bg-ocean-900/30 p-3 flex-shrink-0">
            <h2 className="text-sm font-bold text-ocean-200 mb-2">구역 생성</h2>
            {error && <div className="text-xs text-red-400 mb-2 px-2 py-1 bg-red-950/30 border border-red-800/40 rounded">{error}</div>}
            <div className="space-y-2">
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="구역 이름"
                className="w-full text-sm px-2.5 py-1.5 rounded border border-ocean-700 bg-ocean-950 text-ocean-200 focus:outline-none focus:border-ocean-500"
              />
              <select
                value={zoneType}
                onChange={(e) => setZoneType(e.target.value as ZoneType)}
                className="w-full text-sm px-2.5 py-1.5 rounded border border-ocean-700 bg-ocean-950 text-ocean-200"
              >
                <option value="prohibited">🔴 금지 (prohibited)</option>
                <option value="restricted">🟡 제한 (restricted)</option>
                <option value="caution">🔵 주의 (caution)</option>
              </select>
              <div>
                <div className="text-xs text-ocean-500 mb-1">GeoJSON Geometry</div>
                <textarea
                  value={geometryText}
                  onChange={(e) => setGeometryText(e.target.value)}
                  rows={6}
                  className="w-full text-xs px-2 py-1.5 rounded border border-ocean-700 bg-ocean-950 text-ocean-200 font-mono leading-relaxed focus:outline-none focus:border-ocean-500"
                />
                <div className={`mt-2 rounded border px-2.5 py-2 text-xs ${geometryPreview.valid ? "border-emerald-500/30 bg-emerald-500/8 text-emerald-200" : "border-amber-500/30 bg-amber-500/8 text-amber-200"}`}>
                  <div className="font-medium">Turf.js preview {geometryPreview.valid ? "유효" : "검토 필요"}</div>
                  {geometryPreview.error ? (
                    <div className="mt-1 text-[11px] opacity-90">{geometryPreview.error}</div>
                  ) : (
                    <div className="mt-1 space-y-1 text-[11px]">
                      <div>면적: {geometryPreview.areaKm2?.toFixed(3)} km²</div>
                      <div>BBOX: {geometryPreview.bboxText}</div>
                      <div>대표점: {geometryPreview.centroidText}</div>
                    </div>
                  )}
                </div>
              </div>
              <button
                onClick={createZone}
                disabled={creating || !name.trim() || !geometryPreview.valid}
                className="w-full text-sm py-1.5 rounded border border-cyan-600 text-cyan-300 hover:bg-cyan-900/20 disabled:opacity-40 transition-colors"
              >
                {creating ? "생성 중..." : "구역 생성"}
              </button>
            </div>
          </section>

          {/* 구역 목록 */}
          <section className="rounded border border-ocean-800 bg-ocean-900/30 p-3 flex-1 min-h-0 overflow-auto">
            <h2 className="text-sm font-bold text-ocean-200 mb-2">
              구역 목록
              <span className="ml-2 text-xs text-ocean-500 font-normal">
                활성 {zones.filter((z) => z.active).length} / 전체 {zones.length}
              </span>
            </h2>
            <div className="space-y-1.5">
              {zones.map((z) => {
                const c = TYPE_COLOR[z.zone_type] ?? { badge: "text-ocean-300 border-ocean-700", text: "text-ocean-300", border: "border-ocean-700" };
                const isSelected = selectedZoneId === z.zone_id;
                return (
                  <div
                    key={z.zone_id}
                    onClick={() => setSelectedZoneId(isSelected ? null : z.zone_id)}
                    className={`rounded border p-2.5 cursor-pointer transition-colors ${
                      isSelected
                        ? `bg-ocean-800/60 ${c.border}`
                        : "bg-ocean-950/40 border-ocean-800 hover:border-ocean-700"
                    } ${!z.active ? "opacity-50" : ""}`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="min-w-0">
                        <div className="text-sm text-ocean-100 font-medium truncate">{z.name}</div>
                        <div className="text-xs text-ocean-500 font-mono truncate">{z.zone_id}</div>
                      </div>
                      <div className="flex items-center gap-1.5 flex-shrink-0">
                        <span className={`text-xs px-2 py-0.5 rounded border ${c.badge}`}>
                          {TYPE_LABEL[z.zone_type] ?? z.zone_type}
                        </span>
                        <span className={`text-xs px-2 py-0.5 rounded border ${
                          z.active
                            ? "text-green-300 border-green-500/30 bg-green-500/10"
                            : "text-ocean-400 border-ocean-700"
                        }`}>
                          {z.active ? "활성" : "비활성"}
                        </span>
                      </div>
                    </div>
                    {z.active && (
                      <button
                        onClick={(e) => { e.stopPropagation(); deactivateZone(z.zone_id); }}
                        className="mt-2 text-xs px-2.5 py-1 rounded border border-red-500/50 text-red-300 hover:bg-red-500/10"
                      >
                        비활성화
                      </button>
                    )}
                  </div>
                );
              })}
              {!loading && zones.length === 0 && (
                <div className="text-xs text-ocean-500 py-8 text-center">등록된 구역이 없습니다.</div>
              )}
            </div>
          </section>
        </div>

        {/* ── 오른쪽: 구역 지도 ──────────────────────────────────────────────── */}
        <section className="min-h-0 hidden xl:block">
          <ZoneMapPanel
            zones={zones}
            selectedZoneId={selectedZoneId}
            onSelectZone={setSelectedZoneId}
          />
        </section>
      </div>
    </div>
  );
}
