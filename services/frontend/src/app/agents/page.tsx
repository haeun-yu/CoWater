"use client";

import { useEffect, useState } from "react";
import {
  useAILogStore,
  isAIAgent,
  type ActivityLogEntry,
} from "@/stores/aiLogStore";
import { useAlertStore } from "@/stores/alertStore";
import { usePlatformStore } from "@/stores/platformStore";
import { formatDistanceToNow, format } from "date-fns";
import { ko } from "date-fns/locale";

const AGENTS_URL =
  process.env.NEXT_PUBLIC_AGENTS_URL ?? "http://localhost:7701";

// ── 에이전트 메타 ──────────────────────────────────────────────────────────────

interface PipelineStepDef {
  icon: string;
  title: string;
  sub: string;
  tone?: "idle" | "active" | "alert";
}

interface AgentMeta {
  name: string;
  type: "rule" | "ai";
  level: string;
  role: string;
  trigger: string;
  output: string;
  color: string;
  input: string;
  triggeredBy?: string; // 이 AI 에이전트를 호출하는 Rule 에이전트 ID
  pipeline: PipelineStepDef[];
  subProcess?: { from: string; to: string } | null;
}

const AGENT_META: Record<string, AgentMeta> = {
  "cpa-agent": {
    name: "CPA/TCPA",
    type: "rule",
    level: "L1",
    color: "#2e8dd4",
    role: "충돌 위험 감지",
    trigger: "CPA < 0.5nm & TCPA < 30분 (critical: 0.2nm & 10분)",
    output: "cpa 경보 발생",
    input: "전체 선박 위치·속도·침로 (실시간 AIS 스트림)",
    pipeline: [
      { icon: "◈", title: "데이터 수신", sub: "AIS 위치·속도·침로" },
      {
        icon: "⊕",
        title: "쌍방 CPA 계산",
        sub: "전 선박 조합 벡터 연산",
        tone: "active",
      },
      { icon: "◉", title: "임계값 비교", sub: "0.2NM·10min / 0.5NM·30min" },
      { icon: "◎", title: "경보 발행", sub: "cpa Alert" },
    ],
    subProcess: { from: "CPAAgent (critical)", to: "ReportAgent (LLM)" },
  },
  "zone-monitor": {
    name: "Zone Monitor",
    type: "rule",
    level: "L1",
    color: "#22d3ee",
    role: "구역 침입 감시",
    trigger: "선박 위치 ∈ 설정된 금지/주의 구역 경계 내",
    output: "zone_intrusion 경보 발생",
    input: "선박 위치 + 사전 설정된 구역 GeoJSON 경계",
    pipeline: [
      { icon: "◈", title: "위치 수신", sub: "선박 AIS 좌표" },
      {
        icon: "⊕",
        title: "구역 로드",
        sub: "GeoJSON 폴리곤 경계 (5분 갱신)",
        tone: "active",
      },
      { icon: "◉", title: "포함 검사", sub: "Point-in-Polygon" },
      { icon: "◎", title: "경보 발행", sub: "zone_intrusion Alert" },
    ],
    subProcess: { from: "ZoneMonitor (critical)", to: "ReportAgent (LLM)" },
  },
  "anomaly-rule": {
    name: "Anomaly Rule",
    type: "rule",
    level: "L1",
    color: "#fbbf24",
    role: "이상 행동 탐지",
    trigger: "AIS 90초 소실 | SOG ≥5kt 급감 | ROT ≥25°/min",
    output: "anomaly / ais_off 경보 발생",
    input: "AIS 위치 보고 스트림 (타임스탬프·속도·회전율)",
    pipeline: [
      { icon: "◈", title: "데이터 수신", sub: "AIS 스트림 (20초 타이머)" },
      {
        icon: "⊕",
        title: "상태 캐싱",
        sub: "속도·선회율·타임스탬프",
        tone: "active",
      },
      {
        icon: "◉",
        title: "이상 조건 검사",
        sub: "AIS 90s 소실 · SOG▼5kt · ROT▲25°",
      },
      { icon: "◎", title: "경보 발행", sub: "anomaly / ais_off Alert" },
    ],
    subProcess: { from: "AnomalyRule", to: "AnomalyAI (LLM)" },
  },
  "anomaly-ai": {
    name: "Anomaly AI",
    type: "ai",
    level: "L2",
    color: "#a78bfa",
    role: "이상 행동 AI 분석",
    trigger: "Anomaly Rule 에이전트의 anomaly/ais_off 경보 수신",
    output: "원인 진단 + 대응 권고",
    input: "Rule 경보 데이터 (선박 ID·마지막 위치·속도·상태) + 이상 유형",
    triggeredBy: "anomaly-rule",
    pipeline: [
      { icon: "◈", title: "경보 수신", sub: "anomaly-rule 트리거" },
      {
        icon: "⊕",
        title: "컨텍스트 구성",
        sub: "경보 + 최근 선박 위치",
        tone: "active",
      },
      { icon: "◉", title: "LLM 분석", sub: "Claude / Ollama 추론" },
      { icon: "◎", title: "권고 발행", sub: "compliance Alert (진단+권고)" },
    ],
    subProcess: null,
  },
  "distress-agent": {
    name: "Distress",
    type: "ai",
    level: "L3",
    color: "#f87171",
    role: "조난 상황 대응",
    trigger:
      "nav_status: not_under_command/aground (직접) 또는 ais_off warning (anomaly-rule 경유)",
    output: "SAR 대응 지침 생성",
    input: "조난 신호·AIS 소실 경보 + 선박 마지막 위치·상태",
    triggeredBy: "platform_report / anomaly-rule",
    pipeline: [
      { icon: "◈", title: "조난 감지", sub: "nav_status 직접 or ais_off 경보" },
      {
        icon: "⊕",
        title: "상황 판단",
        sub: "not_under_command · aground · ais_소실",
        tone: "active",
      },
      { icon: "◉", title: "SAR 대응 생성", sub: "L2+ LLM 권고문 생성" },
      { icon: "◎", title: "경보 발행", sub: "distress Alert (critical)" },
    ],
    subProcess: { from: "Distress (critical)", to: "ReportAgent (LLM)" },
  },
  "report-agent": {
    name: "Report",
    type: "ai",
    level: "L2",
    color: "#34d399",
    role: "사건 보고서 생성",
    trigger: "critical 경보 수신 (cpa / zone_intrusion / distress)",
    output: "AI 종합 사건 보고서",
    input: "경보 데이터 + 관련 선박 이력 + 구역 정보",
    triggeredBy: "cpa-agent / zone-monitor / distress-agent",
    pipeline: [
      {
        icon: "◈",
        title: "Critical 수신",
        sub: "cpa · distress · zone_intrusion",
      },
      {
        icon: "⊕",
        title: "데이터 수집",
        sub: "경보 + 선박 이력",
        tone: "active",
      },
      { icon: "◉", title: "보고서 생성", sub: "Claude / Ollama LLM" },
      { icon: "◎", title: "보고서 발행", sub: "compliance Info" },
    ],
    subProcess: null,
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
  cpa: "충돌 위험",
  zone_intrusion: "구역 침입",
  anomaly: "이상 행동",
  ais_off: "AIS 소실",
  distress: "조난",
  compliance: "상황 보고",
};

// ── Agent Status (API 응답) ────────────────────────────────────────────────────
// 백엔드 base.py health()는 "type" 키로 반환 — agent_type이 아님

interface AgentStatus {
  agent_id: string;
  name: string;
  type: string; // API 반환 키: "type" (rule | ai)
  level: string;
  enabled: boolean;
  failure_count?: number;
  last_error?: string | null;
}

// ── 페이지 ────────────────────────────────────────────────────────────────────

export default function AgentsPage() {
  const logs = useAILogStore((s) => s.logs);
  const clearLogs = useAILogStore((s) => s.clear);
  const alerts = useAlertStore((s) => s.alerts);
  const platforms = usePlatformStore((s) => s.platforms);

  const [agentFilter, setAgentFilter] = useState<string>("all");
  const [typeFilter, setTypeFilter] = useState<"all" | "rule" | "ai">("all");
  const [expandedLog, setExpandedLog] = useState<string | null>(null);
  const [statuses, setStatuses] = useState<AgentStatus[]>([]);
  const [updating, setUpdating] = useState<string | null>(null);
  const [apiStatus, setApiStatus] = useState<"ok" | "fallback" | "unknown">(
    "unknown",
  );
  const [runtimeMode, setRuntimeMode] = useState<
    "Autonomous Control" | "Human-in-the-Loop" | "Observation Only"
  >("Autonomous Control");

  useEffect(() => {
    fetch(`${AGENTS_URL}/agents`)
      .then((r) => r.json())
      .then((s: AgentStatus[]) => setStatuses(s))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (logs.some((l) => l.model?.includes("fallback")))
      setApiStatus("fallback");
    else if (
      logs.some(
        (l) =>
          l.model && !l.model.includes("fallback") && isAIAgent(l.agent_id),
      )
    )
      setApiStatus("ok");
  }, [logs]);

  async function toggleAgent(id: string, enable: boolean) {
    setUpdating(id);
    try {
      await fetch(
        `${AGENTS_URL}/agents/${id}/${enable ? "enable" : "disable"}`,
        { method: "PATCH" },
      );
      setStatuses((p) =>
        p.map((a) => (a.agent_id === id ? { ...a, enabled: enable } : a)),
      );
    } finally {
      setUpdating(null);
    }
  }

  async function setLevel(id: string, level: string) {
    setUpdating(id);
    try {
      await fetch(`${AGENTS_URL}/agents/${id}/level`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ level }),
      });
      setStatuses((p) =>
        p.map((a) => (a.agent_id === id ? { ...a, level } : a)),
      );
    } finally {
      setUpdating(null);
    }
  }

  function getPlatformName(id: string) {
    const p = platforms[id];
    return p?.name && p.name !== p.platform_id
      ? p.name
      : id.replace(/^MMSI-/, "");
  }

  // 에이전트별 처리 건수
  function logCount(id: string) {
    return logs.filter((l) => l.agent_id === id).length;
  }

  // 현재 활성 경보를 발생시킨 에이전트
  const activeAlertAgents = new Set(
    alerts.filter((a) => a.status === "new").map((a) => a.generated_by),
  );

  const filteredLogs = logs
    .filter((l) => agentFilter === "all" || l.agent_id === agentFilter)
    .filter((l) => typeFilter === "all" || l.agent_type === typeFilter);

  // 통계
  const criticalCount = alerts.filter(
    (a) => a.status === "new" && a.severity === "critical",
  ).length;
  const warningCount = alerts.filter(
    (a) => a.status === "new" && a.severity === "warning",
  ).length;
  const aiCount = logs.filter((l) => isAIAgent(l.agent_id)).length;
  const ruleCount = logs.length - aiCount;

  // statuses가 비어있을 때 fallback 목록 생성
  function agentsOf(agentType: "rule" | "ai"): AgentStatus[] {
    const live = statuses.filter((a) => a.type === agentType);
    if (live.length > 0) return live;
    return Object.entries(AGENT_META)
      .filter(([, m]) => m.type === agentType)
      .map(([id, m]) => ({
        agent_id: id,
        name: m.name,
        type: agentType,
        level: m.level,
        enabled: true,
      }));
  }

  const ruleAgents = agentsOf("rule");
  const aiAgents = agentsOf("ai");
  const focusAgentId =
    agentFilter === "all"
      ? (filteredLogs[0]?.agent_id ?? "cpa-agent")
      : agentFilter;
  const focusMeta = AGENT_META[focusAgentId] ?? AGENT_META["cpa-agent"];

  return (
    <div className="h-full overflow-hidden bg-slate-950 text-slate-200">
      <header className="h-16 border-b border-slate-800 px-5 flex items-center justify-between">
        <div>
          <h1 className="text-sm font-bold tracking-wide text-white">
            통합 에이전트 관제
          </h1>
          <p className="text-[11px] text-slate-500 mt-0.5">
            Rule 동기 처리 + AI 비동기 처리 파이프라인
          </p>
        </div>
        <div className="flex items-center gap-4 text-xs">
          <span className="text-ocean-400">
            Rule <span className="text-white font-mono">{ruleCount}</span>
          </span>
          <span className="text-cyan-400">
            AI <span className="text-white font-mono">{aiCount}</span>
          </span>
          <span className="text-slate-400">
            이벤트 <span className="text-white font-mono">{logs.length}</span>
          </span>
        </div>
      </header>

      <main className="h-[calc(100%-64px)] grid grid-cols-1 xl:grid-cols-[280px_minmax(0,1fr)_460px] overflow-hidden">
        <section className="border-r border-slate-800 bg-slate-950/60 flex flex-col overflow-hidden">
          <div className="p-4 border-b border-slate-800">
            <div className="text-[11px] text-slate-500 uppercase tracking-widest font-bold">
              Agent Orchestrator
            </div>
          </div>
          <div className="flex-1 overflow-auto p-4 space-y-5">
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-[10px] text-blue-400 font-bold uppercase">
                  Rule Based (Synchronous)
                </span>
                <span className="text-[10px] text-slate-600">
                  {ruleAgents.filter((a) => a.enabled).length} Active
                </span>
              </div>
              <div className="space-y-1.5">
                {ruleAgents.map((a) => {
                  const selected = agentFilter === a.agent_id;
                  return (
                    <button
                      key={a.agent_id}
                      onClick={() => {
                        setAgentFilter(a.agent_id);
                        setTypeFilter("rule");
                      }}
                      className={`w-full text-left p-2.5 rounded border text-xs font-semibold transition-colors ${selected ? "bg-blue-600/10 border-blue-500/30 text-white" : "bg-slate-900/50 border-slate-800 text-slate-400 hover:text-slate-200"}`}
                    >
                      <div className="flex items-center justify-between">
                        <span>
                          {AGENT_META[a.agent_id]?.name ?? a.agent_id}
                        </span>
                        <span className="text-[10px]">↻</span>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-[10px] text-violet-400 font-bold uppercase">
                  AI Based (Asynchronous)
                </span>
                <span className="text-[10px] text-slate-600">
                  {aiAgents.filter((a) => a.enabled).length} Ready
                </span>
              </div>
              <div className="space-y-1.5">
                {aiAgents.map((a) => {
                  const selected = agentFilter === a.agent_id;
                  return (
                    <button
                      key={a.agent_id}
                      onClick={() => {
                        setAgentFilter(a.agent_id);
                        setTypeFilter("ai");
                      }}
                      className={`w-full text-left p-2.5 rounded border text-xs font-semibold transition-colors ${selected ? "bg-violet-600/10 border-violet-500/30 text-white" : "bg-slate-900 border-slate-800 text-slate-400 hover:text-slate-200"}`}
                    >
                      <div className="flex items-center justify-between">
                        <span>
                          {AGENT_META[a.agent_id]?.name ?? a.agent_id}
                        </span>
                        <span className="text-[10px]">⚡</span>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
          <div className="p-4 border-t border-slate-800">
            <button
              onClick={() => {
                setAgentFilter("all");
                setTypeFilter("all");
              }}
              className="w-full text-xs py-1.5 rounded border border-slate-700 text-slate-300 hover:border-slate-500"
            >
              전체 에이전트 보기
            </button>
          </div>
        </section>

        <section className="border-r border-slate-800 flex flex-col overflow-hidden">
          <div className="p-5 border-b border-slate-800 flex items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-bold text-white tracking-tight">
                Agent Pipeline Flow
              </h2>
              <p className="text-xs text-slate-500 mt-1">
                {focusMeta.name}: {focusMeta.role}
              </p>
            </div>
            <span className="px-2 py-1 text-[10px] rounded border border-emerald-500/30 text-emerald-300 bg-emerald-500/10">
              LATENCY: {Math.max(8, Math.min(42, logs.length || 12))}ms
            </span>
          </div>
          <div className="flex-1 overflow-auto p-4 bg-[radial-gradient(#1e293b_1px,transparent_1px)] [background-size:24px_24px]">
            <HorizontalPipeline
              steps={focusMeta.pipeline}
              criticalCount={criticalCount}
              warningCount={warningCount}
              active={logs.length > 0}
            />
          </div>
          <div className="border-t border-slate-800 bg-slate-900/30 h-44 px-6 flex items-center gap-6">
            <div className="flex-none">
              <div className="text-[10px] text-slate-500 font-bold uppercase mb-2">
                Sub-Process Trigger
              </div>
              {focusMeta.subProcess ? (
                <div className="flex items-center gap-3 text-xs font-mono">
                  <span className="px-3 py-2 bg-slate-950 border border-slate-800 rounded">
                    {focusMeta.subProcess.from}
                  </span>
                  <span className="text-slate-600">→</span>
                  <span className="px-3 py-2 bg-violet-600/20 border border-violet-500/50 rounded text-violet-400 font-bold">
                    {focusMeta.subProcess.to}
                  </span>
                </div>
              ) : (
                <div className="text-xs text-slate-600 italic font-mono">
                  독립 실행 에이전트
                </div>
              )}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex justify-between items-end mb-2 text-[10px]">
                <span className="text-slate-400 italic">
                  Reasoning Progress
                </span>
                <span className="text-violet-400 font-mono">
                  {apiStatus === "fallback" ? "Fallback mode" : "Generating"}
                </span>
              </div>
              <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
                <div
                  className="bg-violet-500 h-full"
                  style={{
                    width: `${Math.min(100, 25 + (logs.length % 15) * 5)}%`,
                  }}
                />
              </div>
            </div>
          </div>
        </section>

        <section className="bg-slate-950 flex flex-col overflow-hidden">
          <div className="p-4 border-b border-slate-800 space-y-3">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-sm font-bold text-white">
                  Agent Detail &amp; Runtime
                </h3>
                <p className="text-[10px] text-slate-500 mt-0.5">
                  {focusMeta.name} · {focusMeta.role}
                </p>
                <div className="flex gap-1 mt-1.5">
                  <span className="px-2 py-0.5 bg-blue-500/20 text-blue-400 text-[10px] font-bold border border-blue-500/20 rounded">
                    {focusMeta.level} Operation
                  </span>
                  <span className="px-2 py-0.5 bg-slate-800 text-slate-400 text-[10px] font-bold rounded">
                    AUTO-RECOVERY
                  </span>
                </div>
              </div>
              <button
                onClick={clearLogs}
                className="text-[10px] px-2 py-1 rounded border border-slate-700 text-slate-300 hover:border-red-500/60 hover:text-red-300"
              >
                로그 초기화
              </button>
            </div>

            {apiStatus === "fallback" && (
              <div className="px-2.5 py-2 bg-amber-500/10 border border-amber-500/40 rounded text-xs text-amber-300">
                ANTHROPIC_API_KEY 미설정으로 fallback 권고가 생성 중입니다.
              </div>
            )}

            <div className="grid grid-cols-2 gap-2">
              <div className="bg-slate-900/50 border border-slate-800 p-2 rounded">
                <div className="text-[9px] text-slate-500 uppercase font-bold mb-1">
                  Input (Prompt)
                </div>
                <p className="text-[10px] text-slate-400 font-mono leading-tight line-clamp-2">
                  {focusMeta.input}
                </p>
              </div>
              <div className="bg-violet-900/10 border border-violet-500/20 p-2 rounded">
                <div className="text-[9px] text-violet-400 uppercase font-bold mb-1">
                  Result (Completion)
                </div>
                <p className="text-[10px] text-violet-300 font-mono leading-tight line-clamp-2">
                  {focusMeta.output}
                </p>
              </div>
            </div>

            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="text-[11px] text-slate-400">Current Mode</span>
                <select
                  value={runtimeMode}
                  onChange={(e) =>
                    setRuntimeMode(
                      e.target.value as
                        | "Autonomous Control"
                        | "Human-in-the-Loop"
                        | "Observation Only",
                    )
                  }
                  className="bg-slate-900 border border-slate-700 rounded text-[10px] py-1 pl-2 pr-8 text-white"
                >
                  <option>Autonomous Control</option>
                  <option>Human-in-the-Loop</option>
                  <option>Observation Only</option>
                </select>
              </div>
              <button className="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded text-[10px] font-bold transition-colors">
                Apply Config
              </button>
            </div>

            <div className="flex items-center gap-2 flex-wrap">
              {(["all", "rule", "ai"] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setTypeFilter(t)}
                  className={`text-xs px-2.5 py-1 rounded border ${typeFilter === t ? "bg-ocean-700 text-white border-ocean-600" : "border-slate-700 text-slate-400"}`}
                >
                  {t === "all" ? "전체" : t.toUpperCase()}
                </button>
              ))}
            </div>
          </div>

          <div className="flex-1 overflow-auto p-3 space-y-2">
            {filteredLogs.length === 0 ? (
              <div className="h-full flex items-center justify-center text-sm text-slate-500">
                처리 기록 없음
              </div>
            ) : (
              filteredLogs.map((log) => (
                <LogCard
                  key={log.id}
                  log={log}
                  expanded={expandedLog === log.id}
                  onToggle={() =>
                    setExpandedLog(expandedLog === log.id ? null : log.id)
                  }
                  getPlatformName={getPlatformName}
                />
              ))
            )}
          </div>
        </section>
      </main>
    </div>
  );
}

// ── 파이프라인 뷰 ─────────────────────────────────────────────────────────────

function PipelineView({
  ruleAgents,
  aiAgents,
  logCount,
  activeAlertAgents,
  criticalCount,
  warningCount,
  platforms,
  updating,
  onToggle,
  onLevel,
  apiStatus,
}: {
  ruleAgents: AgentStatus[];
  aiAgents: AgentStatus[];
  logCount: (id: string) => number;
  activeAlertAgents: Set<string>;
  criticalCount: number;
  warningCount: number;
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
          <span
            className={`w-1.5 h-1.5 rounded-full bg-cyan-500 inline-block ${apiStatus !== "unknown" ? "animate-pulse" : ""}`}
          />
          AI 에이전트
          {apiStatus === "ok" && (
            <span className="text-green-400 font-normal ml-1">✓ Claude</span>
          )}
          {apiStatus === "fallback" && (
            <span className="text-amber-400 font-normal ml-1">fallback</span>
          )}
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
        <div className="text-ocean-400 font-semibold text-center">
          경보 출력
        </div>
        {criticalCount > 0 && (
          <div className="flex items-center gap-1.5 justify-center">
            <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
            <span className="text-red-400 font-mono font-bold">
              {criticalCount}
            </span>
            <span className="text-red-400/70">위험</span>
          </div>
        )}
        {warningCount > 0 && (
          <div className="flex items-center gap-1.5 justify-center">
            <span className="w-2 h-2 rounded-full bg-amber-500" />
            <span className="text-amber-400 font-mono font-bold">
              {warningCount}
            </span>
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
  label,
  value,
  subtitle,
  color,
  active,
}: {
  label: string;
  value: string;
  subtitle: string;
  color: string;
  active: boolean;
}) {
  return (
    <div
      className="bg-ocean-900/40 border border-ocean-800/60 rounded-lg p-2.5 flex flex-col justify-center items-center gap-1 min-w-[76px]"
      style={{ borderColor: active ? `${color}40` : undefined }}
    >
      <span
        className={`w-2 h-2 rounded-full ${active ? "animate-pulse" : ""}`}
        style={{ background: active ? color : "#334155" }}
      />
      <div
        className="text-xs font-semibold text-center"
        style={{ color: active ? color : "#4a7a9b" }}
      >
        {label}
      </div>
      <div className="text-sm font-mono font-bold text-white">{value}</div>
      <div className="text-xs text-ocean-400 text-center leading-tight">
        {subtitle}
      </div>
    </div>
  );
}

function PipelineArrow() {
  return (
    <div className="flex items-center text-ocean-500 flex-shrink-0 self-center px-0.5">
      <svg width="18" height="10" viewBox="0 0 18 10" fill="none">
        <path
          d="M1 5h14M12 1l4 4-4 4"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
}

function HorizontalPipeline({
  steps,
  criticalCount,
  warningCount,
  active,
}: {
  steps: PipelineStepDef[];
  criticalCount: number;
  warningCount: number;
  active: boolean;
}) {
  const hit = criticalCount > 0 || warningCount > 0;
  const nodes: React.ReactNode[] = [];
  steps.forEach((step, i) => {
    const isLast = i === steps.length - 1;
    const tone: "idle" | "active" | "alert" =
      step.tone ??
      (isLast ? (hit ? "alert" : "active") : i === 0 ? "idle" : "active");
    const resolvedTone: "idle" | "active" | "alert" =
      (isLast || i === steps.length - 2) && hit ? "alert" : tone;
    nodes.push(
      <PipelineStep
        key={`step-${i}`}
        icon={step.icon}
        title={step.title}
        sub={step.sub}
        tone={resolvedTone}
      />,
    );
    if (!isLast) {
      nodes.push(<PipelineRail key={`rail-${i}`} pulse={active} />);
    }
  });
  return (
    <div className="flex items-center w-full max-w-4xl mx-auto justify-between relative px-2 py-10">
      {nodes}
    </div>
  );
}

function PipelineRail({ pulse, label }: { pulse: boolean; label?: string }) {
  return (
    <div
      className="flex-1 h-[2px] mx-3 relative"
      style={{
        backgroundImage: "linear-gradient(90deg, #3b82f6 50%, transparent 50%)",
        backgroundSize: "8px 1px",
      }}
    >
      {pulse && (
        <div className="absolute -top-1 w-2 h-2 bg-blue-500 rounded-full animate-ping left-[30%]" />
      )}
      {label && (
        <span className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-[10px] bg-slate-950 px-2 text-blue-500 font-mono">
          {label}
        </span>
      )}
    </div>
  );
}

function PipelineStep({
  icon,
  title,
  sub,
  tone,
}: {
  icon: string;
  title: string;
  sub: string;
  tone: "idle" | "active" | "alert";
}) {
  const toneClass =
    tone === "alert"
      ? "bg-red-500/20 border-red-500 text-red-400"
      : tone === "active"
        ? "bg-blue-600/10 border-blue-500 text-blue-400"
        : "bg-slate-900 border-slate-700 text-slate-300";

  return (
    <div className="z-10 flex flex-col items-center gap-3">
      <div
        className={`w-16 h-16 rounded-xl border-2 flex items-center justify-center shadow-2xl ${toneClass} ${tone === "alert" ? "animate-pulse" : ""}`}
      >
        <span className="text-3xl">{icon}</span>
      </div>
      <div className="text-center">
        <div className="text-[11px] font-bold text-white">{title}</div>
        <div className="text-[9px] text-slate-500">{sub}</div>
      </div>
    </div>
  );
}

function PipelineAgentRow({
  agent,
  count,
  isActive,
  isUpdating,
  onToggle,
  onLevel,
}: {
  agent: AgentStatus;
  count: number;
  isActive: boolean;
  isUpdating: boolean;
  onToggle: (id: string, e: boolean) => void;
  onLevel: (id: string, l: string) => void;
}) {
  const meta = AGENT_META[agent.agent_id];
  const color = meta?.color ?? "#7ab8d9";
  const isAI = agent.type === "ai";

  return (
    <div
      className={`flex items-center gap-1.5 rounded px-2 py-1.5 transition-colors ${
        agent.enabled ? "bg-ocean-800/30" : "bg-ocean-900/20 opacity-50"
      }`}
    >
      {/* 상태 도트 */}
      <span
        className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
          !agent.enabled
            ? "bg-ocean-700"
            : isActive
              ? isAI
                ? "bg-cyan-400 animate-pulse"
                : "bg-green-400 animate-pulse"
              : "bg-ocean-600"
        }`}
      />

      {/* 이름 */}
      <span
        className="flex-1 truncate font-medium"
        style={{ color: agent.enabled ? color : "#4a7a9b" }}
      >
        {meta?.name ?? agent.agent_id}
      </span>

      {/* 처리 건수 */}
      {count > 0 && (
        <span
          className="font-mono text-xs tabular-nums flex-shrink-0"
          style={{ color, opacity: 0.8 }}
        >
          {count}건
        </span>
      )}

      {/* 레벨 (AI만 변경 가능) */}
      {isAI ? (
        <select
          value={agent.level}
          onChange={(e) => onLevel(agent.agent_id, e.target.value)}
          disabled={isUpdating}
          className="text-xs bg-ocean-900 border border-ocean-700 text-ocean-300 rounded px-1 py-0.5 flex-shrink-0 disabled:opacity-40 cursor-pointer"
        >
          <option value="L1">L1</option>
          <option value="L2">L2</option>
          <option value="L3">L3</option>
        </select>
      ) : (
        <span className="text-ocean-400 font-mono flex-shrink-0">
          {agent.level}
        </span>
      )}

      {/* ON/OFF */}
      <button
        onClick={() => onToggle(agent.agent_id, !agent.enabled)}
        disabled={isUpdating}
        className={`text-xs px-2 py-0.5 rounded font-medium transition-colors flex-shrink-0 disabled:opacity-40 ${
          agent.enabled
            ? "bg-ocean-700 text-white hover:bg-ocean-600"
            : "bg-ocean-800 text-ocean-500 hover:bg-ocean-700"
        }`}
      >
        {isUpdating ? "…" : agent.enabled ? "ON" : "OFF"}
      </button>
    </div>
  );
}

// ── 처리 기록 카드 (2단 구조) ─────────────────────────────────────────────────

function LogCard({
  log,
  expanded,
  onToggle,
  getPlatformName,
}: {
  log: ActivityLogEntry;
  expanded: boolean;
  onToggle: () => void;
  getPlatformName: (id: string) => string;
}) {
  const meta = AGENT_META[log.agent_id];
  const color = meta?.color ?? "#7ab8d9";
  const isAI = isAIAgent(log.agent_id);
  const isFallback = log.model?.includes("fallback");
  const sev = SEV[log.severity as keyof typeof SEV] ?? SEV.info;
  const isCPA = log.alert_type === "cpa";

  const cpa_nm =
    typeof log.metadata?.cpa_nm === "number" ? log.metadata.cpa_nm : null;
  const tcpa_min =
    typeof log.metadata?.tcpa_min === "number" ? log.metadata.tcpa_min : null;

  return (
    <div
      className={`rounded-lg border-l-2 border border-ocean-800/50 overflow-hidden ${sev.border}`}
    >
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
          <span
            className={`text-xs px-1.5 py-0.5 rounded flex-shrink-0 border ${
              isAI
                ? "bg-cyan-900/40 text-cyan-300 border-cyan-800/50"
                : "bg-ocean-800/60 text-ocean-400 border-ocean-700/40"
            }`}
          >
            {isAI ? "AI" : "Rule"}
          </span>

          {/* 경보 유형 */}
          <span className="text-xs px-1.5 py-0.5 rounded bg-ocean-800/60 text-ocean-300 border border-ocean-700/40 flex-shrink-0">
            {ALERT_TYPE_KR[log.alert_type] ?? log.alert_type}
          </span>

          {/* 심각도 배지 */}
          <span
            className={`text-xs font-bold flex-shrink-0 px-1.5 py-0.5 rounded ${sev.badge}`}
          >
            {sev.label}
          </span>

          {isFallback && (
            <span className="text-xs text-amber-400/60 flex-shrink-0">
              fallback
            </span>
          )}

          {/* 시간 */}
          <span className="ml-auto text-xs text-ocean-500 flex-shrink-0">
            {formatDistanceToNow(new Date(log.timestamp), {
              addSuffix: true,
              locale: ko,
            })}
          </span>

          {/* 펼치기 화살표 */}
          <span
            className={`text-ocean-400 text-xs transition-transform flex-shrink-0 ${expanded ? "rotate-90" : ""}`}
          >
            ▶
          </span>
        </div>

        {/* CPA: 관계 강조 표시 */}
        {isCPA && log.platform_ids.length === 2 ? (
          <div className="mt-2 flex items-center gap-2">
            <span className="text-xs px-2 py-1 rounded bg-ocean-800 text-ocean-200 font-mono border border-ocean-700/40">
              {getPlatformName(log.platform_ids[0])}
            </span>
            <div className="flex-1 flex flex-col items-center">
              <div
                className={`w-full h-px ${sev.dot === "bg-red-500" ? "bg-red-500/40" : "bg-amber-500/40"}`}
              />
              <div className="flex gap-3 text-xs mt-0.5">
                {cpa_nm !== null && (
                  <span className={sev.text + " font-mono font-bold"}>
                    {cpa_nm.toFixed(2)} NM
                  </span>
                )}
                {tcpa_min !== null && (
                  <span className="text-ocean-400 font-mono">
                    TCPA {tcpa_min.toFixed(1)}분
                  </span>
                )}
              </div>
            </div>
            <span className="text-xs px-2 py-1 rounded bg-ocean-800 text-ocean-200 font-mono border border-ocean-700/40">
              {getPlatformName(log.platform_ids[1])}
            </span>
          </div>
        ) : (
          <>
            {/* 메시지 미리보기 */}
            <p className="mt-1.5 text-xs text-ocean-300 leading-snug line-clamp-1">
              {log.message}
            </p>
            {/* 관련 선박 */}
            {log.platform_ids.length > 0 && (
              <div className="flex gap-1 mt-1.5 flex-wrap">
                {log.platform_ids.slice(0, 4).map((id) => (
                  <span
                    key={id}
                    className="text-xs px-1.5 py-0.5 bg-ocean-800 text-ocean-300 rounded font-mono border border-ocean-700/30"
                  >
                    {getPlatformName(id)}
                  </span>
                ))}
                {log.platform_ids.length > 4 && (
                  <span className="text-xs text-ocean-400">
                    +{log.platform_ids.length - 4}
                  </span>
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
            <span>
              {format(new Date(log.timestamp), "yyyy/MM/dd HH:mm:ss")}
            </span>
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
                    {cpa_nm !== null && (
                      <MetricBadge
                        label="CPA"
                        value={`${cpa_nm.toFixed(3)} NM`}
                        sev={log.severity}
                      />
                    )}
                    {tcpa_min !== null && (
                      <MetricBadge
                        label="TCPA"
                        value={`${tcpa_min.toFixed(1)} 분`}
                        sev={log.severity}
                      />
                    )}
                  </div>
                )}
                {/* 기타 메타데이터 */}
                {Object.entries(log.metadata ?? {})
                  .filter(
                    ([k]) =>
                      !["cpa_nm", "tcpa_min", "dedup_key", "ai_model"].includes(
                        k,
                      ),
                  )
                  .map(([k, v]) => (
                    <DataRow key={k} label={k} value={String(v)} />
                  ))}
              </div>
            )}
            {/* 관련 선박 상세 (CPA일 때 양 선박 표시) */}
            {log.platform_ids.length > 0 && (
              <div className="mt-2 flex gap-2 flex-wrap">
                {log.platform_ids.map((id, i) => (
                  <span
                    key={id}
                    className="text-xs px-2 py-1 bg-ocean-800/60 text-ocean-200 rounded font-mono border border-ocean-700/40"
                  >
                    {isCPA && log.platform_ids.length === 2 ? (
                      <>
                        <span className="text-ocean-500 mr-1">
                          {i === 0 ? "선박 A" : "선박 B"}
                        </span>
                        {id.replace(/^MMSI-/, "")}
                      </>
                    ) : (
                      id.replace(/^MMSI-/, "")
                    )}
                  </span>
                ))}
              </div>
            )}
          </DetailSection>

          {/* 섹션: 처리 결과 */}
          <DetailSection title="처리 결과 / 출력" icon="⬡">
            <p className="text-xs text-ocean-200 leading-relaxed">
              {log.message}
            </p>
            {meta && (
              <div className="mt-1.5 text-xs text-ocean-500">{meta.output}</div>
            )}
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
  title,
  icon,
  accent = "ocean",
  children,
}: {
  title: string;
  icon: string;
  accent?: "ocean" | "cyan" | "amber";
  children: React.ReactNode;
}) {
  const accentColor = {
    ocean: "text-ocean-500",
    cyan: "text-cyan-400",
    amber: "text-amber-400",
  }[accent];

  return (
    <div className="px-4 py-2.5 border-t border-ocean-800/30">
      <div
        className={`flex items-center gap-1.5 text-xs font-semibold mb-2 ${accentColor}`}
      >
        <span>{icon}</span>
        <span>{title}</span>
      </div>
      {children}
    </div>
  );
}

function DataRow({
  label,
  value,
  highlight,
}: {
  label: string;
  value: string;
  highlight?: string;
}) {
  return (
    <div className="flex items-start gap-2 text-xs">
      <span className="text-ocean-400 flex-shrink-0 w-24">{label}</span>
      <span
        className="text-ocean-300 leading-snug"
        style={highlight ? { color: highlight } : undefined}
      >
        {value}
      </span>
    </div>
  );
}

function MetricBadge({
  label,
  value,
  sev,
}: {
  label: string;
  value: string;
  sev: string;
}) {
  const color =
    sev === "critical"
      ? "text-red-300 border-red-700/50 bg-red-950/50"
      : sev === "warning"
        ? "text-amber-300 border-amber-700/50 bg-amber-950/50"
        : "text-blue-300 border-blue-700/50 bg-blue-950/50";

  return (
    <div className={`rounded px-2.5 py-1.5 border ${color} text-center`}>
      <div className="text-xs opacity-60">{label}</div>
      <div className="text-sm font-mono font-bold">{value}</div>
    </div>
  );
}
