export type Health = 'ONLINE' | 'OFFLINE' | 'ERROR' | 'DEGRADED';

export type Device = {
  id: string;
  name: string;
  type: string;
  status: Health;
  battery: number;
  connection: string;
  device_agent_id?: string;
  connectivity_status?: string;
  gateway_agent_id?: string | null;
};

export type Mission = {
  id: string;
  title: string;
  status: string;
  progress: number;
};

export type EventItem = {
  type: string;
  severity: string;
  title: string;
  at: string;
};

export type Proposal = {
  proposal_id: string;
  title: string;
  status: string;
};

export type Connection = {
  connection_id: string;
  agent_a_id: string;
  agent_b_id: string;
  connection_type: string;
  deleted_at?: string | null;
};

export type Meta = {
  server?: { host?: string; port?: number };
  agent?: { agent_id?: string; name?: string; role?: string; layer?: string };
};

