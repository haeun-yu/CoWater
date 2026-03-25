import { initialVessels } from '../data/vessels';
import { decodePositionReport, decodeVoyageReport, encodePositionReport, encodeVoyageReport } from './ais';
import type { AisNmeaFrame, Vessel } from '../types';

const roundHeading = (value: number) => ((value % 360) + 360) % 360;

type RoutePoint = {
  latitude: number;
  longitude: number;
};

type RouteState = {
  direction: 1 | -1;
  progressNm: number;
  route: RoutePoint[];
  routeLengthNm: number;
};

const vesselRoutes: Record<string, RoutePoint[]> = {
  // ── 기존 4척 ────────────────────────────────────────────────────────────
  '440123456': [
    { latitude: 35.0702, longitude: 129.0798 },
    { latitude: 35.043,  longitude: 129.135  },
    { latitude: 35.016,  longitude: 129.192  },
    { latitude: 34.993,  longitude: 129.252  },
  ],
  '440234567': [
    { latitude: 35.0269, longitude: 129.1351 },
    { latitude: 35.052,  longitude: 129.184  },
    { latitude: 35.081,  longitude: 129.232  },
    { latitude: 35.118,  longitude: 129.286  },
  ],
  '440345678': [
    { latitude: 35.0168, longitude: 129.1507 },
    { latitude: 35.038,  longitude: 129.192  },
    { latitude: 35.062,  longitude: 129.234  },
    { latitude: 35.038,  longitude: 129.272  },
    { latitude: 35.016,  longitude: 129.234  },
  ],
  '440456789': [
    { latitude: 35.045,  longitude: 129.198  },
    { latitude: 35.062,  longitude: 129.238  },
    { latitude: 35.082,  longitude: 129.278  },
    { latitude: 35.062,  longitude: 129.318  },
  ],

  // ── 추가 15척 ────────────────────────────────────────────────────────────
  // 모든 경유점은 대한해협 / 부산 외해 (lat<35.05 or lng>129.20) 열린 바다만 사용

  // MV Korea Express — 동쪽 열린 바다 → 부산 외항 접근수로
  '440600001': [
    { latitude: 34.95,  longitude: 129.40 },
    { latitude: 34.97,  longitude: 129.28 },
    { latitude: 35.00,  longitude: 129.18 },
    { latitude: 35.03,  longitude: 129.08 },
  ],

  // MV Busan Gate — 부산 외항 → 남서향 출항 (중국/대한해협 서수로)
  '440600002': [
    { latitude: 35.03,  longitude: 129.08 },
    { latitude: 34.94,  longitude: 128.97 },
    { latitude: 34.83,  longitude: 128.84 },
    { latitude: 34.72,  longitude: 128.72 },
  ],

  // MT Red Star — 대한해협 서부 → 북향 입항
  '440600003': [
    { latitude: 34.76,  longitude: 128.92 },
    { latitude: 34.85,  longitude: 128.97 },
    { latitude: 34.94,  longitude: 129.00 },
    { latitude: 35.02,  longitude: 129.03 },
  ],

  // MV Pacific Dawn — 동쪽 열린 바다 → 서향 입항
  '440600004': [
    { latitude: 35.08,  longitude: 129.45 },
    { latitude: 35.06,  longitude: 129.33 },
    { latitude: 35.04,  longitude: 129.22 },
    { latitude: 35.02,  longitude: 129.12 },
  ],

  // SV Stella Maris — 부산 외항 → 남서향 제주
  '440600005': [
    { latitude: 35.02,  longitude: 129.01 },
    { latitude: 34.92,  longitude: 128.90 },
    { latitude: 34.80,  longitude: 128.78 },
    { latitude: 34.68,  longitude: 128.66 },
  ],

  // TB Iron Bull — 외항 접근수로 왕복 (lat<35.03 구간만)
  '440600006': [
    { latitude: 35.00,  longitude: 129.08 },
    { latitude: 34.98,  longitude: 129.12 },
    { latitude: 35.00,  longitude: 129.16 },
    { latitude: 35.02,  longitude: 129.12 },
  ],

  // MV Hanjin Pioneer — 대한해협 동수로 → 북향
  '440600007': [
    { latitude: 34.82,  longitude: 129.22 },
    { latitude: 34.92,  longitude: 129.24 },
    { latitude: 35.02,  longitude: 129.26 },
    { latitude: 35.12,  longitude: 129.28 },
  ],

  // MT Ulsan Arrow — 외항 → 북동향 울산 (동쪽 열린 바다)
  '440600008': [
    { latitude: 35.03,  longitude: 129.15 },
    { latitude: 35.14,  longitude: 129.28 },
    { latitude: 35.26,  longitude: 129.42 },
    { latitude: 35.38,  longitude: 129.54 },
  ],

  // SV Geoje Ferry — 부산 외항 → 서향 거제 (대한해협 서수로)
  '440600009': [
    { latitude: 35.02,  longitude: 129.00 },
    { latitude: 34.96,  longitude: 128.90 },
    { latitude: 34.90,  longitude: 128.78 },
    { latitude: 34.84,  longitude: 128.66 },
  ],

  // RV Deep Blue — 대한해협 중부 서베이 루프
  '440600010': [
    { latitude: 34.88,  longitude: 129.20 },
    { latitude: 34.82,  longitude: 129.12 },
    { latitude: 34.78,  longitude: 129.04 },
    { latitude: 34.82,  longitude: 128.96 },
    { latitude: 34.88,  longitude: 129.04 },
    { latitude: 34.88,  longitude: 129.20 },
  ],

  // MV Eastern Horizon — 동쪽 먼 바다 → 서향 입항
  '440600011': [
    { latitude: 35.05,  longitude: 129.55 },
    { latitude: 35.04,  longitude: 129.42 },
    { latitude: 35.03,  longitude: 129.30 },
    { latitude: 35.02,  longitude: 129.16 },
  ],

  // MT Dark Whale — 대한해협 남부 → 북향 입항
  '440600013': [
    { latitude: 34.68,  longitude: 128.97 },
    { latitude: 34.78,  longitude: 129.00 },
    { latitude: 34.88,  longitude: 129.01 },
    { latitude: 34.98,  longitude: 129.02 },
  ],

  // SV Tsushima Link — 부산 외항 → 남동향 대마도
  '440600014': [
    { latitude: 35.02,  longitude: 129.04 },
    { latitude: 34.94,  longitude: 129.14 },
    { latitude: 34.84,  longitude: 129.25 },
    { latitude: 34.72,  longitude: 129.36 },
  ],

  // MV Dongbang Pioneer — 동쪽 외해 → 북동향 포항 (열린 바다)
  '440600015': [
    { latitude: 35.02,  longitude: 129.22 },
    { latitude: 35.10,  longitude: 129.28 },
    { latitude: 35.18,  longitude: 129.34 },
    { latitude: 35.26,  longitude: 129.40 },
  ],
};

