import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import {
  MapContainer,
  Marker,
  Polygon,
  Polyline,
  Popup,
  TileLayer,
  Tooltip,
  useMap,
  useMapEvents,
} from "react-leaflet";
import {
  applyFramesToVessels,
  DEFAULT_MOTH_SUB_URL,
  parseFrameBatchPayload,
} from "./lib/aisStream";
import L from "leaflet";
import 'leaflet.heat';
import { calcMetersPerPixel, createShipIcon } from "./lib/shipIcon";
import { buildDangerZone } from "./lib/dangerZone";
import { findCpaAlerts, type CpaAlert } from "./lib/cpa";
import type {
  AisNmeaFrame,
  NavigationStatus,
  Vessel,
  VesselType,
} from "./types";

declare module 'leaflet' {
  function heatLayer(latlngs: [number, number, number][], options?: object): L.Layer;
}

// ---------- icons ----------

const VESSEL_ICONS: Record<VesselType, string> = {
  Cargo: "🚢",
  Tanker: "🛢️",
  Passenger: "⛴️",
  Tug: "🛥️",
  Research: "🔬",
};

// ---------- danger zone ----------

const ZONE_COLOR: Record<VesselType, string> = {
  Cargo: "#3b9dff",
  Tanker: "#ff5c5c",
  Passenger: "#10b981",
  Tug: "#f59e0b",
  Research: "#a78bfa",
};

// ---------- trail data model ----------

interface TrailPoint { lat: number; lng: number; sog: number; t: number; }
const TRAIL_MAX_MS = 5 * 60 * 1000; // 5 minutes

// ---------- event model ----------

interface MarineEvent {
  id: string;
  type: 'cpa_danger' | 'cpa_warning' | 'course_change' | 'status_change' | 'hazard_port' | 'ais_silence' | 'anchor_drag';
  severity: 'info' | 'warning' | 'danger';
  message: string;
  timestamp: number;
  mmsi?: string;
}
const MAX_EVENTS = 40;
// Busan port centre (for hazard approach detection)
const BUSAN_PORT = { lat: 35.10, lng: 129.04 };
const HAZARD_PORT_NM = 2.0; // nm threshold

// ---------- layer flags ----------

interface LayerFlags { dangerZones: boolean; trails: boolean; labels: boolean; cpaLines: boolean; heatmap: boolean; }

const LAYER_LABELS: Record<keyof LayerFlags, string> = {
  dangerZones: '위험구간',
  trails:      '항적',
  labels:      '선박명',
  cpaLines:    '충돌 경보선',
  heatmap:     '밀도 히트맵',
};

function DangerZone({
  vessel,
  selected,
}: {
  vessel: Vessel;
  selected: boolean;
}) {
  const zone = buildDangerZone(vessel);
  if (zone.points.length < 3) return null;

  const color = vessel.hazardousCargo
    ? "#ff6b35"
    : ZONE_COLOR[vessel.vesselType];
  const isAnchor = zone.kind === "anchor";

  return (
    <Polygon
      positions={zone.points}
      pathOptions={{
        color: color,
        fillColor: color,
        fillOpacity: isAnchor ? 0.06 : selected ? 0.3 : 0.14,
        opacity: isAnchor ? 0.4 : selected ? 0.8 : 0.45,
        weight: isAnchor ? 1.2 : selected ? 1.5 : 1.0,
        dashArray: isAnchor ? "4 4" : undefined,
        lineCap: "round",
        lineJoin: "round",
      }}
    />
  );
}

// ---------- nav status ----------

const NAV_STATUS_COLOR: Record<NavigationStatus, string> = {
  "Under way": "badge-blue",
  "At anchor": "badge-yellow",
  Moored: "badge-gray",
  Restricted: "badge-red",
};

const NAV_STATUS_KO: Record<NavigationStatus, string> = {
  "Under way": "항해 중",
  "At anchor": "정박",
  Moored: "계류",
  Restricted: "운항 제한",
};

type MothConnectionState = "connecting" | "connected" | "disconnected" | "error";

const MOTH_STATUS_KO: Record<MothConnectionState, string> = {
  connecting: "연결 중",
  connected: "연결됨",
  disconnected: "끊김",
  error: "오류",
};

const MOTH_SUB_URL = import.meta.env.VITE_MOTH_SUB_URL ?? DEFAULT_MOTH_SUB_URL;
const DEFAULT_CENTER = { lat: 35.08, lng: 129.13 };

// ── Report zoom level changes to parent ──────────────────────────────────────
function ZoomTracker({ onZoom }: { onZoom: (z: number) => void }) {
  const map = useMap();
  useMapEvents({ zoomend: () => onZoom(map.getZoom()) });
  return null;
}

