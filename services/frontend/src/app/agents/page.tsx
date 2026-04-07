"use client";

import { useEffect, useState } from "react";
import { useAILogStore, isAIAgent, type ActivityLogEntry } from "@/stores/aiLogStore";
import { useAlertStore } from "@/stores/alertStore";
import { usePlatformStore } from "@/stores/platformStore";
import { formatDistanceToNow, format } from "date-fns";
import { ko } from "date-fns/locale";

const AGENTS_URL = process.env.NEXT_PUBLIC_AGENTS_URL ?? "http://localhost:7701";

// ── 에이전트 메타 ──────────────────────────────────────────────────────────────

interface AgentMeta {
  name: string; type: "rule" | "ai"; level: string;
  role: string; trigger: string; output: string; color: string;
  input: string;
  triggeredBy?: string; // 이 AI 에이전트를 호출하는 Rule 에이전트 ID
}

const AGENT_META: Record<string, AgentMeta> = {
  "cpa-agent": {
    name: "CPA/TCPA", type: "rule", level: "L1", color: "#2e8dd4",
    role: "충돌 위험 감지",
    trigger: "CPA < 0.5nm & TCPA < 30분 (critical: 0.2nm & 10분)",
    output: "cpa 경보 발생",
    input: "전체 선박 위치·속도·침로 (실시간 AIS 스트림)",
  },
  "zone-monitor": {
    name: "Zone Monitor", type: "rule", level: "L1", color: "#22d3ee",
    role: "구역 침입 감시",
    trigger: "선박 위치 ∈ 설정된 금지/주의 구역 경계 내",
    output: "zone_intrusion 경보 발생",
    input: "선박 위치 + 사전 설정된 구역 GeoJSON 경계",
  },
  "anomaly-rule": {
    name: "Anomaly Rule", type: "rule", level: "L1", color: "#fbbf24",
    role: "이상 행동 탐지",
    trigger: "AIS 90초 소실 | SOG ≥5kt 급감 | ROT ≥25°/min",
    output: "anomaly / ais_off 경보 발생",
    input: "AIS 위치 보고 스트림 (타임스탬프·속도·회전율)",
  },
  "anomaly-ai": {
    name: "Anomaly AI", type: "ai", level: "L2", color: "#a78bfa",
    role: "이상 행동 AI 분석",
    trigger: "Anomaly Rule 에이전트의 anomaly/ais_off 경보 수신",
    output: "원인 진단 + 대응 권고",
    input: "Rule 경보 데이터 (선박 ID·마지막 위치·속도·상태) + 이상 유형",
    triggeredBy: "anomaly-rule",
  },
  "distress-agent": {
    name: "Distress", type: "ai", level: "L3", color: "#f87171",
    role: "조난 상황 대응",
    trigger: "not_under_command / aground / AIS 소실 상태 감지",
    output: "SAR 대응 지침 생성",
    input: "조난 신호·AIS 소실 경보 + 선박 마지막 위치·상태",
    triggeredBy: "anomaly-rule",
  },
  "report-agent": {
    name: "Report", type: "ai", level: "L2", color: "#34d399",
    role: "사건 보고서 생성",
    trigger: "critical 경보 수신 (cpa / zone_intrusion / distress)",
    output: "AI 종합 사건 보고서",
    input: "경보 데이터 + 관련 선박 이력 + 구역 정보",
    triggeredBy: "cpa-agent",
  },
};

// ── 심각도 색상 (일관성) ────────────────────────────────────────────────────────

const SEV = {
  critical: {
    border: "border-l-red-500",
    headerBg: "bg-red-950/30",
    text: "text-red-400",
    badge: "bg-red-900/50 text-red-300 border border-red-700/50",
    dot: "bg-red-500",
    label: "위험",
  },
  warning: {
    border: "border-l-amber-500",
    headerBg: "bg-amber-950/20",
    text: "text-amber-400",
    badge: "bg-amber-900/50 text-amber-300 border border-amber-700/50",
    dot: "bg-amber-500",
    label: "주의",
  },
  info: {
    border: "border-l-blue-500",
    headerBg: "",
    text: "text-blue-400",
    badge: "bg-blue-900/50 text-blue-300 border border-blue-700/50",
    dot: "bg-blue-500",
    label: "정보",
  },
} as const;

