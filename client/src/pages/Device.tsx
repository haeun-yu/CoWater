import { PageCard } from '../components/layout/PageCard';
import { useRegistryPreview } from '../hooks/useRegistryPreview';
import { devicesFallback } from '../data';
import { useParams, useSearchParams } from 'react-router-dom';
import type { Device } from '../types';

export function DevicePage() {
  const params = useParams();
  const [searchParams] = useSearchParams();
  const deviceId = searchParams.get('id') || params.deviceId;
  const devices = useRegistryPreview<Device[]>('/devices', devicesFallback);
  const deviceList = Array.isArray(devices.data) ? devices.data : devicesFallback;

  return (
    <div className="grid gap-5 xl:grid-cols-2">
      <PageCard title="Device">
        {deviceId ? <p className="mb-3 rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-[#8da8b5]">Selected device: {deviceId}</p> : null}
        <div className="grid gap-3">
          {deviceList.map((device) => (
            <article key={device.id} className="rounded-2xl border border-white/10 bg-white/5 p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <strong className="block">{device.name}</strong>
                  <p className="text-sm text-[#8da8b5]">{device.device_agent_id ?? 'unassigned'}</p>
                </div>
                <span className="rounded-full px-3 py-1 text-sm bg-white/10">{device.status}</span>
              </div>
            </article>
          ))}
        </div>
      </PageCard>

      <PageCard title="Thresholds">
        <ul className="list-disc space-y-2 pl-5 text-[#8da8b5]">
          <li>Battery warning at 30% and auto-return at 10%.</li>
          <li>Offline is declared after 10 seconds without heartbeat.</li>
          <li>gateway_agent_id points to an agent id, not a device endpoint.</li>
        </ul>
      </PageCard>
    </div>
  );
}
