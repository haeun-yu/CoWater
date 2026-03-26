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
import { predictRoutePositionAndHeading } from './routePrediction';

// ── Constants ─────────────────────────────────────────────────────────────────

export const CPA_WARN_NM   = 0.4;   // nm  – show warning (orange) ~740m
export const CPA_DANGER_NM = 0.2;   // nm  – show danger  (red)    ~370m
export const TCPA_MAX_MIN  = 5;     // min – 5분 이내 접근만 경보
export const TCPA_DANGER_MIN = 3;   // min – 3분 이내 + CPA < 0.2nm → 위험(red)
export const MIN_CPA_IMPROVEMENT_NM = 0.15; // 최솟값 개선량 최소치 — 평행 항주 제거
/** 현재 거리 / CPA 최소 비율 — 실제로 수렴 중인 경우만 경보 */
export const MIN_CONVERGENCE_RATIO = 3.0;
/** CPA 계산 대상 최소 속도 (kn) — 저속/표류 선박 제외 */
const MIN_SOG_FOR_CPA = 2.0;

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
  actionTitle: string;
  actionDetail: string;
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

function buildAction(encounter: ColregEncounter, severity: AlertSeverity) {
  if (encounter === 'head-on') {
    return severity === 'danger'
      ? { title: '양측 즉시 우현 회피', detail: '정면 마주침입니다. 조기 우현 변침과 감속 여부를 즉시 확인하세요.' }
      : { title: '우현 회피 준비', detail: '정면 접근 추세입니다. 양 선박의 우현 회피 가능성을 우선 감시하세요.' };
  }

  if (encounter === 'crossing-starboard') {
    return severity === 'danger'
      ? { title: '자선 우선 회피', detail: '상대선이 우현에서 접근합니다. 조기 감속 또는 우현 변침 판단이 필요합니다.' }
      : { title: '우현 접근 감시', detail: '우현 횡단 상황입니다. 회피 여유가 줄어드는지 지속 감시하세요.' };
  }

  if (encounter === 'crossing-port') {
    return severity === 'danger'
      ? { title: '상대 회피 미흡 대비', detail: '좌현 횡단이지만 위험도가 높습니다. 상대선 회피 실패 가능성에 대비해 감속을 준비하세요.' }
      : { title: '진로 유지 우선', detail: '좌현 횡단 상황입니다. 상대선 회피 동작을 우선 확인하되 과도한 변침은 피하세요.' };
  }

  if (encounter === 'overtaking') {
    return severity === 'danger'
      ? { title: '추월 간격 즉시 확보', detail: '추월 상황입니다. 횡방향 분리 확보와 속력 차 관리가 필요합니다.' }
      : { title: '추월 분리 유지', detail: '추월 접근입니다. 추월선과 피추월선 간 분리 간격을 계속 확인하세요.' };
  }

  return severity === 'danger'
    ? { title: '침로 재확인 필요', detail: '평행 접근이지만 위험도는 높습니다. AIS와 레이더로 실제 closing 여부를 재확인하세요.' }
    : { title: '접근 추세 감시', detail: '평행 또는 동향 접근입니다. 실제 이격이 유지되는지 계속 확인하세요.' };
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
  const routePosition = predictRoutePositionAndHeading(vessel, seconds);
  if (routePosition) {
    return {
      latitude: routePosition[0],
      longitude: routePosition[1],
      heading: routePosition[2],
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
    v => (v.navigationStatus === 'Under way' || v.navigationStatus === 'Restricted')
      && v.sog >= MIN_SOG_FOR_CPA,
  );

  const alerts: CpaAlert[] = [];

  for (let i = 0; i < active.length; i++) {
    for (let j = i + 1; j < active.length; j++) {
      const a = active[i];
      const b = active[j];

      const { currentDistance, cpa, tcpa, cpaPosA, cpaPosB } = calcCpa(a, b);
      const distanceImprovement = currentDistance - cpa;
      const encounter = classifyEncounter(a, b);
      const severity = cpa < CPA_DANGER_NM && tcpa <= TCPA_DANGER_MIN ? 'danger' : 'warning';
      const action = buildAction(encounter.type, severity);

      if (cpa > CPA_WARN_NM)  continue;   // 0.4nm 이상 → 무시
      if (tcpa <= 0) continue;            // 이미 멀어지는 중
      if (tcpa > TCPA_MAX_MIN) continue;  // 5분 초과 → 무시
      if (distanceImprovement < MIN_CPA_IMPROVEMENT_NM) continue; // 평행/동향 → 무시
      // 현재 거리가 CPA의 MIN_CONVERGENCE_RATIO배 이상이어야 "수렴 중"으로 판단
      if (currentDistance < cpa * MIN_CONVERGENCE_RATIO) continue;

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
        actionTitle: action.title,
        actionDetail: action.detail,
        riskScore: scoreRisk(cpa, tcpa, distanceImprovement),
        severity,
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