const toRadians = (value: number) => (value * Math.PI) / 180;

const distanceNm = (from: RoutePoint, to: RoutePoint) => {
  const meanLatitude = toRadians((from.latitude + to.latitude) / 2);
  const deltaLatitudeNm = (to.latitude - from.latitude) * 60;
  const deltaLongitudeNm = (to.longitude - from.longitude) * 60 * Math.cos(meanLatitude);
  return Math.hypot(deltaLatitudeNm, deltaLongitudeNm);
};

const bearingBetween = (from: RoutePoint, to: RoutePoint) => {
  const deltaLongitude = (to.longitude - from.longitude) * Math.cos(toRadians((from.latitude + to.latitude) / 2));
  const deltaLatitude = to.latitude - from.latitude;
  const heading = (Math.atan2(deltaLongitude, deltaLatitude) * 180) / Math.PI;
  return roundHeading(heading);
};

const getRouteLength = (route: RoutePoint[]) =>
  route.slice(1).reduce((total, point, index) => total + distanceNm(route[index], point), 0);

const getRoutePosition = (route: RoutePoint[], progressNm: number) => {
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
      return {
        position: {
          latitude: Number((start.latitude + (end.latitude - start.latitude) * ratio).toFixed(5)),
          longitude: Number((start.longitude + (end.longitude - start.longitude) * ratio).toFixed(5)),
        },
        heading: bearingBetween(start, end),
      };
    }
    remaining -= segmentLength;
  }

  return {
    position: route[route.length - 1],
    heading: bearingBetween(route[route.length - 2], route[route.length - 1]),
  };
};

