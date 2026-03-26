import type { Vessel } from '../types';

export type RoutePoint = {
  latitude: number;
  longitude: number;
};

export type RouteState = {
  direction: 1 | -1;
  progressNm: number;
  route: RoutePoint[];
  routeLengthNm: number;
};

export const roundHeading = (value: number) => ((value % 360) + 360) % 360;

export const vesselRoutes: Record<string, RoutePoint[]> = {
  '440123456': [
    { latitude: 35.0702, longitude: 129.0798 },
    { latitude: 35.043, longitude: 129.135 },
    { latitude: 35.016, longitude: 129.192 },
    { latitude: 34.993, longitude: 129.252 },
  ],
  '440234567': [
    { latitude: 35.0269, longitude: 129.1351 },
    { latitude: 35.052, longitude: 129.184 },
    { latitude: 35.081, longitude: 129.232 },
    { latitude: 35.118, longitude: 129.286 },
  ],
  '440345678': [
    { latitude: 35.0168, longitude: 129.1507 },
    { latitude: 35.038, longitude: 129.192 },
    { latitude: 35.062, longitude: 129.234 },
    { latitude: 35.038, longitude: 129.272 },
    { latitude: 35.016, longitude: 129.234 },
  ],
  '440456789': [
    { latitude: 35.045, longitude: 129.198 },
    { latitude: 35.062, longitude: 129.238 },
    { latitude: 35.082, longitude: 129.278 },
    { latitude: 35.062, longitude: 129.318 },
  ],
  // 🔴 데모1: Korea Express — 서향 (Dark Whale과 정면 충돌)
  '440600001': [
    { latitude: 35.02, longitude: 129.18 },
    { latitude: 35.02, longitude: 129.05 },
    { latitude: 35.02, longitude: 128.95 },
  ],
  '440600002': [
    { latitude: 35.03, longitude: 129.08 },
    { latitude: 34.94, longitude: 128.97 },
    { latitude: 34.83, longitude: 128.84 },
    { latitude: 34.72, longitude: 128.72 },
  ],
  // 🟠 데모2: Red Star — SW향 (Tsushima Link와 교차)
  '440600003': [
    { latitude: 35.02, longitude: 129.14 },
    { latitude: 34.94, longitude: 129.06 },
    { latitude: 34.84, longitude: 128.96 },
  ],
  '440600004': [
    { latitude: 35.08, longitude: 129.45 },
    { latitude: 35.06, longitude: 129.33 },
    { latitude: 35.04, longitude: 129.22 },
    { latitude: 35.02, longitude: 129.12 },
  ],
  '440600005': [
    { latitude: 35.02, longitude: 129.01 },
    { latitude: 34.92, longitude: 128.9 },
    { latitude: 34.8, longitude: 128.78 },
    { latitude: 34.68, longitude: 128.66 },
  ],
  '440600006': [
    { latitude: 35.0, longitude: 129.08 },
    { latitude: 34.98, longitude: 129.12 },
    { latitude: 35.0, longitude: 129.16 },
    { latitude: 35.02, longitude: 129.12 },
  ],
  '440600007': [
    { latitude: 34.82, longitude: 129.22 },
    { latitude: 34.92, longitude: 129.24 },
    { latitude: 35.02, longitude: 129.26 },
    { latitude: 35.12, longitude: 129.28 },
  ],
  // ⚠️ 데모3: Ulsan Arrow — 부산항 북향 진입 (위험물·hazard_port)
  // BUSAN_PORT(35.10, 129.04)에서 2.3nm 남쪽 출발 → 2nm 경계 통과 시 이벤트
  '440600008': [
    { latitude: 35.062, longitude: 129.04 },
    { latitude: 35.115, longitude: 129.04 },
  ],
  // 🔄 데모5: Geoje Ferry — 90° 급선회 경로 → ROT > 12°/min 이벤트
  // 남향 → 서향으로 급격하게 변침
  '440600009': [
    { latitude: 35.02, longitude: 129.00 },
    { latitude: 34.95, longitude: 129.00 },  // 남향 구간
    { latitude: 34.95, longitude: 128.88 },  // 90° 서향 선회 (ROT 급증)
    { latitude: 34.95, longitude: 128.76 },
  ],
  '440600010': [
    { latitude: 34.88, longitude: 129.2 },
    { latitude: 34.82, longitude: 129.12 },
    { latitude: 34.78, longitude: 129.04 },
    { latitude: 34.82, longitude: 128.96 },
    { latitude: 34.88, longitude: 129.04 },
    { latitude: 34.88, longitude: 129.2 },
  ],
  '440600011': [
    { latitude: 35.05, longitude: 129.55 },
    { latitude: 35.04, longitude: 129.42 },
    { latitude: 35.03, longitude: 129.3 },
    { latitude: 35.02, longitude: 129.16 },
  ],
  // 🔴 데모1 파트너: Dark Whale — 동향 (Korea Express와 정면 충돌)
  '440600013': [
    { latitude: 35.02, longitude: 129.14 },
    { latitude: 35.02, longitude: 129.28 },
    { latitude: 35.02, longitude: 129.42 },
  ],
  // 🟠 데모2 파트너: Tsushima Link — NE향 (Red Star와 교차)
  '440600014': [
    { latitude: 34.97, longitude: 129.07 },
    { latitude: 35.03, longitude: 129.16 },
    { latitude: 35.10, longitude: 129.25 },
  ],
  '440600015': [
    { latitude: 35.02, longitude: 129.22 },
    { latitude: 35.1, longitude: 129.28 },
    { latitude: 35.18, longitude: 129.34 },
    { latitude: 35.26, longitude: 129.4 },
  ],

  // ⚓ 데모4: Sea Tiger — 정박 중 앵커 드래그 (조류 표류)
  // 초기 위치에서 북쪽으로 서서히 이탈 → 50m+ 시 anchor_drag 이벤트
  '440600012': [
    { latitude: 35.020, longitude: 129.10 },
    { latitude: 35.026, longitude: 129.10 },
  ],
};

