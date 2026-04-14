"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAlertStore } from "@/stores/alertStore";
import { useAuthStore } from "@/stores/authStore";
import { usePlatformStore } from "@/stores/platformStore";
import { useSystemStore } from "@/stores/systemStore";
import { getCoreApiUrl } from "@/lib/publicUrl";
import type { Alert, AlertSeverity, AlertStatus, CommandRole } from "@/types";
import { formatDistanceToNow, format, isAfter, subHours } from "date-fns";
import { ko } from "date-fns/locale";
import { AlertButton, PlatformButton } from "@/components/alerts/AlertButton";
import PageHeader from "@/components/ui/PageHeader";
import MetricCard from "@/components/ui/MetricCard";
import FilterChip from "@/components/ui/FilterChip";
import SectionHeading from "@/components/ui/SectionHeading";
import StatusBadge from "@/components/ui/StatusBadge";
import EmptyState from "@/components/ui/EmptyState";

const ROLE_ORDER: Record<CommandRole, number> = { viewer: 0, operator: 1, admin: 2 };

async function apiDeleteAlerts(alertIds: string[], token: string) {
  const res = await fetch(`${getCoreApiUrl()}/alerts`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ alert_ids: alertIds }),
  });
  if (!res.ok) throw new Error(`Delete failed: ${res.status}`);
  return res.json() as Promise<{ deleted: number }>;
}

async function apiRunAlertAction(alertId: string, action: string, token: string) {
  const res = await fetch(`${getCoreApiUrl()}/alerts/${alertId}/action`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ action }),
  });
  if (!res.ok) throw new Error(`Action failed: ${res.status}`);
  return res.json() as Promise<Alert>;
}

const SEVERITY_LABEL: Record<AlertSeverity, string> = {
  critical: "위험",
  warning: "주의",
  info: "정보",
};
const SEVERITY_STYLE: Record<
  AlertSeverity,
  { border: string; bg: string; text: string; pill: string }
