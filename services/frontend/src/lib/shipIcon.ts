/**
 * SVG isometric pseudo-3D ship icon — MapLibre Marker용.
 *
 * 원본: haeun-yu/make-cowater branch (src/lib/shipIcon.ts)
 * 변경: Leaflet L.divIcon → { html, anchorX, anchorY, width, height }
 *       VesselType → PlatformType / 실제 선폭 대신 타입별 기본 치수 사용
 *
 * 세 면 구성:
 *   TOP   – 갑판 (가장 밝음)
 *   SIDE  – 우현 선체 (중간)
 *   STERN – 선미 면 (가장 어두움)
 * SVG 전체가 heading 각도로 선수 방향 회전.
 */

import {
  PLATFORM_COLORS,
  PLATFORM_SELECTED_COLOR,
  PLATFORM_DIMS,
  ZOOM_SCALE_BASE,
  ZOOM_SCALE_REF,
  ICON_MIN_LENGTH,
  ICON_PAD,
  ALERT_RING_COLOR,
} from "@/config";

// ── 로컬 타입 alias ──────────────────────────────────────────────────────────

type Pal = { top: string; side: string; stern: string; bridge: string };

const PALETTE: Record<string, Pal> = PLATFORM_COLORS as Record<string, Pal>;
const SELECTED_PAL: Pal = PLATFORM_SELECTED_COLOR;
const BASE_DIMS = PLATFORM_DIMS;

/** zoom 레벨에 따른 스케일 배율 */
function zoomScale(zoom: number): number {
  return Math.pow(ZOOM_SCALE_BASE, Math.max(0, zoom - ZOOM_SCALE_REF));
}

export interface ShipIconResult {
  html:    string;
  width:   number;
  height:  number;
  anchorX: number; // 선체 중심 X (MapLibre Marker offset 계산용)
  anchorY: number; // 선체 중심 Y
}

