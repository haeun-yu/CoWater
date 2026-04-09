"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/stores/authStore";

export default function LoginPage() {
  const router = useRouter();
  const login = useAuthStore((s) => s.login);
  const status = useAuthStore((s) => s.status);
  const role = useAuthStore((s) => s.role);
  const message = useAuthStore((s) => s.message);
  const initialize = useAuthStore((s) => s.initialize);
  const [token, setToken] = useState("");

  useEffect(() => {
    void initialize();
  }, [initialize]);

  useEffect(() => {
    if (status === "authenticated") {
      router.replace("/");
    }
  }, [router, status]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const ok = await login(token);
    if (ok) router.replace("/");
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center px-6">
      <div className="w-full max-w-md rounded-2xl border border-ocean-800 bg-slate-900/90 shadow-2xl p-6">
        <div className="mb-6">
          <p className="text-xs tracking-[0.25em] text-ocean-400 font-semibold">COWATER</p>
          <h1 className="mt-2 text-2xl font-bold text-white">권한 로그인</h1>
          <p className="mt-2 text-sm text-slate-400 leading-6">
            시스템 조회 및 명령 실행을 위해 역할 토큰으로 로그인하세요.
          </p>
        </div>

        <form className="space-y-4" onSubmit={handleSubmit}>
          <div>
            <label className="block text-xs font-semibold text-slate-400 mb-2">접근 토큰</label>
            <input
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="예: viewer-dev / operator-dev / admin-dev"
              className="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-slate-100 placeholder:text-slate-600 focus:outline-none focus:border-ocean-500"
            />
          </div>

          {message && (
            <div className={`rounded-xl border px-3 py-2 text-xs ${status === "unauthenticated" ? "border-red-800/50 bg-red-950/20 text-red-300" : "border-slate-800 bg-slate-950/50 text-slate-400"}`}>
              {message}
            </div>
          )}

          <button
            type="submit"
            disabled={!token.trim() || status === "checking"}
            className="w-full rounded-xl bg-ocean-600 hover:bg-ocean-500 disabled:bg-slate-800 disabled:text-slate-500 text-white py-3 text-sm font-semibold transition-colors"
          >
            {status === "checking" ? "확인 중..." : "로그인"}
          </button>
        </form>

        <div className="mt-6 grid grid-cols-3 gap-2 text-[11px]">
          <div className="rounded-xl border border-slate-800 bg-slate-950/50 px-3 py-2">
            <p className="text-slate-300 font-semibold">viewer</p>
            <p className="mt-1 text-slate-500">조회 전용</p>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-950/50 px-3 py-2">
            <p className="text-amber-300 font-semibold">operator</p>
            <p className="mt-1 text-slate-500">경보 처리</p>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-950/50 px-3 py-2">
            <p className="text-red-300 font-semibold">admin</p>
            <p className="mt-1 text-slate-500">에이전트 제어</p>
          </div>
        </div>

        {role && <p className="mt-4 text-xs text-green-300">현재 권한: {role}</p>}
      </div>
    </div>
  );
}
