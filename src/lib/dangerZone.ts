/**
 * Danger-zone geometry for each vessel.
 *
 * Three zone shapes:
 *   'lance'  – straight course: tapered spear in the COG direction.
 *              Length   ∝ SOG × 5 min horizon.
 *              Width    = beam × 1.2 at the base, tapers to a point.
 *
 *   'arc'    – turning: curved swept band along the predicted turning circle.
 *              Turning radius R = V / |ROT_rad/s|.
 *              The corridor is R ± beam/2 wide, clipped to 270 °.
 *
 *   'anchor' – at anchor / moored: approximate swing-circle polygon.
 *              Radius ≈ vessel length (chain + hull).
 */

import type { Vessel } from '../types';

// ── Geo helper ───────────────────────────────────────────────────────────────

/** Move (lat, lng) by distM metres along bearingDeg. Returns [lat, lng]. */
function dest(lat: number, lng: number, bearingDeg: number, distM: number): [number, number] {
  const R  = 6_371_000;
  const d  = distM / R;
  const b  = (bearingDeg * Math.PI) / 180;
  const φ1 = (lat * Math.PI) / 180;
  const λ1 = (lng * Math.PI) / 180;
  const sinφ2 = Math.sin(φ1) * Math.cos(d) + Math.cos(φ1) * Math.sin(d) * Math.cos(b);
  const φ2    = Math.asin(sinφ2);
  const λ2    = λ1 + Math.atan2(
    Math.sin(b) * Math.sin(d) * Math.cos(φ1),
    Math.cos(d) - Math.sin(φ1) * sinφ2,
  );
  return [(φ2 * 180) / Math.PI, ((λ2 * 180) / Math.PI + 540) % 360 - 180];
}

// ── Public types ─────────────────────────────────────────────────────────────

export type ZoneKind = 'lance' | 'arc' | 'anchor' | 'none';

export interface DangerZoneData {
  points: [number, number][];
  kind: ZoneKind;
}

// ── Core builder ─────────────────────────────────────────────────────────────

const TIME_HORIZON_S = 1 * 60; // 1-minute look-ahead
const ROT_THRESHOLD  = 2;       // °/min – below this = "straight"

export function buildDangerZone(vessel: Vessel): DangerZoneData {
  const { latitude: lat, longitude: lng, sog, cog, rateOfTurn: rot,
          beam, length, navigationStatus } = vessel;

  // ── Anchored / Moored ─────────────────────────────────────────────────────
  if (navigationStatus === 'At anchor' || navigationStatus === 'Moored') {
    const r   = length * 0.9;
    const pts: [number, number][] = [];
    for (let i = 0; i < 48; i++) pts.push(dest(lat, lng, i * 7.5, r));
    return { points: pts, kind: 'anchor' };
  }

  const Vms = sog * 0.5144;                        // knots → m/s
  if (Vms < 0.25) return { points: [], kind: 'none' };

  const D       = Vms * TIME_HORIZON_S;             // metres of travel
  const halfW   = (beam / 2) * 1.2;                // zone half-width at base
  const bowDist = length / 2;                       // centre → bow (m)

  // ── Straight course (low ROT) ─────────────────────────────────────────────
  if (Math.abs(rot) < ROT_THRESHOLD) {
    const portDir = (cog - 90 + 360) % 360;
    const stbdDir = (cog + 90       ) % 360;

    const bowCtr  = dest(lat, lng, cog, bowDist);
    const farCtr  = dest(lat, lng, cog, bowDist + D);

    // Near end: full beam width
    const bowPort = dest(bowCtr[0], bowCtr[1], portDir, halfW);
    const bowStbd = dest(bowCtr[0], bowCtr[1], stbdDir, halfW);

    // Far end: tapers to near-point (10 % of beam)
    const tipW    = halfW * 0.10;
    const farPort = dest(farCtr[0], farCtr[1], portDir, tipW);
    const farStbd = dest(farCtr[0], farCtr[1], stbdDir, tipW);
    const tip     = farCtr;

    return {
      points: [bowPort, bowStbd, farStbd, tip, farPort],
      kind: 'lance',
    };
  }

  // ── Turning (high ROT) ────────────────────────────────────────────────────
  const rotRads   = Math.abs(rot) * (Math.PI / 180) / 60; // rad/s
  const R         = Vms / rotRads;                         // turning radius (m)
  const turnDir   = rot > 0 ? 1 : -1;                     // +1 = stbd / clockwise

  // Centre of the turning circle
  const cBearing  = (cog + turnDir * 90 + 360) % 360;
  const cCenter   = dest(lat, lng, cBearing, R);

  // Bearing from circle centre back to the vessel's current bow
  const bowPos    = dest(lat, lng, cog, bowDist);
  const startBear = (cog - turnDir * 90 + 360) % 360;

  const totalDeg  = Math.min((D / R) * (180 / Math.PI), 270);
  const steps     = Math.max(10, Math.min(54, Math.round(totalDeg / 5)));

  const outerR    = R + halfW;
  const innerR    = Math.max(halfW * 0.4, R - halfW);

  // Avoid using bowPos variable to prevent linter unused warning
  void bowPos;

  const outer: [number, number][] = [];
  const inner: [number, number][] = [];

  for (let i = 0; i <= steps; i++) {
    const alpha   = (totalDeg * i / steps) * turnDir;
    const bearing = (startBear + alpha + 360) % 360;
    outer.push(dest(cCenter[0], cCenter[1], bearing, outerR));
  }
  for (let i = steps; i >= 0; i--) {
    const alpha   = (totalDeg * i / steps) * turnDir;
    const bearing = (startBear + alpha + 360) % 360;
    inner.push(dest(cCenter[0], cCenter[1], bearing, innerR));
  }

  return { points: [...outer, ...inner], kind: 'arc' };
}