// ── Follow selected vessel: fly on selection, then track position updates ─────
function FollowVessel({ vessel }: { vessel: { mmsi: string; latitude: number; longitude: number } | null }) {
  const map = useMap();
  const prevMmsi = useRef<string | null>(null);
  const prevPos  = useRef<{ lat: number; lng: number } | null>(null);
  useEffect(() => {
    if (!vessel) {
      prevMmsi.current = null;
      prevPos.current  = null;
      return;
    }
    const { mmsi, latitude: lat, longitude: lng } = vessel;
    const isNewSelection = mmsi !== prevMmsi.current;
    const posChanged = prevPos.current
      ? prevPos.current.lat !== lat || prevPos.current.lng !== lng
      : false;

    if (isNewSelection || posChanged) {
      map.flyTo([lat, lng], undefined, { duration: 0.6, easeLinearity: 0.5 });
    }
    prevMmsi.current = mmsi;
    prevPos.current  = { lat, lng };
  }, [vessel?.mmsi, vessel?.latitude, vessel?.longitude, map]);  // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}

const formatUtc = (value: string) =>
  new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "short",
    timeStyle: "medium",
    timeZone: "UTC",
  }).format(new Date(value));

// ---------- sub-components ----------

function NavBadge({ status }: { status: NavigationStatus }) {
  return (
    <span className={`nav-badge ${NAV_STATUS_COLOR[status]}`}>
      {NAV_STATUS_KO[status]}
    </span>
  );
}

function LiveDot() {
  return <span className="live-dot" aria-label="실시간" />;
}

function SogBar({ sog, max = 25 }: { sog: number; max?: number }) {
  const pct = Math.min((sog / max) * 100, 100);
  return (
    <div className="sog-bar-wrap" title={`SOG ${sog.toFixed(1)} kn`}>
      <div className="sog-bar-fill" style={{ width: `${pct}%` }} />
    </div>
  );
}

function InfoRow({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="info-row">
      <span className="info-label">{label}</span>
      <strong className={mono ? "mono" : undefined}>{value}</strong>
    </div>
  );
}

function DetailSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="detail-section">
      <p className="detail-section-title">{title}</p>
      <div className="detail-grid">{children}</div>
    </div>
  );
}

// ---------- TrailLayer component ----------

function TrailLayer({ vessel, points, visible }: { vessel: Vessel; points: TrailPoint[]; visible: boolean }) {
  if (!visible || points.length < 2) return null;
  const now = Date.now();
  const color = vessel.hazardousCargo ? '#ff6b35' : ZONE_COLOR[vessel.vesselType];
  const bands = [
    { pts: points.filter(p => now - p.t <= 30_000),                                     opacity: 0.75, weight: 2.2 },
    { pts: points.filter(p => now - p.t > 30_000  && now - p.t <= 120_000),             opacity: 0.40, weight: 1.8 },
    { pts: points.filter(p => now - p.t > 120_000),                                     opacity: 0.18, weight: 1.5 },
  ];
  return (
    <>
      {bands.map((band, i) =>
        band.pts.length >= 2 ? (
          <Polyline
            key={i}
            positions={band.pts.map(p => [p.lat, p.lng] as [number, number])}
            pathOptions={{ color, weight: band.weight, opacity: band.opacity, dashArray: '3 6', lineCap: 'round' }}
          />
        ) : null
      )}
    </>
  );
}

// ---------- HeatmapLayer component ----------

function HeatmapLayer({ points, visible }: { points: [number, number, number][]; visible: boolean }) {
  const map = useMap();
  const layerRef = useRef<L.Layer | null>(null);
  useEffect(() => {
    if (layerRef.current) { map.removeLayer(layerRef.current); layerRef.current = null; }
    if (!visible || points.length === 0) return;
    layerRef.current = (L as any).heatLayer(points, { radius: 30, blur: 20, max: 5, gradient: { 0.2: '#0ea5e9', 0.5: '#f59e0b', 0.8: '#ef4444' } });
    layerRef.current!.addTo(map);
    return () => { if (layerRef.current) { map.removeLayer(layerRef.current); layerRef.current = null; } };
  }, [points, visible, map]);
  return null;
}

// ---------- VesselSparkChart component ----------

function VesselSparkChart({ history }: { history: {t: number, sog: number, cog: number}[] }) {
  if (history.length < 2) return <p className="chart-empty">데이터 수집 중...</p>;
  const W = 220, H = 60, PAD = 4;
  const maxSog = Math.max(...history.map(h => h.sog), 1);
  const sogPts = history.map((h, i) => {
    const x = PAD + (i / (history.length - 1)) * (W - PAD * 2);
    const y = H - PAD - (h.sog / maxSog) * (H - PAD * 2);
    return `${x},${y}`;
  }).join(' ');
  const cogPts = history.map((h, i) => {
    const x = PAD + (i / (history.length - 1)) * (W - PAD * 2);
    const y = H - PAD - (h.cog / 360) * (H - PAD * 2);
    return `${x},${y}`;
  }).join(' ');
  const lastSog = history[history.length - 1].sog;
  const lastCog = history[history.length - 1].cog;
  return (
    <div className="spark-chart">
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
        <polyline points={sogPts} fill="none" stroke="#14c6e8" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" opacity="0.9" />
        <polyline points={cogPts} fill="none" stroke="#f59e0b" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" opacity="0.7" />
      </svg>
      <div className="spark-legend">
        <span className="spark-sog">SOG {lastSog.toFixed(1)} kn</span>
        <span className="spark-cog">COG {lastCog.toFixed(0)}°</span>
      </div>
    </div>
  );
}