const ALERT_TYPE_KR: Record<string, string> = {
  cpa: "충돌 위험", zone_intrusion: "구역 침입", anomaly: "이상 행동",
  ais_off: "AIS 소실", distress: "조난", compliance: "상황 보고",
};

// ── Agent Status (API 응답) ────────────────────────────────────────────────────
// 백엔드 base.py health()는 "type" 키로 반환 — agent_type이 아님

interface AgentStatus {
  agent_id: string; name: string;
  type: string;   // API 반환 키: "type" (rule | ai)
  level: string; enabled: boolean;
  failure_count?: number; last_error?: string | null;
}

// ── 페이지 ────────────────────────────────────────────────────────────────────

export default function AgentsPage() {
  const logs      = useAILogStore((s) => s.logs);
  const clearLogs = useAILogStore((s) => s.clear);
  const alerts    = useAlertStore((s) => s.alerts);
  const platforms = usePlatformStore((s) => s.platforms);

  const [agentFilter, setAgentFilter] = useState<string>("all");
  const [typeFilter, setTypeFilter]   = useState<"all" | "rule" | "ai">("all");
  const [expandedLog, setExpandedLog] = useState<string | null>(null);
  const [statuses, setStatuses]       = useState<AgentStatus[]>([]);
  const [updating, setUpdating]       = useState<string | null>(null);
  const [apiStatus, setApiStatus]     = useState<"ok" | "fallback" | "unknown">("unknown");

  useEffect(() => {
    fetch(`${AGENTS_URL}/agents`)
      .then((r) => r.json())
      .then((s: AgentStatus[]) => setStatuses(s))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (logs.some((l) => l.model?.includes("fallback"))) setApiStatus("fallback");
    else if (logs.some((l) => l.model && !l.model.includes("fallback") && isAIAgent(l.agent_id)))
      setApiStatus("ok");
  }, [logs]);

  async function toggleAgent(id: string, enable: boolean) {
    setUpdating(id);
    try {
      await fetch(`${AGENTS_URL}/agents/${id}/${enable ? "enable" : "disable"}`, { method: "PATCH" });
      setStatuses((p) => p.map((a) => a.agent_id === id ? { ...a, enabled: enable } : a));
    } finally { setUpdating(null); }
  }

  async function setLevel(id: string, level: string) {
    setUpdating(id);
    try {
      await fetch(`${AGENTS_URL}/agents/${id}/level`, {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ level }),
      });
      setStatuses((p) => p.map((a) => a.agent_id === id ? { ...a, level } : a));
    } finally { setUpdating(null); }
  }

  function getPlatformName(id: string) {
    const p = platforms[id];
    return (p?.name && p.name !== p.platform_id) ? p.name : id.replace(/^MMSI-/, "");
  }

  // 에이전트별 처리 건수
  function logCount(id: string) { return logs.filter((l) => l.agent_id === id).length; }

  // 현재 활성 경보를 발생시킨 에이전트
  const activeAlertAgents = new Set(
    alerts.filter((a) => a.status === "new").map((a) => a.generated_by)
  );

  const filteredLogs = logs
    .filter((l) => agentFilter === "all" || l.agent_id === agentFilter)
    .filter((l) => typeFilter  === "all" || l.agent_type === typeFilter);

  // 통계
  const criticalCount = alerts.filter((a) => a.status === "new" && a.severity === "critical").length;
  const warningCount  = alerts.filter((a) => a.status === "new" && a.severity === "warning").length;
  const aiCount       = logs.filter((l) => isAIAgent(l.agent_id)).length;
  const ruleCount     = logs.length - aiCount;

  // statuses가 비어있을 때 fallback 목록 생성
  function agentsOf(agentType: "rule" | "ai"): AgentStatus[] {
    const live = statuses.filter((a) => a.type === agentType);
    if (live.length > 0) return live;
    return Object.entries(AGENT_META)
      .filter(([, m]) => m.type === agentType)
      .map(([id, m]) => ({ agent_id: id, name: m.name, type: agentType, level: m.level, enabled: true }));
  }

  return (
    <div className="h-full flex flex-col overflow-hidden bg-[#020d1a]">

      {/* ── 헤더 ── */}
      <div className="flex-shrink-0 px-5 py-3 border-b border-ocean-800/60">
        <div className="flex items-center justify-between mb-3">
          <h1 className="text-sm font-bold text-white tracking-wider">에이전트 파이프라인</h1>
          <div className="flex items-center gap-4 text-xs">
            <span className="text-ocean-400">Rule <span className="text-white font-mono">{ruleCount}</span></span>
            <span className="text-ocean-400">AI <span className="text-white font-mono">{aiCount}</span></span>
            <span className="text-ocean-400">전체 <span className="text-white font-mono">{logs.length}</span>건</span>
          </div>
        </div>

        {/* API Key 경고 */}
        {apiStatus === "fallback" && (
          <div className="mb-3 px-3 py-2 bg-amber-500/10 border border-amber-500/40 rounded text-xs">
            <span className="text-amber-400 font-medium">⚠ AI 분석 불완전 </span>
            <span className="text-amber-300/70">— ANTHROPIC_API_KEY 미설정. </span>
            <code className="bg-amber-900/30 px-1 rounded text-amber-300">ANTHROPIC_API_KEY</code>
            <span className="text-amber-300/70"> 환경변수 설정 후 에이전트 재시작 필요.</span>
          </div>
        )}

        {/* ── 파이프라인 뷰 ── */}
        <PipelineView
          ruleAgents={agentsOf("rule")}
          aiAgents={agentsOf("ai")}
          logCount={logCount}
          activeAlertAgents={activeAlertAgents}
          criticalCount={criticalCount}
          warningCount={warningCount}
          platforms={platforms}
          updating={updating}
          onToggle={toggleAgent}
          onLevel={setLevel}
          apiStatus={apiStatus}
        />

        {/* ── 필터 ── */}
        <div className="flex items-center gap-2 flex-wrap mt-3">
          <div className="flex gap-1 bg-ocean-900/60 rounded-lg p-0.5">
            {(["all", "rule", "ai"] as const).map((t) => (
              <button key={t} onClick={() => setTypeFilter(t)}
                className={`text-xs px-3 py-1 rounded-md transition-colors ${
                  typeFilter === t ? "bg-ocean-700 text-white" : "text-ocean-400 hover:text-ocean-200"
                }`}>
                {t === "all" ? "전체" : t === "rule" ? "Rule" : "AI"}
              </button>
            ))}
          </div>
          <div className="flex gap-1 flex-wrap">
            <button onClick={() => setAgentFilter("all")}
              className={`text-xs px-2.5 py-1 rounded border transition-colors ${
                agentFilter === "all"
                  ? "bg-ocean-700 text-white border-ocean-600"
                  : "text-ocean-500 border-ocean-800 hover:border-ocean-600 hover:text-ocean-300"
              }`}>
              전체 ({logs.length})
            </button>
            {Object.entries(AGENT_META).map(([id, meta]) => {
              const count = logCount(id);
              if (count === 0) return null;
              return (
                <button key={id} onClick={() => setAgentFilter(id)}
                  className={`text-xs px-2.5 py-1 rounded border transition-colors ${
                    agentFilter === id ? "text-white border-current" : "text-ocean-500 border-ocean-800 hover:border-ocean-600 hover:text-ocean-300"
                  }`}
                  style={agentFilter === id ? { borderColor: meta.color, color: meta.color, background: `${meta.color}18` } : {}}>
                  {meta.name} ({count})
                </button>
              );
            })}
          </div>
          {logs.length > 0 && (
            <button onClick={clearLogs} className="ml-auto text-xs text-ocean-400 hover:text-red-400 transition-colors">
              초기화
            </button>
          )}
        </div>
      </div>

      {/* ── 로그 목록 ── */}
      <div className="flex-1 overflow-auto px-5 py-3 space-y-2">
        {filteredLogs.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-48 gap-3">
            <div className="text-4xl opacity-10 text-ocean-400">⬡</div>
            <div className="text-sm text-ocean-500">처리 기록 없음</div>
            <div className="text-xs text-ocean-500">에이전트가 경보를 처리하면 여기에 표시됩니다</div>
          </div>
        ) : (
          filteredLogs.map((log) => (
            <LogCard
              key={log.id}
              log={log}
              expanded={expandedLog === log.id}
              onToggle={() => setExpandedLog(expandedLog === log.id ? null : log.id)}
              getPlatformName={getPlatformName}
            />
          ))
        )}
      </div>
    </div>
  );
}

