import { create } from "zustand";

export interface ToastItem {
  id: string;
  severity: "critical" | "warning" | "info";
  agentName: string;
  alertType: string;
  message: string;
  platformIds: string[];
}

interface ToastStore {
  toasts: ToastItem[];
  push: (t: Omit<ToastItem, "id">) => void;
  dismiss: (id: string) => void;
}

let _seq = 0;

export const useToastStore = create<ToastStore>((set) => ({
  toasts: [],
  push: (t) =>
    set((s) => ({
      toasts: [{ ...t, id: String(++_seq) }, ...s.toasts].slice(0, 5),
    })),
  dismiss: (id) =>
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));
