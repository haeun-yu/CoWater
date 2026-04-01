import { create } from "zustand";
import type { Alert } from "@/types";

interface AlertStore {
  alerts: Alert[];
  unreadCount: number;

  addAlert: (alert: Alert) => void;
  updateAlert: (alert: Partial<Alert> & { alert_id: string }) => void;
  acknowledge: (alertId: string) => void;
  resolve: (alertId: string) => void;
  setAll: (alerts: Alert[]) => void;
}

export const useAlertStore = create<AlertStore>((set) => ({
  alerts: [],
  unreadCount: 0,

  addAlert: (alert) =>
    set((state) => ({
      alerts: [alert, ...state.alerts].slice(0, 200),
      unreadCount: state.unreadCount + (alert.status === "new" ? 1 : 0),
    })),

  updateAlert: (update) =>
    set((state) => ({
      alerts: state.alerts.map((a) =>
        a.alert_id === update.alert_id ? { ...a, ...update } : a
      ),
    })),

  acknowledge: (alertId) =>
    set((state) => ({
      alerts: state.alerts.map((a) =>
        a.alert_id === alertId
          ? { ...a, status: "acknowledged", acknowledged_at: new Date().toISOString() }
          : a
      ),
    })),

  resolve: (alertId) =>
    set((state) => ({
      alerts: state.alerts.map((a) =>
        a.alert_id === alertId
          ? { ...a, status: "resolved", resolved_at: new Date().toISOString() }
          : a
      ),
    })),

  setAll: (alerts) =>
    set({
      alerts,
      unreadCount: alerts.filter((a) => a.status === "new").length,
    }),
}));
