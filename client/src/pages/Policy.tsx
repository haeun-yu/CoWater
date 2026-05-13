import { PageCard } from '../components/layout/PageCard';

export function PolicyPage() {
  return (
    <div className="grid gap-5 xl:grid-cols-2">
      <PageCard title="Policy">
        <ul className="list-disc space-y-2 pl-5 text-[#8da8b5]">
          <li>Critical battery policy uses 10% as the auto-return trigger.</li>
          <li>30% remains a warning threshold only.</li>
        </ul>
      </PageCard>
      <PageCard title="Automation">
        <p className="text-[#8da8b5]">SystemSentinel and MissionPlanner collaborate through events, not direct shared state.</p>
      </PageCard>
    </div>
  );
}

