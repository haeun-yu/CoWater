import type { Connection, Device, EventItem, Mission, Proposal } from './types';

export const devicesFallback: Device[] = [
  { id: 'usv-01', name: 'USV Alpha', type: 'USV', status: 'ONLINE', battery: 82, connection: 'RF', device_agent_id: 'agent-usv-01' },
  { id: 'auv-01', name: 'AUV Echo', type: 'AUV', status: 'DEGRADED', battery: 29, connection: 'ACOUSTIC', device_agent_id: 'agent-auv-01' },
  { id: 'rov-01', name: 'ROV Delta', type: 'ROV', status: 'OFFLINE', battery: 11, connection: 'WIRED', device_agent_id: 'agent-rov-01' },
];

export const missionsFallback: Mission[] = [
  { id: 'mission-001', title: 'A 구역 탐색', status: 'IN_PROGRESS', progress: 64 },
  { id: 'mission-002', title: '복귀 준비', status: 'READY', progress: 0 },
];

export const eventsFallback: EventItem[] = [
  { type: 'SYS_INTENT_CLASSIFIED', severity: 'INFO', title: '사용자 요청 분류 완료', at: '2026-05-13 10:12' },
  { type: 'SYS_TASK_DISPATCHED', severity: 'INFO', title: 'Task 전달 완료', at: '2026-05-13 10:15' },
  { type: 'SYS_ANOMALY_DETECTED', severity: 'WARNING', title: '배터리 경고 30%', at: '2026-05-13 10:16' },
];

export const proposalsFallback: Proposal[] = [
  { proposal_id: 'proposal-001', title: '해역 정찰', status: 'PROPOSED' },
  { proposal_id: 'proposal-002', title: '귀환 및 재정비', status: 'APPROVED' },
];

export const connectionsFallback: Connection[] = [
  { connection_id: 'conn-001', agent_a_id: 'agent-usv-01', agent_b_id: 'agent-auv-01', connection_type: 'RELAY' },
  { connection_id: 'conn-002', agent_a_id: 'agent-usv-01', agent_b_id: 'agent-rov-01', connection_type: 'DIRECT', deleted_at: '2026-05-13T09:00:00Z' },
];

