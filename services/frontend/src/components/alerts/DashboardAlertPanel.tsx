"use client";

import { useMemo, useState } from "react";
import { getCoreApiUrl } from "@/lib/publicUrl";
import { useAlertStore } from "@/stores/alertStore";
import { useAuthStore } from "@/stores/authStore";
import { usePlatformStore } from "@/stores/platformStore";
import { useSystemStore } from "@/stores/systemStore";
import { useToastStore } from "@/stores/toastStore";
import type { Alert, AlertSeverity, CommandRole } from "@/types";
import { formatDistanceToNow } from "date-fns";
import { ko } from "date-fns/locale";
import Link from "next/link";
import { PlatformButton } from "./AlertButton";

const SEVERITY_LABEL: Record<AlertSeverity, string> = {
  critical: "위험",
  warning: "주의",
  info: "정보",
};

const SEVERITY_DOT: Record<AlertSeverity, string> = {
  critical: "bg-red-400",
  warning: "bg-yellow-400",
  info: "bg-blue-400",
};

const SEVERITY_TEXT: Record<AlertSeverity, string> = {
  critical: "text-red-400",
  warning: "text-yellow-400",
  info: "text-blue-400",
};

const ALERT_TYPE_KR: Record<string, string> = {
  cpa: "충돌 위험",
  zone_intrusion: "구역 침입",
  zone_exit: "구역 이탈",
  anomaly: "이상 행동",
  ais_off: "AIS 소실",
  ais_recovered: "AIS 복구",
  distress: "조난",
  compliance: "상황 보고",
  traffic: "교통 혼잡",
};

const ROLE_ORDER: Record<CommandRole, number> = { viewer: 0, operator: 1, admin: 2 };

