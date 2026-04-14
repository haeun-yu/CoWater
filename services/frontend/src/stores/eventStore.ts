import { create } from "zustand";

export interface EventRecord {
  id: string;
  channel: string;
  type: string;
  timestamp: number;
  flow_id: string;
  event_id: string;
  agent_id: string;
  payload: Record<string, unknown>;
  causation_id?: string;
}

interface EventStore {
  events: EventRecord[];
  addEvent: (event: EventRecord) => void;
  clearEvents: () => void;
  getEventsByFlowId: (flowId: string) => EventRecord[];
  getEventsByType: (type: string) => EventRecord[];
}

export const useEventStore = create<EventStore>((set, get) => ({
  events: [],

  addEvent: (event: EventRecord) => {
    set((state) => {
      // Keep only last 1000 events in memory
      const events = [event, ...state.events].slice(0, 1000);
      return { events };
    });
  },

  clearEvents: () => set({ events: [] }),

  getEventsByFlowId: (flowId: string) => {
    return get().events.filter((e) => e.flow_id === flowId);
  },

  getEventsByType: (type: string) => {
    return get().events.filter((e) => e.type === type);
  },
}));
