import type { AisNmeaFrame, Vessel, VesselDynamicData, VesselStaticData } from '../types';

// ---------------------------------------------------------------------------
// 6-bit NMEA armoring
// ---------------------------------------------------------------------------

/** Encode a 6-bit value (0–63) to an NMEA armored ASCII character. */
function armorChar(val: number): string {
  let ascii = val + 48;
  if (ascii > 87) ascii += 8;
  return String.fromCharCode(ascii);
}

/** Decode an NMEA armored ASCII character back to a 6-bit value (0–63). */
function dearmorChar(ch: string): number {
  let v = ch.charCodeAt(0) - 48;
  if (v > 40) v -= 8;
  return v & 0x3f;
}

// ---------------------------------------------------------------------------
// ITU 6-bit text charset
// ---------------------------------------------------------------------------

function asciiToItu6(ascii: number): number {
  if (ascii >= 64 && ascii <= 95) return ascii - 64;
  if (ascii >= 32 && ascii <= 63) return ascii;
  return 32; // space fallback
}

function itu6ToAscii(val: number): string {
  if (val >= 0 && val <= 31) return String.fromCharCode(val + 64);
  return String.fromCharCode(val);
}

// ---------------------------------------------------------------------------
// BitWriter
// ---------------------------------------------------------------------------

class BitWriter {
  private bits: number[] = [];

  uint(value: number, width: number): this {
    for (let i = width - 1; i >= 0; i--) {
      this.bits.push((value >>> i) & 1);
    }
    return this;
  }

  int(value: number, width: number): this {
    // two's complement: mask to `width` bits then treat as unsigned
    const masked = ((value % (1 << width)) + (1 << width)) % (1 << width);
    return this.uint(masked, width);
  }

  text(value: string, numChars: number): this {
    const padded = value.toUpperCase().padEnd(numChars, '@');
    for (let i = 0; i < numChars; i++) {
      const ch = padded[i] ?? '@';
      const itu = asciiToItu6(ch.charCodeAt(0));
      this.uint(itu, 6);
    }
    return this;
  }

  toPayload(): { payload: string; fillBits: number } {
    const totalBits = this.bits.length;
    const fillBits = (6 - (totalBits % 6)) % 6;
    // pad to multiple of 6
    const padded = [...this.bits, ...Array(fillBits).fill(0)];
    let payload = '';
    for (let i = 0; i < padded.length; i += 6) {
      const val = (padded[i] << 5) | (padded[i + 1] << 4) | (padded[i + 2] << 3) |
                  (padded[i + 3] << 2) | (padded[i + 4] << 1) | padded[i + 5];
      payload += armorChar(val);
    }
    return { payload, fillBits };
  }
}

// ---------------------------------------------------------------------------
// BitReader
// ---------------------------------------------------------------------------

class BitReader {
  private bits: number[];
  private pos = 0;

  constructor(payload: string) {
    this.bits = [];
    for (const ch of payload) {
      const val = dearmorChar(ch);
      for (let i = 5; i >= 0; i--) {
        this.bits.push((val >>> i) & 1);
      }
    }
  }

  uint(width: number): number {
    let result = 0;
    for (let i = 0; i < width; i++) {
      result = (result << 1) | (this.bits[this.pos++] ?? 0);
    }
    return result >>> 0;
  }

  int(width: number): number {
    const raw = this.uint(width);
    // sign extend
    if (width > 0 && (raw >>> (width - 1)) & 1) {
      return raw - (1 << width);
    }
    return raw;
  }

  text(numChars: number): string {
    let result = '';
    for (let i = 0; i < numChars; i++) {
      const val = this.uint(6);
      result += itu6ToAscii(val);
    }
    return result.replace(/@+$/, '').trimEnd();
  }
}

// ---------------------------------------------------------------------------
// NMEA checksum & sentence builder
// ---------------------------------------------------------------------------

function nmeaChecksum(body: string): string {
  let xor = 0;
  for (let i = 0; i < body.length; i++) {
    xor ^= body.charCodeAt(i);
  }
  return xor.toString(16).toUpperCase().padStart(2, '0');
}

