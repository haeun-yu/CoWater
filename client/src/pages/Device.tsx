import { useState } from 'react';
import { PageCard } from '../components/layout/PageCard';
import { useDevice } from '../hooks/useDevice';
import { useMothStream } from '../hooks/useMothStream';
import type { Device } from '../types';

type TabType = 'devices' | 'agents' | 'connections';

export function DevicePage() {
  const [activeTab, setActiveTab] = useState<TabType>('devices');
  const [selectedDeviceId, setSelectedDeviceId] = useState<string | null>(null);
  const { devices } = useDevice();
  const { streamMap, connected } = useMothStream();

  // Only real operational devices (exclude System Agents with type OTHER/SYSTEM)
  const operationalDevices = devices.filter(
    d => d.type && !['SYSTEM', 'OTHER'].includes(d.type.toUpperCase())
  );

  // Agents tab: all devices that have an agent assigned
  const agentDevices = devices.filter(d => d.device_agent_id);

  // Connections tab: build parent-child hierarchy from parent_id
  const childDevices = devices.filter(d => d.parent_id);

  const selectedDevice = selectedDeviceId
    ? operationalDevices.find(d => d.id === selectedDeviceId)
    : null;

  // Merge registry data with real-time Moth stream
  const getStreamData = (device: Device) => {
    // Try matching by numeric device registry_id stored as string in stream
    const byId = streamMap.get(String(device.id));
    return byId || null;
  };

  const getBatteryValue = (device: Device) => {
    const stream = getStreamData(device);
    return stream?.battery_percent ?? device.battery_percent ?? device.battery ?? null;
  };

  const getStatusValue = (device: Device) => {
    const stream = getStreamData(device);
    return stream?.status ?? device.status ?? 'UNKNOWN';
  };

  const getBatteryColor = (battery: number | null) => {
    if (battery === null) return '#6b7280';
    if (battery > 50) return '#10b981';
    if (battery > 20) return '#f59e0b';
    return '#ef4444';
  };

  const getStatusBadge = (status: string) => {
    switch (status?.toUpperCase()) {
      case 'ONLINE':  return 'text-green-400 bg-green-400/10 border-green-400/20';
      case 'OFFLINE': return 'text-red-400 bg-red-400/10 border-red-400/20';
      case 'DEGRADED': return 'text-amber-400 bg-amber-400/10 border-amber-400/20';
      default: return 'text-gray-400 bg-gray-400/10 border-gray-400/20';
    }
  };

  const tabs: { id: TabType; label: string; count: number }[] = [
    { id: 'devices', label: 'Devices', count: operationalDevices.length },
    { id: 'agents', label: 'Agents', count: agentDevices.length },
    { id: 'connections', label: 'Connections', count: childDevices.length },
  ];

  return (
    <div className="grid gap-5 xl:grid-cols-2">
      <PageCard title="Device Management">
        {/* Moth connection indicator */}
        <div className="flex items-center gap-2 mb-3 text-xs">
          <span className={`h-2 w-2 rounded-full ${connected ? 'bg-green-400' : 'bg-gray-500'}`} />
          <span className="text-[#64748b]">
            Moth stream: {connected ? 'connected' : 'connecting...'}
          </span>
        </div>

        {/* Tabs */}
        <div className="flex gap-0 mb-4 border-b border-white/10">
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2 text-sm border-b-2 transition -mb-px ${
                activeTab === tab.id
                  ? 'border-blue-500 text-blue-400'
                  : 'border-transparent text-[#8da8b5] hover:text-white'
              }`}
            >
              {tab.label}
              <span className="ml-1.5 text-xs opacity-60">({tab.count})</span>
            </button>
          ))}
        </div>

        <div className="space-y-2 max-h-[420px] overflow-y-auto pr-1">
          {/* ── Devices Tab ── */}
          {activeTab === 'devices' && (
            operationalDevices.length === 0
              ? <p className="text-sm text-[#8da8b5]">No operational devices</p>
              : operationalDevices.map(device => {
                  const battery = getBatteryValue(device);
                  const status = getStatusValue(device);
                  return (
                    <button
                      key={device.id}
                      onClick={() => setSelectedDeviceId(device.id)}
                      className={`w-full text-left rounded-lg border p-3 transition ${
                        selectedDeviceId === device.id
                          ? 'border-blue-500/40 bg-blue-500/10'
                          : 'border-white/10 bg-white/5 hover:bg-white/8'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <div>
                          <strong className="text-sm block">{device.name}</strong>
                          <span className="text-xs text-[#8da8b5]">{device.type}</span>
                        </div>
                        <span className={`text-xs px-2 py-0.5 rounded border ${getStatusBadge(status)}`}>
                          {status}
                        </span>
                      </div>
                      {battery !== null && (
                        <div className="flex items-center gap-2 text-xs">
                          <span className="text-[#8da8b5] w-14">Battery</span>
                          <div className="flex-1 h-1.5 rounded-full bg-white/10 overflow-hidden">
                            <div
                              className="h-full rounded-full"
                              style={{ width: `${battery}%`, backgroundColor: getBatteryColor(battery) }}
                            />
                          </div>
                          <span style={{ color: getBatteryColor(battery) }}>{battery.toFixed(0)}%</span>
                        </div>
                      )}
                    </button>
                  );
                })
          )}

          {/* ── Agents Tab ── */}
          {activeTab === 'agents' && (
            agentDevices.length === 0
              ? <p className="text-sm text-[#8da8b5]">No agents assigned</p>
              : agentDevices.map(device => (
                <div key={device.id} className="rounded-lg border border-white/10 bg-white/5 p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <strong className="text-sm">{device.name}</strong>
                    <span className="text-xs text-[#8da8b5]">{device.type}</span>
                  </div>
                  <div className="space-y-1">
                    <p className="text-xs text-[#64748b]">Agent ID</p>
                    <p className="text-xs font-mono text-[#8da8b5] break-all">{device.device_agent_id}</p>
                  </div>
                  {device.gateway_agent_id && (
                    <div className="space-y-1 border-t border-white/10 pt-2">
                      <p className="text-xs text-[#64748b]">Gateway Agent</p>
                      <p className="text-xs font-mono text-[#8da8b5] break-all">{device.gateway_agent_id}</p>
                    </div>
                  )}
                </div>
              ))
          )}

          {/* ── Connections Tab ── */}
          {activeTab === 'connections' && (
            childDevices.length === 0
              ? (
                <div className="text-sm text-[#8da8b5] space-y-2">
                  <p>No parent-child connections yet.</p>
                  <p className="text-xs text-[#64748b]">
                    Connections are established when a Device Agent registers with a parent (e.g., ROV tethered to USV). Start a device agent with a parent configured to see connections here.
                  </p>
                </div>
              )
              : childDevices.map(child => {
                  const parent = devices.find(d => d.id === child.parent_id);
                  return (
                    <div key={child.id} className="rounded-lg border border-white/10 bg-white/5 p-3">
                      <div className="flex items-center gap-3">
                        <div className="flex-1 min-w-0">
                          <p className="text-xs text-[#64748b] mb-1">Parent</p>
                          <p className="text-sm font-semibold truncate">{parent?.name ?? child.parent_id}</p>
                          <p className="text-xs text-[#64748b]">{parent?.type}</p>
                        </div>
                        <div className="text-[#8da8b5] flex-shrink-0">→</div>
                        <div className="flex-1 min-w-0">
                          <p className="text-xs text-[#64748b] mb-1">Child</p>
                          <p className="text-sm font-semibold truncate">{child.name}</p>
                          <p className="text-xs text-[#64748b]">{child.type}</p>
                        </div>
                      </div>
                      {child.is_submerged && (
                        <div className="mt-2 text-xs text-blue-300 flex items-center gap-1">
                          <span>🌊</span> Submerged
                        </div>
                      )}
                    </div>
                  );
                })
          )}
        </div>
      </PageCard>

      {/* ── Details Panel ── */}
      <PageCard title="Device Details">
        {selectedDevice ? (
          <div className="space-y-4">
            {/* Static Info */}
            <div className="space-y-3 border-b border-white/10 pb-4">
              <div>
                <p className="text-xs text-[#64748b] mb-1">Name</p>
                <strong className="text-lg block">{selectedDevice.name}</strong>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <p className="text-xs text-[#64748b] mb-1">Type</p>
                  <p className="text-sm text-[#8da8b5]">{selectedDevice.type}</p>
                </div>
                <div>
                  <p className="text-xs text-[#64748b] mb-1">Status</p>
                  <span className={`text-sm px-2 py-0.5 rounded border inline-block ${getStatusBadge(getStatusValue(selectedDevice))}`}>
                    {getStatusValue(selectedDevice)}
                  </span>
                </div>
              </div>
              {selectedDevice.device_agent_id && (
                <div>
                  <p className="text-xs text-[#64748b] mb-1">Agent ID</p>
                  <p className="text-xs font-mono text-[#8da8b5] break-all">{selectedDevice.device_agent_id}</p>
                </div>
              )}
              <div>
                <p className="text-xs text-[#64748b] mb-1">Device ID</p>
                <p className="text-xs font-mono text-[#64748b] break-all">{selectedDevice.id}</p>
              </div>
            </div>

            {/* Real-time Stream Data */}
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <p className="text-sm font-semibold text-[#8da8b5]">Live Stream</p>
                <span className={`h-2 w-2 rounded-full ${connected ? 'bg-green-400 animate-pulse' : 'bg-gray-500'}`} />
              </div>
              {(() => {
                const stream = getStreamData(selectedDevice);
                const battery = getBatteryValue(selectedDevice);
                return (
                  <div className="rounded-lg border border-white/10 bg-white/5 p-3 space-y-3">
                    {/* Battery */}
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <p className="text-xs text-[#64748b]">Battery</p>
                        <span
                          className="text-sm font-semibold"
                          style={{ color: getBatteryColor(battery) }}
                        >
                          {battery !== null ? `${battery.toFixed(1)}%` : 'N/A'}
                        </span>
                      </div>
                      <div className="h-3 rounded-full bg-white/10 overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all duration-500"
                          style={{
                            width: battery !== null ? `${battery}%` : '0%',
                            backgroundColor: getBatteryColor(battery),
                          }}
                        />
                      </div>
                    </div>

                    {/* Location */}
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div>
                        <p className="text-[#64748b] mb-0.5">Latitude</p>
                        <p className="text-[#8da8b5] font-mono">
                          {stream?.latitude != null ? stream.latitude.toFixed(5) : (selectedDevice.latitude?.toFixed(5) ?? 'N/A')}
                        </p>
                      </div>
                      <div>
                        <p className="text-[#64748b] mb-0.5">Longitude</p>
                        <p className="text-[#8da8b5] font-mono">
                          {stream?.longitude != null ? stream.longitude.toFixed(5) : (selectedDevice.longitude?.toFixed(5) ?? 'N/A')}
                        </p>
                      </div>
                    </div>

                    {/* Depth / Submersion */}
                    {selectedDevice.is_submerged !== undefined && (
                      <div className="flex items-center justify-between text-xs border-t border-white/10 pt-2">
                        <p className="text-[#64748b]">State</p>
                        <span className={selectedDevice.is_submerged ? 'text-blue-300' : 'text-green-300'}>
                          {selectedDevice.is_submerged ? '🌊 Submerged' : '🌤 Surface'}
                        </span>
                      </div>
                    )}

                    {/* Last update */}
                    {stream && (
                      <p className="text-xs text-[#64748b] border-t border-white/10 pt-2">
                        Last update: {new Date(stream.last_updated).toLocaleTimeString()}
                      </p>
                    )}
                    {!stream && (
                      <p className="text-xs text-[#64748b]">
                        Waiting for live data from Moth stream...
                      </p>
                    )}
                  </div>
                );
              })()}
            </div>
          </div>
        ) : (
          <div className="space-y-3 text-sm text-[#8da8b5]">
            <p>Select a device from the Devices tab to view details and live stream data.</p>
            <div className="rounded-lg border border-white/10 bg-white/5 p-3 space-y-2">
              <p className="text-xs font-semibold text-[#8da8b5]">Battery thresholds</p>
              <ul className="text-xs text-[#64748b] space-y-1 list-disc pl-4">
                <li>{'> 50%'} — Normal (green)</li>
                <li>20–50% — Warning (amber)</li>
                <li>{'< 20%'} — Critical (red), auto-return at {'< 10%'}</li>
                <li>Offline declared after 10s without heartbeat</li>
              </ul>
            </div>
          </div>
        )}
      </PageCard>
    </div>
  );
}