export function createShipIcon(
  platformType: string,
  heading: number,
  isSelected: boolean,
  isAlert: boolean,
  zoom: number,
): ShipIconResult {
  const pal   = isSelected ? SELECTED_PAL : (PALETTE[platformType] ?? PALETTE.vessel);
  const base  = BASE_DIMS[platformType] ?? BASE_DIMS.vessel;
  const scale = zoomScale(zoom);

  const Lpx  = Math.max(ICON_MIN_LENGTH, base.L * scale);
  const Wpx  = Math.max(3, base.W * scale);
  const H    = Math.max(1.5, Wpx * 0.36);   // 3D 돌출 깊이

  // Isometric 오프셋 (30° → cos30=0.866, sin30=0.5)
  const ISO_X = H * 0.866;
  const ISO_Y = H * 0.5;

  const PAD  = ICON_PAD;
  const svgW = Wpx + ISO_X + PAD * 2;
  const svgH = Lpx + ISO_Y + PAD * 2;

  // 갑판 box 원점
  const bx = PAD;
  const by = PAD;

  // 선체 중심 (회전 피벗)
  const cx = bx + Wpx / 2;
  const cy = by + Lpx / 2;

  // ── Face 경로 ──────────────────────────────────────────────────────────────

  const top  = `M${bx},${by} L${bx+Wpx},${by} L${bx+Wpx},${by+Lpx} L${bx},${by+Lpx} Z`;

  const side = [
    `M${bx+Wpx},${by}`,
    `L${bx+Wpx+ISO_X},${by+ISO_Y}`,
    `L${bx+Wpx+ISO_X},${by+Lpx+ISO_Y}`,
    `L${bx+Wpx},${by+Lpx} Z`,
  ].join(' ');

  const stern = [
    `M${bx},${by+Lpx}`,
    `L${bx+Wpx},${by+Lpx}`,
    `L${bx+Wpx+ISO_X},${by+Lpx+ISO_Y}`,
    `L${bx+ISO_X},${by+Lpx+ISO_Y} Z`,
  ].join(' ');

  // 선수 줄무늬 (bow stripe)
  const bowH     = Math.max(2, Lpx * 0.10);
  const bowStripe = `M${bx},${by} L${bx+Wpx},${by} L${bx+Wpx},${by+bowH} L${bx},${by+bowH} Z`;

  // 선교 (bridge / superstructure)
  const brX   = bx + Wpx * 0.14;
  const brY   = by + Lpx * 0.32;
  const brW   = Wpx * 0.72;
  const brH   = Lpx * 0.20;
  const brSH  = H * 0.58;
  const brSX  = brSH * 0.866;
  const brSY  = brSH * 0.5;

  const bridgeTop = `M${brX},${brY} L${brX+brW},${brY} L${brX+brW},${brY+brH} L${brX},${brY+brH} Z`;
  const bridgeSide = [
    `M${brX+brW},${brY}`,
    `L${brX+brW+brSX},${brY+brSY}`,
    `L${brX+brW+brSX},${brY+brH+brSY}`,
    `L${brX+brW},${brY+brH} Z`,
  ].join(' ');

  // ── CPA 경보 링 ────────────────────────────────────────────────────────────

  const ringR    = Math.max(Lpx, Wpx) * 0.60 + 4;
  const ringColor = ALERT_RING_COLOR;
  const alertRing = isAlert
    ? `<circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="${ringR.toFixed(1)}"
         fill="none" stroke="${ringColor}" stroke-width="1.8"
         style="animation:ship-ring 0.8s linear infinite;transform-origin:${cx.toFixed(1)}px ${cy.toFixed(1)}px;"/>
       <circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="${ringR.toFixed(1)}"
         fill="none" stroke="${ringColor}" stroke-width="1.1" opacity="0.5"
         style="animation:ship-ring 0.8s linear infinite 0.26s;transform-origin:${cx.toFixed(1)}px ${cy.toFixed(1)}px;"/>`
    : '';

  // ── 선택 글로우 필터 ───────────────────────────────────────────────────────

  const uid      = Math.random().toString(36).slice(2, 7);
  const glowDef  = isSelected
    ? `<filter id="gf${uid}" x="-50%" y="-50%" width="200%" height="200%">
         <feGaussianBlur stdDeviation="3" result="b"/>
         <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
       </filter>`
    : '';
  const glowAttr = isSelected ? `filter="url(#gf${uid})"` : '';

  const W_int   = Math.ceil(svgW);
  const H_int   = Math.ceil(svgH);

  const html = `<div style="position:relative;width:${W_int}px;height:${H_int}px;">
<style>@keyframes ship-ring{from{opacity:1;transform:scale(1)}to{opacity:0;transform:scale(1.5)}}</style>
<svg width="${W_int}" height="${H_int}" xmlns="http://www.w3.org/2000/svg"
  style="overflow:visible;transform:rotate(${heading}deg);transform-origin:${cx.toFixed(1)}px ${cy.toFixed(1)}px;filter:drop-shadow(1px 2px 4px rgba(0,0,0,0.7));">
<defs>
  ${glowDef}
  <linearGradient id="dl${uid}" x1="0" y1="0" x2="0.55" y2="1">
    <stop offset="0%" stop-color="rgba(255,255,255,0.22)"/>
    <stop offset="100%" stop-color="rgba(0,0,0,0.04)"/>
  </linearGradient>
</defs>
<!-- 드롭 섀도 -->
<path d="${top}" fill="rgba(0,0,0,0.28)" transform="translate(2.5,4)"/>
<!-- 선미 면 -->
<path d="${stern}" fill="${pal.stern}" stroke="rgba(0,0,0,0.3)" stroke-width="0.4"/>
<!-- 우현 면 -->
<path d="${side}"  fill="${pal.side}"  stroke="rgba(0,0,0,0.3)" stroke-width="0.4"/>
<!-- 갑판 -->
<path d="${top}" fill="${pal.top}" stroke="rgba(255,255,255,0.14)" stroke-width="0.6" ${glowAttr}/>
<!-- 조명 그라디언트 -->
<path d="${top}" fill="url(#dl${uid})"/>
<!-- 선수 줄무늬 -->
<path d="${bowStripe}" fill="${pal.bridge}" opacity="0.75"/>
<!-- 선교 우현 -->
<path d="${bridgeSide}" fill="${pal.stern}" opacity="0.85"/>
<!-- 선교 갑판 -->
<path d="${bridgeTop}" fill="${pal.bridge}" stroke="rgba(255,255,255,0.18)" stroke-width="0.5"/>
${alertRing}
</svg>
</div>`;

  return { html, width: W_int, height: H_int, anchorX: cx, anchorY: cy };
}