> = {
  critical: {
    border: "border-red-500/50",
    bg: "bg-red-500/8",
    text: "text-red-400",
    pill: "bg-red-500/20 text-red-300 border-red-500/40",
  },
  warning: {
    border: "border-yellow-500/50",
    bg: "bg-yellow-500/8",
    text: "text-yellow-400",
    pill: "bg-yellow-500/20 text-yellow-300 border-yellow-500/40",
  },
  info: {
    border: "border-blue-500/40",
    bg: "bg-blue-500/6",
    text: "text-blue-400",
    pill: "bg-blue-500/20 text-blue-300 border-blue-500/40",
  },
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
const STATUS_LABEL: Record<AlertStatus, string> = {
  new: "미확인",
  acknowledged: "확인됨",
  resolved: "해결됨",
};

type TimeFilter = "all" | "1h" | "6h" | "24h";

export default function AlertsPage() {
  const router = useRouter();
  const alerts = useAlertStore((s) => s.alerts);
  const updateAlert = useAlertStore((s) => s.updateAlert);
  const removeAlerts = useAlertStore((s) => s.removeAlerts);
  const platforms = usePlatformStore((s) => s.platforms);
  const alertLoad = useSystemStore((s) => s.initialData.alerts);
  const token = useAuthStore((s) => s.token);
  const role = useAuthStore((s) => s.role);
  const [severityFilter, setSeverityFilter] = useState<AlertSeverity | "all">(
    "all",
  );
  const [statusFilter, setStatusFilter] = useState<
    "new" | "acknowledged" | "all"
  >("all");
  const [timeFilter, setTimeFilter] = useState<TimeFilter>("all");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [modalAlertId, setModalAlertId] = useState<string | null>(null);
  const [acting, setActing] = useState<string | null>(null);
  const [agentFilter, setAgentFilter] = useState<string | "all">("all");
  const [workflowFilter, setWorkflowFilter] = useState<string | "all">("all");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState(false);
  const [pastPage, setPastPage] = useState(1);
  const PAST_PAGE_SIZE = 30;

  const canOperate = !!token && !!role && ROLE_ORDER[role] >= ROLE_ORDER.operator;
  const canAdmin = !!token && !!role && ROLE_ORDER[role] >= ROLE_ORDER.admin;

  const agentFilters = Array.from(new Set(alerts.map((alert) => alert.generated_by))).sort();
  const workflowFilters = Array.from(new Set(alerts.map((alert) => getWorkflowState(alert)).filter((state): state is string => state !== null))).sort();

  // 시간 필터
  const now = new Date();
  const timeFiltered = alerts.filter((a) => {
    if (timeFilter === "all") return true;
    const hours = timeFilter === "1h" ? 1 : timeFilter === "6h" ? 6 : 24;
    return isAfter(new Date(a.created_at), subHours(now, hours));
  });

  const filtered = timeFiltered
    .filter((a) => severityFilter === "all" || a.severity === severityFilter)
    .filter((a) => statusFilter === "all" || a.status === statusFilter)
    .filter((a) => agentFilter === "all" || a.generated_by === agentFilter)
    .filter((a) => workflowFilter === "all" || getWorkflowState(a) === workflowFilter);

  // 필터 변경 시 페이지 리셋
  useEffect(() => { setPastPage(1); }, [severityFilter, statusFilter, timeFilter, agentFilter, workflowFilter]);

  // 요약 통계
  const newAlerts = alerts.filter((a) => a.status === "new");
  const criticalNew = newAlerts.filter((a) => a.severity === "critical").length;
  const warningNew = newAlerts.filter((a) => a.severity === "warning").length;
  const infoNew = newAlerts.filter((a) => a.severity === "info").length;
  const acknowledgedAll = alerts.filter(
    (a) => a.status === "acknowledged",
  ).length;

  // 활성(미확인) / 과거(확인+해결) 분리
  const active = filtered.filter((a) => a.status === "new");
  const past = filtered.filter((a) => a.status !== "new");

  const allFilteredIds = filtered.map((a) => a.alert_id);
  const allSelected =
    allFilteredIds.length > 0 && allFilteredIds.every((id) => selected.has(id));
  const someSelected = selected.size > 0;

  function toggleAll() {
    if (allSelected) {
      setSelected(new Set());
    } else {
      setSelected(new Set(allFilteredIds));
    }
  }

  function toggleOne(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  async function handleDelete() {
    if (selected.size === 0) return;
    setDeleting(true);
    try {
      const ids = Array.from(selected);
      if (!token || !role || ROLE_ORDER[role] < ROLE_ORDER.admin) return;
      await apiDeleteAlerts(ids, token);
      removeAlerts(ids);
      setSelected(new Set());
    } catch (e) {
      console.error(e);
    } finally {
      setDeleting(false);
    }
  }

  function getPlatformName(id: string) {
    const p = platforms[id];
    if (!p) return id.replace(/^MMSI-/, "");
    return p.name && p.name !== p.platform_id
      ? p.name
      : id.replace(/^MMSI-/, "");
  }

  async function runAction(alertId: string, action: string) {
    if (!token || !role || ROLE_ORDER[role] < ROLE_ORDER.operator) return;
    setActing(`${alertId}:${action}`);
    try {
      const updated = await apiRunAlertAction(alertId, action, token);
      updateAlert(updated);
    } catch (e) {
      console.error(e);
    } finally {
      setActing(null);
    }
  }

  const modalAlert = modalAlertId
    ? (alerts.find((a) => a.alert_id === modalAlertId) ?? null)
    : null;

  return (
    <div className="page-shell">
      <PageHeader
        title="경보 현황"
        actions={[
          someSelected && role && ROLE_ORDER[role] >= ROLE_ORDER.admin ? (
            <button
              key="delete"
              onClick={handleDelete}
              disabled={deleting}
              className="flex items-center gap-1.5 rounded border border-red-500/50 bg-red-500/10 px-3 py-1.5 text-xs text-red-400 transition-colors hover:bg-red-500/20 disabled:opacity-50"
            >
              {deleting ? "삭제 중…" : `선택 삭제 (${selected.size}건)`}
            </button>
          ) : null,
          <div key="count" className="text-xs text-ocean-500">전체 {alerts.length}건</div>,
        ]}
        stats={[
          <MetricCard key="critical" label="미확인 위험" value={criticalNew} tone={criticalNew > 0 ? "critical" : "neutral"} valueClassName="text-xl" />,
          <MetricCard key="warning" label="미확인 주의" value={warningNew} tone={warningNew > 0 ? "warning" : "neutral"} valueClassName="text-xl" />,
          <MetricCard key="info" label="미확인 정보" value={infoNew} tone="info" valueClassName="text-xl" />,
          <MetricCard key="ack" label="확인 완료" value={acknowledgedAll} valueClassName="text-xl" />,
          <MetricCard key="new" label="전체 미확인" value={newAlerts.length} tone={newAlerts.length > 0 ? "warning" : "neutral"} valueClassName="text-xl" />,
        ]}
      />

      <div className="flex-shrink-0 px-5 pb-4">
        <div className="flex flex-wrap gap-2 rounded-2xl border border-ocean-800/70 bg-ocean-950/35 p-3">
          {/* 심각도 */}
          <div className="flex gap-1">
            {(["all", "critical", "warning", "info"] as const).map((f) => {
              const s = f !== "all" ? SEVERITY_STYLE[f] : null;
              return (
                <FilterChip
                  key={f}
                  onClick={() => setSeverityFilter(f)}
                  active={severityFilter === f}
                  tone={f === "critical" ? "critical" : f === "warning" ? "warning" : f === "info" ? "info" : "neutral"}
                  className={severityFilter === f && f !== "all" ? `${s!.pill} border-current` : ""}
                >
                  {f === "all" ? "전체" : SEVERITY_LABEL[f]}
                </FilterChip>
              );
            })}
          </div>

          {/* 상태 */}
          <div className="flex gap-1">
            {(["all", "new", "acknowledged"] as const).map((f) => (
              <FilterChip
                key={f}
                onClick={() => setStatusFilter(f)}
                active={statusFilter === f}
              >
                {f === "all" ? "전체 상태" : STATUS_LABEL[f as AlertStatus]}
              </FilterChip>
            ))}
          </div>

          <div className="flex gap-1">
            <FilterChip
              onClick={() => setAgentFilter("all")}
              active={agentFilter === "all"}
            >
              전체 에이전트
            </FilterChip>
            {agentFilters.map((agentId) => (
              <FilterChip
                key={agentId}
                onClick={() => setAgentFilter(agentId)}
                active={agentFilter === agentId}
              >
                {agentId}
              </FilterChip>
            ))}
          </div>

          <div className="flex gap-1">
            <FilterChip
              onClick={() => setWorkflowFilter("all")}
              active={workflowFilter === "all"}
            >
              전체 워크플로우
            </FilterChip>
            {workflowFilters.map((workflow) => (
              <FilterChip
                key={workflow}
                onClick={() => setWorkflowFilter(workflow)}
                active={workflowFilter === workflow}
              >
                {workflowLabel(workflow)}
              </FilterChip>
            ))}
          </div>

          {/* 시간 */}
          <div className="flex gap-1 ml-auto">
            {(["all", "1h", "6h", "24h"] as const).map((f) => (
              <FilterChip
                key={f}
                onClick={() => setTimeFilter(f)}
                active={timeFilter === f}
              >
                {f === "all" ? "전체 시간" : `최근 ${f}`}
              </FilterChip>
            ))}
          </div>

          {/* 전체 선택 (admin 전용 — 삭제 기능에만 사용) */}
          {canAdmin && filtered.length > 0 && (
            <label className="flex items-center gap-1.5 cursor-pointer ml-2 select-none">
              <input
                type="checkbox"
                checked={allSelected}
                onChange={toggleAll}
                className="w-3.5 h-3.5 accent-red-500 cursor-pointer"
              />
              <span className="text-xs text-ocean-500">전체 선택</span>
            </label>
          )}
        </div>
      </div>

      {/* 목록 */}
      <div className="flex-1 overflow-auto px-5 py-4 space-y-4">
        {/* ── 활성 경보 ── */}
        {statusFilter !== "acknowledged" && (
          <section className="content-surface rounded-2xl p-4">
            <SectionHeading title="미확인 경보" count={active.length > 0 ? active.length : undefined} tone={active.length > 0 ? "critical" : "neutral"} />
            {active.length === 0 ? (
              <EmptyState title={alertLoad.status === "loading" ? "경보 로딩 중..." : alertLoad.status === "error" ? "경보 로드 실패" : "미확인 경보 없음 ✓"} compact />
            ) : (
              <div className="space-y-1.5">
                {active.map((a) => (
                  <AlertRow
                    key={a.alert_id}
                    alert={a}
                    expanded={expanded === a.alert_id}
                    onToggle={() =>
                      setExpanded(expanded === a.alert_id ? null : a.alert_id)
                    }
                    onAck={() => runAction(a.alert_id, "acknowledge")}
                    getPlatformName={getPlatformName}
                    onSelectPlatform={(id) => router.push(`/platforms/${id}`)}
                    isActive
                    canOperate={canOperate}
                    canAdmin={canAdmin}
                    checked={selected.has(a.alert_id)}
                    onCheck={() => toggleOne(a.alert_id)}
                    onOpenModal={() => setModalAlertId(a.alert_id)}
                    onAction={runAction}
                    acting={acting}
                  />
                ))}
              </div>
            )}
          </section>
        )}

        {/* ── 과거 경보 ── */}
        {statusFilter !== "new" && past.length > 0 && (
          <section className="content-surface rounded-2xl p-4">
            <SectionHeading title="확인 / 해결된 경보" count={past.length} />
            <div className="space-y-1">
              {past.slice(0, pastPage * PAST_PAGE_SIZE).map((a) => (
                <AlertRow
                  key={a.alert_id}
                  alert={a}
                  expanded={expanded === a.alert_id}
                  onToggle={() =>
                    setExpanded(expanded === a.alert_id ? null : a.alert_id)
                  }
                  onAck={() => runAction(a.alert_id, "acknowledge")}
                  getPlatformName={getPlatformName}
                  onSelectPlatform={(id) => router.push(`/platforms/${id}`)}
                  isActive={false}
                  canOperate={canOperate}
                  canAdmin={canAdmin}
                  checked={selected.has(a.alert_id)}
                  onCheck={() => toggleOne(a.alert_id)}
                  onOpenModal={() => setModalAlertId(a.alert_id)}
                  onAction={runAction}
                  acting={acting}
                />
              ))}
            </div>
            {past.length > pastPage * PAST_PAGE_SIZE && (
              <button
                onClick={() => setPastPage((p) => p + 1)}
                className="mt-2 w-full text-xs py-2 rounded border border-ocean-800 text-ocean-500 hover:text-ocean-300 hover:border-ocean-600 transition-colors"
              >
                더 보기 ({past.length - pastPage * PAST_PAGE_SIZE}건 남음)
              </button>
            )}
          </section>
        )}

        {filtered.length === 0 && (
          <EmptyState title="조건에 맞는 경보 없음" description="필터를 조정해보세요" />
        )}
      </div>

      {modalAlert && (
        <AlertActionModal
          alert={modalAlert}
          onClose={() => setModalAlertId(null)}
          onAction={runAction}
          acting={acting}
          canOperate={canOperate}
          getPlatformName={getPlatformName}
        />
      )}
    </div>
  );
}

function AlertRow({
  alert,
  expanded,
  onToggle,
  onAck,
  getPlatformName,
  onSelectPlatform,
  isActive,
  canOperate,
  canAdmin,
  checked,
  onCheck,
  onOpenModal,
  onAction,
  acting,
}: {
  alert: Alert;
  expanded: boolean;
  onToggle: () => void;
  onAck: () => void;
  getPlatformName: (id: string) => string;
  onSelectPlatform: (id: string) => void;
  isActive: boolean;
  canOperate: boolean;
  canAdmin: boolean;
  checked: boolean;
  onCheck: () => void;
  onOpenModal: () => void;
  onAction: (alertId: string, action: string) => void;
  acting: string | null;
}) {
  const s = SEVERITY_STYLE[alert.severity];
  const fallback = Boolean(alert.metadata?.llm_fallback);
  const source = String(
    (alert.metadata as Record<string, unknown> | null)?.source ?? "agent-runtime",
  );
  const workflowState = getWorkflowState(alert);
  const actionHistory = getActionHistory(alert);

  return (
    <div
      className={`rounded border transition-all ${s.border} ${isActive ? s.bg : "bg-transparent opacity-55"} ${checked ? "ring-1 ring-red-500/40" : ""}`}
    >
      {/* 요약 행 */}
      <div className="px-3 py-2.5 flex items-start gap-3">
        {/* 체크박스 (admin 전용 — 삭제 기능에만 사용) */}
        {canAdmin && (
          <div
            className="flex-shrink-0 pt-0.5"
            onClick={(e) => e.stopPropagation()}
          >
            <input
              type="checkbox"
              checked={checked}
              onChange={onCheck}
              className="w-3.5 h-3.5 accent-red-500 cursor-pointer"
            />
          </div>
        )}
        <div
          className="flex-1 cursor-pointer flex items-start gap-3"
          onClick={onToggle}
        >
          {/* 심각도 */}
          <div className="flex-shrink-0 pt-0.5 flex flex-col items-center gap-1">
            <span className={`text-xs font-bold ${s.text}`}>
              {SEVERITY_LABEL[alert.severity]}
            </span>
            {isActive && (
              <span
                className={`w-1.5 h-1.5 rounded-full ${s.text.replace("text-", "bg-")} ${alert.severity === "critical" ? "animate-pulse" : ""}`}
              />
            )}
          </div>

          {/* 내용 */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-0.5 flex-wrap">
                <StatusBadge>
                  {ALERT_TYPE_KR[alert.alert_type] ?? alert.alert_type}
                </StatusBadge>
                <StatusBadge tone={alert.status === "resolved" ? "success" : alert.status === "acknowledged" ? "info" : alert.severity === "critical" ? "critical" : alert.severity === "warning" ? "warning" : "neutral"}>
                  {STATUS_LABEL[alert.status]}
                </StatusBadge>
                <StatusBadge>
                  {alert.generated_by}
                </StatusBadge>
                <StatusBadge>
                  {source}
                </StatusBadge>
                {workflowState && (
                  <StatusBadge tone="info" className="bg-violet-500/10 border-violet-500/30 text-violet-300">
                    {workflowLabel(workflowState)}
                  </StatusBadge>
                )}
              <span className="text-xs text-ocean-400 ml-auto">
                {formatDistanceToNow(new Date(alert.created_at), {
                  addSuffix: true,
                  locale: ko,
                })}
              </span>
            </div>
            <div className="text-xs text-ocean-200 leading-snug">
              {alert.message}
            </div>

            {fallback && (
              <div className="mt-1 inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded border border-amber-500/40 bg-amber-500/10 text-amber-300">
                LLM 실패 fallback 적용
              </div>
            )}

            {alert.platform_ids.length > 0 && (
              <div className="flex gap-1 mt-1 flex-wrap">
                {alert.platform_ids.map((id) => (
                  <PlatformButton
                    key={id}
                    onClick={() => onSelectPlatform(id)}
                    title="클릭하여 선박 상세 페이지로 이동"
                  >
                    {getPlatformName(id)}
                  </PlatformButton>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 확장 상세 */}
      {expanded && (
        <div className="px-3 pb-3 border-t border-current/15 pt-2.5 space-y-2.5">
          {/* 타임라인 */}
          <div className="grid grid-cols-3 gap-3 text-xs">
            <div>
              <div className="text-ocean-500 mb-0.5">발생</div>
              <div className="text-ocean-300 font-mono">
                {format(new Date(alert.created_at), "MM/dd HH:mm:ss")}
              </div>
            </div>
            {alert.acknowledged_at && (
              <div>
                <div className="text-ocean-500 mb-0.5">확인</div>
                <div className="text-ocean-300 font-mono">
                  {format(new Date(alert.acknowledged_at), "MM/dd HH:mm:ss")}
                </div>
              </div>
            )}
            {alert.resolved_at && (
              <div>
                <div className="text-ocean-500 mb-0.5">해결</div>
                <div className="text-ocean-300 font-mono">
                  {format(new Date(alert.resolved_at), "MM/dd HH:mm:ss")}
                </div>
              </div>
            )}
          </div>

          {actionHistory.length > 0 && (
            <div className="rounded border border-ocean-800 bg-ocean-900/40 p-2.5">
              <div className="mb-2 text-xs text-ocean-500">처리 이력</div>
              <div className="space-y-1.5">
                {actionHistory.map((entry, index) => (
                  <div key={`${entry.action}-${entry.executed_at}-${index}`} className="flex items-center gap-2 text-xs text-ocean-300">
                    <span className="rounded bg-ocean-800 px-1.5 py-0.5 text-ocean-400">{actionLabel(entry.action)}</span>
                    <span>{entry.executor ?? "operator-ui"}</span>
                    <span className="text-ocean-500 font-mono ml-auto">{format(new Date(entry.executed_at), "MM/dd HH:mm:ss")}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* AI 권고 */}
          {alert.recommendation ? (
            <div className="bg-ocean-900/70 rounded p-2.5 border border-ocean-800">
              <div className="text-xs text-ocean-500 mb-1.5 flex items-center gap-1.5">
                <span>⬡</span>
                <span>AI 분석 · 권고사항</span>
              </div>
              <div className="text-xs text-ocean-300 leading-relaxed whitespace-pre-wrap">
                {alert.recommendation}
              </div>
            </div>
          ) : (
            <div className="text-xs text-ocean-500">
              AI 권고 없음 (Rule 에이전트 생성)
            </div>
          )}

          {/* 액션 (operator 이상 전용) */}
          {isActive && canOperate && (
            <div className="flex flex-wrap items-center gap-2">
              <AlertButton variant="primary" onClick={onAck}>
                인지 처리
              </AlertButton>
              {alert.alert_type === "cpa" && (
                <AlertButton
                  variant="info"
                  onClick={() =>
                    onAction(alert.alert_id, "request_course_change")
                  }
                  disabled={
                    acting === `${alert.alert_id}:request_course_change`
                  }
                >
                  변침 요청 자동처리
                </AlertButton>
              )}
              {alert.alert_type === "zone_intrusion" && (
                <AlertButton
                  variant="info"
                  onClick={() => onAction(alert.alert_id, "request_zone_exit")}
                  disabled={acting === `${alert.alert_id}:request_zone_exit`}
                >
                  구역 이탈 요청
                </AlertButton>
              )}
              {(alert.alert_type === "distress" ||
                alert.alert_type === "ais_off") && (
                <AlertButton
                  variant="danger"
                  onClick={() => onAction(alert.alert_id, "notify_guard")}
                  disabled={acting === `${alert.alert_id}:notify_guard`}
                >
                  관계기관 통보
                </AlertButton>
              )}
              <AlertButton
                variant="violet"
                onClick={() => onAction(alert.alert_id, "start_investigation")}
                disabled={acting === `${alert.alert_id}:start_investigation`}
              >
                조사 시작
              </AlertButton>
              <AlertButton
                variant="warning"
                onClick={() => onAction(alert.alert_id, "escalate")}
                disabled={acting === `${alert.alert_id}:escalate`}
              >
                상위 보고
              </AlertButton>
              <AlertButton
                variant="secondary"
                onClick={onOpenModal}
              >
                상세 모달
              </AlertButton>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function AlertActionModal({
  alert,
  onClose,
  onAction,
  acting,
  canOperate,
  getPlatformName,
}: {
  alert: Alert;
  onClose: () => void;
  onAction: (alertId: string, action: string) => void;
  acting: string | null;
  canOperate: boolean;
  getPlatformName: (id: string) => string;
}) {
  const fallback = Boolean(alert.metadata?.llm_fallback);
  const workflowState = getWorkflowState(alert);
  const actions = getActionHistory(alert);

  return (
    <div
      className="fixed inset-0 z-50 bg-black/55 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl rounded-xl border border-ocean-700 bg-ocean-950 p-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3 mb-3">
          <div>
            <div className="text-sm text-ocean-100 font-bold">
              경보 상세 및 자동 처리
            </div>
            <div className="text-xs text-ocean-500 mt-0.5">
              {ALERT_TYPE_KR[alert.alert_type] ?? alert.alert_type} ·{" "}
              {alert.generated_by}
              {workflowState && ` · ${workflowLabel(workflowState)}`}
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-xs px-2 py-1 rounded border border-ocean-700 text-ocean-300"
          >
            닫기
          </button>
        </div>

        <div className="text-xs text-ocean-200 leading-relaxed mb-2">
          {alert.message}
        </div>
        <div className="flex flex-wrap gap-1 mb-3">
          {alert.platform_ids.map((id) => (
            <span
              key={id}
              className="text-xs px-1.5 py-0.5 bg-ocean-800 text-ocean-300 rounded font-mono"
            >
              {getPlatformName(id)}
            </span>
          ))}
        </div>

        {alert.recommendation && (
          <div className="rounded border border-ocean-800 bg-ocean-900/50 p-2.5 text-xs text-ocean-300 whitespace-pre-wrap">
            {fallback && (
              <div className="mb-1.5 text-amber-300">
                LLM 실패로 Rule 기반 fallback 권고가 표시됩니다.
              </div>
            )}
            {alert.recommendation}
          </div>
        )}

        {actions.length > 0 && (
          <div className="mt-3 rounded border border-ocean-800 bg-ocean-900/40 p-2.5">
            <div className="mb-2 text-xs text-ocean-500">처리 이력</div>
            <div className="space-y-1.5">
              {actions.map((entry, index) => (
                <div key={`${entry.action}-${entry.executed_at}-${index}`} className="flex items-center gap-2 text-xs text-ocean-300">
                  <span className="rounded bg-ocean-800 px-1.5 py-0.5 text-ocean-400">{actionLabel(entry.action)}</span>
                  <span>{entry.executor ?? "operator-ui"}</span>
                  <span className="ml-auto text-ocean-500 font-mono">{format(new Date(entry.executed_at), "MM/dd HH:mm:ss")}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {canOperate ? (
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              onClick={() => onAction(alert.alert_id, "acknowledge")}
              disabled={acting === `${alert.alert_id}:acknowledge`}
              className="text-xs px-3 py-1.5 rounded border border-ocean-600 text-ocean-200 disabled:opacity-40"
            >
              인지 처리
            </button>
            <button
              onClick={() => onAction(alert.alert_id, "resolve")}
              disabled={acting === `${alert.alert_id}:resolve`}
              className="text-xs px-3 py-1.5 rounded border border-green-500/40 text-green-300 disabled:opacity-40"
            >
              해결 처리
            </button>
            <button
              onClick={() => onAction(alert.alert_id, "notify_guard")}
              disabled={acting === `${alert.alert_id}:notify_guard`}
              className="text-xs px-3 py-1.5 rounded border border-red-500/40 text-red-300 disabled:opacity-40"
            >
              관계기관 통보
            </button>
            <button
              onClick={() => onAction(alert.alert_id, "start_investigation")}
              disabled={acting === `${alert.alert_id}:start_investigation`}
              className="text-xs px-3 py-1.5 rounded border border-violet-500/40 text-violet-300 disabled:opacity-40"
            >
              조사 시작
            </button>
            <button
              onClick={() => onAction(alert.alert_id, "escalate")}
              disabled={acting === `${alert.alert_id}:escalate`}
              className="text-xs px-3 py-1.5 rounded border border-amber-500/40 text-amber-300 disabled:opacity-40"
            >
              상위 보고
            </button>
          </div>
        ) : (
          <div className="mt-3 text-xs text-ocean-500">
            경보 처리 권한이 없습니다. operator 이상 로그인이 필요합니다.
          </div>
        )}
      </div>
    </div>
  );
}

type AlertActionEntry = {
  action: string;
  executed_at: string;
  executor?: string;
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
