import { useRegistryPreview } from './useRegistryPreview';
import { missionsFallback, proposalsFallback } from '../data';
import type { Mission, Proposal } from '../types';

export function useMission() {
  const missions = useRegistryPreview<Mission[]>('/missions', missionsFallback);
  const proposals = useRegistryPreview<Proposal[]>('/mission-proposals', proposalsFallback);

  return {
    missions: Array.isArray(missions.data) ? missions.data : missionsFallback,
    proposals: Array.isArray(proposals.data) ? proposals.data : proposalsFallback,
    isLoading: missions.isLoading || proposals.isLoading,
  };
}

