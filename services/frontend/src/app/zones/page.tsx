"use client";

import { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7700";

type ZoneType = "prohibited" | "restricted" | "caution";

interface Zone {
  zone_id: string;
  name: string;
  zone_type: string;
  geometry: { type: string };
  rules: Record<string, unknown>;
  active: boolean;
  created_at: string;
  updated_at: string;
}

const TYPE_LABEL: Record<string, string> = {
  prohibited: "금지",
  restricted: "제한",
  caution: "주의",
};

const TYPE_STYLE: Record<string, string> = {
  prohibited: "text-red-300 bg-red-500/15 border-red-500/30",
  restricted: "text-yellow-300 bg-yellow-500/15 border-yellow-500/30",
  caution: "text-blue-300 bg-blue-500/15 border-blue-500/30",
};

export default function ZonesPage() {
  const [zones, setZones] = useState<Zone[]>([]);
  const [name, setName] = useState("");
  const [zoneType, setZoneType] = useState<ZoneType>("restricted");
  const [geometryText, setGeometryText] = useState(
    '{"type":"Polygon","coordinates":[[[126.37,34.77],[126.39,34.77],[126.39,34.79],[126.37,34.79],[126.37,34.77]]]}',
  );
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadZones() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/zones?active_only=false`);
      if (!res.ok) throw new Error(`zones load failed (${res.status})`);
      const data = (await res.json()) as Zone[];
      setZones(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "구역 목록 로드 실패");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadZones();
  }, []);

  async function createZone() {
    setCreating(true);
    setError(null);
    try {
      const geometry = JSON.parse(geometryText);
      const res = await fetch(`${API_URL}/zones`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          zone_type: zoneType,
          geometry,
          rules: {},
        }),
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
      const res = await fetch(`${API_URL}/zones/${zoneId}/deactivate`, {
        method: "PATCH",
      });
      if (!res.ok) throw new Error(`zone deactivate failed (${res.status})`);
      await loadZones();
    } catch (e) {
      setError(e instanceof Error ? e.message : "구역 비활성화 실패");
    }
  }

  return (
    <div className="h-full flex flex-col overflow-hidden">
      <div className="px-5 py-3 border-b border-ocean-800 flex items-center justify-between">
        <div>
          <h1 className="text-base font-bold text-ocean-200 tracking-wider">
            구역 관리
          </h1>
          <p className="text-xs text-ocean-500 mt-0.5">
            Zone Monitor가 참조하는 금지/제한 구역을 관리합니다.
          </p>
        </div>
        <button
          onClick={loadZones}
          className="text-xs px-3 py-1.5 border border-ocean-700 rounded text-ocean-300 hover:border-ocean-500"
        >
          새로고침
        </button>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[360px_minmax(0,1fr)] gap-3 p-4 min-h-0 flex-1">
        <section className="rounded border border-ocean-800 bg-ocean-900/30 p-3">
          <h2 className="text-sm font-bold text-ocean-200 mb-2">구역 생성</h2>
          <div className="space-y-2">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="구역 이름"
              className="w-full text-xs px-2 py-1.5 rounded border border-ocean-700 bg-ocean-950 text-ocean-200"
            />
            <select
              value={zoneType}
              onChange={(e) => setZoneType(e.target.value as ZoneType)}
              className="w-full text-xs px-2 py-1.5 rounded border border-ocean-700 bg-ocean-950 text-ocean-200"
            >
              <option value="prohibited">금지 (prohibited)</option>
              <option value="restricted">제한 (restricted)</option>
              <option value="caution">주의 (caution)</option>
            </select>
            <textarea
              value={geometryText}
              onChange={(e) => setGeometryText(e.target.value)}
              rows={8}
              className="w-full text-xs px-2 py-1.5 rounded border border-ocean-700 bg-ocean-950 text-ocean-200 font-mono"
            />
            <button
              onClick={createZone}
              disabled={creating || !name.trim()}
              className="text-xs px-3 py-1.5 rounded border border-cyan-600 text-cyan-300 disabled:opacity-40"
            >
              {creating ? "생성 중..." : "구역 생성"}
            </button>
          </div>
        </section>

        <section className="rounded border border-ocean-800 bg-ocean-900/30 p-3 min-h-0 overflow-auto">
          <h2 className="text-sm font-bold text-ocean-200 mb-2">구역 목록</h2>
          {loading && <div className="text-xs text-ocean-500">로딩 중...</div>}
          {error && <div className="text-xs text-red-400 mb-2">{error}</div>}

          <div className="space-y-2">
            {zones.map((z) => (
              <div
                key={z.zone_id}
                className="rounded border border-ocean-800 bg-ocean-950/40 p-2.5"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-sm text-ocean-100 font-medium truncate">
                      {z.name}
                    </div>
                    <div className="text-xs text-ocean-500 font-mono">
                      {z.zone_id}
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span
                      className={`text-xs px-2 py-0.5 rounded border ${TYPE_STYLE[z.zone_type] ?? "text-ocean-300 border-ocean-700"}`}
                    >
                      {TYPE_LABEL[z.zone_type] ?? z.zone_type}
                    </span>
                    <span
                      className={`text-xs px-2 py-0.5 rounded border ${z.active ? "text-green-300 border-green-500/30 bg-green-500/10" : "text-ocean-400 border-ocean-700"}`}
                    >
                      {z.active ? "활성" : "비활성"}
                    </span>
                  </div>
                </div>
                <div className="text-xs text-ocean-400 mt-1">
                  geometry: {z.geometry?.type ?? "unknown"}
                </div>
                {z.active && (
                  <button
                    onClick={() => deactivateZone(z.zone_id)}
                    className="mt-2 text-xs px-2.5 py-1 rounded border border-red-500/50 text-red-300 hover:bg-red-500/10"
                  >
                    비활성화
                  </button>
                )}
              </div>
            ))}
            {!loading && zones.length === 0 && (
              <div className="text-xs text-ocean-500 py-5 text-center">
                등록된 구역이 없습니다.
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
