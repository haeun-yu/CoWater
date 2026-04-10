import type { PlatformType, WsMessage } from "../types";

type JsonRecord = Record<string, unknown>;

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null;
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isNullableString(value: unknown): value is string | null | undefined {
  return value === null || value === undefined || typeof value === "string";
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isNullableFiniteNumber(value: unknown): value is number | null | undefined {
  return value === null || value === undefined || isFiniteNumber(value);
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(isString);
}

function isPlatformType(value: unknown): value is PlatformType {
  return ["vessel", "rov", "usv", "auv", "drone", "buoy"].includes(String(value));
}

function isPositionUpdateMessage(value: JsonRecord): value is Extract<WsMessage, { type: "position_update" }> {
  return (
    value.type === "position_update" &&
    isString(value.platform_id) &&
    isString(value.timestamp) &&
    isFiniteNumber(value.lat) &&
    isFiniteNumber(value.lon) &&
    isNullableFiniteNumber(value.sog) &&
    isNullableFiniteNumber(value.cog) &&
    isNullableFiniteNumber(value.heading) &&
    isNullableString(value.nav_status) &&
    (value.platform_type === undefined || isPlatformType(value.platform_type)) &&
    (value.name === undefined || isString(value.name)) &&
    (value.source_protocol === undefined || isString(value.source_protocol))
  );
}

function isAlertMessage(value: JsonRecord): value is Extract<WsMessage, { type: "alert_created" | "alert_updated" }> {
  return (
    (value.type === "alert_created" || value.type === "alert_updated") &&
    isString(value.alert_id) &&
    isString(value.alert_type) &&
    isString(value.severity) &&
    isString(value.status) &&
    isStringArray(value.platform_ids) &&
    isString(value.generated_by) &&
    isString(value.message) &&
    isNullableString(value.recommendation) &&
    isRecord(value.metadata ?? {}) &&
    isString(value.created_at) &&
    isNullableString(value.acknowledged_at) &&
    isNullableString(value.resolved_at) &&
    isNullableString(value.zone_id)
  );
}

export function parseWsMessage(raw: string): WsMessage | null {
  let parsed: unknown;

  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }

  if (!isRecord(parsed)) {
    return null;
  }

  if (isPositionUpdateMessage(parsed) || isAlertMessage(parsed)) {
    return parsed;
  }

  return null;
}
