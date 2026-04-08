/**
 * 프론트엔드 전역 설정.
 *
 * 지도 초기 위치·줌, 항적 시각화, 플랫폼 색상·아이콘 치수, WebSocket 타이밍 등
 * 코드 수정 없이 바꿔야 하는 값들을 한곳에서 관리한다.
 *
 * NEXT_PUBLIC_* 환경 변수로 오버라이드 가능한 항목은 주석에 표시.
 */

// ── 지도 초기 설정 ───────────────────────────────────────────────────────────
// .env.local: NEXT_PUBLIC_MAP_LON, NEXT_PUBLIC_MAP_LAT, NEXT_PUBLIC_MAP_ZOOM

export const MAP_CENTER: [number, number] = [
  Number(process.env.NEXT_PUBLIC_MAP_LON ?? 126.55),
  Number(process.env.NEXT_PUBLIC_MAP_LAT ?? 34.75),
];
export const MAP_ZOOM = Number(process.env.NEXT_PUBLIC_MAP_ZOOM ?? 8);
export const MAP_OSM_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
export const MAP_OSM_ATTRIBUTION = "© OpenStreetMap contributors";
export const MAP_OPENSEAMAP_SEAMARK_TILE_URL = "https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png";
export const MAP_OPENSEAMAP_ATTRIBUTION = "© OpenSeaMap contributors";

/** OSM 기본 타일 불투명도 (0~1) */
export const MAP_OSM_OPACITY = 0.35;
export const MAP_SHIP_LAYER_MIN_ZOOM = 9;
export const MAP_CLUSTER_MAX_ZOOM = 8;
export const MAP_NAV_AID_FETCH_MIN_ZOOM = 9;

/** 선박 선택 시 최소 줌 레벨 */
export const MAP_SELECT_MIN_ZOOM = 11;
/** 선박 선택 시 flyTo 애니메이션 시간 (ms) */
export const MAP_SELECT_FLY_DURATION = 800;
/** 실시간 추적 easeTo 애니메이션 시간 (ms) */
export const MAP_TRACK_EASE_DURATION = 300;
export const MAP_SELECTED_SAFETY_BUFFER_NM = 0.5;
export const MAP_SELECTED_HEADING_SECTOR_RADIUS_NM = 1.2;
export const MAP_SELECTED_HEADING_SECTOR_ANGLE_DEG = 50;
export const MAP_SELECTED_PREDICTION_MINUTES = 12;
export const MAP_HISTORY_SIMPLIFY_TOLERANCE_KM = 0.03;

// ── 항적(Trail) 시각화 ───────────────────────────────────────────────────────

/** 플랫폼당 최대 항적 포인트 수 */
export const TRAIL_MAX = 90;
/** 불투명 구간 포인트 수 (뒤에서부터) */
export const TRAIL_RECENT = 15;
/** 반투명 구간 끝 포인트 인덱스 (뒤에서부터) */
export const TRAIL_MID = 45;

/** 구간별 opacity: old → mid → recent */
export const TRAIL_OPACITY = { old: 0.12, mid: 0.38, recent: 0.82 };

export const TRAIL_LINE_WIDTH = 2.0;
export const TRAIL_CASING_WIDTH = 3.5;
export const TRAIL_CASING_COLOR = "#020d1a";
/** 외곽선 opacity = 해당 구간 opacity × 이 배율 */
export const TRAIL_CASING_OPACITY_FACTOR = 0.55;

// ── Alert 시각화 ─────────────────────────────────────────────────────────────

/**
 * 지도 위 마커를 강조 표시할 alert 최소 심각도.
 * "critical" | "warning"
 */
export const ALERT_HIGHLIGHT_SEVERITY: "critical" | "warning" = "critical";

/** 경보 중인 플랫폼의 항적 색상 */
export const ALERT_TRAIL_COLOR = "#ef4444";
/** 경보 링 색상 */
export const ALERT_RING_COLOR = "#ef4444";

// ── 플랫폼 타입별 색상 팔레트 ────────────────────────────────────────────────

type Pal = { top: string; side: string; stern: string; bridge: string };

export const PLATFORM_COLORS: Record<string, Pal> = {
  vessel: { top: "#2e8dd4", side: "#1c5f8a", stern: "#0f3b57", bridge: "#4aadee" },
  usv:    { top: "#22d3ee", side: "#0e9baf", stern: "#077282", bridge: "#40eeff" },
  rov:    { top: "#a78bfa", side: "#7c5bcf", stern: "#5330a0", bridge: "#c4a8ff" },
  auv:    { top: "#818cf8", side: "#5960cc", stern: "#3540a0", bridge: "#a0a8ff" },
  drone:  { top: "#34d399", side: "#1e9e70", stern: "#10704e", bridge: "#50efb4" },
  buoy:   { top: "#fbbf24", side: "#c48a0a", stern: "#8f6000", bridge: "#ffdb4a" },
};

/** 선택된 플랫폼 강조 색상 */
export const PLATFORM_SELECTED_COLOR: Pal = {
  top: "#f5a623", side: "#c47d08", stern: "#8a5200", bridge: "#ffc142",
};

// ── 플랫폼 타입별 아이콘 치수 (px, zoom 9 기준) ──────────────────────────────

export const PLATFORM_DIMS: Record<string, { L: number; W: number }> = {
  vessel: { L: 28, W:  9 },
  usv:    { L: 18, W:  5 },
  rov:    { L: 14, W: 10 },
  auv:    { L: 16, W:  5 },
  drone:  { L: 12, W: 11 },
  buoy:   { L: 12, W: 12 },
};

/** 지도 위 선박 실루엣 렌더링용 상대 길이/폭(m) */
export const PLATFORM_RENDER_METERS: Record<string, { length: number; beam: number }> = {
  vessel: { length: 90, beam: 18 },
  usv: { length: 28, beam: 8 },
  rov: { length: 16, beam: 10 },
  auv: { length: 22, beam: 7 },
  drone: { length: 14, beam: 10 },
  buoy: { length: 10, beam: 10 },
};

export const OVERPASS_API_URL =
  process.env.NEXT_PUBLIC_OVERPASS_API_URL ?? "https://overpass-api.de/api/interpreter";

/** zoom 스케일 배율 기저 (zoom 9 → 1.0, zoom 11 → ~2.0) */
export const ZOOM_SCALE_BASE = 1.42;
/** zoom 스케일 기준 줌 레벨 */
export const ZOOM_SCALE_REF = 9;

/** 아이콘 최소 길이 (px) */
export const ICON_MIN_LENGTH = 8;
/** SVG 패딩 (px) */
export const ICON_PAD = 4;

// ── WebSocket ────────────────────────────────────────────────────────────────

/** 연결 끊김 후 재연결 대기 시간 (ms) */
export const WS_RECONNECT_DELAY_MS = 3000;
export const WS_RECONNECT_MAX_DELAY_MS = 30000;
/** ping 전송 주기 (ms) */
export const WS_PING_INTERVAL_MS = 20_000;