export default function DashboardAlertPanel() {
  const alerts = useAlertStore((s) => s.alerts);
  const updateAlert = useAlertStore((s) => s.updateAlert);
  const token = useAuthStore((s) => s.token);
  const role = useAuthStore((s) => s.role);
  const platforms = usePlatformStore((s) => s.platforms);
  const select = usePlatformStore((s) => s.select);
  const alertStream = useSystemStore((s) => s.streams.alert);
  const alertLoad = useSystemStore((s) => s.initialData.alerts);
  const toastPush = useToastStore((s) => s.push);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [filter, setFilter] = useState<AlertSeverity | "all">("all");
  const [pendingAlertId, setPendingAlertId] = useState<string | null>(null);
  const canOperate = !!token && !!role && ROLE_ORDER[role] >= ROLE_ORDER.operator;

  const newAlerts = useMemo(() => alerts.filter((a) => a.status === "new"), [alerts]);
  const critical = newAlerts.filter((a) => a.severity === "critical").length;
  const warning = newAlerts.filter((a) => a.severity === "warning").length;
  const info = newAlerts.filter((a) => a.severity === "info").length;

  // 대시보드: 미확인만, 최신 30건
  const displayed = useMemo(
    () =>
      (filter === "all" ? newAlerts : newAlerts.filter((alert) => alert.severity === filter))
        .sort((a, b) => {
          const severityRank = { critical: 0, warning: 1, info: 2 };
          return severityRank[a.severity] - severityRank[b.severity]
            || new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
        })
        .slice(0, 30),
    [filter, newAlerts],
  );

  const topCritical = displayed.find((alert) => alert.severity === "critical");

  async function acknowledge(alertId: string) {
    if (!token || !role || ROLE_ORDER[role] < ROLE_ORDER.operator) return;
    setPendingAlertId(alertId);
    try {
      const res = await fetch(`${getCoreApiUrl()}/alerts/${alertId}/action`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ action: "acknowledge" }),
      });
      if (!res.ok) {
        throw new Error(`acknowledge failed: ${res.status}`);
      }
      const updated = (await res.json()) as Alert;
      updateAlert(updated);
    } catch (error) {
      console.error("[alerts] acknowledge failed", error);
      toastPush({
        severity: "warning",
        agentName: "시스템",
        alertType: "경보 처리",
        message: "경보 인지 처리에 실패했습니다. 잠시 후 다시 시도해주세요.",
        platformIds: [],
      });
    } finally {
      setPendingAlertId((current) => (current === alertId ? null : current));
    }
  }

  function getPlatformName(id: string) {
    const p = platforms[id];
    if (!p) return id.replace(/^MMSI-/, "");
    return p.name && p.name !== p.platform_id
      ? p.name
      : id.replace(/^MMSI-/, "");
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex-shrink-0 border-b border-ocean-800/80 px-4 py-4">
        <div className="mb-2 flex items-start justify-between gap-3">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.28em] text-ocean-400">조치 패널</div>
            <span className="mt-1 block text-sm font-semibold text-ocean-100">실시간 경보</span>
            <div className="mt-1 text-xs text-ocean-500">긴급도 기준으로 우선 정렬하고, 세부 판단은 펼쳐서 확인합니다.</div>
          </div>
          <Link
            href="/alerts"
            className="rounded-full border border-ocean-700 px-2.5 py-1 text-[11px] text-ocean-400 transition-colors hover:border-ocean-500 hover:text-ocean-200"
          >
            전체 보기
          </Link>
        </div>
        <div className="mb-3 text-[11px] text-ocean-500">
          경보 스트림: {alertStream.status === "connected" ? "정상" : alertStream.status === "reconnecting" ? "재연결 중" : alertStream.status === "error" ? "오류" : "연결 중"}
        </div>
        <div className="grid grid-cols-3 gap-2 text-[11px]">
          <AlertCountCard label="위험" value={critical} tone="critical" />
          <AlertCountCard label="주의" value={warning} tone="warning" />
          <AlertCountCard label="정보" value={info} tone="info" />
        </div>

        {topCritical ? (
          <div className="mt-3 rounded-2xl border border-red-500/30 bg-red-500/10 p-3">
            <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-red-200">우선 확인</div>
            <div className="mt-1 text-sm font-medium text-red-100 line-clamp-2">{topCritical.message}</div>
            <div className="mt-1 text-[11px] text-red-200/80">{ALERT_TYPE_KR[topCritical.alert_type] ?? topCritical.alert_type}</div>
          </div>
        ) : (
          <div className="mt-3 rounded-2xl border border-emerald-400/25 bg-emerald-400/10 px-3 py-2 text-xs text-emerald-200">
            현재 즉시 대응이 필요한 긴급 경보는 없습니다.
          </div>
        )}

        {newAlerts.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {(["all", "critical", "warning", "info"] as const).map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setFilter(value)}
                className={`rounded-full border px-3 py-1 text-[11px] transition-colors ${filter === value ? "border-ocean-500 bg-ocean-700 text-ocean-100" : "border-ocean-700/80 bg-ocean-900/55 text-ocean-400 hover:border-ocean-500 hover:text-ocean-200"}`}
              >
                {value === "all" ? "전체" : SEVERITY_LABEL[value]}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto">
        {displayed.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 gap-2 text-ocean-400">
            <span className="text-lg">✓</span>
            <span className="text-xs">
              {alertLoad.status === "loading"
                ? "경보 로딩 중..."
                : alertLoad.status === "error"
                  ? "경보 로드 실패"
                  : "미확인 경보 없음"}
            </span>
          </div>
        ) : (
          displayed.map((alert) => {
            const isExpanded = expanded === alert.alert_id;
            return (
              <div
                key={alert.alert_id}
                className="border-b border-ocean-900/80"
              >
                <button
                  className="w-full px-4 py-3 text-left transition-colors hover:bg-ocean-800/30"
                  onClick={() =>
                    setExpanded(isExpanded ? null : alert.alert_id)
                  }
                  aria-expanded={isExpanded}
                  aria-controls={`dashboard-alert-${alert.alert_id}`}
                >
                  <div className="flex items-start gap-2">
                    <span className={`mt-1.5 h-2 w-2 rounded-full flex-shrink-0 ${SEVERITY_DOT[alert.severity]} ${alert.severity === "critical" ? "animate-pulse" : ""}`} />
                    <div className="flex-1 min-w-0">
                      <div className="mb-1 flex items-center gap-1.5">
                        <span
                          className={`text-xs font-bold ${SEVERITY_TEXT[alert.severity]}`}
                        >
                          {SEVERITY_LABEL[alert.severity]}
                        </span>
                        <span className="text-xs text-ocean-400">
                          {ALERT_TYPE_KR[alert.alert_type] ?? alert.alert_type}
                        </span>
                      </div>
                      <div className="text-sm text-ocean-200 leading-snug line-clamp-2">
                        {alert.message}
                      </div>
                      <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-ocean-400">
                        <span>{alert.platform_ids.length}개 대상</span>
                        <span>·</span>
                        {formatDistanceToNow(new Date(alert.created_at), {
                          addSuffix: true,
                          locale: ko,
                        })}
                      </div>
                    </div>
                  </div>
                </button>

                {isExpanded && (
                  <div id={`dashboard-alert-${alert.alert_id}`} className="space-y-3 px-4 pb-4">
                    <div className="space-y-1">
                      <div className="text-[10px] font-semibold text-ocean-500 uppercase tracking-wider">
                        경보 내용
                      </div>
                      <div className="rounded-xl border border-ocean-800/80 bg-ocean-900/50 p-3 text-xs leading-relaxed text-ocean-200">
                        {alert.message}
                      </div>
                    </div>

                    {alert.platform_ids.length > 0 && (
                      <div className="space-y-1">
                        <div className="text-[10px] font-semibold text-ocean-500 uppercase tracking-wider">
                          영향 대상
                        </div>
                        <div className="flex gap-1.5 flex-wrap">
                          {alert.platform_ids.map((id) => (
                            <PlatformButton
                              key={id}
                              onClick={() => select(id)}
                              title="클릭하여 지도에서 선박 선택"
                            >
                              {getPlatformName(id)}
                            </PlatformButton>
                          ))}
                        </div>
                      </div>
                    )}

                    {alert.recommendation && (
                      <div className="space-y-1">
                        <div className="text-[10px] font-semibold text-ocean-500 uppercase tracking-wider flex items-center gap-1">
                          분석 및 제안
                          {Boolean(
                            (alert.metadata as Record<string, unknown> | null)
                              ?.llm_fallback,
                          ) && (
                            <span className="text-amber-300 text-[9px] font-normal">(LLM 폴백)</span>
                          )}
                        </div>
                        <div className="rounded-xl border border-cyan-700/40 bg-ocean-900/55 p-3 text-xs leading-relaxed text-ocean-300">
                          {alert.recommendation}
                        </div>
                      </div>
                    )}

                    {canOperate && (
                      <button
                        onClick={() => acknowledge(alert.alert_id)}
                        disabled={pendingAlertId === alert.alert_id}
                        className="w-full rounded-xl bg-ocean-700 px-3 py-2 text-xs font-medium text-ocean-200 transition-colors hover:bg-ocean-600 disabled:bg-ocean-800 disabled:text-ocean-500"
                      >
                        {pendingAlertId === alert.alert_id ? "처리 중..." : "✓ 인지 처리"}
                      </button>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

function AlertCountCard({ label, value, tone }: { label: string; value: number; tone: AlertSeverity }) {
  const toneClass =
    tone === "critical"
      ? "border-red-400/25 bg-red-400/10 text-red-200"
      : tone === "warning"
        ? "border-amber-400/25 bg-amber-400/10 text-amber-200"
        : "border-blue-400/25 bg-blue-400/10 text-blue-200";

  return (
    <div className={`rounded-xl border px-3 py-2 ${toneClass}`}>
      <div className="text-[10px] uppercase tracking-[0.16em] opacity-80">{label}</div>
      <div className="mt-1 font-mono text-sm">{value}</div>
    </div>
  );
}
