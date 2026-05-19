import { useState, useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { PageCard } from '../components/layout/PageCard';
import { useRegistryPreview } from '../hooks/useRegistryPreview';
import { proposalsFallback } from '../data';
import { SYSTEM_AGENT_URL, postJson, fetchJson } from '../services/api';
import type { Proposal } from '../types';

interface Approval {
  approval_id: string;
  target_id: string;
  target_type: string;
  status: string;
  summary: string;
  metadata?: Record<string, unknown>;
}

export function ProposalPage() {
  const queryClient = useQueryClient();
  const [selectedProposalId, setSelectedProposalId] = useState<string | null>(null);
  const [processing, setProcessing] = useState<string | null>(null);
  const [approvals, setApprovals] = useState<Record<string, Approval>>({});

  const proposals = useRegistryPreview<Proposal[]>('/mission-proposals', proposalsFallback);
  const proposalList = Array.isArray(proposals.data) ? proposals.data : proposalsFallback;

  // Fetch approvals to map to proposals
  useEffect(() => {
    fetchJson<Approval[]>('/approvals')
      .then(data => {
        const map: Record<string, Approval> = {};
        (Array.isArray(data) ? data : []).forEach(a => {
          if (a.target_type === 'mission_proposal') {
            map[a.target_id] = a;
          }
        });
        setApprovals(map);
      })
      .catch(err => console.error('Failed to fetch approvals:', err));
  }, []);

  const selectedProposal = proposalList.find(p => p.proposal_id === selectedProposalId) || proposalList[0] || null;
  const selectedApproval = selectedProposal ? approvals[selectedProposal.proposal_id] : null;

  const handleApproveReject = async (approved: boolean) => {
    if (!selectedApproval?.approval_id) return;
    setProcessing(selectedApproval.approval_id);
    try {
      await postJson(`${SYSTEM_AGENT_URL}/approvals/${selectedApproval.approval_id}/decision`, {
        approved,
        decided_by: 'operator',
        notes: approved ? 'Approved via UI' : 'Rejected via UI',
      });
      queryClient.invalidateQueries({ queryKey: ['registry-preview', '/mission-proposals'] });
      setApprovals(prev => ({
        ...prev,
        [selectedProposal!.proposal_id]: {
          ...selectedApproval,
          status: approved ? 'APPROVED' : 'REJECTED'
        }
      }));
      setSelectedProposalId(null);
    } catch (err) {
      console.error('Approval failed:', err);
    } finally {
      setProcessing(null);
    }
  };

  return (
    <div className="grid gap-5 xl:grid-cols-2">
      <PageCard title="Proposals">
        <div className="space-y-2 max-h-96 overflow-y-auto">
          {proposalList.length === 0 ? (
            <p className="text-sm text-[#8da8b5]">No proposals</p>
          ) : (
            proposalList.map((proposal) => (
              <button
                key={proposal.proposal_id}
                onClick={() => setSelectedProposalId(proposal.proposal_id)}
                className={`w-full text-left rounded-xl border p-3 transition ${
                  selectedProposalId === proposal.proposal_id
                    ? 'border-white/30 bg-white/10'
                    : 'border-white/10 bg-white/5 hover:bg-white/8'
                }`}
              >
                <strong className="block text-sm">{proposal.title}</strong>
                <span className={`text-xs mt-1 inline-block px-2 py-0.5 rounded ${
                  proposal.status === 'PROPOSED' ? 'bg-yellow-400/20 text-yellow-300' :
                  proposal.status === 'APPROVED' ? 'bg-green-400/20 text-green-300' :
                  'bg-gray-400/20 text-gray-300'
                }`}>
                  {proposal.status}
                </span>
              </button>
            ))
          )}
        </div>
      </PageCard>

      <PageCard title="Proposal Details">
        {selectedProposal ? (
          <div className="space-y-4">
            <div className="space-y-3 border-b border-white/10 pb-4">
              <div>
                <p className="text-xs text-[#64748b] mb-1">Title</p>
                <strong className="text-lg block">{selectedProposal.title}</strong>
              </div>

              {selectedProposal.goal && (
                <div>
                  <p className="text-xs text-[#64748b] mb-1">Goal</p>
                  <p className="text-sm text-[#8da8b5]">{selectedProposal.goal}</p>
                </div>
              )}

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <p className="text-xs text-[#64748b] mb-1">Status</p>
                  <span className={`text-sm font-semibold inline-block px-2 py-1 rounded ${
                    selectedProposal.status === 'PROPOSED' ? 'bg-yellow-400/20 text-yellow-300' :
                    selectedProposal.status === 'APPROVED' ? 'bg-green-400/20 text-green-300' :
                    'bg-gray-400/20 text-gray-300'
                  }`}>
                    {selectedProposal.status}
                  </span>
                </div>
                {selectedProposal.mission_type && (
                  <div>
                    <p className="text-xs text-[#64748b] mb-1">Mission Type</p>
                    <p className="text-sm text-[#8da8b5]">{selectedProposal.mission_type}</p>
                  </div>
                )}
              </div>

              {selectedProposal.created_at && (
                <div>
                  <p className="text-xs text-[#64748b] mb-1">Created</p>
                  <p className="text-xs text-[#8da8b5]">
                    {new Date(selectedProposal.created_at).toLocaleString()}
                  </p>
                </div>
              )}

              <div>
                <p className="text-xs text-[#64748b] mb-1">Proposal ID</p>
                <p className="text-xs font-mono text-[#64748b] break-all">{selectedProposal.proposal_id}</p>
              </div>

              {selectedProposal.approval_id && (
                <div>
                  <p className="text-xs text-[#64748b] mb-1">Approval ID</p>
                  <p className="text-xs font-mono text-[#64748b] break-all">{selectedProposal.approval_id}</p>
                </div>
              )}
            </div>

            {selectedApproval && selectedApproval.status === 'PENDING' && (
              <div className="flex gap-2">
                <button
                  onClick={() => handleApproveReject(true)}
                  disabled={processing === selectedApproval.approval_id}
                  className="flex-1 px-4 py-2 bg-green-600 text-white text-sm rounded hover:bg-green-700 disabled:opacity-50 font-semibold"
                >
                  {processing === selectedApproval.approval_id ? 'Processing...' : '✓ Approve'}
                </button>
                <button
                  onClick={() => handleApproveReject(false)}
                  disabled={processing === selectedApproval.approval_id}
                  className="flex-1 px-4 py-2 bg-red-600 text-white text-sm rounded hover:bg-red-700 disabled:opacity-50 font-semibold"
                >
                  {processing === selectedApproval.approval_id ? 'Processing...' : '✕ Reject'}
                </button>
              </div>
            )}

            {selectedApproval && selectedApproval.status !== 'PENDING' && (
              <div className={`rounded-lg p-3 border ${
                selectedApproval.status === 'APPROVED'
                  ? 'bg-green-500/10 border-green-500/20'
                  : 'bg-red-500/10 border-red-500/20'
              }`}>
                <p className={`text-sm ${
                  selectedApproval.status === 'APPROVED'
                    ? 'text-green-300'
                    : 'text-red-300'
                }`}>
                  {selectedApproval.status === 'APPROVED'
                    ? '✓ This proposal has been approved and mission created.'
                    : '✕ This proposal has been rejected.'}
                </p>
              </div>
            )}

            {!selectedApproval && (
              <div className="rounded-lg bg-yellow-500/10 border border-yellow-500/20 p-3">
                <p className="text-sm text-yellow-300">⚠ No approval found for this proposal</p>
              </div>
            )}
          </div>
        ) : (
          <p className="text-sm text-[#8da8b5]">Select a proposal to view details</p>
        )}
      </PageCard>
    </div>
  );
}

