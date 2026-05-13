import { PageCard } from '../components/layout/PageCard';
import { useRegistryPreview } from '../hooks/useRegistryPreview';
import { proposalsFallback } from '../data';
import type { Proposal } from '../types';

export function ProposalPage() {
  const proposals = useRegistryPreview<Proposal[]>('/mission-proposals', proposalsFallback);
  const proposalList = Array.isArray(proposals.data) ? proposals.data : proposalsFallback;

  return (
    <div className="grid gap-5 xl:grid-cols-2">
      <PageCard title="Proposal">
        <div className="grid gap-3">
          {proposalList.map((proposal) => (
            <article key={proposal.proposal_id} className="rounded-2xl border border-white/10 bg-white/5 p-4">
              <strong className="block">{proposal.title}</strong>
              <span className="text-sm text-[#8da8b5]">{proposal.status}</span>
            </article>
          ))}
        </div>
      </PageCard>

      <PageCard title="Approval Flow">
        <ul className="list-disc space-y-2 pl-5 text-[#8da8b5]">
          <li>Proposal statuses follow docs/core/schema.md.</li>
          <li>Replanning is captured as a mission event, not a proposal state.</li>
        </ul>
      </PageCard>
    </div>
  );
}

