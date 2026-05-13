import { PageCard } from '../components/layout/PageCard';
import { useRegistryPreview } from '../hooks/useRegistryPreview';
import { eventsFallback } from '../data';
import type { EventItem } from '../types';

export function EventLogPage() {
  const events = useRegistryPreview<EventItem[]>('/events', eventsFallback);
  const eventList = Array.isArray(events.data) ? events.data : eventsFallback;

  return (
    <div className="grid gap-5 xl:grid-cols-2">
      <PageCard title="Event Log">
        <div className="grid gap-3">
          {eventList.map((event) => (
            <div key={`${event.type}-${event.at}`} className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-white/10 bg-white/5 p-4">
              <span className="rounded-full px-3 py-1 text-sm bg-white/10">{event.type}</span>
              <strong>{event.title}</strong>
              <span className="text-sm text-[#8da8b5]">{event.at}</span>
            </div>
          ))}
        </div>
      </PageCard>

      <PageCard title="Event Contract">
        <ul className="list-disc space-y-2 pl-5 text-[#8da8b5]">
          <li>SYS_AGENT_CONNECTION_CREATED and SYS_AGENT_CONNECTION_DELETED are also tracked.</li>
          <li>Legacy task result names are normalized on ingest.</li>
        </ul>
      </PageCard>
    </div>
  );
}

