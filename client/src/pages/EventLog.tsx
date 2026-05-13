import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { PageCard } from '../components/layout/PageCard';
import { useRegistryPreview } from '../hooks/useRegistryPreview';
import { eventsFallback } from '../data';
import { REGISTRY_URL } from '../services/api';
import type { EventItem } from '../types';

interface Alert {
  alert_id: string;
  title: string;
  severity: string;
  status: string;
  description?: string;
  created_at?: string;
}

const SEVERITY_STYLE: Record<string, string> = {
  CRITICAL: 'bg-red-600/20 text-red-400 border-red-600/30',
  ERROR:    'bg-red-500/20 text-red-300 border-red-500/30',
  WARNING:  'bg-amber-500/20 text-amber-300 border-amber-500/30',
  INFO:     'bg-blue-500/20 text-blue-300 border-blue-500/30',
};

export function EventLogPage() {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<'events' | 'alerts'>('events');
  const [severityFilter, setSeverityFilter] = useState<string | null>(null);
  const [acking, setAcking] = useState<string | null>(null);

  const events = useRegistryPreview<EventItem[]>('/events', eventsFallback, 5_000);
  const alerts = useRegistryPreview<Alert[]>('/alerts', [], 10_000);

  const eventList = Array.isArray(events.data) ? events.data : eventsFallback;
  const alertList = Array.isArray(alerts.data) ? alerts.data : [];
  const openAlerts = alertList.filter(a => a.status === 'OPEN' || a.status === 'PENDING');

  const severities = ['INFO', 'WARNING', 'ERROR', 'CRITICAL'];
  const filteredEvents = severityFilter
    ? eventList.filter(e => e.severity?.toUpperCase() === severityFilter)
    : eventList;

  const handleAck = async (alert: Alert) => {
    setAcking(alert.alert_id);
    try {
      await fetch(`${REGISTRY_URL}/alerts/${alert.alert_id}/ack`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved: true, notes: 'Acknowledged via UI' }),
      });
      queryClient.invalidateQueries({ queryKey: ['registry-preview', '/alerts'] });
    } catch (err) {
      console.error('Ack failed:', err);
    } finally {
      setAcking(null);
    }
  };

  return (
    <div className="grid gap-5 xl:grid-cols-2">
      <PageCard title="Event Log">
        {/* Tabs */}
        <div className="flex gap-0 mb-4 border-b border-white/10">
          {([
            { id: 'events', label: 'Events', count: eventList.length },
            { id: 'alerts', label: 'Alerts', count: openAlerts.length, warn: openAlerts.length > 0 },
          ] as const).map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-4 py-2 text-sm border-b-2 transition -mb-px ${
                tab === t.id
                  ? 'border-blue-500 text-blue-400'
                  : 'border-transparent text-[#8da8b5] hover:text-white'
              }`}
            >
              {t.label}
              <span className={`ml-1.5 text-xs ${('warn' in t && t.warn) ? 'text-amber-400' : 'opacity-60'}`}>
                ({t.count})
              </span>
            </button>
          ))}
        </div>

        {/* Events tab */}
        {tab === 'events' && (
          <div className="space-y-3">
            <div className="flex gap-2 flex-wrap">
              <button
                onClick={() => setSeverityFilter(null)}
                className={`px-3 py-1 text-xs rounded border transition ${
                  severityFilter === null
                    ? 'bg-white/10 border-white/20 text-white'
                    : 'bg-white/5 border-white/10 text-[#8da8b5] hover:bg-white/10'
                }`}
              >
                All ({eventList.length})
              </button>
              {severities.map(sev => {
                const count = eventList.filter(e => e.severity?.toUpperCase() === sev).length;
                return (
                  <button
                    key={sev}
                    onClick={() => setSeverityFilter(sev)}
                    className={`px-3 py-1 text-xs rounded border transition ${
                      severityFilter === sev
                        ? `${SEVERITY_STYLE[sev]} border-current`
                        : 'bg-white/5 border-white/10 text-[#8da8b5] hover:bg-white/10'
                    }`}
                  >
                    {sev} ({count})
                  </button>
                );
              })}
            </div>
            <div className="space-y-2 max-h-72 overflow-y-auto">
              {filteredEvents.length === 0 ? (
                <p className="text-xs text-[#64748b] py-4">No events</p>
              ) : filteredEvents.map((event, idx) => (
                <div
                  key={event.event_id ?? `${event.type}-${idx}`}
                  className={`rounded-lg border p-3 ${SEVERITY_STYLE[event.severity?.toUpperCase()] ?? 'bg-white/5 border-white/10'}`}
                >
                  <div className="flex items-start justify-between gap-2 mb-1">
                    <strong className="text-sm">{event.title}</strong>
                    <span className="text-xs whitespace-nowrap font-semibold">{event.severity}</span>
                  </div>
                  <p className="text-xs opacity-75">{event.type}</p>
                  {event.description && <p className="text-xs opacity-60 mt-1">{event.description}</p>}
                  <p className="text-xs opacity-50 mt-2">
                    {event.created_at ? new Date(event.created_at).toLocaleTimeString() : event.at}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Alerts tab */}
        {tab === 'alerts' && (
          <div className="space-y-2 max-h-80 overflow-y-auto">
            {alertList.length === 0 ? (
              <p className="text-sm text-[#8da8b5]">No alerts</p>
            ) : alertList.map(alert => (
              <div
                key={alert.alert_id}
                className={`rounded-lg border p-3 space-y-2 ${
                  alert.status === 'OPEN'
                    ? (SEVERITY_STYLE[alert.severity?.toUpperCase()] ?? 'bg-white/5 border-white/10')
                    : 'bg-white/3 border-white/5 opacity-50'
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <strong className="text-sm block">{alert.title}</strong>
                    <span className="text-xs opacity-75">{alert.severity} · {alert.status}</span>
                  </div>
                  {(alert.status === 'OPEN' || alert.status === 'PENDING') && (
                    <button
                      onClick={() => handleAck(alert)}
                      disabled={acking === alert.alert_id}
                      className="px-2 py-1 text-xs bg-white/10 text-white rounded hover:bg-white/20 disabled:opacity-50 whitespace-nowrap"
                    >
                      {acking === alert.alert_id ? '...' : 'Ack'}
                    </button>
                  )}
                </div>
                {alert.description && <p className="text-xs opacity-60">{alert.description}</p>}
                {alert.created_at && (
                  <p className="text-xs opacity-50">{new Date(alert.created_at).toLocaleTimeString()}</p>
                )}
              </div>
            ))}
          </div>
        )}
      </PageCard>

      <PageCard title="Event Contract">
        <ul className="list-disc space-y-2 pl-5 text-[#8da8b5] text-sm">
          <li>Events are immutable records; alerts have lifecycle (OPEN → ACK → CLOSED).</li>
          <li>SYS_AGENT_CONNECTION_CREATED and SYS_AGENT_CONNECTION_DELETED are tracked.</li>
          <li>Legacy task result names are normalized on ingest.</li>
          <li>Events auto-refresh every 5s; alerts every 10s.</li>
          <li>Click <strong>Ack</strong> on an alert to acknowledge it.</li>
        </ul>
      </PageCard>
    </div>
  );
}
