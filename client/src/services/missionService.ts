import { fetchJson } from './api';
import type { Mission, Proposal } from '../types';

export function listMissions() {
  return fetchJson<Mission[]>('/missions');
}

export function listProposals() {
  return fetchJson<Proposal[]>('/mission-proposals');
}