// ── 파이프라인 뷰 ─────────────────────────────────────────────────────────────

function PipelineView({
  ruleAgents, aiAgents, logCount, activeAlertAgents, criticalCount, warningCount,
  platforms, updating, onToggle, onLevel, apiStatus,
}: {
  ruleAgents: AgentStatus[]; aiAgents: AgentStatus[];
  logCount: (id: string) => number;
  activeAlertAgents: Set<string>;
  criticalCount: number; warningCount: number;
  platforms: Record<string, unknown>;
  updating: string | null;
  onToggle: (id: string, e: boolean) => void;
  onLevel: (id: string, l: string) => void;
  apiStatus: string;
}) {
  const platformCount = Object.keys(platforms).length;

  return (
    <div className="flex items-stretch gap-1.5 text-xs">

      {/* 노드 1: AIS 데이터 */}
      <PipelineSourceNode
        label="AIS 스트림"
        value={`${platformCount}척`}
        subtitle="실시간 위치 보고"
        color="#2e8dd4"
        active={platformCount > 0}
      />

      <PipelineArrow />

      {/* 노드 2: Rule 에이전트 */}
      <div className="flex-1 bg-ocean-900/40 border border-ocean-800/60 rounded-lg p-2.5 min-w-0">
        <div className="text-ocean-400 font-semibold mb-2 flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-ocean-500 inline-block" />
          Rule 에이전트
        </div>
        <div className="space-y-1.5">
          {ruleAgents.map((a) => (
            <PipelineAgentRow
              key={a.agent_id}
              agent={a}
              count={logCount(a.agent_id)}
              isActive={activeAlertAgents.has(a.agent_id)}
              isUpdating={updating === a.agent_id}
              onToggle={onToggle}
              onLevel={onLevel}
            />
          ))}
        </div>
      </div>

      <PipelineArrow />

      {/* 노드 3: AI 에이전트 */}
      <div className="flex-1 bg-ocean-900/40 border border-ocean-800/60 rounded-lg p-2.5 min-w-0">
        <div className="text-cyan-400 font-semibold mb-2 flex items-center gap-1.5">
          <span className={`w-1.5 h-1.5 rounded-full bg-cyan-500 inline-block ${apiStatus !== "unknown" ? "animate-pulse" : ""}`} />
          AI 에이전트
          {apiStatus === "ok" && <span className="text-green-400 font-normal ml-1">✓ Claude</span>}
          {apiStatus === "fallback" && <span className="text-amber-400 font-normal ml-1">fallback</span>}
        </div>
        <div className="space-y-1.5">
          {aiAgents.map((a) => (
            <PipelineAgentRow
              key={a.agent_id}
              agent={a}
              count={logCount(a.agent_id)}
              isActive={activeAlertAgents.has(a.agent_id)}
              isUpdating={updating === a.agent_id}
              onToggle={onToggle}
              onLevel={onLevel}
            />
          ))}
        </div>
      </div>

      <PipelineArrow />

      {/* 노드 4: 경보 출력 */}
      <div className="bg-ocean-900/40 border border-ocean-800/60 rounded-lg p-2.5 flex flex-col justify-center gap-1.5 min-w-[80px]">
        <div className="text-ocean-400 font-semibold text-center">경보 출력</div>
        {criticalCount > 0 && (
          <div className="flex items-center gap-1.5 justify-center">
            <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
            <span className="text-red-400 font-mono font-bold">{criticalCount}</span>
            <span className="text-red-400/70">위험</span>
          </div>
        )}
        {warningCount > 0 && (
          <div className="flex items-center gap-1.5 justify-center">
            <span className="w-2 h-2 rounded-full bg-amber-500" />
            <span className="text-amber-400 font-mono font-bold">{warningCount}</span>
            <span className="text-amber-400/70">주의</span>
          </div>
        )}
        {criticalCount === 0 && warningCount === 0 && (
          <div className="text-center text-ocean-400">활성 없음</div>
        )}
      </div>
    </div>
  );
}

