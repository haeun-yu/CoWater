"use client";

import { useState } from "react";
import { getCoreApiUrl } from "@/lib/publicUrl";
import { useAlertStore } from "@/stores/alertStore";
import { useAuthStore } from "@/stores/authStore";
import { usePlatformStore } from "@/stores/platformStore";
import type { Alert, AlertSeverity, CommandRole } from "@/types";
import { formatDistanceToNow } from "date-fns";
import { ko } from "date-fns/locale";
import { AlertButton, PlatformButton } from "./AlertButton";
import { AlertBadge } from "./AlertBadge";

const SEVERITY_LABEL: Record<AlertSeverity, string> = {
  critical: "위험",
  warning: "주의",
  info: "정보",
};

const ROLE_ORDER: Record<CommandRole, number> = { viewer: 0, operator: 1, admin: 2 };

export default function AlertPanel({ compact }: { compact?: boolean }) {
  const alerts = useAlertStore((s) => s.alerts);
  const updateAlert = useAlertStore((s) => s.updateAlert);
  const token = useAuthStore((s) => s.token);
  const role = useAuthStore((s) => s.role);
  const [filter, setFilter] = useState<AlertSeverity | "all">("all");
  const [expanded, setExpanded] = useState<string | null>(null);
  const select = usePlatformStore((s) => s.select);
  const canOperate = !!token && !!role && ROLE_ORDER[role] >= ROLE_ORDER.operator;

  const newCount = alerts.filter((a) => a.status === "new").length;
  const criticalCount = alerts.filter(
    (a) => a.severity === "critical" && a.status === "new",
  ).length;

  // In compact mode, show only new alerts, prioritize critical
  const filtered = alerts
    .filter((a) => filter === "all" || a.severity === filter)
    .filter((a) => !compact || a.status === "new");

  async function acknowledge(alertId: string) {
    if (!token || !role || ROLE_ORDER[role] < ROLE_ORDER.operator) return;
    const res = await fetch(`${getCoreApiUrl()}/alerts/${alertId}/action`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ action: "acknowledge" }),
    });
    if (!res.ok) return;
    const updated = (await res.json()) as Alert;
    updateAlert(updated);
  }

  async function runAction(alertId: string, action: string) {
    if (!token || !role || ROLE_ORDER[role] < ROLE_ORDER.operator) return;
    const res = await fetch(`${getCoreApiUrl()}/alerts/${alertId}/action`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ action }),
    });
    if (!res.ok) return;
    const updated = (await res.json()) as Alert;
    updateAlert(updated);
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* 헤더 */}
      <div className="px-3 py-2 border-b border-ocean-800 flex-shrink-0">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-bold text-ocean-200 tracking-wider">
            경보 현황
          </span>
          <div className="flex gap-2 text-xs">
            <span className="text-ocean-500">{newCount} 신규</span>
            {criticalCount > 0 && (
              <span className="text-red-400 font-bold animate-pulse">
                {criticalCount} 위험
              </span>
            )}
          </div>
        </div>
        {/* 필터 탭 */}
        <div className="flex gap-1">
          {(["all", "critical", "warning", "info"] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`text-xs px-2 py-0.5 rounded transition-colors ${
                filter === f
                  ? f === "all"
                    ? "bg-ocean-700 text-ocean-100"
                    : `bg-severity-${f} text-white border`
                  : "text-ocean-500 hover:text-ocean-300"
              }`}
            >
              {f === "all" ? "전체" : SEVERITY_LABEL[f]}
            </button>
          ))}
        </div>
      </div>

      {/* 경보 목록 */}
      <div className="flex-1 overflow-y-auto">
        {filtered.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-ocean-400 text-xs">
            경보 없음
          </div>
        ) : (
          filtered.map((alert) => (
            <AlertRow
              key={alert.alert_id}
              alert={alert}
              expanded={expanded === alert.alert_id}
              onToggle={() =>
                setExpanded(expanded === alert.alert_id ? null : alert.alert_id)
              }
              onAck={() => acknowledge(alert.alert_id)}
              onAction={(action) => runAction(alert.alert_id, action)}
              onSelectPlatform={(id) => select(id)}
              canOperate={canOperate}
            />
          ))
        )}
      </div>
    </div>
  );
}

