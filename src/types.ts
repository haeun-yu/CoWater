export type NavigationStatus = 'Under way' | 'At anchor' | 'Moored' | 'Restricted';

export type VesselType = 'Cargo' | 'Tanker' | 'Passenger' | 'Tug' | 'Research';

export interface VesselStaticData {
  mmsi: string;
  name: string;
  callSign: string;
  imo: string;
  vesselType: VesselType;
  length: number;
  beam: number;
  destination: string;
  etaUtc: string;
  draft: number;
  hazardousCargo: boolean;
}

export interface VesselDynamicData {
  latitude: number;
  longitude: number;
  utcTime: string;
  positionAccuracy: 'High' | 'Low';
  sog: number;
  cog: number;
  heading: number;
  rateOfTurn: number;
  navigationStatus: NavigationStatus;
}

export interface Vessel extends VesselStaticData, VesselDynamicData {}

export interface AisNmeaFrame {
  sentence: string;
  kind: 'position' | 'voyage';
  mmsi: string;
}
