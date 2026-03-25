/**
 * SVG isometric pseudo-3D ship icon for Leaflet DivIcon.
 *
 * Three visible faces of the box:
 *   TOP  – main deck (brightest)
 *   SIDE – starboard hull (medium)
 *   STERN – aft face (darkest)
 *
 * The whole SVG rotates by vessel.heading around the hull centre so the
 * arrow always points toward the bow regardless of heading.
 */
import L from 'leaflet';
import type { Vessel, VesselType } from '../types';

// ── Colour palettes ─────────────────────────────────────────────────────────

type Pal = { top: string; side: string; stern: string; bridge: string };

const PALETTE: Record<VesselType, Pal> = {
  Cargo:     { top: '#1e6db5', side: '#134e87', stern: '#0c3460', bridge: '#3090e8' },
  Tanker:    { top: '#b91c1c', side: '#7f1414', stern: '#540d0d', bridge: '#e04040' },
  Passenger: { top: '#0d7a5e', side: '#085544', stern: '#053d30', bridge: '#16b888' },
  Tug:       { top: '#b45309', side: '#7c3a06', stern: '#521f02', bridge: '#e07c10' },
  Research:  { top: '#6d28d9', side: '#4c1d95', stern: '#321570', bridge: '#8b5cf6' },
};

const SEL_PAL: Pal = { top: '#c17c10', side: '#7a4e08', stern: '#4e2e02', bridge: '#f5a623' };

// ── Helpers ──────────────────────────────────────────────────────────────────

function clamp(v: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, v));
}

// ── Icon factory ─────────────────────────────────────────────────────────────

/**
 * metersPerPixel at a given zoom level and latitude.
 * Web Mercator formula: 40075016.686 * cos(lat) / 2^(zoom+8)
 */
export function calcMetersPerPixel(lat: number, zoom: number): number {
  return (40075016.686 * Math.abs(Math.cos((lat * Math.PI) / 180))) / Math.pow(2, zoom + 8);
}

