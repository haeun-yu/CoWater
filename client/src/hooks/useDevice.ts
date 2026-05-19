import { useRegistryPreview } from './useRegistryPreview';
import { connectionsFallback, devicesFallback } from '../data';
import type { Connection, Device } from '../types';

export function useDevice() {
  const devices = useRegistryPreview<Device[]>('/devices', devicesFallback);
  const connections = useRegistryPreview<Connection[]>('/agent-connections', connectionsFallback);

  return {
    devices: Array.isArray(devices.data) ? devices.data : devicesFallback,
    connections: Array.isArray(connections.data) ? connections.data : connectionsFallback,
    isLoading: devices.isLoading || connections.isLoading,
  };
}

