import { create } from "zustand";

export interface ActivityLogEntry {
  id: string;
  timestamp: string;
  agent_id: string;
  agent_name: string;
  agent_type: "rule" | "ai";
  alert_type: string;
  severity: string;
  message: string;          // 경보 메시지 (rule 에이전트 포함)
  recommendation: string | null;  // AI 권고 (AI 에이전트만)
  platform_ids: string[];
  model: string | null;     // AI 모델명 (AI만)
  metadata: Record<string, unknown>; // 원시 메타데이터 (cpa_nm, tcpa_min 등)
}

// 하위 호환 alias
export type AILogEntry = ActivityLogEntry;

const AI_AGENT_IDS = new Set(["anomaly-ai", "distress-agent", "report-agent"]);

interface AILogStore {
  logs: ActivityLogEntry[];
  addLog: (entry: ActivityLogEntry) => void;
  updateLog: (entry: ActivityLogEntry) => void;
  clear: () => void;
}

export const useAILogStore = create<AILogStore>((set) => ({
  logs: [],
  addLog: (entry) =>
    set((state) => ({
      logs: [entry, ...state.logs].slice(0, 200),
    })),
  updateLog: (entry) =>
    set((state) => {
      const idx = state.logs.findIndex((l) => l.id === entry.id);
      if (idx === -1) return { logs: [entry, ...state.logs].slice(0, 200) };
      const updated = [...state.logs];
      updated[idx] = { ...updated[idx], ...entry };
      return { logs: updated };
    }),
  clear: () => set({ logs: [] }),
}));

export function isAIAgent(agentId: string): boolean {
  return AI_AGENT_IDS.has(agentId);
}
