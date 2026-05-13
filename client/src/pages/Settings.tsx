import { PageCard } from '../components/layout/PageCard';

export function SettingsPage() {
  return (
    <div className="grid gap-5 xl:grid-cols-2">
      <PageCard title="Settings">
        <ul className="list-disc space-y-2 pl-5 text-[#8da8b5]">
          <li>Heartbeat interval: 1 second.</li>
          <li>Offline timeout: 10 seconds.</li>
          <li>Battery override can be allowed by operator policy.</li>
        </ul>
      </PageCard>
      <PageCard title="Registry">
        <p className="text-[#8da8b5]">System agent, device agent, and client all read from the same docs-defined contract.</p>
      </PageCard>
    </div>
  );
}

