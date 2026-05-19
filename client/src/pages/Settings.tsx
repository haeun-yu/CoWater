import { useEffect, useState } from 'react';
import { PageCard } from '../components/layout/PageCard';
import { fetchJson } from '../services/api';
import type { Config } from '../types';

export function SettingsPage() {
  const [configs, setConfigs] = useState<Config[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchJson<Config[]>('/configs')
      .then(setConfigs)
      .catch(() => setConfigs([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="grid gap-5 xl:grid-cols-2">
      <PageCard title="Settings">
        {loading ? (
          <p className="text-[#8da8b5]">Loading configuration...</p>
        ) : configs.length === 0 ? (
          <ul className="list-disc space-y-2 pl-5 text-[#8da8b5]">
            <li>Heartbeat interval: 1 second.</li>
            <li>Offline timeout: 10 seconds.</li>
            <li>Battery override can be allowed by operator policy.</li>
          </ul>
        ) : (
          <div className="space-y-3 max-h-96 overflow-y-auto">
            {configs.map((config) => (
              <div key={config.key} className="rounded-lg border border-white/10 bg-white/5 p-3 space-y-1">
                <strong className="text-sm block text-[#8da8b5]">{config.key}</strong>
                <p className="text-sm text-[#64748b] font-mono break-all">
                  {typeof config.value === 'object' ? JSON.stringify(config.value) : String(config.value)}
                </p>
              </div>
            ))}
          </div>
        )}
      </PageCard>
      <PageCard title="Registry">
        <p className="text-[#8da8b5] mb-3">System agent, device agent, and client all read from the same docs-defined contract.</p>
        {configs.length > 0 && (
          <div className="text-xs text-[#64748b] bg-white/5 p-3 rounded border border-white/10">
            <p><strong className="text-[#8da8b5]">Configuration Keys:</strong></p>
            <ul className="list-disc pl-5 mt-2 space-y-1">
              {configs.map(c => <li key={c.key}>{c.key}</li>)}
            </ul>
          </div>
        )}
      </PageCard>
    </div>
  );
}