export function createShipIcon(
  vessel: Vessel,
  selected: boolean,
  mpp: number,
  alertLevel: 'warning' | 'danger' | null = null,
): L.DivIcon {
  const pal = selected ? SEL_PAL : PALETTE[vessel.vesselType];

  // Convert real vessel dimensions to pixels using current map scale.
  // Floor at MIN_L so the icon stays clickable/visible at low zoom levels.
  const MIN_L = 10;
  const rawL  = vessel.length / mpp;
  const rawW  = vessel.beam   / mpp;
  // If the ship is below minimum, scale both dimensions up proportionally.
  const upscale = rawL < MIN_L ? MIN_L / rawL : 1;
  const Lpx = rawL * upscale;
  const Wpx = Math.max(3, rawW * upscale);
  const H   = Math.max(2, Wpx * 0.32);             // 3-D extrusion depth

  // Isometric offset (30 ° angle → cos30=0.866, sin30=0.5)
  const ISO_X = H * 0.866;
  const ISO_Y = H * 0.5;

  const PAD  = 3;
  const svgW = Wpx + ISO_X + PAD * 2;
  const svgH = Lpx + ISO_Y + PAD * 2;

  // Box origin (top-left of top face)
  const bx = PAD;
  const by = PAD;
  const cx = bx + Wpx / 2;  // hull centre-x  (rotation pivot x)
  const cy = by + Lpx / 2;  // hull centre-y  (rotation pivot y)

  // ── Face paths ────────────────────────────────────────────────────────────

  // TOP face  (deck)
  const top =
    `M${bx},${by} L${bx+Wpx},${by} L${bx+Wpx},${by+Lpx} L${bx},${by+Lpx} Z`;

  // STARBOARD side face  (right)
  const side = [
    `M${bx+Wpx},${by}`,
    `L${bx+Wpx+ISO_X},${by+ISO_Y}`,
    `L${bx+Wpx+ISO_X},${by+Lpx+ISO_Y}`,
    `L${bx+Wpx},${by+Lpx} Z`,
  ].join(' ');

  // STERN face  (back)
  const stern = [
    `M${bx},${by+Lpx}`,
    `L${bx+Wpx},${by+Lpx}`,
    `L${bx+Wpx+ISO_X},${by+Lpx+ISO_Y}`,
    `L${bx+ISO_X},${by+Lpx+ISO_Y} Z`,
  ].join(' ');

  // ── Bow stripe (contrasting colour at bow tip) ────────────────────────────
  const bowH = Lpx * 0.09;
  const bowStripe =
    `M${bx},${by} L${bx+Wpx},${by} L${bx+Wpx},${by+bowH} L${bx},${by+bowH} Z`;

  // ── Bridge / superstructure ───────────────────────────────────────────────
  const brX  = bx + Wpx * 0.14;
  const brY  = by + Lpx * 0.33;
  const brW  = Wpx * 0.72;
  const brH  = Lpx * 0.20;
  const brSH = H * 0.60;        // bridge extrusion height
  const brSX = brSH * 0.866;
  const brSY = brSH * 0.5;

  const bridgeTop  =
    `M${brX},${brY} L${brX+brW},${brY} L${brX+brW},${brY+brH} L${brX},${brY+brH} Z`;
  const bridgeSide = [
    `M${brX+brW},${brY}`,
    `L${brX+brW+brSX},${brY+brSY}`,
    `L${brX+brW+brSX},${brY+brH+brSY}`,
    `L${brX+brW},${brY+brH} Z`,
  ].join(' ');

  // ── CPA alert ring ────────────────────────────────────────────────────────
  const ringR = Math.max(Lpx, Wpx) * 0.58 + 4;
  const ringColor = alertLevel === 'danger' ? '#ff3535' : '#ff9900';
  const ringSpeed = alertLevel === 'danger' ? '0.75s' : '1.3s';
  const alertRing = alertLevel
    ? `<circle cx="${cx}" cy="${cy}" r="${ringR.toFixed(1)}"
         fill="none" stroke="${ringColor}" stroke-width="1.8"
         class="cpa-ring" style="animation-duration:${ringSpeed};transform-origin:${cx.toFixed(1)}px ${cy.toFixed(1)}px;"/>
       <circle cx="${cx}" cy="${cy}" r="${ringR.toFixed(1)}"
         fill="none" stroke="${ringColor}" stroke-width="1.2" opacity="0.55"
         class="cpa-ring" style="animation-duration:${ringSpeed};animation-delay:${alertLevel === 'danger' ? '0.25s' : '0.45s'};transform-origin:${cx.toFixed(1)}px ${cy.toFixed(1)}px;"/>`
    : '';

  // ── Hazardous cargo indicator ─────────────────────────────────────────────
  const hazard = vessel.hazardousCargo
    ? `<circle cx="${cx}" cy="${by+Lpx*0.84}" r="${clamp(Wpx*0.15,2.2,4.5)}"
         fill="#ff6b35" stroke="rgba(255,255,255,0.9)" stroke-width="0.8"/>`
    : '';

  // ── Glow filter (selected) ────────────────────────────────────────────────
  const uid = vessel.mmsi.slice(-5);
  const glowDef = selected
    ? `<filter id="gf${uid}" x="-40%" y="-40%" width="180%" height="180%">
         <feGaussianBlur stdDeviation="2.8" result="b"/>
         <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
       </filter>`
    : '';
  const glowAttr = selected ? `filter="url(#gf${uid})"` : '';

  // ── Assemble SVG ──────────────────────────────────────────────────────────
  const W = Math.ceil(svgW);
  const H_svg = Math.ceil(svgH);

  const html = `<svg width="${W}" height="${H_svg}" xmlns="http://www.w3.org/2000/svg"
  style="overflow:visible;transform:rotate(${vessel.heading}deg);transform-origin:${cx}px ${cy}px;filter:drop-shadow(1px 2px 4px rgba(0,0,0,0.65));">
<defs>
  ${glowDef}
  <linearGradient id="dl${uid}" x1="0" y1="0" x2="0.55" y2="1">
    <stop offset="0%" stop-color="rgba(255,255,255,0.22)"/>
    <stop offset="100%" stop-color="rgba(0,0,0,0.05)"/>
  </linearGradient>
</defs>

<!-- drop shadow -->
<path d="${top}" fill="rgba(0,0,0,0.25)" transform="translate(2.5,4)"/>

<!-- stern face (darkest) -->
<path d="${stern}" fill="${pal.stern}" stroke="rgba(0,0,0,0.3)" stroke-width="0.4"/>

<!-- starboard face (medium) -->
<path d="${side}"  fill="${pal.side}"  stroke="rgba(0,0,0,0.3)" stroke-width="0.4"/>

<!-- top face / deck -->
<path d="${top}" fill="${pal.top}" stroke="rgba(255,255,255,0.14)" stroke-width="0.6" ${glowAttr}/>

<!-- lighting gradient on deck -->
<path d="${top}" fill="url(#dl${uid})"/>

<!-- bow stripe -->
<path d="${bowStripe}" fill="${pal.bridge}" opacity="0.75"/>

<!-- bridge side -->
<path d="${bridgeSide}" fill="${pal.stern}" opacity="0.85"/>

<!-- bridge top -->
<path d="${bridgeTop}" fill="${pal.bridge}" stroke="rgba(255,255,255,0.18)" stroke-width="0.5"/>

${alertRing}
${hazard}
</svg>`;

  return L.divIcon({
    className: '',
    html,
    iconSize:   [W, H_svg],
    iconAnchor: [cx, cy],
  });
}
