import type { AisNmeaFrame, Vessel } from "../types";
import {
  decodePositionReport,
  decodeVoyageReport,
  encodePositionReport,
  encodeVoyageReport,
  peekAisFrame,
} from "./ais";

const decoder = new TextDecoder();
const encoder = new TextEncoder();

export const AIS_STREAM_MIME =
  "application/x-ais-nmea; charset=utf-8; schema=demo-vdm-batch;";

export const DEFAULT_MOTH_NAME = "marine-ais";
export const DEFAULT_MOTH_PORT = "8287";
export const DEFAULT_MOTH_HOST = "cobot.center";
export const DEFAULT_MOTH_PUB_URL = `wss://${DEFAULT_MOTH_HOST}:${DEFAULT_MOTH_PORT}/pang/ws/pub?channel=instant&name=${DEFAULT_MOTH_NAME}&source=base&track=data&mode=single`;
export const DEFAULT_MOTH_SUB_URL = `wss://${DEFAULT_MOTH_HOST}:${DEFAULT_MOTH_PORT}/pang/ws/sub?channel=instant&name=${DEFAULT_MOTH_NAME}&source=base&track=data&mode=single`;

const parseFrameHeader = (sentence: string): AisNmeaFrame => {
  const firstLine = sentence.split('\n')[0];
  const { msgType, mmsi } = peekAisFrame(firstLine);
  return {
    sentence,
    kind: msgType === 5 ? 'voyage' : 'position',
    mmsi,
  };
};

export const createFrameBatch = (vessels: Vessel[]) =>
  vessels.flatMap((vessel) => [
    encodePositionReport(vessel),
    encodeVoyageReport(vessel),
  ]);

export const serializeFrameBatch = (frames: AisNmeaFrame[]) =>
  encoder.encode(frames.map((frame) => frame.sentence).join("\n"));

export const parseFrameBatchPayload = (payload: ArrayBuffer | Uint8Array): AisNmeaFrame[] => {
  const bytes = payload instanceof Uint8Array ? payload : new Uint8Array(payload);
  const text = decoder.decode(bytes);
  const lines = text.split('\n').map(l => l.trim()).filter(Boolean);

  const result: AisNmeaFrame[] = [];
  // key: seqId string, value: accumulated sentence lines
  const pending = new Map<string, string[]>();

  for (const line of lines) {
    const fields = line.slice(1).split('*')[0].split(',');
    const total = parseInt(fields[1] ?? '1', 10);
    const index = parseInt(fields[2] ?? '1', 10);
    const seqId = fields[3] ?? '';

    if (total === 1) {
      result.push(parseFrameHeader(line));
    } else {
      const key = seqId || `auto-${total}`;
      if (!pending.has(key)) pending.set(key, []);
      const parts = pending.get(key)!;
      parts[index - 1] = line;
      if (parts.filter(Boolean).length === total) {
        result.push(parseFrameHeader(parts.join('\n')));
        pending.delete(key);
      }
    }
  }

  return result;
};

export const applyFramesToVessels = (
  frames: AisNmeaFrame[],
  existingVessels: Vessel[],
) => {
  const byMmsi = new Map(
    existingVessels.map((vessel) => [vessel.mmsi, vessel]),
  );
  const ensureVessel = (mmsi: string) => {
    const existing = byMmsi.get(mmsi);
    if (existing) {
      return existing;
    }

    const created: Vessel = {
      mmsi,
      name: mmsi,
      callSign: "-",
      imo: "-",
      vesselType: "Cargo",
      length: 0,
      beam: 0,
      destination: "-",
      etaUtc: new Date().toISOString(),
      draft: 0,
      hazardousCargo: false,
      latitude: 0,
      longitude: 0,
      utcTime: new Date().toISOString(),
      positionAccuracy: "Low",
      sog: 0,
      cog: 0,
      heading: 0,
      rateOfTurn: 0,
      navigationStatus: "Under way",
    };
    byMmsi.set(mmsi, created);
    return created;
  };

  for (const frame of frames) {
    if (frame.kind === "position") {
      const decoded = decodePositionReport(frame.sentence);
      const existing = ensureVessel(decoded.mmsi);
      byMmsi.set(decoded.mmsi, { ...existing, ...decoded.data });
      continue;
    }

    const decoded = decodeVoyageReport(frame.sentence);
    const existing = ensureVessel(decoded.mmsi);
    byMmsi.set(decoded.mmsi, { ...existing, ...decoded.data });
  }

  return Array.from(byMmsi.values());
};
