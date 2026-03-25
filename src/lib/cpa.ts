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
import { predictRoutePosition } from './routePrediction';

// ── Constants ─────────────────────────────────────────────────────────────────

export const CPA_WARN_NM   = 1.0;   // nm  – show warning (orange)
export const CPA_DANGER_NM = 0.5;   // nm  – show danger  (red)
export const TCPA_MAX_MIN  = 12;    // min – ignore approaches too far in future
export const TCPA_DANGER_MIN = 8;   // min – only near-term risks escalate to red
export const MIN_CPA_IMPROVEMENT_NM = 0.05; // ignore near-parallel / non-closing pairs

const KNOTS_TO_MS = 0.5144;
const NM_TO_M     = 1852;
const DEG_TO_M    = 111_320;        // metres per degree latitude (approx)
const TURN_EPSILON_RAD_S = 1e-5;
const COARSE_STEP_SEC = 10;
const REFINE_STEP_SEC = 1;

// ── Types ─────────────────────────────────────────────────────────────────────

export type AlertSeverity = 'warning' | 'danger';
export type ColregEncounter = 'head-on' | 'crossing-starboard' | 'crossing-port' | 'overtaking' | 'parallel';

export interface CpaAlert {
  mmsiA: string;
  mmsiB: string;
  nameA: string;
  nameB: string;
  vesselTypeA: Vessel['vesselType'];
  vesselTypeB: Vessel['vesselType'];
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
  colreg: ColregEncounter;
  colregLabel: string;
  riskScore: number;
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

function signedAngleDifference(a: number, b: number) {
  return ((a - b + 540) % 360) - 180;
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

function bearingFrom(a: Vessel, b: Vessel) {
  const avgLat = (a.latitude + b.latitude) / 2;
  const cosLat = Math.max(0.2, Math.cos((avgLat * Math.PI) / 180));
  const dx = (b.longitude - a.longitude) * cosLat * DEG_TO_M;
  const dy = (b.latitude - a.latitude) * DEG_TO_M;
  return normalizeDegrees((Math.atan2(dx, dy) * 180) / Math.PI);
}

function relativeBearing(from: Vessel, to: Vessel) {
  return normalizeDegrees(bearingFrom(from, to) - from.cog);
}

function classifyEncounter(a: Vessel, b: Vessel): { type: ColregEncounter; label: string } {
  const relA = relativeBearing(a, b);
  const relB = relativeBearing(b, a);
  const courseDiff = Math.abs(signedAngleDifference(a.cog, b.cog));

  if (courseDiff > 150 && (relA <= 15 || relA >= 345) && (relB <= 15 || relB >= 345)) {
    return { type: 'head-on', label: '정면 마주침' };
  }

  if (courseDiff < 30 && (relA > 112.5 && relA < 247.5 || relB > 112.5 && relB < 247.5)) {
    return { type: 'overtaking', label: '추월 상황' };
  }

  if (relA > 0 && relA < 112.5) {
    return { type: 'crossing-starboard', label: '우현 횡단' };
  }

  if (relA > 247.5 && relA < 360) {
    return { type: 'crossing-port', label: '좌현 횡단' };
  }

  return { type: 'parallel', label: '평행/동향 접근' };
}

function scoreRisk(cpa: number, tcpa: number, improvementNm: number) {
  const cpaScore = Math.max(0, 1 - cpa / CPA_WARN_NM);
  const tcpaScore = Math.max(0, 1 - tcpa / TCPA_MAX_MIN);
  const closureScore = Math.min(1, improvementNm / CPA_WARN_NM);
  return Math.round((cpaScore * 0.5 + tcpaScore * 0.35 + closureScore * 0.15) * 100);
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
  const routePosition = predictRoutePosition(vessel, seconds);
  if (routePosition) {
    return {
      latitude: routePosition[0],
      longitude: routePosition[1],
      heading: vessel.cog,
    };
  }

  let state: PredictedState = {
    latitude: vessel.latitude,
    longitude: vessel.longitude,
    heading: Number.isFinite(vessel.cog) ? vessel.cog : vessel.heading,
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
  currentDistance: number;
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
    currentDistance: positionDistanceNm([a.latitude, a.longitude], [b.latitude, b.longitude]),
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

      const { currentDistance, cpa, tcpa, cpaPosA, cpaPosB } = calcCpa(a, b);
      const distanceImprovement = currentDistance - cpa;
      const encounter = classifyEncounter(a, b);

      if (cpa > CPA_WARN_NM)  continue;   // too far
      if (tcpa <= 0) continue;            // not actually closing any further
      if (tcpa > TCPA_MAX_MIN) continue;  // too far in future
      if (distanceImprovement < MIN_CPA_IMPROVEMENT_NM) continue; // near-parallel / same-track

      alerts.push({
        mmsiA:    a.mmsi,
        mmsiB:    b.mmsi,
        nameA:    a.name,
        nameB:    b.name,
        vesselTypeA: a.vesselType,
        vesselTypeB: b.vesselType,
        cpa,
        tcpa,
        posA:     [a.latitude, a.longitude],
        posB:     [b.latitude, b.longitude],
        cpaPosA,
        cpaPosB,
        cpaPoint: midpoint(cpaPosA, cpaPosB),
        colreg: encounter.type,
        colregLabel: encounter.label,
        riskScore: scoreRisk(cpa, tcpa, distanceImprovement),
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