function PipelineSourceNode({
  label, value, subtitle, color, active,
}: { label: string; value: string; subtitle: string; color: string; active: boolean }) {
  return (
    <div
      className="bg-ocean-900/40 border border-ocean-800/60 rounded-lg p-2.5 flex flex-col justify-center items-center gap-1 min-w-[76px]"
      style={{ borderColor: active ? `${color}40` : undefined }}
    >
      <span
        className={`w-2 h-2 rounded-full ${active ? "animate-pulse" : ""}`}
        style={{ background: active ? color : "#334155" }}
      />
      <div className="text-xs font-semibold text-center" style={{ color: active ? color : "#4a7a9b" }}>{label}</div>
      <div className="text-sm font-mono font-bold text-white">{value}</div>
      <div className="text-xs text-ocean-400 text-center leading-tight">{subtitle}</div>
    </div>
  );
}

function PipelineArrow() {
  return (
    <div className="flex items-center text-ocean-500 flex-shrink-0 self-center px-0.5">
      <svg width="18" height="10" viewBox="0 0 18 10" fill="none">
        <path d="M1 5h14M12 1l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    </div>
  );
}

function PipelineAgentRow({
  agent, count, isActive, isUpdating, onToggle, onLevel,
}: {
  agent: AgentStatus; count: number; isActive: boolean;
  isUpdating: boolean;
  onToggle: (id: string, e: boolean) => void;
  onLevel: (id: string, l: string) => void;
}) {
  const meta = AGENT_META[agent.agent_id];
  const color = meta?.color ?? "#7ab8d9";
  const isAI = agent.type === "ai";

  return (
    <div className={`flex items-center gap-1.5 rounded px-2 py-1.5 transition-colors ${
      agent.enabled ? "bg-ocean-800/30" : "bg-ocean-900/20 opacity-50"
    }`}>
      {/* 상태 도트 */}
      <span
        className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
          !agent.enabled ? "bg-ocean-700" :
          isActive ? isAI ? "bg-cyan-400 animate-pulse" : "bg-green-400 animate-pulse" : "bg-ocean-600"
        }`}
      />

      {/* 이름 */}
      <span className="flex-1 truncate font-medium" style={{ color: agent.enabled ? color : "#4a7a9b" }}>
        {meta?.name ?? agent.agent_id}
      </span>

      {/* 처리 건수 */}
      {count > 0 && (
        <span className="font-mono text-xs tabular-nums flex-shrink-0"
          style={{ color, opacity: 0.8 }}>
          {count}건
        </span>
      )}

      {/* 레벨 (AI만 변경 가능) */}
      {isAI ? (
        <select value={agent.level} onChange={(e) => onLevel(agent.agent_id, e.target.value)}
          disabled={isUpdating}
          className="text-xs bg-ocean-900 border border-ocean-700 text-ocean-300 rounded px-1 py-0.5 flex-shrink-0 disabled:opacity-40 cursor-pointer">
          <option value="L1">L1</option>
          <option value="L2">L2</option>
          <option value="L3">L3</option>
        </select>
      ) : (
        <span className="text-ocean-400 font-mono flex-shrink-0">{agent.level}</span>
      )}

      {/* ON/OFF */}
      <button
        onClick={() => onToggle(agent.agent_id, !agent.enabled)}
        disabled={isUpdating}
        className={`text-xs px-2 py-0.5 rounded font-medium transition-colors flex-shrink-0 disabled:opacity-40 ${
          agent.enabled ? "bg-ocean-700 text-white hover:bg-ocean-600" : "bg-ocean-800 text-ocean-500 hover:bg-ocean-700"
        }`}>
        {isUpdating ? "…" : agent.enabled ? "ON" : "OFF"}
      </button>
    </div>
  );
}

// ── 처리 기록 카드 (2단 구조) ─────────────────────────────────────────────────

function LogCard({
  log, expanded, onToggle, getPlatformName,
}: {
  log: ActivityLogEntry; expanded: boolean;
  onToggle: () => void;
  getPlatformName: (id: string) => string;
}) {
  const meta = AGENT_META[log.agent_id];
  const color = meta?.color ?? "#7ab8d9";
  const isAI = isAIAgent(log.agent_id);
  const isFallback = log.model?.includes("fallback");
  const sev = SEV[log.severity as keyof typeof SEV] ?? SEV.info;
  const isCPA = log.alert_type === "cpa";

  const cpa_nm   = typeof log.metadata?.cpa_nm   === "number" ? log.metadata.cpa_nm   : null;
  const tcpa_min = typeof log.metadata?.tcpa_min  === "number" ? log.metadata.tcpa_min : null;

  return (
    <div className={`rounded-lg border-l-[3px] border border-ocean-800/50 overflow-hidden ${sev.border}`}>

      {/* ── 1단: 요약 ── */}
      <div
        className={`px-3 py-2.5 cursor-pointer transition-colors hover:bg-ocean-800/20 ${sev.headerBg}`}
        onClick={onToggle}
      >
        {/* 헤더 행 */}
        <div className="flex items-center gap-2 flex-wrap">
          {/* 에이전트 이름 */}
          <span className="text-xs font-bold flex-shrink-0" style={{ color }}>
            {meta?.name ?? log.agent_id}
          </span>

          {/* Rule / AI 배지 */}
          <span className={`text-xs px-1.5 py-0.5 rounded flex-shrink-0 border ${
            isAI
              ? "bg-cyan-900/40 text-cyan-300 border-cyan-800/50"
              : "bg-ocean-800/60 text-ocean-400 border-ocean-700/40"
          }`}>
            {isAI ? "AI" : "Rule"}
          </span>

          {/* 경보 유형 */}
          <span className="text-xs px-1.5 py-0.5 rounded bg-ocean-800/60 text-ocean-300 border border-ocean-700/40 flex-shrink-0">
            {ALERT_TYPE_KR[log.alert_type] ?? log.alert_type}
          </span>

          {/* 심각도 배지 */}
          <span className={`text-xs font-bold flex-shrink-0 px-1.5 py-0.5 rounded ${sev.badge}`}>
            {sev.label}
          </span>

          {isFallback && (
            <span className="text-xs text-amber-400/60 flex-shrink-0">fallback</span>
          )}

          {/* 시간 */}
          <span className="ml-auto text-xs text-ocean-500 flex-shrink-0">
            {formatDistanceToNow(new Date(log.timestamp), { addSuffix: true, locale: ko })}
          </span>

          {/* 펼치기 화살표 */}
          <span className={`text-ocean-400 text-xs transition-transform flex-shrink-0 ${expanded ? "rotate-90" : ""}`}>▶</span>
        </div>

        {/* CPA: 관계 강조 표시 */}
        {isCPA && log.platform_ids.length === 2 ? (
          <div className="mt-2 flex items-center gap-2">
            <span className="text-xs px-2 py-1 rounded bg-ocean-800 text-ocean-200 font-mono border border-ocean-700/40">
              {getPlatformName(log.platform_ids[0])}
            </span>
            <div className="flex-1 flex flex-col items-center">
              <div className={`w-full h-px ${sev.dot === "bg-red-500" ? "bg-red-500/40" : "bg-amber-500/40"}`} />
              <div className="flex gap-3 text-xs mt-0.5">
                {cpa_nm   !== null && <span className={sev.text + " font-mono font-bold"}>{cpa_nm.toFixed(2)} NM</span>}
                {tcpa_min !== null && <span className="text-ocean-400 font-mono">TCPA {tcpa_min.toFixed(1)}분</span>}
              </div>
            </div>
            <span className="text-xs px-2 py-1 rounded bg-ocean-800 text-ocean-200 font-mono border border-ocean-700/40">
              {getPlatformName(log.platform_ids[1])}
            </span>
          </div>
        ) : (
          <>
            {/* 메시지 미리보기 */}
            <p className="mt-1.5 text-xs text-ocean-300 leading-snug line-clamp-1">{log.message}</p>
            {/* 관련 선박 */}
            {log.platform_ids.length > 0 && (
              <div className="flex gap-1 mt-1.5 flex-wrap">
                {log.platform_ids.slice(0, 4).map((id) => (
                  <span key={id} className="text-xs px-1.5 py-0.5 bg-ocean-800 text-ocean-300 rounded font-mono border border-ocean-700/30">
                    {getPlatformName(id)}
                  </span>
                ))}
                {log.platform_ids.length > 4 && (
                  <span className="text-xs text-ocean-400">+{log.platform_ids.length - 4}</span>
                )}
              </div>
            )}
          </>
        )}
      </div>

      {/* ── 2단: 상세 ── */}
      {expanded && (
        <div className="border-t border-ocean-800/40 bg-ocean-950/40">

          {/* 발생 시각 + 모델 */}
          <div className="px-4 pt-3 pb-1 flex items-center gap-3 text-xs text-ocean-400">
            <span>{format(new Date(log.timestamp), "yyyy/MM/dd HH:mm:ss")}</span>
            {log.model && (
              <span className="px-1.5 py-0.5 bg-ocean-800/60 text-ocean-400 rounded border border-ocean-700/40">
                {log.model}
              </span>
            )}
          </div>

          {/* 섹션: 왜 발생했는가 */}
          <DetailSection title="발생 원인 / 입력 데이터" icon="→">
            {meta && (
              <div className="space-y-1.5">
                {/* 트리거 조건 */}
                <DataRow label="트리거 조건" value={meta.trigger} />
                {/* 입력 데이터 */}
                <DataRow label="분석 대상" value={meta.input} />
                {/* AI 에이전트라면 어떤 에이전트가 트리거했는지 */}
                {isAI && meta.triggeredBy && AGENT_META[meta.triggeredBy] && (
                  <DataRow
                    label="트리거한 에이전트"
                    value={AGENT_META[meta.triggeredBy].name}
                    highlight={AGENT_META[meta.triggeredBy].color}
                  />
                )}
                {/* CPA 수치 */}
                {isCPA && (cpa_nm !== null || tcpa_min !== null) && (
                  <div className="flex gap-4 mt-1">
                    {cpa_nm   !== null && <MetricBadge label="CPA"  value={`${cpa_nm.toFixed(3)} NM`}  sev={log.severity} />}
                    {tcpa_min !== null && <MetricBadge label="TCPA" value={`${tcpa_min.toFixed(1)} 분`} sev={log.severity} />}
                  </div>
                )}
                {/* 기타 메타데이터 */}
                {Object.entries(log.metadata ?? {})
                  .filter(([k]) => !["cpa_nm", "tcpa_min", "dedup_key", "ai_model"].includes(k))
                  .map(([k, v]) => (
                    <DataRow key={k} label={k} value={String(v)} />
                  ))
                }
              </div>
            )}
            {/* 관련 선박 상세 (CPA일 때 양 선박 표시) */}
            {log.platform_ids.length > 0 && (
              <div className="mt-2 flex gap-2 flex-wrap">
                {log.platform_ids.map((id, i) => (
                  <span key={id} className="text-xs px-2 py-1 bg-ocean-800/60 text-ocean-200 rounded font-mono border border-ocean-700/40">
                    {isCPA && log.platform_ids.length === 2
                      ? <><span className="text-ocean-500 mr-1">{i === 0 ? "선박 A" : "선박 B"}</span>{id.replace(/^MMSI-/, "")}</>
                      : id.replace(/^MMSI-/, "")
                    }
                  </span>
                ))}
              </div>
            )}
          </DetailSection>

          {/* 섹션: 처리 결과 */}
          <DetailSection title="처리 결과 / 출력" icon="⬡">
            <p className="text-xs text-ocean-200 leading-relaxed">{log.message}</p>
            {meta && <div className="mt-1.5 text-xs text-ocean-500">{meta.output}</div>}
          </DetailSection>

          {/* 섹션: AI 권고 (AI 에이전트만) */}
          {isAI && (
            <DetailSection
              title={isFallback ? "AI 권고 (fallback 모드)" : "AI 권고"}
              icon="✦"
              accent={isFallback ? "amber" : "cyan"}
            >
              {log.recommendation ? (
                <pre className="text-xs text-ocean-100 leading-relaxed whitespace-pre-wrap font-sans">
                  {log.recommendation}
                </pre>
              ) : (
                <p className="text-xs text-ocean-400 italic">
                  {log.model?.includes("L1") || !log.model
                    ? "L1 모드 — 권고 생성 비활성"
                    : "LLM 호출 결과 없음"}
                </p>
              )}
            </DetailSection>
          )}
        </div>
      )}
    </div>
  );
}

// ── 공통 UI 부품 ──────────────────────────────────────────────────────────────

function DetailSection({
  title, icon, accent = "ocean", children,
}: {
  title: string; icon: string;
  accent?: "ocean" | "cyan" | "amber";
  children: React.ReactNode;
}) {
  const accentColor = {
    ocean: "text-ocean-500",
    cyan:  "text-cyan-400",
    amber: "text-amber-400",
  }[accent];

  return (
    <div className="px-4 py-2.5 border-t border-ocean-800/30">
      <div className={`flex items-center gap-1.5 text-xs font-semibold mb-2 ${accentColor}`}>
        <span>{icon}</span>
        <span>{title}</span>
      </div>
      {children}
    </div>
  );
}

function DataRow({ label, value, highlight }: { label: string; value: string; highlight?: string }) {
  return (
    <div className="flex items-start gap-2 text-xs">
      <span className="text-ocean-400 flex-shrink-0 w-24">{label}</span>
      <span className="text-ocean-300 leading-snug" style={highlight ? { color: highlight } : undefined}>
        {value}
      </span>
    </div>
  );
}

function MetricBadge({ label, value, sev }: { label: string; value: string; sev: string }) {
  const color = sev === "critical" ? "text-red-300 border-red-700/50 bg-red-950/50"
    : sev === "warning" ? "text-amber-300 border-amber-700/50 bg-amber-950/50"
    : "text-blue-300 border-blue-700/50 bg-blue-950/50";

  return (
    <div className={`rounded px-2.5 py-1.5 border ${color} text-center`}>
      <div className="text-xs opacity-60">{label}</div>
      <div className="text-sm font-mono font-bold">{value}</div>
    </div>
  );
}
