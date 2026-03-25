/**
 * CPA / TCPA calculation — ITU / COLREG standard relative-velocity method.
 *
 * All internal math uses a local flat-earth Cartesian frame (metres).
 * Output distances are in nautical miles, times in minutes.
 *
 * Compared to the earlier straight-line-only implementation, this version
 * predicts vessel motion using heading, speed, and rate of turn so the CPA
 * result matches the turn-aware danger-zone visuals more closely.
 */
import type { Vessel } from '../types';

// ── Constants ─────────────────────────────────────────────────────────────────

export const CPA_WARN_NM   = 1.0;   // nm  – show warning (orange)
export const CPA_DANGER_NM = 0.5;   // nm  – show danger  (red)
export const TCPA_MAX_MIN  = 12;    // min – ignore approaches too far in future
export const TCPA_DANGER_MIN = 8;   // min – only near-term risks escalate to red

const KNOTS_TO_MS = 0.5144;
const NM_TO_M     = 1852;
const DEG_TO_M    = 111_320;        // metres per degree latitude (approx)
const TURN_EPSILON_RAD_S = 1e-5;
const COARSE_STEP_SEC = 10;
const REFINE_STEP_SEC = 1;

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
  /** Predicted position of A at TCPA */
  cpaPosA: [number, number];
  /** Predicted position of B at TCPA */
  cpaPosB: [number, number];
  /** Midpoint between the two predicted CPA positions */
  cpaPoint: [number, number];
  severity: AlertSeverity;
}

// ── Core maths ────────────────────────────────────────────────────────────────

interface PredictedState {
  latitude: number;
  longitude: number;
  heading: number;
}

function normalizeDegrees(value: number) {
  return ((value % 360) + 360) % 360;
}

function positionDistanceNm(a: [number, number], b: [number, number]) {
  const avgLat = (a[0] + b[0]) / 2;
  const cosLat = Math.max(0.2, Math.cos((avgLat * Math.PI) / 180));
  const dx = (b[1] - a[1]) * cosLat * DEG_TO_M;
  const dy = (b[0] - a[0]) * DEG_TO_M;
  return Math.hypot(dx, dy) / NM_TO_M;
}

function midpoint(a: [number, number], b: [number, number]): [number, number] {
  return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
}

function advanceState(state: PredictedState, vessel: Vessel, seconds: number): PredictedState {
  const speedMs = vessel.sog * KNOTS_TO_MS;
  if (speedMs < 1e-6 || seconds <= 0) {
    return state;
  }

  const heading0 = (state.heading * Math.PI) / 180;
  const rotRadPerSec = (vessel.rateOfTurn * Math.PI) / 180 / 60;

  let eastMeters = 0;
  let northMeters = 0;
  let heading1 = heading0;

  if (Math.abs(rotRadPerSec) < TURN_EPSILON_RAD_S) {
    eastMeters = speedMs * Math.sin(heading0) * seconds;
    northMeters = speedMs * Math.cos(heading0) * seconds;
  } else {
    heading1 = heading0 + rotRadPerSec * seconds;
    eastMeters = (speedMs / rotRadPerSec) * (Math.cos(heading0) - Math.cos(heading1));
    northMeters = (speedMs / rotRadPerSec) * (Math.sin(heading1) - Math.sin(heading0));
  }

  const deltaLat = northMeters / DEG_TO_M;
  const midLat = state.latitude + deltaLat / 2;
  const cosLat = Math.max(0.2, Math.cos((midLat * Math.PI) / 180));
  const deltaLng = eastMeters / (DEG_TO_M * cosLat);

  return {
    latitude: state.latitude + deltaLat,
    longitude: state.longitude + deltaLng,
    heading: normalizeDegrees((heading1 * 180) / Math.PI),
  };
}

function predictState(vessel: Vessel, seconds: number): PredictedState {
  let state: PredictedState = {
    latitude: vessel.latitude,
    longitude: vessel.longitude,
    heading: Number.isFinite(vessel.heading) ? vessel.heading : vessel.cog,
  };

  let remaining = seconds;
  while (remaining > 0) {
    const step = Math.min(remaining, COARSE_STEP_SEC);
    state = advanceState(state, vessel, step);
    remaining -= step;
  }

  return state;
}

/**
 * Compute CPA (nm) and TCPA (min) for two vessels.
 * Uses turn-aware forward prediction so alert geometry stays consistent with
 * the current danger-zone model.
 */
export function calcCpa(a: Vessel, b: Vessel): {
  cpa: number;
  tcpa: number;
  cpaPosA: [number, number];
  cpaPosB: [number, number];
} {
  const horizonSec = TCPA_MAX_MIN * 60;

  let bestTimeSec = 0;
  let bestPosA: [number, number] = [a.latitude, a.longitude];
  let bestPosB: [number, number] = [b.latitude, b.longitude];
  let bestDistanceNm = positionDistanceNm(bestPosA, bestPosB);

  for (let seconds = COARSE_STEP_SEC; seconds <= horizonSec; seconds += COARSE_STEP_SEC) {
    const nextA = predictState(a, seconds);
    const nextB = predictState(b, seconds);
    const nextPosA: [number, number] = [nextA.latitude, nextA.longitude];
    const nextPosB: [number, number] = [nextB.latitude, nextB.longitude];
    const distanceNm = positionDistanceNm(nextPosA, nextPosB);

    if (distanceNm < bestDistanceNm) {
      bestDistanceNm = distanceNm;
      bestTimeSec = seconds;
      bestPosA = nextPosA;
      bestPosB = nextPosB;
    }
  }

  const refineStart = Math.max(0, bestTimeSec - COARSE_STEP_SEC);
  const refineEnd = Math.min(horizonSec, bestTimeSec + COARSE_STEP_SEC);

  for (let seconds = refineStart; seconds <= refineEnd; seconds += REFINE_STEP_SEC) {
    const nextA = predictState(a, seconds);
    const nextB = predictState(b, seconds);
    const nextPosA: [number, number] = [nextA.latitude, nextA.longitude];
    const nextPosB: [number, number] = [nextB.latitude, nextB.longitude];
    const distanceNm = positionDistanceNm(nextPosA, nextPosB);

    if (distanceNm < bestDistanceNm) {
      bestDistanceNm = distanceNm;
      bestTimeSec = seconds;
      bestPosA = nextPosA;
      bestPosB = nextPosB;
    }
  }

  return {
    cpa: bestDistanceNm,
    tcpa: bestTimeSec / 60,
    cpaPosA: bestPosA,
    cpaPosB: bestPosB,
  };
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

      const { cpa, tcpa, cpaPosA, cpaPosB } = calcCpa(a, b);

      if (cpa > CPA_WARN_NM)  continue;   // too far
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
        cpaPosA,
        cpaPosB,
        cpaPoint: midpoint(cpaPosA, cpaPosB),
        severity: cpa < CPA_DANGER_NM && tcpa <= TCPA_DANGER_MIN ? 'danger' : 'warning',
      });
    }
  }

  // Sort: danger first, then by imminence, then by CPA distance
  return alerts.sort((x, y) => {
    if (x.severity !== y.severity) return x.severity === 'danger' ? -1 : 1;
    if (x.tcpa !== y.tcpa) return x.tcpa - y.tcpa;
    return x.cpa - y.cpa;
  });
}
