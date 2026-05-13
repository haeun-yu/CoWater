import { PageCard } from '../components/layout/PageCard';
import { StatCard } from '../components/layout/StatCard';

export function AnalyticsPage() {
  return (
    <div className="grid gap-5 xl:grid-cols-2">
      <PageCard title="Analytics">
        <ul className="list-disc space-y-2 pl-5 text-[#8da8b5]">
          <li>Task success rate, mission completion, and anomaly trends live here.</li>
          <li>Insight reports are read from the registry and surfaced in the dashboard.</li>
        </ul>
      </PageCard>
      <PageCard title="Operational Health">
        <div className="grid gap-3 sm:grid-cols-2">
          <StatCard label="Heartbeat SLA" value="1s / 10s" hint="send / offline" />
          <StatCard label="Battery warning" value="30%" hint="soft warning" />
          <StatCard label="Auto-return" value="10%" hint="mission safe mode" />
          <StatCard label="Mission flow" value="Proposal → Mission" hint="docs-aligned" />
        </div>
      </PageCard>
    </div>
  );
}

