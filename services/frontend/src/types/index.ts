export type PlatformType = "vessel" | "rov" | "usv" | "auv" | "drone" | "buoy";

export interface Platform {
  platform_id: string;
  platform_type: PlatformType;
  name: string;
  flag: string | null;
  source_protocol: string;
  moth_channel: string | null;
  capabilities: string[];
  metadata: Record<string, unknown>;
}

export interface PlatformState extends Platform {
  lat: number;
  lon: number;
  sog: number | null;
  cog: number | null;
  heading: number | null;
  nav_status: string | null;
  last_seen: string;   // ISO timestamp
}

export interface SpatialReferencePoint {
  time: string;
  lat: number;
  lon: number;
}

export interface NearbyPlatform {
  platform_id: string;
  platform_type: PlatformType;
  name: string;
  lat: number;
  lon: number;
  sog: number | null;
  cog: number | null;
  heading: number | null;
  nav_status: string | null;
  distance_nm: number;
}

export interface NearbyZone {
  zone_id: string;
  name: string;
  zone_type: string;
  active: boolean;
  contains_platform: boolean;
  distance_nm: number;
  rules: Record<string, unknown>;
}

export interface PlatformSpatialContext {
  platform_id: string;
  reference: SpatialReferencePoint;
  nearby_platforms: NearbyPlatform[];
  nearby_zones: NearbyZone[];
  nearest_fairway: NearbyZone | null;
  route_deviation_nm: number | null;
  in_fairway: boolean;
}

export interface ZoneDwellSession {
  zone_id: string;
  zone_name: string;
  zone_type: string | null;
  entered_at: string;
  exited_at: string | null;
  dwell_minutes: number | null;
  active: boolean;
}

export interface PlatformZoneDwell {
  platform_id: string;
  active_sessions: ZoneDwellSession[];
  recent_sessions: ZoneDwellSession[];
}

export type AlertSeverity = "critical" | "warning" | "info";
export type AlertStatus = "new" | "acknowledged" | "resolved";
export type AlertType =
  | "cpa"
  | "zone_intrusion"
  | "anomaly"
  | "ais_off"
  | "distress"
  | "compliance"
  | "traffic";

export interface Alert {
  alert_id: string;
  alert_type: AlertType;
  severity: AlertSeverity;
  status: AlertStatus;
  platform_ids: string[];
  zone_id: string | null;
  generated_by: string;
  message: string;
  recommendation: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
}

export type AgentLevel = "L1" | "L2" | "L3";

export interface AgentInfo {
  agent_id: string;
  name: string;
  type: "rule" | "ai";
  level: AgentLevel;
  enabled: boolean;
}

// WebSocket 메시지
type AlertWsFields = {
  alert_id: string; alert_type: AlertType; severity: AlertSeverity;
  message: string; platform_ids: string[]; recommendation: string | null;
  created_at: string; status: AlertStatus; generated_by: string;
  zone_id: string | null; metadata: Record<string, unknown>;
  acknowledged_at: string | null; resolved_at: string | null;
};

export type WsMessage =
  | { type: "position_update"; platform_id: string; platform_type?: PlatformType; name?: string; timestamp: string; schema_version?: number; source?: string; source_protocol?: string; lat: number; lon: number; sog: number | null; cog: number | null; heading: number | null; nav_status: string | null }
  | ({ type: "alert_created" } & AlertWsFields)
  | ({ type: "alert_updated" } & AlertWsFields);
