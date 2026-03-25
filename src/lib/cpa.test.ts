import test from 'node:test';
import assert from 'node:assert/strict';
import { calcCpa, CPA_DANGER_NM, findCpaAlerts, TCPA_MAX_MIN } from './cpa';
import { predictRoutePosition } from './routePrediction';
import type { Vessel } from '../types';

const LAT = 35;
const COS_LAT = Math.cos((LAT * Math.PI) / 180);

function nmToLat(nm: number) {
  return nm / 60;
}

function nmToLng(nm: number) {
  return nm / (60 * COS_LAT);
}

function createVessel(overrides: Partial<Vessel>): Vessel {
  return {
    mmsi: '440000000',
    name: 'Test Vessel',
    callSign: 'TEST1',
    imo: '9000000',
    vesselType: 'Cargo',
    length: 120,
    beam: 20,
    destination: 'Test Port',
    etaUtc: '2026-03-25T12:00:00Z',
    draft: 7,
    hazardousCargo: false,
    latitude: LAT,
    longitude: 129,
    utcTime: '2026-03-25T08:00:00Z',
    positionAccuracy: 'High',
    sog: 10,
    cog: 90,
    heading: 90,
    rateOfTurn: 0,
    navigationStatus: 'Under way',
    ...overrides,
  };
}

test('calcCpa detects head-on encounter with near-zero CPA', () => {
  const a = createVessel({
    mmsi: '440000001',
    longitude: 129 - nmToLng(1),
    cog: 90,
    heading: 90,
  });
  const b = createVessel({
    mmsi: '440000002',
    longitude: 129 + nmToLng(1),
    cog: 270,
    heading: 270,
  });

  const result = calcCpa(a, b);

  assert.ok(result.cpa < 0.03, `expected near collision, got ${result.cpa} nm`);
  assert.ok(Math.abs(result.tcpa - 6) < 0.5, `expected ~6 min, got ${result.tcpa} min`);
});

test('turn rate changes predicted CPA compared with straight-line motion', () => {
  const a = createVessel({
    mmsi: '440000003',
    longitude: 129 - nmToLng(1),
    cog: 90,
    heading: 90,
  });
  const bStraight = createVessel({
    mmsi: '440000004',
    longitude: 129 + nmToLng(1),
    cog: 270,
    heading: 270,
    rateOfTurn: 0,
  });
  const bTurning = createVessel({
    ...bStraight,
    mmsi: '440000005',
    rateOfTurn: 20,
  });

  const straight = calcCpa(a, bStraight);
  const turning = calcCpa(a, bTurning);

  assert.ok(turning.cpa > straight.cpa + 0.2, `expected turn to widen CPA: ${straight.cpa} -> ${turning.cpa}`);
});

test('findCpaAlerts excludes anchored vessels', () => {
  const underWay = createVessel({
    mmsi: '440000006',
    longitude: 129 - nmToLng(0.5),
    cog: 90,
    heading: 90,
  });
  const anchored = createVessel({
    mmsi: '440000007',
    longitude: 129 + nmToLng(0.5),
    cog: 270,
    heading: 270,
    navigationStatus: 'At anchor',
  });

  const alerts = findCpaAlerts([underWay, anchored]);
  assert.equal(alerts.length, 0);
});

test('alert midpoint sits between the two predicted CPA positions', () => {
  const a = createVessel({
    mmsi: '440000008',
    longitude: 129 - nmToLng(1),
    cog: 90,
    heading: 90,
  });
  const b = createVessel({
    mmsi: '440000009',
    latitude: LAT - nmToLat(1),
    cog: 0,
    heading: 0,
  });

  const [alert] = findCpaAlerts([a, b]);

  assert.ok(alert);
  assert.equal(Number(((alert.cpaPosA[0] + alert.cpaPosB[0]) / 2).toFixed(6)), Number(alert.cpaPoint[0].toFixed(6)));
  assert.equal(Number(((alert.cpaPosA[1] + alert.cpaPosB[1]) / 2).toFixed(6)), Number(alert.cpaPoint[1].toFixed(6)));
});

test('findCpaAlerts ignores encounters beyond the configured TCPA horizon', () => {
  const separationNm = 2 * 10 * (TCPA_MAX_MIN + 4) / 60;
  const a = createVessel({
    mmsi: '440000010',
    longitude: 129 - nmToLng(separationNm / 2),
    cog: 90,
    heading: 90,
  });
  const b = createVessel({
    mmsi: '440000011',
    longitude: 129 + nmToLng(separationNm / 2),
    cog: 270,
    heading: 270,
  });

  const alerts = findCpaAlerts([a, b]);
  assert.equal(alerts.length, 0);
});

test('near-threshold future encounter stays warning until it becomes near-term', () => {
  const separationNm = 2 * 10 * 10 / 60;
  const a = createVessel({
    mmsi: '440000012',
    longitude: 129 - nmToLng(separationNm / 2),
    cog: 90,
    heading: 90,
  });
  const b = createVessel({
    mmsi: '440000013',
    longitude: 129 + nmToLng(separationNm / 2),
    cog: 270,
    heading: 270,
  });

  const [alert] = findCpaAlerts([a, b]);
  assert.ok(alert);
  assert.ok(alert.cpa < CPA_DANGER_NM);
  assert.equal(alert.severity, 'warning');
});

test('route-based prediction follows the shared simulator route instead of drifting off by heading', () => {
  const vessel = createVessel({
    mmsi: '440123456',
    latitude: 35.0702,
    longitude: 129.0798,
    sog: 12,
    cog: 40,
    heading: 210,
    rateOfTurn: 18,
  });

  const predicted = predictRoutePosition(vessel, 180);

  assert.ok(predicted);
  assert.ok(predicted[0] < vessel.latitude, `expected route to move southward, got ${predicted[0]}`);
  assert.ok(predicted[1] > vessel.longitude, `expected route to move eastward, got ${predicted[1]}`);
});

test('parallel motion does not create a false CPA alert', () => {
  const a = createVessel({
    mmsi: '440000014',
    latitude: LAT,
    longitude: 129,
    sog: 12,
    cog: 90,
    heading: 90,
  });
  const b = createVessel({
    mmsi: '440000015',
    latitude: LAT + nmToLat(0.2),
    longitude: 129,
    sog: 12,
    cog: 90,
    heading: 90,
  });

  const alerts = findCpaAlerts([a, b]);
  assert.equal(alerts.length, 0);
});