function AlertRow({
  alert,
  expanded,
  onToggle,
  onAck,
  onAction,
  onSelectPlatform,
  canOperate,
}: {
  alert: Alert;
  expanded: boolean;
  onToggle: () => void;
  onAck: () => void;
  onAction: (action: string) => void;
  onSelectPlatform: (id: string) => void;
  canOperate: boolean;
}) {
  const isNew = alert.status === "new";
  const isResolved = alert.status === "resolved";
  const source = String((alert.metadata as Record<string, unknown> | null)?.source ?? "agent-runtime");
  const workflowState = getWorkflowState(alert);
  const actionHistory = getActionHistory(alert);

  return (
    <div
      className={`border-b border-ocean-900 ${isNew ? `bg-severity-${alert.severity}` : "opacity-60"}`}
    >
      {/* 요약 행 */}
      <div
        className="px-3 py-2 cursor-pointer flex items-start gap-2"
        onClick={onToggle}
      >
        <span
          className={`text-xs font-bold mt-0.5 severity-${alert.severity} flex-shrink-0`}
        >
          {SEVERITY_LABEL[alert.severity]}
        </span>
        <div className="flex-1 min-w-0">
          <div className="text-xs text-ocean-200 leading-snug line-clamp-2">
            {alert.message}
          </div>
          <div className="text-xs text-ocean-400 mt-0.5">
            {formatDistanceToNow(new Date(alert.created_at), {
              addSuffix: true,
              locale: ko,
            })}
            {" · "}
            <span className="text-ocean-500">{alert.generated_by}</span>
          </div>
          <div className="mt-1 flex flex-wrap gap-1">
            {/* 정보성 뱃지 - 클릭 불가 */}
            <AlertBadge variant="source" title={source}>
              {source}
            </AlertBadge>
            <AlertBadge
              variant={isResolved ? "resolved" : isNew ? "active" : "acknowledged"}
            >
              {alertStatusLabel(alert.status)}
            </AlertBadge>
            {workflowState && <AlertBadge variant="workflow">{workflowLabel(workflowState)}</AlertBadge>}
          </div>
        </div>
        {isNew && (
          <span className="w-1.5 h-1.5 rounded-full bg-current flex-shrink-0 mt-1.5 animate-pulse" />
        )}
      </div>

      {/* 확장 상세 */}
      {expanded && (
        <div className="px-3 pb-2 space-y-2">
          {/* 관련 선박 - 클릭 가능한 버튼 */}
          {alert.platform_ids.length > 0 && (
            <div className="flex flex-wrap gap-1">
              <span className="text-xs text-ocean-500">관련 선박:</span>
              {alert.platform_ids.map((id) => (
                <PlatformButton
                  key={id}
                  onClick={() => onSelectPlatform(id)}
                  title="클릭하여 지도에서 선박 선택"
                >
                  {id}
                </PlatformButton>
              ))}
            </div>
          )}

          {/* AI 권고사항 */}
          {alert.recommendation && (
            <div className="text-xs text-ocean-300 bg-ocean-900 rounded p-2 leading-relaxed border border-ocean-700">
              <span className="text-ocean-500 text-xs block mb-1">AI 권고</span>
              {Boolean(
                (alert.metadata as Record<string, unknown> | null)
                  ?.llm_fallback,
              ) && (
                <div className="block mb-1">
                  <AlertBadge variant="fallback" className="text-xs">
                    LLM 실패 fallback
                  </AlertBadge>
                </div>
              )}
              {alert.recommendation}
            </div>
          )}

          {actionHistory.length > 0 && (
            <div className="text-xs text-ocean-400 bg-ocean-950/60 rounded p-2 border border-ocean-800">
              최근 처리: {actionLabel(actionHistory[actionHistory.length - 1].action)}
            </div>
          )}

          {/* 작업 버튼 */}
          {canOperate && (
            <div className="flex flex-wrap gap-2 pt-1">
              {/* 기존 3개: new 상태에서만 */}
              {isNew && (
                <>
                  <AlertButton
                    variant="primary"
                    onClick={onAck}
                    title="경보를 인지 처리합니다"
                  >
                    인지 처리
                  </AlertButton>
                  <AlertButton
                    variant="violet"
                    onClick={() => onAction("start_investigation")}
                    title="조사를 시작합니다"
                  >
                    조사 시작
                  </AlertButton>
                  <AlertButton
                    variant="warning"
                    onClick={() => onAction("escalate")}
                    title="상위 부서에 보고합니다"
                  >
                    상위 보고
                  </AlertButton>
                </>
              )}

              {/* 신규 1: resolve — resolved 아닐 때 */}
              {!isResolved && (
                <AlertButton
                  variant="success"
                  onClick={() => onAction("resolve")}
                  title="경보를 해결 처리합니다"
                >
                  해결 처리
                </AlertButton>
              )}

              {/* 신규 2: notify_guard — new + distress/ais_off */}
              {isNew && (alert.alert_type === "distress" || alert.alert_type === "ais_off") && (
                <AlertButton
                  variant="danger"
                  onClick={() => onAction("notify_guard")}
                  title="관계 기관에 통보합니다"
                >
                  관계기관 통보
                </AlertButton>
              )}

              {/* 신규 3: request_course_change — new + cpa */}
              {isNew && alert.alert_type === "cpa" && (
                <AlertButton
                  variant="info"
                  onClick={() => onAction("request_course_change")}
                  title="선박에 변침을 요청합니다"
                >
                  변침 요청
                </AlertButton>
              )}

              {/* 신규 4: request_speed_reduction — new */}
              {isNew && (
                <AlertButton
                  variant="info"
                  onClick={() => onAction("request_speed_reduction")}
                  title="선박에 감속을 요청합니다"
                >
                  감속 요청
                </AlertButton>
              )}

              {/* 신규 5: request_zone_exit — new + zone_intrusion */}
              {isNew && alert.alert_type === "zone_intrusion" && (
                <AlertButton
                  variant="info"
                  onClick={() => onAction("request_zone_exit")}
                  title="선박이 구역을 이탈하도록 요청합니다"
                >
                  구역 이탈 요청
                </AlertButton>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

type AlertActionEntry = {
  action: string;
  executed_at: string;
};

function getWorkflowState(alert: Alert): string | null {
  const workflowState = (alert.metadata as Record<string, unknown> | null)?.workflow_state;
  return typeof workflowState === "string" ? workflowState : null;
}

function getActionHistory(alert: Alert): AlertActionEntry[] {
  const actions = (alert.metadata as Record<string, unknown> | null)?.actions;
  if (!Array.isArray(actions)) return [];
  return actions.filter((entry): entry is AlertActionEntry => {
    if (!entry || typeof entry !== "object") return false;
    const candidate = entry as Record<string, unknown>;
    return typeof candidate.action === "string" && typeof candidate.executed_at === "string";
  });
}

function workflowLabel(workflowState: string) {
  if (workflowState === "investigating") return "조사 중";
  if (workflowState === "escalated") return "상위 보고";
  if (workflowState === "resolved") return "해결 흐름";
  return workflowState;
}

function actionLabel(action: string) {
  if (action === "acknowledge") return "인지";
  if (action === "resolve") return "해결";
  if (action === "notify_guard") return "기관 통보";
  if (action === "request_course_change") return "변침 요청";
  if (action === "request_speed_reduction") return "감속 요청";
  if (action === "request_zone_exit") return "구역 이탈 요청";
  if (action === "start_investigation") return "조사 시작";
  if (action === "escalate") return "상위 보고";
  return action;
}

function alertStatusLabel(status: Alert["status"]) {
  if (status === "new") return "활성";
  if (status === "acknowledged") return "인지됨";
  if (status === "resolved") return "해결됨";
  return status;
}
