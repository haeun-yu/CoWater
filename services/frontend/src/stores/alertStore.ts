import { create } from "zustand";
import type { Alert } from "@/types";

interface AlertStore {
  alerts: Alert[];
  unreadCount: number;

  addAlert: (alert: Alert) => void;
  acknowledge: (alertId: string) => void;
  resolve: (alertId: string) => void;
  setAll: (alerts: Alert[]) => void;
}

export const useAlertStore = create<AlertStore>((set) => ({
  alerts: [],
  unreadCount: 0,

  addAlert: (alert) =>
    set((state) => ({
      alerts: [alert, ...state.alerts].slice(0, 200), // 최대 200개
      unreadCount: state.unreadCount + (alert.status === "new" ? 1 : 0),
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
