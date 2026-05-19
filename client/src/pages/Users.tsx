import { PageCard } from '../components/layout/PageCard';

export function UsersPage() {
  return (
    <div className="grid gap-5 xl:grid-cols-2">
      <PageCard title="Users">
        <ul className="list-disc space-y-2 pl-5 text-[#8da8b5]">
          <li>ADMIN can change system settings.</li>
          <li>OPERATOR reviews proposals and missions.</li>
          <li>VIEWER observes dashboards and event logs.</li>
        </ul>
      </PageCard>
      <PageCard title="Access">
        <p className="text-[#8da8b5]">Authorization belongs in the system contract, not just the UI.</p>
      </PageCard>
    </div>
  );
}

