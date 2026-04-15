import { create } from "zustand";
import { getCoreApiUrl } from "@/lib/publicUrl";
import type { CommandRole } from "@/types";

const STORAGE_KEY = "cowater-session-token";

type AuthStatus = "checking" | "authenticated" | "unauthenticated";

interface AuthStore {
  token: string | null;
  actor: string | null;
  role: CommandRole | null;
  status: AuthStatus;
  initialized: boolean;
  message: string | null;
  initialize: () => Promise<void>;
  login: (token: string) => Promise<boolean>;
  logout: () => void;
}

async function fetchMe(token: string) {
  const res = await fetch(`${getCoreApiUrl()}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as { authenticated: boolean; actor: string; role: CommandRole };
}

export const useAuthStore = create<AuthStore>((set, get) => ({
  token: null,
  actor: null,
  role: null,
  status: "checking",
  initialized: false,
  message: null,

  initialize: async () => {
    if (get().initialized) return;
    if (typeof window === "undefined") return;

    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (!stored) {
      set({ status: "unauthenticated", initialized: true, message: "로그인이 필요합니다." });
      return;
    }

    try {
      const me = await fetchMe(stored);
      set({
        token: stored,
        actor: me.actor,
        role: me.role,
        status: "authenticated",
        initialized: true,
        message: null,
      });
    } catch {
      window.localStorage.removeItem(STORAGE_KEY);
      set({
        token: null,
        actor: null,
        role: null,
        status: "unauthenticated",
        initialized: true,
        message: "세션이 없거나 만료되었습니다. 다시 로그인하세요.",
      });
    }
  },

  login: async (tokenInput: string) => {
    const rawToken = tokenInput.trim();
    set({ status: "checking", message: null });
    try {
      const res = await fetch(`${getCoreApiUrl()}/auth/login`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${rawToken}`,
        },
        body: JSON.stringify({ token: rawToken }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const payload = (await res.json()) as {
        access_token: string;
        actor: string;
        role: CommandRole;
      };
      if (typeof window !== "undefined") {
        window.localStorage.setItem(STORAGE_KEY, payload.access_token);
      }
      set({
        token: payload.access_token,
        actor: payload.actor,
        role: payload.role,
        status: "authenticated",
        initialized: true,
        message: null,
      });
      return true;
    } catch {
      set({
        token: null,
        actor: null,
        role: null,
        status: "unauthenticated",
        initialized: true,
        message: "토큰이 유효하지 않거나 권한 확인에 실패했습니다.",
      });
      return false;
    }
  },

  logout: () => {
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(STORAGE_KEY);
    }
    set({
      token: null,
      actor: null,
      role: null,
      status: "unauthenticated",
      initialized: true,
      message: "로그아웃되었습니다.",
    });
  },
}));
