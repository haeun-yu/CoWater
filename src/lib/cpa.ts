/**
 * CPA / TCPA calculation — ITU / COLREG standard relative-velocity method.
 *
 * All internal math uses a local flat-earth Cartesian frame (metres).
 * Output distances are in nautical miles, times in minutes.
 */
import type { Vessel } from '../types';

// ── Constants ─────────────────────────────────────────────────────────────────

export const CPA_WARN_NM   = 1.0;   // nm  – show warning (orange)
export const CPA_DANGER_NM = 0.5;   // nm  – show danger  (red)
export const TCPA_MAX_MIN  = 30;    // min – ignore approaches further in future

const KNOTS_TO_MS = 0.5144;
const NM_TO_M     = 1852;
const DEG_TO_M    = 111_320;        // metres per degree latitude (approx)

// ── Types ─────────────────────────────────────────────────────────────────────

export type AlertSeverity = 'warning' | 'danger';

export interface CpaAlert {
  mmsiA: string;
  mmsiB: string;
  nameA: string;
  nameB: string;
  cpa:   number;   // nautical miles
  tcpa:  number;   // minutes  (always ≥ 0 for returned alerts)
  posA:  [number, number];   // [lat, lng]
  posB:  [number, number];
  /** Predicted position of A at TCPA (for CPA point marker) */
  cpaPoint: [number, number];
  severity: AlertSeverity;
}

// ── Core maths ────────────────────────────────────────────────────────────────

interface Vec2 { x: number; y: number }

/** Convert vessel position + COG/SOG to a velocity vector in m/s. */
function velocity(vessel: Vessel): Vec2 {
  const cogRad = (vessel.cog * Math.PI) / 180;
  const v = vessel.sog * KNOTS_TO_MS;
  return { x: v * Math.sin(cogRad), y: v * Math.cos(cogRad) };
}

/**
 * Compute CPA (nm) and TCPA (min) for two vessels.
 * Returns tcpa = Infinity when vessels are not converging.
 */
export function calcCpa(a: Vessel, b: Vessel): { cpa: number; tcpa: number } {
  const avgLat = (a.latitude + b.latitude) / 2;
  const cosLat = Math.cos((avgLat * Math.PI) / 180);

  // Relative position of B w.r.t. A (metres)
  const dx = (b.longitude - a.longitude) * cosLat * DEG_TO_M;
  const dy = (b.latitude  - a.latitude)           * DEG_TO_M;

  const va = velocity(a);
  const vb = velocity(b);

  // Relative velocity of B w.r.t. A
  const dvx = vb.x - va.x;
  const dvy = vb.y - va.y;

  const relSpdSq = dvx * dvx + dvy * dvy;

  if (relSpdSq < 1e-6) {
    // Essentially same speed & heading – distance stays constant
    return { cpa: Math.hypot(dx, dy) / NM_TO_M, tcpa: Infinity };
  }

  // Time (seconds) to closest point
  const tcpaSec = -(dx * dvx + dy * dvy) / relSpdSq;

  // CPA separation vector
  const cpaX = dx + dvx * tcpaSec;
  const cpaY = dy + dvy * tcpaSec;

  return {
    cpa:  Math.hypot(cpaX, cpaY) / NM_TO_M,
    tcpa: tcpaSec / 60,
  };
}

/**
 * Predict the lat/lng of a vessel after `minutes` at its current COG/SOG.
 */
function predictPos(vessel: Vessel, minutes: number): [number, number] {
  const distM = vessel.sog * KNOTS_TO_MS * minutes * 60;
  const cogRad = (vessel.cog * Math.PI) / 180;
  const cosLat  = Math.cos((vessel.latitude * Math.PI) / 180);

  const dlat = (distM * Math.cos(cogRad)) / DEG_TO_M;
  const dlng = (distM * Math.sin(cogRad)) / (DEG_TO_M * cosLat);

  return [vessel.latitude + dlat, vessel.longitude + dlng];
}

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * Scan all vessel pairs and return active CPA alerts sorted by severity then CPA.
 * Only considers vessels that are under way or restricted (not anchored/moored).
 */
export function findCpaAlerts(vessels: Vessel[]): CpaAlert[] {
  const active = vessels.filter(
    v => v.navigationStatus === 'Under way' || v.navigationStatus === 'Restricted',
  );

  const alerts: CpaAlert[] = [];

  for (let i = 0; i < active.length; i++) {
    for (let j = i + 1; j < active.length; j++) {
      const a = active[i];
      const b = active[j];

      const { cpa, tcpa } = calcCpa(a, b);

      if (cpa > CPA_WARN_NM)  continue;   // too far
      if (tcpa < 0)           continue;   // already past closest point
      if (tcpa > TCPA_MAX_MIN) continue;  // too far in future

      alerts.push({
        mmsiA:    a.mmsi,
        mmsiB:    b.mmsi,
        nameA:    a.name,
        nameB:    b.name,
        cpa,
        tcpa,
        posA:     [a.latitude, a.longitude],
        posB:     [b.latitude, b.longitude],
        cpaPoint: predictPos(a, tcpa),
        severity: cpa < CPA_DANGER_NM ? 'danger' : 'warning',
      });
    }
  }

  // Sort: danger first, then by CPA distance
  return alerts.sort((x, y) => {
    if (x.severity !== y.severity) return x.severity === 'danger' ? -1 : 1;
    return x.cpa - y.cpa;
  });
}
