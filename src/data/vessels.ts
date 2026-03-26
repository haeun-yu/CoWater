import type { Vessel } from '../types';

// 부산 외항 기준점 (기존 선박들이 사용하는 안전 해역):
//  - 남쪽 열린 바다 (대한해협): lat 34.60~34.95, lng 128.60~129.50
//  - 동쪽 열린 바다:           lat 35.00~35.30, lng 129.20~129.60
//  - 외항 접근수로:            lat 35.00~35.08, lng 129.05~129.20  (기존 Haejin Star 영역)

export const initialVessels: Vessel[] = [
  // ── 기존 5척 ──────────────────────────────────────────────────────────────
  {
    mmsi: '440123456',
    name: 'MV Haejin Star',
    callSign: 'D7HS2', imo: '9812345',
    vesselType: 'Cargo', length: 229, beam: 32,
    destination: 'Busan New Port', etaUtc: '2026-03-25T17:40:00Z',
    draft: 11.2, hazardousCargo: false,
    latitude: 35.0702, longitude: 129.0798,
    utcTime: '2026-03-25T08:00:00Z', positionAccuracy: 'High',
    sog: 13.8, cog: 38, heading: 40, rateOfTurn: 1.2,
    navigationStatus: 'Under way',
  },
  {
    mmsi: '440234567',
    name: 'MT Blue Current',
    callSign: 'D7BC8', imo: '9745632',
    vesselType: 'Tanker', length: 249, beam: 44,
    destination: 'Ulsan', etaUtc: '2026-03-25T18:25:00Z',
    draft: 13.4, hazardousCargo: true,
    latitude: 35.0269, longitude: 129.1351,
    utcTime: '2026-03-25T08:00:00Z', positionAccuracy: 'High',
    sog: 11.1, cog: 312, heading: 314, rateOfTurn: -2.1,
    navigationStatus: 'Under way',
  },
  {
    mmsi: '440345678',
    name: 'RV Ocean Pulse',
    callSign: 'D7OP4', imo: '9698877',
    vesselType: 'Research', length: 114, beam: 22,
    destination: 'Survey Sector C', etaUtc: '2026-03-25T19:00:00Z',
    draft: 5.1, hazardousCargo: false,
    latitude: 35.0168, longitude: 129.1507,
    utcTime: '2026-03-25T08:00:00Z', positionAccuracy: 'High',
    sog: 8.4, cog: 118, heading: 120, rateOfTurn: 3.8,
    navigationStatus: 'Restricted',
  },
  {
    mmsi: '440456789',
    name: 'SV Harbor Link',
    callSign: 'D7HL1', imo: '9654321',
    vesselType: 'Passenger', length: 87, beam: 16,
    destination: 'Geoje Terminal', etaUtc: '2026-03-25T16:55:00Z',
    draft: 3.6, hazardousCargo: false,
    latitude: 35.0450, longitude: 129.1980,
    utcTime: '2026-03-25T08:00:00Z', positionAccuracy: 'High',
    sog: 18.6, cog: 212, heading: 210, rateOfTurn: -4.6,
    navigationStatus: 'Under way',
  },
  {
    mmsi: '440567890',
    name: 'TB Guardian',
    callSign: 'D7GD9', imo: '9582104',
    vesselType: 'Tug', length: 42, beam: 12,
    destination: 'Pilot Station', etaUtc: '2026-03-25T16:15:00Z',
    draft: 2.8, hazardousCargo: false,
    latitude: 35.0180, longitude: 129.1320,
    utcTime: '2026-03-25T08:00:00Z', positionAccuracy: 'High',
    sog: 0.3, cog: 90, heading: 90, rateOfTurn: 0,
    navigationStatus: 'At anchor',
  },

  // ── 추가 15척 ─────────────────────────────────────────────────────────────

  // ── 데모 시나리오 1: 🔴 CPA DANGER — MV Korea Express ↔ MT Dark Whale 정면 충돌
  // Korea Express (COG 270°, 서향) ↔ Dark Whale (COG 90°, 동향)
  // 초기 거리 ≈ 2nm, TCPA ≈ 4.5분 → CPA_DANGER 즉시 발화
  {
    mmsi: '440600001',
    name: 'MV Korea Express',
    callSign: 'D7KE3', imo: '9801122',
    vesselType: 'Cargo', length: 185, beam: 30,
    destination: 'Busan New Port', etaUtc: '2026-03-25T19:30:00Z',
    draft: 9.8, hazardousCargo: false,
    latitude: 35.02, longitude: 129.18,
    utcTime: '2026-03-25T08:00:00Z', positionAccuracy: 'High',
    sog: 14.0, cog: 270, heading: 270, rateOfTurn: 0.0,
    navigationStatus: 'Under way',
  },

  // 부산 외항에서 남서향 출항 (중국 방면)
  {
    mmsi: '440600002',
    name: 'MV Busan Gate',
    callSign: 'D7BG5', imo: '9776543',
    vesselType: 'Cargo', length: 195, beam: 30,
    destination: 'Shanghai', etaUtc: '2026-03-26T08:00:00Z',
    draft: 10.5, hazardousCargo: false,
    latitude: 35.03, longitude: 129.08,
    utcTime: '2026-03-25T08:00:00Z', positionAccuracy: 'High',
    sog: 14.2, cog: 217, heading: 216, rateOfTurn: -0.8,
    navigationStatus: 'Under way',
  },

  // ── 데모 시나리오 2 (파트너): 🟠 CPA WARNING — MT Red Star
  // Tsushima Link와 교차 (COG 222° SW향)
  {
    mmsi: '440600003',
    name: 'MT Red Star',
    callSign: 'D7RS6', imo: '9834561',
    vesselType: 'Tanker', length: 178, beam: 32,
    destination: 'Busan Oil Terminal', etaUtc: '2026-03-25T20:10:00Z',
    draft: 12.1, hazardousCargo: false,
    latitude: 35.02, longitude: 129.14,
    utcTime: '2026-03-25T08:00:00Z', positionAccuracy: 'High',
    sog: 11.0, cog: 222, heading: 222, rateOfTurn: 0.0,
    navigationStatus: 'Under way',
  },

  // 동쪽 먼 바다에서 서향 입항
  {
    mmsi: '440600004',
    name: 'MV Pacific Dawn',
    callSign: 'D7PD2', imo: '9691234',
    vesselType: 'Cargo', length: 145, beam: 25,
    destination: 'Busan Newport', etaUtc: '2026-03-25T21:00:00Z',
    draft: 8.4, hazardousCargo: false,
    latitude: 35.08, longitude: 129.45,
    utcTime: '2026-03-25T08:00:00Z', positionAccuracy: 'High',
    sog: 11.5, cog: 260, heading: 262, rateOfTurn: -0.3,
    navigationStatus: 'Under way',
  },

  // 부산 외항에서 남서향 제주행 여객선
  {
    mmsi: '440600005',
    name: 'SV Stella Maris',
    callSign: 'D7SM7', imo: '9612233',
    vesselType: 'Passenger', length: 132, beam: 22,
    destination: 'Jeju', etaUtc: '2026-03-25T23:30:00Z',
    draft: 4.2, hazardousCargo: false,
    latitude: 35.02, longitude: 129.01,
    utcTime: '2026-03-25T08:00:00Z', positionAccuracy: 'High',
    sog: 17.5, cog: 222, heading: 220, rateOfTurn: -1.2,
    navigationStatus: 'Under way',
  },

  // 외항 접근수로 순찰 예인선
  {
    mmsi: '440600006',
    name: 'TB Iron Bull',
    callSign: 'D7IB4', imo: '9544321',
    vesselType: 'Tug', length: 35, beam: 11,
    destination: 'Busan Port', etaUtc: '2026-03-25T17:00:00Z',
    draft: 2.5, hazardousCargo: false,
    latitude: 35.00, longitude: 129.08,
    utcTime: '2026-03-25T08:00:00Z', positionAccuracy: 'High',
    sog: 7.2, cog: 85, heading: 85, rateOfTurn: 2.1,
    navigationStatus: 'Under way',
  },

  // 대한해협 동수로에서 북향 입항 대형화물
  {
    mmsi: '440600007',
    name: 'MV Hanjin Pioneer',
    callSign: 'D7HP8', imo: '9823456',
    vesselType: 'Cargo', length: 210, beam: 32,
    destination: 'Busan New Port', etaUtc: '2026-03-25T22:00:00Z',
    draft: 11.6, hazardousCargo: false,
    latitude: 34.82, longitude: 129.22,
    utcTime: '2026-03-25T08:00:00Z', positionAccuracy: 'High',
    sog: 13.0, cog: 6, heading: 6, rateOfTurn: 0.5,
    navigationStatus: 'Under way',
  },

  // ── 데모 시나리오 3: ⚠️ 위험물 항만 접근 — MT Ulsan Arrow
  // BUSAN_PORT(35.10, 129.04) 남쪽 2.3nm 출발, 북향으로 접근 → 2nm 이내 진입 시 hazard_port 이벤트
  {
    mmsi: '440600008',
    name: 'MT Ulsan Arrow',
    callSign: 'D7UA1', imo: '9756789',
    vesselType: 'Tanker', length: 230, beam: 42,
    destination: 'Busan Oil Terminal', etaUtc: '2026-03-26T02:00:00Z',
    draft: 13.8, hazardousCargo: true,
    latitude: 35.062, longitude: 129.04,
    utcTime: '2026-03-25T08:00:00Z', positionAccuracy: 'High',
    sog: 10.0, cog: 2, heading: 2, rateOfTurn: 0.0,
    navigationStatus: 'Under way',
  },

  // 외항에서 서향 거제행 여객선
  {
    mmsi: '440600009',
    name: 'SV Geoje Ferry',
    callSign: 'D7GF3', imo: '9601122',
    vesselType: 'Passenger', length: 92, beam: 18,
    destination: 'Geoje Okpo', etaUtc: '2026-03-25T17:20:00Z',
    draft: 3.2, hazardousCargo: false,
    latitude: 35.02, longitude: 129.00,
    utcTime: '2026-03-25T08:00:00Z', positionAccuracy: 'High',
    sog: 19.5, cog: 220, heading: 218, rateOfTurn: -2.5,
    navigationStatus: 'Under way',
  },

  // 대한해협 중부 서베이 루프
  {
    mmsi: '440600010',
    name: 'RV Deep Blue',
    callSign: 'D7DB9', imo: '9667890',
    vesselType: 'Research', length: 88, beam: 18,
    destination: 'Survey Zone D', etaUtc: '2026-03-26T00:00:00Z',
    draft: 4.5, hazardousCargo: false,
    latitude: 34.88, longitude: 129.20,
    utcTime: '2026-03-25T08:00:00Z', positionAccuracy: 'High',
    sog: 7.2, cog: 225, heading: 224, rateOfTurn: 1.8,
    navigationStatus: 'Restricted',
  },

  // 동쪽 먼 바다에서 서향 입항
  {
    mmsi: '440600011',
    name: 'MV Eastern Horizon',
    callSign: 'D7EH6', imo: '9789012',
    vesselType: 'Cargo', length: 170, beam: 28,
    destination: 'Busan New Port', etaUtc: '2026-03-25T23:00:00Z',
    draft: 9.2, hazardousCargo: false,
    latitude: 35.05, longitude: 129.55,
    utcTime: '2026-03-25T08:00:00Z', positionAccuracy: 'High',
    sog: 12.2, cog: 265, heading: 266, rateOfTurn: -0.4,
    navigationStatus: 'Under way',
  },

  // ── 데모 시나리오 4: ⚓ 앵커 드래그 — TB Sea Tiger
  // 정박 상태이지만 조류에 의해 북쪽으로 서서히 이탈 (50m 이상 → anchor_drag 이벤트)
  {
    mmsi: '440600012',
    name: 'TB Sea Tiger',
    callSign: 'D7ST5', imo: '9534567',
    vesselType: 'Tug', length: 38, beam: 11,
    destination: 'Busan Port', etaUtc: '2026-03-25T16:00:00Z',
    draft: 2.6, hazardousCargo: false,
    latitude: 35.020, longitude: 129.10,
    utcTime: '2026-03-25T08:00:00Z', positionAccuracy: 'High',
    sog: 1.5, cog: 0, heading: 0, rateOfTurn: 0,
    navigationStatus: 'At anchor',
  },

  // ── 데모 시나리오 1 (파트너): 🔴 CPA DANGER — MT Dark Whale
  // Korea Express와 정면 충돌 코스 (COG 90°, 동향)
  {
    mmsi: '440600013',
    name: 'MT Dark Whale',
    callSign: 'D7DW2', imo: '9812678',
    vesselType: 'Tanker', length: 188, beam: 32,
    destination: 'Ulsan', etaUtc: '2026-03-25T21:30:00Z',
    draft: 12.6, hazardousCargo: false,
    latitude: 35.02, longitude: 129.14,
    utcTime: '2026-03-25T08:00:00Z', positionAccuracy: 'High',
    sog: 12.0, cog: 90, heading: 90, rateOfTurn: 0.0,
    navigationStatus: 'Under way',
  },

  // ── 데모 시나리오 2: 🟠 CPA WARNING — SV Tsushima Link ↔ MT Red Star 교차
  // Tsushima (NE 향) ↔ Red Star (NW 향), 약 3분 후 교차 → 경보
  {
    mmsi: '440600014',
    name: 'SV Tsushima Link',
    callSign: 'D7TL8', imo: '9623456',
    vesselType: 'Passenger', length: 105, beam: 20,
    destination: 'Tsushima Izuhara', etaUtc: '2026-03-25T20:00:00Z',
    draft: 3.8, hazardousCargo: false,
    latitude: 34.97, longitude: 129.07,
    utcTime: '2026-03-25T08:00:00Z', positionAccuracy: 'High',
    sog: 20.0, cog: 48, heading: 48, rateOfTurn: 0.0,
    navigationStatus: 'Under way',
  },

  // 동쪽 외해에서 북동향 포항 연안
  {
    mmsi: '440600015',
    name: 'MV Dongbang Pioneer',
    callSign: 'D7DP7', imo: '9745678',
    vesselType: 'Cargo', length: 155, beam: 25,
    destination: 'Pohang', etaUtc: '2026-03-25T22:30:00Z',
    draft: 8.8, hazardousCargo: false,
    latitude: 35.02, longitude: 129.22,
    utcTime: '2026-03-25T08:00:00Z', positionAccuracy: 'High',
    sog: 11.8, cog: 32, heading: 32, rateOfTurn: 0.3,
    navigationStatus: 'Under way',
  },
];
