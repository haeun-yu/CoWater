import { create } from "zustand";
import type { AgentInfo, AgentLevel } from "@/types";

interface AgentStore {
  agents: AgentInfo[];
  setAll: (agents: AgentInfo[]) => void;
  setEnabled: (agentId: string, enabled: boolean) => void;
  setLevel: (agentId: string, level: AgentLevel) => void;
}

export const useAgentStore = create<AgentStore>((set) => ({
  agents: [],

  setAll: (agents) => set({ agents }),

  setEnabled: (agentId, enabled) =>
    set((state) => ({
      agents: state.agents.map((a) =>
        a.agent_id === agentId ? { ...a, enabled } : a
      ),
    })),

  setLevel: (agentId, level) =>
    set((state) => ({
      agents: state.agents.map((a) =>
        a.agent_id === agentId ? { ...a, level } : a
      ),
    })),
}));
