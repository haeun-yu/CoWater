import { initialVessels } from '../data/vessels';
import { decodePositionReport, decodeVoyageReport, encodePositionReport, encodeVoyageReport } from './ais';
import { advanceRoute, getRouteLength, getRoutePosition, roundHeading, type RoutePoint, type RouteState, vesselRoutes } from './routePrediction';
import type { AisNmeaFrame, Vessel } from '../types';

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
