import { fetchJson } from './api';
import type { Connection, Device } from '../types';

export function listDevices() {
  return fetchJson<Device[]>('/devices');
}

export function listConnections() {
  return fetchJson<Connection[]>('/agent-connections');
}

