/**
 * 공통 상수 정의 — 전역 사용
 * 중복 제거 및 단일 소스화
 */

// ── 경보 관련 ──
export const ALERT_SEVERITY_LABEL = {
  critical: "위험",
  warning: "주의",
  info: "정보",
} as const;

export const ALERT_TYPE_LABEL = {
  cpa: "충돌 위험",
  zone_intrusion: "구역 침입",
  zone_exit: "구역 이탈",
  anomaly: "이상 행동",
  ais_off: "AIS 소실",
  ais_recovered: "AIS 복구",
  distress: "조난",
  compliance: "상황 보고",
  traffic: "교통 혼잡",
} as const;

export const ALERT_STATUS_LABEL = {
  new: "미확인",
  acknowledged: "확인됨",
  resolved: "해결됨",
} as const;

// ── 플랫폼 타입 ──
export const PLATFORM_TYPE_ICON = {
  vessel: "▲",
  usv: "◆",
  rov: "●",
  auv: "◈",
  drone: "✦",
  buoy: "◉",
} as const;

export const PLATFORM_TYPE_LABEL = {
  vessel: "선박",
  usv: "USV",
  rov: "ROV",
  auv: "AUV",
  drone: "드론",
  buoy: "부이",
} as const;

export const PLATFORM_TYPE_COLOR = {
  vessel: "#2e8dd4",
  usv: "#22d3ee",
  rov: "#a78bfa",
  auv: "#818cf8",
  drone: "#34d399",
  buoy: "#fbbf24",
} as const;

// ── 항법 상태 ──
export const NAV_STATUS_LABEL = {
  underway_engine: "항행 중",
  at_anchor: "정박",
  not_under_command: "조종 불능",
  restricted_maneuverability: "조종 제한",
  moored: "계류",
  aground: "좌초",
  engaged_fishing: "어로 작업",
  underway_sailing: "항행 중(범선)",
} as const;

export const NAV_STATUS_BADGE_STYLE = {
  not_under_command: "text-red-400 bg-red-500/15 border-red-500/30",
  aground: "text-red-400 bg-red-500/15 border-red-500/30",
  at_anchor: "text-yellow-400 bg-yellow-500/10 border-yellow-500/20",
  moored: "text-yellow-400 bg-yellow-500/10 border-yellow-500/20",
  underway_engine: "text-green-400 bg-green-500/10 border-green-500/20",
} as const;

// ── 권한 순서 ──
export const ROLE_ORDER = { viewer: 0, operator: 1, admin: 2 } as const;

// ── 리포트 타입 ──
export const REPORT_TYPE_LABEL = {
  summary: "요약",
  detailed: "상세",
  incident: "사건",
} as const;

export const REPORT_TYPE_COLOR = {
  summary: "#38bdf8",
  detailed: "#a78bfa",
  incident: "#f87171",
} as const;