// ---------- LayerToggle component ----------

function LayerToggle({ layers, onChange }: {
  layers: LayerFlags;
  onChange: (key: keyof LayerFlags) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`layer-toggle${open ? ' layer-toggle--open' : ''}`}>
      <button className="layer-toggle-header" onClick={() => setOpen(v => !v)}>
        <span className="layer-toggle-title">레이어</span>
        <span className="layer-toggle-chevron">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div className="layer-toggle-body">
          {(Object.keys(LAYER_LABELS) as (keyof LayerFlags)[]).map(key => (
            <label key={key} className="layer-toggle-item">
              <input
                type="checkbox"
                checked={layers[key]}
                onChange={() => onChange(key)}
                className="layer-checkbox"
              />
              <span>{LAYER_LABELS[key]}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------- EventPanel component ----------

const EVENT_ICON: Record<MarineEvent['type'], string> = {
  cpa_danger:    '🔴',
  cpa_warning:   '🟠',
  course_change: '🔄',
  status_change: '🔵',
  hazard_port:   '⚠️',
  ais_silence:   '📡',
  anchor_drag:   '⚓',
};

function EventPanel({ events, cpaAlerts, onSelect }: {
  events: MarineEvent[];
  cpaAlerts: CpaAlert[];
  onSelect: (mmsi: string) => void;
}) {
  const hasCpa = cpaAlerts.length > 0;
  const hasEvents = events.length > 0;
  if (!hasCpa && !hasEvents) return null;

  return (
    <section className="event-panel">
      <div className="panel-heading">
        <h2 className="event-heading">
          {hasCpa && <span className="event-blink">⚠</span>}
          {' '}이벤트 피드
        </h2>
        <span className="event-count">{(hasCpa ? cpaAlerts.length : 0) + events.length}</span>
      </div>

      <div className="event-list">
        {/* Live CPA alerts at top */}
        {cpaAlerts.map(alert => (
          <div
            key={`cpa-${alert.mmsiA}-${alert.mmsiB}`}
            className={`event-item ${alert.severity}`}
            role="button" tabIndex={0}
            onClick={() => onSelect(alert.mmsiA)}
            onKeyDown={e => e.key === 'Enter' && onSelect(alert.mmsiA)}
          >
            <span className="event-icon">{alert.severity === 'danger' ? '🔴' : '🟠'}</span>
            <div className="event-body">
              <span className="event-msg">
                {alert.severity === 'danger' ? '충돌 위험' : '충돌 주의'}: {alert.nameA} ↔ {alert.nameB}
              </span>
              <span className="event-meta">CPA {alert.cpa.toFixed(2)} nm · TCPA {alert.tcpa.toFixed(1)} min</span>
            </div>
            <span className="event-live-badge">LIVE</span>
          </div>
        ))}

        {/* Historical events */}
        {events.map(evt => (
          <div
            key={evt.id}
            className={`event-item ${evt.severity}`}
            role="button" tabIndex={0}
            onClick={() => evt.mmsi && onSelect(evt.mmsi)}
            onKeyDown={e => e.key === 'Enter' && evt.mmsi && onSelect(evt.mmsi)}
          >
            <span className="event-icon">{EVENT_ICON[evt.type]}</span>
            <div className="event-body">
              <span className="event-msg">{evt.message}</span>
              <span className="event-meta">{new Date(evt.timestamp).toLocaleTimeString('ko-KR', { timeStyle: 'medium' })}</span>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

// ---------- main app ----------

function App() {
  const [vessels, setVessels] = useState<Vessel[]>([]);
  const [selectedMmsi, setSelectedMmsi] = useState<string | null>(null);
  const [frames, setFrames] = useState<AisNmeaFrame[]>([]);
  const [tick, setTick] = useState(0);
  const [zoom, setZoom] = useState(11);
  const [connectionState, setConnectionState] =
    useState<MothConnectionState>("connecting");
  const tickRef = useRef(0);

  // Trail state
  const [trails, setTrails] = useState<Map<string, TrailPoint[]>>(new Map());

  // Event state
  const [events, setEvents] = useState<MarineEvent[]>([]);
  const prevVesselsRef = useRef<Map<string, Vessel>>(new Map());

  // Layer flags state
  const [layers, setLayers] = useState<LayerFlags>({ dangerZones: true, trails: true, labels: false, cpaLines: true, heatmap: false });

  // AIS silence detection
  const lastSeenRef = useRef<Map<string, number>>(new Map());
  const [silentMmsis, setSilentMmsis] = useState<Set<string>>(new Set());
  const prevSilentRef = useRef<Set<string>>(new Set());

  // Anchor drag detection
  const anchorRefMap = useRef<Map<string, {lat: number, lng: number}>>(new Map());
  const anchorDragCooldown = useRef<Map<string, number>>(new Map());

  // Traffic heatmap
  const [heatPoints, setHeatPoints] = useState<[number, number, number][]>([]);

  // Vessel SOG/COG history
  const [vesselHistory, setVesselHistory] = useState<Map<string, {t: number, sog: number, cog: number}[]>>(new Map());

  useEffect(() => {
    let mime: string | null = null;
    let reconnectTimer: number | null = null;
    let socket: WebSocket | null = null;
    let isClosing = false;

    const connect = () => {
      setConnectionState("connecting");
      socket = new WebSocket(MOTH_SUB_URL);
      socket.binaryType = "arraybuffer";

      socket.addEventListener("open", () => {
        setConnectionState("connected");
      });

      socket.addEventListener("message", (event) => {
        if (typeof event.data === "string") {
          mime = event.data;
          return;
        }

        if (!(event.data instanceof ArrayBuffer)) {
          return;
        }

        if (!mime) {
          setConnectionState("error");
          socket?.close(1008, "MIME required before binary");
          return;
        }

        const nextFrames = parseFrameBatchPayload(event.data);
        setFrames(nextFrames);
        setVessels((currentVessels) =>
          applyFramesToVessels(nextFrames, currentVessels),
        );
        tickRef.current += 1;
        setTick(tickRef.current);
      });

      socket.addEventListener("close", () => {
        if (isClosing) {
          return;
        }
        setConnectionState("disconnected");
        reconnectTimer = window.setTimeout(connect, 1500);
      });

      socket.addEventListener("error", () => {
        setConnectionState("error");
      });
    };

    connect();

    return () => {
      isClosing = true;
      if (reconnectTimer) {
        window.clearTimeout(reconnectTimer);
      }
      socket?.close();
    };
  }, []);

  const cpaAlerts = useMemo(() => findCpaAlerts(vessels), [vessels]);

  // Map: mmsi → worst alert severity for that vessel
  const vesselAlertLevel = useMemo(() => {
    const map = new Map<string, 'warning' | 'danger'>();
    for (const alert of cpaAlerts) {
      const upgrade = (mmsi: string, sev: 'warning' | 'danger') => {
        if (!map.has(mmsi) || sev === 'danger') map.set(mmsi, sev);
      };
      upgrade(alert.mmsiA, alert.severity);
      upgrade(alert.mmsiB, alert.severity);
    }
    return map;
  }, [cpaAlerts]);

  // Update trails whenever vessels changes
  useEffect(() => {
    if (vessels.length === 0) return;
    const now = Date.now();
    const cutoff = now - TRAIL_MAX_MS;
    setTrails(prev => {
      const next = new Map(prev);
      for (const v of vessels) {
        const existing = next.get(v.mmsi) ?? [];
        const appended = [...existing, { lat: v.latitude, lng: v.longitude, sog: v.sog, t: now }];
        // Prune old points
        const firstKeep = appended.findIndex(p => p.t > cutoff);
        next.set(v.mmsi, firstKeep > 0 ? appended.slice(firstKeep) : appended);
      }
      return next;
    });
  }, [vessels]);

  // Update lastSeenRef and heatPoints whenever vessels changes
  useEffect(() => {
    if (vessels.length === 0) return;
    const now = Date.now();
    for (const v of vessels) {
      lastSeenRef.current.set(v.mmsi, now);
    }
    // Update heatPoints (rolling buffer of 2000)
    setHeatPoints(prev => {
      const next: [number, number, number][] = [...prev, ...vessels.map(v => [v.latitude, v.longitude, 1] as [number, number, number])];
      return next.length > 2000 ? next.slice(next.length - 2000) : next;
    });
  }, [vessels]);

  // Update vessel SOG/COG history (separate effect)
  useEffect(() => {
    if (vessels.length === 0) return;
    const now = Date.now();
    setVesselHistory(prev => {
      const next = new Map(prev);
      for (const v of vessels) {
        const existing = next.get(v.mmsi) ?? [];
        const appended = [...existing, { t: now, sog: v.sog, cog: v.cog }];
        next.set(v.mmsi, appended.length > 30 ? appended.slice(appended.length - 30) : appended);
      }
      return next;
    });
  }, [vessels]);

  // AIS silence interval (check every 10s, flag vessels silent > 3min)
  useEffect(() => {
    const id = setInterval(() => {
      const now = Date.now();
      const SILENCE_MS = 180_000;
      const newSilent = new Set<string>();
      lastSeenRef.current.forEach((ts, mmsi) => {
        if (now - ts >= SILENCE_MS) newSilent.add(mmsi);
      });
      setSilentMmsis(prev => {
        // Find newly silent vessels
        const newlyQuiet: string[] = [];
        newSilent.forEach(mmsi => {
          if (!prevSilentRef.current.has(mmsi)) newlyQuiet.push(mmsi);
        });
        if (newlyQuiet.length > 0) {
          const evts: MarineEvent[] = newlyQuiet.map(mmsi => ({
            id: `ais-silence-${now}-${mmsi}`,
            type: 'ais_silence' as const,
            severity: 'info' as const,
            message: `MMSI ${mmsi}: AIS 신호 3분 이상 수신 없음`,
            timestamp: now,
            mmsi,
          }));
          setEvents(p => [...evts, ...p].slice(0, MAX_EVENTS));
        }
        prevSilentRef.current = newSilent;
        return newSilent;
      });
    }, 10_000);
    return () => clearInterval(id);
  }, []);

  // Detect vessel events whenever vessels changes
  useEffect(() => {
    if (vessels.length === 0) return;
    const now = Date.now();
    const prev = prevVesselsRef.current;
    const newEvts: MarineEvent[] = [];

    for (const v of vessels) {
      const p = prev.get(v.mmsi);
      if (!p) continue;

      // Navigation status change
      if (p.navigationStatus !== v.navigationStatus) {
        newEvts.push({
          id: `${now}-${v.mmsi}-status`,
          type: 'status_change', severity: 'info',
          message: `${v.name}: ${p.navigationStatus} → ${v.navigationStatus}`,
          timestamp: now, mmsi: v.mmsi,
        });
      }

      // Sudden course change: ROT jumps above 12°/min
      if (Math.abs(v.rateOfTurn) > 12 && Math.abs(p.rateOfTurn) <= 12) {
        newEvts.push({
          id: `${now}-${v.mmsi}-rot`,
          type: 'course_change', severity: 'warning',
          message: `${v.name}: 급격한 침로 변경 (ROT ${v.rateOfTurn.toFixed(1)}°/min)`,
          timestamp: now, mmsi: v.mmsi,
        });
      }

      // Hazardous cargo vessel approaching port
      if (v.hazardousCargo && v.navigationStatus === 'Under way') {
        const dlat = (v.latitude  - BUSAN_PORT.lat) * 111320;
        const dlng = (v.longitude - BUSAN_PORT.lng) * 111320 * Math.cos(v.latitude * Math.PI / 180);
        const distNm = Math.hypot(dlat, dlng) / 1852;
        const prevDlat = (p.latitude  - BUSAN_PORT.lat) * 111320;
        const prevDlng = (p.longitude - BUSAN_PORT.lng) * 111320 * Math.cos(p.latitude * Math.PI / 180);
        const prevDistNm = Math.hypot(prevDlat, prevDlng) / 1852;
        if (distNm < HAZARD_PORT_NM && prevDistNm >= HAZARD_PORT_NM) {
          newEvts.push({
            id: `${now}-${v.mmsi}-hazard-port`,
            type: 'hazard_port', severity: 'danger',
            message: `${v.name}: 위험화물 선박 부산항 ${distNm.toFixed(1)}nm 접근`,
            timestamp: now, mmsi: v.mmsi,
          });
        }
      }

      // Anchor drag detection
      const isAnchored = v.navigationStatus === 'At anchor' || v.navigationStatus === 'Moored';
      const wasAnchored = p.navigationStatus === 'At anchor' || p.navigationStatus === 'Moored';
      if (isAnchored && !anchorRefMap.current.has(v.mmsi)) {
        // First time detected as anchored/moored — record reference position
        anchorRefMap.current.set(v.mmsi, { lat: v.latitude, lng: v.longitude });
      } else if (!isAnchored && wasAnchored) {
        // Vessel left anchored state — remove reference
        anchorRefMap.current.delete(v.mmsi);
      } else if (isAnchored) {
        const ref = anchorRefMap.current.get(v.mmsi);
        if (ref) {
          const avgLat = (v.latitude + ref.lat) / 2;
          const distM = Math.hypot(
            (v.latitude  - ref.lat) * 111320,
            (v.longitude - ref.lng) * 111320 * Math.cos(avgLat * Math.PI / 180),
          );
          if (distM >= 50) {
            const lastDrag = anchorDragCooldown.current.get(v.mmsi) ?? 0;
            if (now - lastDrag >= 600_000) {
              anchorDragCooldown.current.set(v.mmsi, now);
              newEvts.push({
                id: `${now}-${v.mmsi}-anchor-drag`,
                type: 'anchor_drag', severity: 'warning',
                message: `${v.name}: 앵커 드래그 감지 (기준 위치에서 ${distM.toFixed(0)}m 이탈)`,
                timestamp: now, mmsi: v.mmsi,
              });
            }
          }
        }
      }
    }

    prevVesselsRef.current = new Map(vessels.map(v => [v.mmsi, v]));
    if (newEvts.length > 0) {
      setEvents(prev => [...newEvts, ...prev].slice(0, MAX_EVENTS));
    }
  }, [vessels]);

  // Emit events for new CPA danger alerts
  useEffect(() => {
    const now = Date.now();
    const dangerAlerts = cpaAlerts.filter(a => a.severity === 'danger');
    if (dangerAlerts.length === 0) return;
    setEvents(prev => {
      const recentIds = new Set(prev.filter(e => now - e.timestamp < 10_000).map(e => e.id));
      const newEvts = dangerAlerts
        .map(a => ({
          id: `cpa-${a.mmsiA}-${a.mmsiB}`,
          type: 'cpa_danger' as const,
          severity: 'danger' as const,
          message: `충돌 위험: ${a.nameA} ↔ ${a.nameB} | CPA ${a.cpa.toFixed(2)}nm / TCPA ${a.tcpa.toFixed(1)}min`,
          timestamp: now,
        }))
        .filter(e => !recentIds.has(e.id));
      if (newEvts.length === 0) return prev;
      return [...newEvts, ...prev].slice(0, MAX_EVENTS);
    });
  }, [cpaAlerts]);

  const selectedVessel = vessels.find((v) => v.mmsi === selectedMmsi) ?? null;

  return (
    <div className="app-shell">
      {/* ────────── SIDEBAR ────────── */}
      <aside className="sidebar">
        {/* Header */}
        <div className="sidebar-header">
          <div className="brand-row">
            <span className="brand-icon">⚓</span>
            <div>
              <p className="eyebrow">Phase 1 · Maritime Platform</p>
              <h1>CoWater</h1>
            </div>
          </div>
          <p className="subtitle">AIS 기반 실시간 선박 관제 시뮬레이터</p>
        </div>

        {/* Status bar */}
        <div className="status-card">
          <div className="status-item">
            <span className="status-label">Moth 연결</span>
            <span className="status-value">
              <LiveDot /> {MOTH_STATUS_KO[connectionState]}
            </span>
          </div>
          <div className="status-divider" />
          <div className="status-item">
            <span className="status-label">관제 선박</span>
            <span className="status-value accent">{vessels.length} 척</span>
          </div>
          <div className="status-divider" />
          <div className="status-item">
            <span className="status-label">AIS 프레임</span>
            <span className="status-value accent">{frames.length} /s</span>
          </div>
        </div>

        {/* Event panel (replaces CPA alert panel) */}
        <EventPanel
          events={events}
          cpaAlerts={cpaAlerts}
          onSelect={setSelectedMmsi}
        />

        {/* Panels */}
        {selectedVessel ? (
          <VesselDetail
            vessel={selectedVessel}
            frame={frames.find((f) => f.mmsi === selectedVessel.mmsi)}
            onBack={() => setSelectedMmsi(null)}
            history={vesselHistory.get(selectedVessel.mmsi) ?? []}
          />
        ) : (
          <VesselList vessels={vessels} onSelect={setSelectedMmsi} />
        )}
      </aside>

      {/* ────────── MAP PANEL ────────── */}
      <main className="map-panel">
        <div className="map-header">
          <div>
            <p className="eyebrow">Marine Operations View</p>
            <h2>부산 인근 해역 실시간 관제</h2>
          </div>
          <div className="map-header-meta">
            <span className="meta-chip">
              <LiveDot /> moth 중계 구독
            </span>
            <span className="meta-chip muted">좌측에서 선박 선택</span>
          </div>
        </div>

        <div className="map-wrap">
        <LayerToggle layers={layers} onChange={key => setLayers(prev => ({ ...prev, [key]: !prev[key] }))} />
        <MapContainer
          center={[DEFAULT_CENTER.lat, DEFAULT_CENTER.lng]}
          zoom={11}
          scrollWheelZoom
          className="map-view"
        >
          <TileLayer
            attribution='&copy; <a href="https://carto.com/attributions">CARTO</a>'
            url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          />
          <FollowVessel vessel={selectedVessel} />
          <ZoomTracker onZoom={setZoom} />

          {/* Traffic heatmap — rendered below everything */}
          <HeatmapLayer points={heatPoints} visible={layers.heatmap} />

          {/* CPA warning lines — rendered below ship icons */}
          {layers.cpaLines && cpaAlerts.map((alert) => (
            <CpaLine key={`cpa-${alert.mmsiA}-${alert.mmsiB}`} alert={alert} />
          ))}

          {vessels.map((vessel) => (
            <Fragment key={vessel.mmsi}>
              <TrailLayer
                vessel={vessel}
                points={trails.get(vessel.mmsi) ?? []}
                visible={layers.trails}
              />
              {layers.dangerZones && (
                <DangerZone
                  vessel={vessel}
                  selected={vessel.mmsi === selectedMmsi}
                />
              )}
              <Marker
                eventHandlers={{ click: () => setSelectedMmsi(vessel.mmsi) }}
                icon={createShipIcon(
                  vessel,
                  vessel.mmsi === selectedMmsi,
                  calcMetersPerPixel(vessel.latitude, zoom),
                  vesselAlertLevel.get(vessel.mmsi) ?? null,
                  silentMmsis.has(vessel.mmsi),
                )}
                position={[vessel.latitude, vessel.longitude]}
              >
                <Popup className="ship-popup">
                  <div className="popup-inner">
                    <span className="popup-icon">
                      {VESSEL_ICONS[vessel.vesselType]}
                    </span>
                    <div>
                      <strong>{vessel.name}</strong>
                      <p>{vessel.vesselType}</p>
                    </div>
                    <NavBadge status={vessel.navigationStatus} />
                  </div>
                  <div className="popup-stats">
                    <span>SOG {vessel.sog.toFixed(1)} kn</span>
                    <span>HDG {vessel.heading.toFixed(0)}°</span>
                    <span>COG {vessel.cog.toFixed(1)}°</span>
                  </div>
                  {vessel.hazardousCargo && (
                    <p className="popup-hazard">⚠ 위험 화물 탑재</p>
                  )}
                </Popup>
                {layers.labels && (
                  <Tooltip permanent direction="bottom" offset={[0, 8]} className="vessel-label">
                    {vessel.name}
                  </Tooltip>
                )}
              </Marker>
            </Fragment>
          ))}
        </MapContainer>
        </div>

        {/* AIS stream */}
        <section className="stream-panel">
          <div className="panel-heading">
            <h3>
              <LiveDot /> 실시간 AIS 스트림
            </h3>
            <span>최근 8개 프레임 · tick #{tick}</span>
          </div>
          <div className="stream-list">
            {frames.slice(0, 8).map((frame) => (
              <div className="stream-row" key={`${frame.mmsi}-${frame.kind}`}>
                <span
                  className={`stream-kind ${frame.kind === "position" ? "kind-pos" : "kind-voy"}`}
                >
                  {frame.kind === "position" ? "POS" : "VOY"}
                </span>
                <code className="stream-sentence">{frame.sentence}</code>
              </div>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}

// ---------- Vessel list ----------

function VesselList({
  vessels,
  onSelect,
}: {
  vessels: Vessel[];
  onSelect: (mmsi: string) => void;
}) {
  return (
    <section className="list-panel">
      <div className="panel-heading">
        <h2>선박 목록</h2>
        <span>{vessels.length}척 관제 중</span>
      </div>
      <div className="ship-list">
        {vessels.map((vessel) => (
          <button
            className="ship-list-item"
            key={vessel.mmsi}
            onClick={() => onSelect(vessel.mmsi)}
            type="button"
          >
            <div className="ship-item-left">
              <span className="ship-type-icon">
                {VESSEL_ICONS[vessel.vesselType]}
              </span>
              <div className="ship-item-info">
                <strong>{vessel.name}</strong>
                <span className="ship-mmsi">{vessel.mmsi}</span>
              </div>
            </div>
            <div className="ship-item-right">
              <NavBadge status={vessel.navigationStatus} />
              <div className="ship-sog-row">
                <span className="sog-value">{vessel.sog.toFixed(1)} kn</span>
                <SogBar sog={vessel.sog} />
              </div>
              {vessel.hazardousCargo && (
                <span className="hazard-chip">⚠ 위험</span>
              )}
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}

// ---------- Vessel detail ----------

function VesselDetail({
  vessel,
  frame,
  onBack,
  history,
}: {
  vessel: Vessel;
  frame?: AisNmeaFrame;
  onBack: () => void;
  history: {t: number, sog: number, cog: number}[];
}) {
  return (
    <section className="detail-panel">
      <button className="back-button" onClick={onBack} type="button">
        ← 목록으로
      </button>

      <div className="detail-header">
        <span className="detail-vessel-icon">
          {VESSEL_ICONS[vessel.vesselType]}
        </span>
        <div>
          <h2>{vessel.name}</h2>
          <div className="detail-badges">
            <NavBadge status={vessel.navigationStatus} />
            <span className="type-chip">{vessel.vesselType}</span>
            {vessel.hazardousCargo && (
              <span className="hazard-chip pulse">⚠ 위험 화물</span>
            )}
          </div>
        </div>
      </div>

      {/* Quick metrics */}
      <div className="quick-metrics">
        <div className="metric-box">
          <span className="metric-label">SOG</span>
          <span className="metric-value">{vessel.sog.toFixed(1)}</span>
          <span className="metric-unit">kn</span>
          <SogBar sog={vessel.sog} />
        </div>
        <div className="metric-box">
          <span className="metric-label">Heading</span>
          <span className="metric-value">{vessel.heading.toFixed(0)}</span>
          <span className="metric-unit">°</span>
        </div>
        <div className="metric-box">
          <span className="metric-label">COG</span>
          <span className="metric-value">{vessel.cog.toFixed(1)}</span>
          <span className="metric-unit">°</span>
        </div>
        <div className="metric-box">
          <span className="metric-label">흘수</span>
          <span className="metric-value">{vessel.draft.toFixed(1)}</span>
          <span className="metric-unit">m</span>
        </div>
      </div>

      <DetailSection title="식별 정보">
        <InfoRow label="MMSI" value={vessel.mmsi} mono />
        <InfoRow label="Call Sign" value={vessel.callSign} mono />
        <InfoRow label="IMO 번호" value={vessel.imo} mono />
        <InfoRow
          label="선박 크기"
          value={`${vessel.length}m × ${vessel.beam}m`}
        />
      </DetailSection>

      <DetailSection title="위치 · 항법">
        <InfoRow
          label="위도 / 경도"
          value={`${vessel.latitude.toFixed(5)}, ${vessel.longitude.toFixed(5)}`}
          mono
        />
        <InfoRow label="UTC 시간" value={formatUtc(vessel.utcTime)} />
        <InfoRow label="위치 정확도" value={vessel.positionAccuracy} />
        <InfoRow
          label="Rate of Turn"
          value={`${vessel.rateOfTurn.toFixed(1)} °/min`}
        />
      </DetailSection>

      <DetailSection title="항해 계획">
        <InfoRow label="목적지" value={vessel.destination} />
        <InfoRow label="ETA" value={formatUtc(vessel.etaUtc)} />
      </DetailSection>

      {/* SOG/COG history sparkline */}
      <div className="detail-section">
        <p className="detail-section-title">속도 / 침로 이력</p>
        <VesselSparkChart history={history} />
      </div>

      {/* NMEA */}
      <div className="nmea-card">
        <div className="nmea-card-header">
          <span className="panel-title">AIS NMEA</span>
          <span
            className={`stream-kind ${frame?.kind === "position" ? "kind-pos" : "kind-voy"}`}
          >
            {frame?.kind === "position" ? "POS" : "VOY"}
          </span>
        </div>
        <code className="nmea-sentence">{frame?.sentence ?? "N/A"}</code>
      </div>
    </section>
  );
}

// ---------- CPA warning line ----------

function CpaLine({ alert }: { alert: CpaAlert }) {
  const isDanger = alert.severity === 'danger';
  const color    = isDanger ? '#ff3535' : '#ff9900';

  return (
    <Fragment>
      {/* Current link between the two vessels */}
      <Polyline
        positions={[alert.posA, alert.posB]}
        pathOptions={{
          color,
          weight:    isDanger ? 2.2 : 1.6,
          dashArray: isDanger ? '5 4' : '7 5',
          opacity:   isDanger ? 0.85 : 0.65,
        }}
      >
        <Tooltip sticky className="cpa-tooltip">
          <div className="cpa-tooltip-inner">
            <span className={`cpa-sev-badge ${alert.severity}`}>
              {isDanger ? '⚠ 위험' : '주의'}
            </span>
            <span>{alert.nameA} ↔ {alert.nameB}</span>
            <span>CPA&nbsp;<strong>{alert.cpa.toFixed(2)}&nbsp;nm</strong>
              &nbsp;·&nbsp;TCPA&nbsp;<strong>{alert.tcpa.toFixed(1)}&nbsp;min</strong>
            </span>
          </div>
        </Tooltip>
      </Polyline>

      {/* Predicted closest-approach separation segment */}
      <Polyline
        positions={[alert.cpaPosA, alert.cpaPosB]}
        pathOptions={{
          color,
          weight: 1.2,
          dashArray: '2 5',
          opacity: isDanger ? 0.9 : 0.7,
        }}
      />

      {/* Small marker at the midpoint of the predicted CPA geometry */}
      <Polyline
        positions={[alert.cpaPoint, alert.cpaPoint]}
        pathOptions={{ color, weight: 0, opacity: 0 }}
      />
      {/* CPA point diamond */}
      <Marker
        position={alert.cpaPoint}
        icon={cpaPointIcon(color)}
        interactive={false}
      />
    </Fragment>
  );
}

function cpaPointIcon(color: string) {
  return L.divIcon({
    className: '',
    html: `<svg width="12" height="12" viewBox="0 0 12 12" xmlns="http://www.w3.org/2000/svg"
               style="overflow:visible;">
             <polygon points="6,0 12,6 6,12 0,6"
               fill="${color}" fill-opacity="0.85"
               stroke="white" stroke-width="0.8"/>
           </svg>`,
    iconSize:   [12, 12],
    iconAnchor: [6, 6],
  });
}

export default App;
