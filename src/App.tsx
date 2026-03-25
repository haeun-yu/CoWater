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
import { calcMetersPerPixel, createShipIcon } from "./lib/shipIcon";
import { buildDangerZone } from "./lib/dangerZone";
import { findCpaAlerts, type CpaAlert } from "./lib/cpa";
import type {
  AisNmeaFrame,
  NavigationStatus,
  Vessel,
  VesselType,
} from "./types";

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

// ── Smooth map re-centring without remounting the MapContainer ───────────────
function MapCentre({ lat, lng }: { lat: number; lng: number }) {
  const map = useMap();
  const prev = useRef({ lat, lng });
  useEffect(() => {
    const d =
      Math.abs(prev.current.lat - lat) + Math.abs(prev.current.lng - lng);
    if (d > 0.0005) {
      map.flyTo([lat, lng], undefined, { duration: 0.7, easeLinearity: 0.5 });
      prev.current = { lat, lng };
    }
  }, [lat, lng, map]);
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

  const selectedVessel = vessels.find((v) => v.mmsi === selectedMmsi) ?? null;
  const centerLat =
    selectedVessel?.latitude ??
    (vessels.length === 0
      ? DEFAULT_CENTER.lat
      : vessels.reduce((s, v) => s + v.latitude, 0) / vessels.length);
  const centerLng =
    selectedVessel?.longitude ??
    (vessels.length === 0
      ? DEFAULT_CENTER.lng
      : vessels.reduce((s, v) => s + v.longitude, 0) / vessels.length);

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

        {/* CPA alert panel */}
        {cpaAlerts.length > 0 && (
          <CpaAlertPanel alerts={cpaAlerts} onSelect={setSelectedMmsi} />
        )}

        {/* Panels */}
        {selectedVessel ? (
          <VesselDetail
            vessel={selectedVessel}
            frame={frames.find((f) => f.mmsi === selectedVessel.mmsi)}
            onBack={() => setSelectedMmsi(null)}
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

        <MapContainer
          center={[centerLat, centerLng]}
          zoom={11}
          scrollWheelZoom
          className="map-view"
        >
          <TileLayer
            attribution='&copy; <a href="https://carto.com/attributions">CARTO</a>'
            url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          />
          <MapCentre lat={centerLat} lng={centerLng} />
          <ZoomTracker onZoom={setZoom} />

          {/* CPA warning lines — rendered below ship icons */}
          {cpaAlerts.map((alert) => (
            <CpaLine key={`cpa-${alert.mmsiA}-${alert.mmsiB}`} alert={alert} />
          ))}

          {vessels.map((vessel) => (
            <Fragment key={vessel.mmsi}>
              <DangerZone
                vessel={vessel}
                selected={vessel.mmsi === selectedMmsi}
              />
              <Marker
                eventHandlers={{ click: () => setSelectedMmsi(vessel.mmsi) }}
                icon={createShipIcon(
                  vessel,
                  vessel.mmsi === selectedMmsi,
                  calcMetersPerPixel(vessel.latitude, zoom),
                  vesselAlertLevel.get(vessel.mmsi) ?? null,
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
              </Marker>
            </Fragment>
          ))}
        </MapContainer>

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
}: {
  vessel: Vessel;
  frame?: AisNmeaFrame;
  onBack: () => void;
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
      {/* Connecting line between the two vessels */}
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

      {/* Small marker at the predicted CPA point */}
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

// ---------- CPA alert panel ----------

function CpaAlertPanel({
  alerts,
  onSelect,
}: {
  alerts: CpaAlert[];
  onSelect: (mmsi: string) => void;
}) {
  return (
    <section className="alert-panel">
      <div className="panel-heading">
        <h2 className="alert-heading">
          <span className="alert-icon">⚠</span>
          충돌 경보
        </h2>
        <span className="alert-count">{alerts.length}건</span>
      </div>
      <div className="alert-list">
        {alerts.map((alert) => (
          <div
            key={`${alert.mmsiA}-${alert.mmsiB}`}
            className={`alert-item ${alert.severity}`}
            role="button"
            tabIndex={0}
            onClick={() => onSelect(alert.mmsiA)}
            onKeyDown={(e) => e.key === 'Enter' && onSelect(alert.mmsiA)}
          >
            <div className="alert-vessels">
              <span className="alert-ship-name">{alert.nameA}</span>
              <span className="alert-sep">↔</span>
              <span className="alert-ship-name">{alert.nameB}</span>
            </div>
            <div className="alert-metrics">
              <span>CPA&nbsp;<strong>{alert.cpa.toFixed(2)} nm</strong></span>
              <span>TCPA&nbsp;<strong>{alert.tcpa.toFixed(1)} min</strong></span>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

export default App;