function buildSentence(total: number, index: number, seqId: string | number, payloadChunk: string, fillBits: number): string {
  const body = `AIVDM,${total},${index},${seqId},A,${payloadChunk},${fillBits}`;
  return `!${body}*${nmeaChecksum(body)}`;
}

// ---------------------------------------------------------------------------
// Navigation status maps
// ---------------------------------------------------------------------------

const NAV_STATUS_ENCODE: Record<string, number> = {
  'Under way': 0,
  'At anchor': 1,
  'Moored': 5,
  'Restricted': 8,
};

const NAV_STATUS_DECODE: Record<number, VesselDynamicData['navigationStatus']> = {
  0: 'Under way',
  1: 'At anchor',
  5: 'Moored',
  8: 'Restricted',
};

// ---------------------------------------------------------------------------
// Ship type maps
// ---------------------------------------------------------------------------

const SHIP_TYPE_ENCODE: Record<string, number> = {
  Passenger: 60,
  Tug: 52,
  Cargo: 70,
  Tanker: 80,
  Research: 90,
};

function encodeShipType(vesselType: string, hazardousCargo: boolean): number {
  const base = SHIP_TYPE_ENCODE[vesselType] ?? 90;
  if (hazardousCargo && (vesselType === 'Cargo' || vesselType === 'Tanker')) {
    return base + 1;
  }
  return base;
}

function decodeShipType(code: number): { vesselType: VesselStaticData['vesselType']; hazardousCargo: boolean } {
  if (code >= 60 && code <= 69) return { vesselType: 'Passenger', hazardousCargo: false };
  if (code === 52) return { vesselType: 'Tug', hazardousCargo: false };
  if (code >= 70 && code <= 79) return { vesselType: 'Cargo', hazardousCargo: code >= 71 };
  if (code >= 80 && code <= 89) return { vesselType: 'Tanker', hazardousCargo: code >= 81 };
  return { vesselType: 'Research', hazardousCargo: false };
}

// ---------------------------------------------------------------------------
// ROT encoding/decoding
// ---------------------------------------------------------------------------

function encodeROT(degPerMin: number): number {
  if (degPerMin === 0) return 0;
  const sign = degPerMin > 0 ? 1 : -1;
  const indicator = Math.round(4.733 * Math.sqrt(Math.abs(degPerMin))) * sign;
  return Math.max(-128, Math.min(127, indicator));
}

function decodeROT(indicator: number): number {
  if (indicator === 0) return 0;
  const sign = indicator > 0 ? 1 : -1;
  return Math.pow(Math.abs(indicator) / 4.733, 2) * sign;
}

// ---------------------------------------------------------------------------
// ETA encoding/decoding
// ---------------------------------------------------------------------------

function encodeEta(etaUtc: string): { month: number; day: number; hour: number; minute: number } {
  const d = new Date(etaUtc);
  return {
    month: d.getUTCMonth() + 1,
    day: d.getUTCDate(),
    hour: d.getUTCHours(),
    minute: d.getUTCMinutes(),
  };
}

function decodeEta(month: number, day: number, hour: number, minute: number): string {
  const now = new Date();
  let year = now.getUTCFullYear();
  const testDate = new Date(Date.UTC(year, month - 1, day, hour, minute));
  if (testDate < now) year += 1;
  const d = new Date(Date.UTC(year, month - 1, day, hour, minute));
  return d.toISOString();
}

// ---------------------------------------------------------------------------
// Sequence counter for multi-part messages (1–9 rotating)
// ---------------------------------------------------------------------------