const advanceRoute = (state: RouteState, distanceToTravelNm: number) => {
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

const moveVessel = (
  vessel: Vessel,
  secondsElapsed: number,
  tick: number,
  routeState?: RouteState,
): { vessel: Vessel; routeState?: RouteState } => {
  if (vessel.navigationStatus === 'At anchor' || vessel.navigationStatus === 'Moored') {
    return {
      vessel: {
        ...vessel,
        utcTime: new Date(Date.parse(vessel.utcTime) + secondsElapsed * 1000).toISOString(),
        sog: 0.2,
        rateOfTurn: 0,
      },
      routeState,
    };
  }

  const oscillation = Math.sin((tick + Number(vessel.mmsi.slice(-2))) / 8);
  const updatedSog = Number(Math.max(4, vessel.sog + Math.cos(tick / 6) * 0.25).toFixed(1));
  const nauticalMiles = (updatedSog / 3600) * secondsElapsed;

  if (!routeState) {
    const updatedCog = roundHeading(vessel.cog + oscillation * 1.8);
    const updatedHeading = roundHeading(updatedCog + oscillation * 1.2);
    return {
      vessel: {
        ...vessel,
        utcTime: new Date(Date.parse(vessel.utcTime) + secondsElapsed * 1000).toISOString(),
        sog: updatedSog,
        cog: Number(updatedCog.toFixed(1)),
        heading: Number(updatedHeading.toFixed(0)),
        rateOfTurn: Number((oscillation * 4.2).toFixed(1)),
      },
    };
  }

  const nextRouteState = advanceRoute(routeState, nauticalMiles);
  const previousHeading = vessel.heading;
  const { position, heading } = getRoutePosition(nextRouteState.route, nextRouteState.progressNm);
  const updatedCog = roundHeading(heading + oscillation * 1.2);
  const updatedHeading = roundHeading(heading + oscillation * 0.8);
  const headingDelta = ((updatedHeading - previousHeading + 540) % 360) - 180;
  const updatedRot = Number((headingDelta * 3).toFixed(1));

  return {
    vessel: {
      ...vessel,
      latitude: position.latitude,
      longitude: position.longitude,
      utcTime: new Date(Date.parse(vessel.utcTime) + secondsElapsed * 1000).toISOString(),
      sog: updatedSog,
      cog: Number(updatedCog.toFixed(1)),
      heading: Number(updatedHeading.toFixed(0)),
      rateOfTurn: updatedRot,
    },
    routeState: nextRouteState,
  };
};

const parseFrames = (frames: AisNmeaFrame[], existingVessels: Vessel[]) => {
  const byMmsi = new Map(existingVessels.map((vessel) => [vessel.mmsi, vessel]));

  for (const frame of frames) {
    if (frame.kind === 'position') {
      const decoded = decodePositionReport(frame.sentence);
      const existing = byMmsi.get(decoded.mmsi);
      if (existing) {
        byMmsi.set(decoded.mmsi, { ...existing, ...decoded.data });
      }
    } else {
      const decoded = decodeVoyageReport(frame.sentence);
      const existing = byMmsi.get(decoded.mmsi);
      if (existing) {
        byMmsi.set(decoded.mmsi, { ...existing, ...decoded.data });
      }
    }
  }

  return Array.from(byMmsi.values());
};

export interface SimulationSnapshot {
  vessels: Vessel[];
  lastFrames: AisNmeaFrame[];
}

export const createSimulator = () => {
  let vessels = [...initialVessels];
  let tick = 0;
  let routeStates = new Map<string, RouteState>(
    initialVessels
      .filter((vessel) => vesselRoutes[vessel.mmsi])
      .map((vessel) => {
        const route = vesselRoutes[vessel.mmsi];
        return [
          vessel.mmsi,
          {
            direction: 1 as const,
            progressNm: 0,
            route,
            routeLengthNm: getRouteLength(route),
          },
        ];
      }),
  );

  const next = (): SimulationSnapshot => {
    tick += 1;
    const movedVessels = vessels.map((vessel) => {
      const result = moveVessel(vessel, 1, tick, routeStates.get(vessel.mmsi));
      if (result.routeState) {
        routeStates.set(vessel.mmsi, result.routeState);
      }
      return result.vessel;
    });
    const frames = movedVessels.flatMap((vessel) => [encodePositionReport(vessel), encodeVoyageReport(vessel)]);
    vessels = parseFrames(frames, vessels);
    return {
      vessels,
      lastFrames: frames,
    };
  };

  return {
    seed: (): SimulationSnapshot => {
      const frames = vessels.flatMap((vessel) => [encodePositionReport(vessel), encodeVoyageReport(vessel)]);
      vessels = parseFrames(frames, vessels);
      return {
        vessels,
        lastFrames: frames,
      };
    },
    next,
  };
};
