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
    { latitude: 35.1068, longitude: 129.0107 },
    { latitude: 35.128, longitude: 129.055 },
    { latitude: 35.142, longitude: 129.101 },
    { latitude: 35.116, longitude: 129.149 },
    { latitude: 35.084, longitude: 129.12 },
  ],
  '440456789': [
    { latitude: 35.1597, longitude: 129.0664 },
    { latitude: 35.142, longitude: 129.11 },
    { latitude: 35.118, longitude: 129.153 },
    { latitude: 35.091, longitude: 129.198 },
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