let seqCounter = 0;
function nextSeq(): number {
  seqCounter = (seqCounter % 9) + 1;
  return seqCounter;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Peek at the first sentence of a (possibly multi-sentence) AIS frame
 * to extract msgType and MMSI without full decode.
 */
export function peekAisFrame(sentence: string): { msgType: number; mmsi: string } {
  // Extract payload from NMEA sentence: fields[5]
  const body = sentence.slice(1).split('*')[0];
  const fields = body.split(',');
  const payload = fields[5] ?? '';
  const reader = new BitReader(payload);
  const msgType = reader.uint(6);
  reader.uint(2); // repeat indicator
  const mmsiNum = reader.uint(30);
  return { msgType, mmsi: String(mmsiNum) };
}

/**
 * Encode a Type 1 Class A Position Report sentence.
 */
export const encodePositionReport = (vessel: Vessel): AisNmeaFrame => {
  const navStatus = NAV_STATUS_ENCODE[vessel.navigationStatus] ?? 0;
  const rot = encodeROT(vessel.rateOfTurn);
  const sog = Math.round(vessel.sog * 10);
  const posAcc = vessel.positionAccuracy === 'High' ? 1 : 0;
  const lon = Math.round(vessel.longitude * 600000);
  const lat = Math.round(vessel.latitude * 600000);
  const cog = Math.round(vessel.cog * 10);
  const heading = vessel.heading >= 0 && vessel.heading <= 359 ? vessel.heading : 511;

  // Extract UTC seconds from utcTime
  const utcSeconds = new Date(vessel.utcTime).getUTCSeconds();

  const writer = new BitWriter()
    .uint(1, 6)          // message type
    .uint(0, 2)          // repeat
    .uint(parseInt(vessel.mmsi, 10), 30)  // MMSI
    .uint(navStatus, 4)
    .int(rot, 8)
    .uint(sog, 10)
    .uint(posAcc, 1)
    .int(lon, 28)
    .int(lat, 27)
    .uint(cog, 12)
    .uint(heading, 9)
    .uint(utcSeconds, 6)
    .uint(0, 2)          // maneuver indicator
    .uint(0, 3)          // spare
    .uint(0, 1)          // RAIM
    .uint(0, 19);        // radio status

  const { payload, fillBits } = writer.toPayload();
  const sentence = buildSentence(1, 1, '', payload, fillBits);

  return { sentence, kind: 'position', mmsi: vessel.mmsi };
};

/**
 * Decode a Type 1 Position Report sentence.
 */
export const decodePositionReport = (sentence: string): { mmsi: string; data: VesselDynamicData } => {
  const body = sentence.slice(1).split('*')[0];
  const fields = body.split(',');
  const payload = fields[5] ?? '';

  const reader = new BitReader(payload);
  reader.uint(6);  // msg type
  reader.uint(2);  // repeat
  const mmsiNum = reader.uint(30);
  const navCode = reader.uint(4);
  const rotIndicator = reader.int(8);
  const sogRaw = reader.uint(10);
  const posAccRaw = reader.uint(1);
  const lonRaw = reader.int(28);
  const latRaw = reader.int(27);
  const cogRaw = reader.uint(12);
  const headingRaw = reader.uint(9);
  const seconds = reader.uint(6);

  const mmsi = String(mmsiNum);
  const navigationStatus = NAV_STATUS_DECODE[navCode] ?? 'Under way';
  const rateOfTurn = decodeROT(rotIndicator);
  const sog = sogRaw / 10;
  const positionAccuracy: VesselDynamicData['positionAccuracy'] = posAccRaw === 1 ? 'High' : 'Low';
  const longitude = lonRaw / 600000;
  const latitude = latRaw / 600000;
  const cog = cogRaw / 10;
  const heading = headingRaw === 511 ? 0 : headingRaw;

  // Reconstruct a UTC time using current date with the seconds from the message
  const now = new Date();
  now.setUTCSeconds(seconds, 0);
  const utcTime = now.toISOString();

  return {
    mmsi,
    data: {
      latitude,
      longitude,
      utcTime,
      positionAccuracy,
      sog,
      cog,
      heading,
      rateOfTurn,
      navigationStatus,
    },
  };
};

/**
 * Encode a Type 5 Static and Voyage Data report (two-part sentence).
 * The two sentences are joined with '\n' in AisNmeaFrame.sentence.
 */
export const encodeVoyageReport = (vessel: Vessel): AisNmeaFrame => {
  const imoNum = parseInt(vessel.imo.replace(/\D/g, ''), 10) || 0;
  const shipType = encodeShipType(vessel.vesselType, vessel.hazardousCargo);
  const bow = Math.min(511, Math.max(0, Math.round(vessel.length * 0.6)));
  const stern = Math.min(511, Math.max(0, Math.round(vessel.length * 0.4)));
  const port = Math.min(15, Math.max(0, Math.round(vessel.beam / 2)));
  const starboard = Math.min(15, Math.max(0, Math.round(vessel.beam / 2)));
  const draught = Math.round(vessel.draft * 10);
  const eta = encodeEta(vessel.etaUtc);

  const writer = new BitWriter()
    .uint(5, 6)           // message type
    .uint(0, 2)           // repeat
    .uint(parseInt(vessel.mmsi, 10), 30)
    .uint(0, 2)           // AIS version
    .uint(imoNum, 30)     // IMO number
    .text(vessel.callSign, 7)
    .text(vessel.name, 20)
    .uint(shipType, 8)
    .uint(bow, 9)
    .uint(stern, 9)
    .uint(port, 4)
    .uint(starboard, 4)
    .uint(1, 4)           // EPFD = GPS
    .uint(eta.month, 4)
    .uint(eta.day, 5)
    .uint(eta.hour, 5)
    .uint(eta.minute, 6)
    .uint(draught, 8)
    .text(vessel.destination, 20)
    .uint(0, 1)           // DTE
    .uint(0, 7);          // spare

  const { payload } = writer.toPayload();
  // fillBits for type 5: 426 bits = 71 chars, 71 * 6 = 426, so fillBits = 0
  const fillBits = 0;

  const seq = nextSeq();
  // Split payload into two parts: first up to 56 chars, rest in second
  const part1 = payload.slice(0, 56);
  const part2 = payload.slice(56);

  const sentence1 = buildSentence(2, 1, seq, part1, 0);
  const sentence2 = buildSentence(2, 2, seq, part2, fillBits);
  const combined = `${sentence1}\n${sentence2}`;

  return { sentence: combined, kind: 'voyage', mmsi: vessel.mmsi };
};

/**
 * Decode a Type 5 Static and Voyage Data report.
 * Accepts either the first sentence alone or both sentences joined with '\n'.
 */
export const decodeVoyageReport = (sentence: string): { mmsi: string; data: VesselStaticData } => {
  // Reassemble payload from potentially two sentences
  const lines = sentence.split('\n').map(l => l.trim()).filter(Boolean);
  let fullPayload = '';
  for (const line of lines) {
    const body = line.slice(1).split('*')[0];
    const fields = body.split(',');
    fullPayload += fields[5] ?? '';
  }

  const reader = new BitReader(fullPayload);
  reader.uint(6);  // msg type
  reader.uint(2);  // repeat
  const mmsiNum = reader.uint(30);
  reader.uint(2);  // AIS version
  const imoNum = reader.uint(30);
  const callSign = reader.text(7);
  const name = reader.text(20);
  const shipTypeCode = reader.uint(8);
  const bow = reader.uint(9);
  const stern = reader.uint(9);
  const portDim = reader.uint(4);
  const starboardDim = reader.uint(4);
  reader.uint(4);  // EPFD
  const etaMonth = reader.uint(4);
  const etaDay = reader.uint(5);
  const etaHour = reader.uint(5);
  const etaMinute = reader.uint(6);
  const draughtRaw = reader.uint(8);
  const destination = reader.text(20);

  const mmsi = String(mmsiNum);
  const { vesselType, hazardousCargo } = decodeShipType(shipTypeCode);
  const length = bow + stern;
  const beam = portDim + starboardDim;
  const draft = draughtRaw / 10;
  const etaUtc = decodeEta(etaMonth, etaDay, etaHour, etaMinute);
  const imo = String(imoNum);

  return {
    mmsi,
    data: {
      mmsi,
      name,
      callSign,
      imo,
      vesselType,
      length,
      beam,
      destination,
      etaUtc,
      draft,
      hazardousCargo,
    },
  };
};