const toRadians = (value: number) => (value * Math.PI) / 180;

const angleDiff = (a: number, b: number) => {
  const diff = ((a - b + 540) % 360) - 180;
  return Math.abs(diff);
};

const toLocalNm = (origin: RoutePoint, point: RoutePoint) => {
  const meanLatitude = toRadians((origin.latitude + point.latitude) / 2);
  return {
    x: (point.longitude - origin.longitude) * 60 * Math.cos(meanLatitude),
    y: (point.latitude - origin.latitude) * 60,
  };
};

export const distanceNm = (from: RoutePoint, to: RoutePoint) => {
  const delta = toLocalNm(from, to);
  return Math.hypot(delta.x, delta.y);
};

export const bearingBetween = (from: RoutePoint, to: RoutePoint) => {
  const delta = toLocalNm(from, to);
  const heading = (Math.atan2(delta.x, delta.y) * 180) / Math.PI;
  return roundHeading(heading);
};

export const getRouteLength = (route: RoutePoint[]) =>
  route.slice(1).reduce((total, point, index) => total + distanceNm(route[index], point), 0);

export const getRoutePosition = (route: RoutePoint[], progressNm: number, direction: 1 | -1 = 1) => {
  if (route.length < 2) {
    return {
      position: route[0],
      heading: 0,
    };
  }

  let remaining = progressNm;
  for (let index = 1; index < route.length; index += 1) {
    const start = route[index - 1];
    const end = route[index];
    const segmentLength = distanceNm(start, end);
    if (remaining <= segmentLength || index === route.length - 1) {
      const ratio = segmentLength === 0 ? 0 : Math.min(Math.max(remaining / segmentLength, 0), 1);
      const forwardHeading = bearingBetween(start, end);
      return {
        position: {
          latitude: Number((start.latitude + (end.latitude - start.latitude) * ratio).toFixed(5)),
          longitude: Number((start.longitude + (end.longitude - start.longitude) * ratio).toFixed(5)),
        },
        heading: direction === 1 ? forwardHeading : roundHeading(forwardHeading + 180),
      };
    }
    remaining -= segmentLength;
  }

  const tailHeading = bearingBetween(route[route.length - 2], route[route.length - 1]);
  return {
    position: route[route.length - 1],
    heading: direction === 1 ? tailHeading : roundHeading(tailHeading + 180),
  };
};

export const advanceRoute = (state: RouteState, distanceToTravelNm: number) => {
  let nextProgress = state.progressNm + distanceToTravelNm * state.direction;
  let nextDirection = state.direction;

  while (nextProgress > state.routeLengthNm || nextProgress < 0) {
    if (nextProgress > state.routeLengthNm) {
      nextProgress = state.routeLengthNm - (nextProgress - state.routeLengthNm);
      nextDirection = -1;
    } else if (nextProgress < 0) {
      nextProgress = -nextProgress;
      nextDirection = 1;
    }
  }

  return {
    ...state,
    progressNm: nextProgress,
    direction: nextDirection,
  };
};

export const inferRouteState = (vessel: Vessel): RouteState | null => {
  const route = vesselRoutes[vessel.mmsi];
  if (!route || route.length < 2) {
    return null;
  }

  let bestDistanceSq = Number.POSITIVE_INFINITY;
  let bestProgressNm = 0;
  let bestForwardHeading = vessel.cog;

  let progressPrefixNm = 0;
  const vesselPoint: RoutePoint = { latitude: vessel.latitude, longitude: vessel.longitude };

  for (let index = 1; index < route.length; index += 1) {
    const start = route[index - 1];
    const end = route[index];
    const segment = toLocalNm(start, end);
    const point = toLocalNm(start, vesselPoint);
    const segmentLengthSq = segment.x * segment.x + segment.y * segment.y;
    const segmentLengthNm = Math.sqrt(segmentLengthSq);

    let t = 0;
    if (segmentLengthSq > 0) {
      t = (point.x * segment.x + point.y * segment.y) / segmentLengthSq;
      t = Math.min(Math.max(t, 0), 1);
    }

    const projectedX = segment.x * t;
    const projectedY = segment.y * t;
    const distanceSq = (point.x - projectedX) ** 2 + (point.y - projectedY) ** 2;

    if (distanceSq < bestDistanceSq) {
      bestDistanceSq = distanceSq;
      bestProgressNm = progressPrefixNm + segmentLengthNm * t;
      bestForwardHeading = bearingBetween(start, end);
    }

    progressPrefixNm += segmentLengthNm;
  }

  const reverseHeading = roundHeading(bestForwardHeading + 180);
  const direction = angleDiff(vessel.cog, bestForwardHeading) <= angleDiff(vessel.cog, reverseHeading) ? 1 : -1;

  return {
    direction,
    progressNm: bestProgressNm,
    route,
    routeLengthNm: getRouteLength(route),
  };
};

export const predictRoutePosition = (vessel: Vessel, seconds: number): [number, number] | null => {
  const routeState = inferRouteState(vessel);
  if (!routeState) {
    return null;
  }

  const distanceToTravelNm = (vessel.sog / 3600) * seconds;
  const nextState = advanceRoute(routeState, distanceToTravelNm);
  const { position } = getRoutePosition(nextState.route, nextState.progressNm, nextState.direction);
  return [position.latitude, position.longitude];
};
