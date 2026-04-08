import { create } from "zustand";
import type { Alert } from "@/types";

const countUnread = (alerts: Alert[]) => alerts.filter((alert) => alert.status === "new").length;

interface AlertStore {
  alerts: Alert[];
  unreadCount: number;

  addAlert: (alert: Alert) => void;
  updateAlert: (alert: Partial<Alert> & { alert_id: string }) => void;
  acknowledge: (alertId: string) => void;
  resolve: (alertId: string) => void;
  setAll: (alerts: Alert[]) => void;
  removeAlerts: (alertIds: string[]) => void;
}

export const useAlertStore = create<AlertStore>((set) => ({
  alerts: [],
  unreadCount: 0,

  addAlert: (alert) =>
    set((state) => {
      const alerts = [alert, ...state.alerts.filter((a) => a.alert_id !== alert.alert_id)].slice(0, 200);
      return {
        alerts,
        unreadCount: countUnread(alerts),
      };
    }),

  updateAlert: (update) =>
    set((state) => {
      const alerts = state.alerts.map((a) =>
        a.alert_id === update.alert_id ? { ...a, ...update } : a
      );
      return { alerts, unreadCount: countUnread(alerts) };
    }),

  acknowledge: (alertId) =>
    set((state) => {
      const alerts = state.alerts.map((a) =>
        a.alert_id === alertId
          ? { ...a, status: "acknowledged", acknowledged_at: new Date().toISOString() }
          : a
      );
      return { alerts, unreadCount: countUnread(alerts) };
    }),

  resolve: (alertId) =>
    set((state) => {
      const alerts = state.alerts.map((a) =>
        a.alert_id === alertId
          ? { ...a, status: "resolved", resolved_at: new Date().toISOString() }
          : a
      );
      return { alerts, unreadCount: countUnread(alerts) };
    }),

  setAll: (alerts) =>
    set({
      alerts,
      unreadCount: alerts.filter((a) => a.status === "new").length,
    }),

  removeAlerts: (alertIds) =>
    set((state) => {
      const ids = new Set(alertIds);
      const next = state.alerts.filter((a) => !ids.has(a.alert_id));
      return { alerts: next, unreadCount: countUnread(next) };
    }),
}));
