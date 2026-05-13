export type Health = 'ONLINE' | 'OFFLINE' | 'ERROR' | 'DEGRADED';

export type Device = {
  id: string;
  name: string;
  type: string;
  status: Health;
  battery: number;
  battery_percent?: number | null;
  connection: string;
  device_agent_id?: string;
  connectivity_status?: string;
  gateway_agent_id?: string | null;
  parent_id?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  is_submerged?: boolean;
};

export type Mission = {
  id?: string;
  mission_id?: string;
  title: string;
  status: string;
  progress?: number;
  priority?: string;
  source_proposal_id?: string;
  source_event_id?: string;
  target_area?: string;
  created_by?: { type: string; id: string };
  created_at?: string;
  updated_at?: string;
  tasks?: Task[];
};

export type Task = {
  task_id: string;
  type: string;
  status: 'PENDING' | 'IN_PROGRESS' | 'COMPLETED' | 'FAILED';
  device_id?: string;
  created_at?: string;
  updated_at?: string;
};

export type EventItem = {
  event_id?: string;
  type: string;
  severity: string;
  title: string;
  at?: string;
  description?: string;
  target_type?: string;
  target_id?: string;
  created_at?: string;
};

export type Proposal = {
  proposal_id: string;
  id?: string;
  title: string;
  goal?: string;
  status: string;
  mission_type?: string;
  approval_id?: string;
  requires_approval?: boolean;
  created_at?: string;
};

export type Policy = {
  policy_id: string;
  policy_name: string;
  name?: string;
  description: string;
  enabled: boolean;
  trigger_condition?: Record<string, unknown>;
  action?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
};

export type Config = {
  key: string;
  value: unknown;
};

export type Rule = {
  rule_id: string;
  name: string;
  description?: string;
  condition?: Record<string, unknown>;
  action?: Record<string, unknown>;
  enabled: boolean;
  created_at?: string;
  updated_at?: string;
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

