"use client";

import { useEffect, useState } from "react";
import { useAILogStore, isAIAgent, type ActivityLogEntry } from "@/stores/aiLogStore";
import { useAlertStore } from "@/stores/alertStore";
import { usePlatformStore } from "@/stores/platformStore";
import { formatDistanceToNow, format } from "date-fns";
import { ko } from "date-fns/locale";

const AGENTS_URL = process.env.NEXT_PUBLIC_AGENTS_URL ?? "http://localhost:7701";

const AGENT_META: Record<string, {
  name: string; type: "rule" | "ai"; level: string;
  role: string; trigger: string; output: string; color: string;
}> = {
  "cpa-agent":      { name: "CPA/TCPA",     type: "rule", level: "L1", color: "#2e8dd4", role: "충돌 위험 감지",     trigger: "두 선박 CPA < 0.5nm & TCPA < 30분",           output: "cpa 경보" },
  "zone-monitor":   { name: "Zone Monitor", type: "rule", level: "L1", color: "#22d3ee", role: "구역 침입 감지",     trigger: "선박 위치가 금지/제한구역 내 진입",             output: "zone_intrusion 경보" },
  "anomaly-rule":   { name: "Anomaly Rule", type: "rule", level: "L1", color: "#fbbf24", role: "이상 행동 감지",     trigger: "AIS 90초 소실 | 속도 5kt 급감 | ROT 25°/min+", output: "anomaly/ais_off 경보" },
  "anomaly-ai":     { name: "Anomaly AI",   type: "ai",   level: "L2", color: "#a78bfa", role: "이상 행동 AI 분석",  trigger: "anomaly/ais_off 경보 수신 후 자동 실행",        output: "원인 진단 + 권고문" },
  "distress-agent": { name: "Distress",     type: "ai",   level: "L3", color: "#f87171", role: "조난 상황 대응",     trigger: "not_under_command/aground 상태 감지",           output: "SAR 대응 지침" },
  "report-agent":   { name: "Report",       type: "ai",   level: "L2", color: "#34d399", role: "상황 보고서 생성",   trigger: "critical 경보 수신 (distress/cpa/zone)",        output: "공식 사건 보고서" },
};

const SEVERITY_BORDER: Record<string, string> = {
  critical: "border-l-red-500",
  warning:  "border-l-yellow-500",
  info:     "border-l-blue-500",
};
const SEVERITY_TEXT: Record<string, string> = {
  critical: "text-red-400",
  warning:  "text-yellow-400",
  info:     "text-blue-400",
};
const ALERT_TYPE_KR: Record<string, string> = {
  cpa: "충돌 위험", zone_intrusion: "구역 침입", anomaly: "이상 행동",
  ais_off: "AIS 소실", distress: "조난", compliance: "상황 보고",
};

interface AgentStatus {
  agent_id: string; name: string; agent_type: string;
  level: string; enabled: boolean;
}

export default function AgentsPage() {
  const logs          = useAILogStore((s) => s.logs);
  const clearLogs     = useAILogStore((s) => s.clear);
  const alerts        = useAlertStore((s) => s.alerts);
  const platforms     = usePlatformStore((s) => s.platforms);
  const [agentFilter, setAgentFilter]     = useState<string>("all");
  const [typeFilter, setTypeFilter]       = useState<"all" | "rule" | "ai">("all");
  const [expandedLog, setExpandedLog]     = useState<string | null>(null);
  const [agentStatuses, setAgentStatuses] = useState<AgentStatus[]>([]);
  const [updating, setUpdating]           = useState<string | null>(null);
  const [apiStatus, setApiStatus]         = useState<"ok" | "fallback" | "unknown">("unknown");

  useEffect(() => {
    fetch(`${AGENTS_URL}/agents`)
      .then((r) => r.json())
      .then((statuses: AgentStatus[]) => {
        setAgentStatuses(statuses);
      })
      .catch(() => {});
  }, []);

  // fallback 여부: ai_model이 fallback인 로그가 있으면
  useEffect(() => {
    const hasFallback = logs.some((l) => l.model?.includes("fallback"));
    const hasReal     = logs.some((l) => l.model && !l.model.includes("fallback") && isAIAgent(l.agent_id));
    if (hasFallback) setApiStatus("fallback");
    else if (hasReal) setApiStatus("ok");
  }, [logs]);

  async function toggleAgent(agentId: string, enabled: boolean) {
    setUpdating(agentId);
    try {
      await fetch(`${AGENTS_URL}/agents/${agentId}/${enabled ? "enable" : "disable"}`, { method: "PATCH" });
      setAgentStatuses((prev) => prev.map((a) => a.agent_id === agentId ? { ...a, enabled } : a));
    } finally { setUpdating(null); }
  }

  async function setLevel(agentId: string, level: string) {
    setUpdating(agentId);
    try {
      await fetch(`${AGENTS_URL}/agents/${agentId}/level`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ level }),
      });
      setAgentStatuses((prev) => prev.map((a) => a.agent_id === agentId ? { ...a, level } : a));
    } finally { setUpdating(null); }
  }

  const activeAgents = new Set(alerts.map((a) => a.generated_by));

  const filteredLogs = logs
    .filter((l) => agentFilter === "all" || l.agent_id === agentFilter)
    .filter((l) => typeFilter === "all" || l.agent_type === typeFilter);

  function getPlatformName(id: string) {
    const p = platforms[id];
    if (!p) return id.replace(/^MMSI-/, "");
    return p.name && p.name !== p.platform_id ? p.name : id.replace(/^MMSI-/, "");
  }

  const ruleStatuses = agentStatuses.filter((a) => a.agent_type === "rule");
  const aiStatuses   = agentStatuses.filter((a) => a.agent_type === "ai");

  // 통계
  const totalProcessed = logs.length;
  const aiProcessed    = logs.filter((l) => isAIAgent(l.agent_id)).length;
  const ruleProcessed  = totalProcessed - aiProcessed;

  return (
    <div className="h-full flex flex-col overflow-hidden bg-[#020d1a]">
      {/* 헤더 */}
      <div className="flex-shrink-0 px-5 py-3 border-b border-ocean-800/60">
        <div className="flex items-center justify-between mb-3">
          <h1 className="text-sm font-bold text-white tracking-wider">에이전트 관리</h1>
          <div className="flex gap-4 text-xs">
            <span className="text-ocean-400">Rule <span className="text-white font-mono">{ruleProcessed}</span>건</span>
            <span className="text-ocean-400">AI <span className="text-white font-mono">{aiProcessed}</span>건</span>
            <span className="text-ocean-400">전체 <span className="text-white font-mono">{totalProcessed}</span>건 처리</span>
          </div>
        </div>

        {/* API Key 경고 */}
        {apiStatus === "fallback" && (
          <div className="mb-3 px-3 py-2 bg-amber-500/10 border border-amber-500/40 rounded text-xs">
            <div className="flex items-center gap-2 text-amber-400 font-medium mb-0.5">
              <span>⚠</span> AI 분석 불완전 — ANTHROPIC_API_KEY 미설정
            </div>
            <div className="text-amber-300/70">
              현재 rule 기반 fallback 권고문을 사용 중입니다. Claude AI 분석을 활성화하려면
              {" "}<code className="bg-amber-900/30 px-1 rounded">ANTHROPIC_API_KEY</code> 환경변수를 설정 후 에이전트를 재시작하세요.
            </div>
          </div>
        )}

        {/* 에이전트 카드 */}
        <div className="grid grid-cols-2 gap-3 mb-3">
          {/* Rule */}
          <div className="bg-ocean-900/50 border border-ocean-800/60 rounded-lg p-3">
            <div className="text-xs font-semibold text-ocean-300 mb-2.5 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-ocean-400 inline-block" />
              규칙 에이전트
            </div>
            <div className="space-y-2">
              {(ruleStatuses.length > 0 ? ruleStatuses : Object.entries(AGENT_META).filter(([,m]) => m.type === "rule").map(([id]) => ({ agent_id: id, name: AGENT_META[id].name, agent_type: "rule", level: "L1", enabled: true }))).map((agent) => {
                const meta = AGENT_META[agent.agent_id];
                const count = logs.filter((l) => l.agent_id === agent.agent_id).length;
                const isActive = activeAgents.has(agent.agent_id);
                return (
                  <AgentCard
                    key={agent.agent_id}
                    agent={agent}
                    meta={meta}
                    count={count}
                    isActive={isActive}
                    isUpdating={updating === agent.agent_id}
                    onToggle={(e) => toggleAgent(agent.agent_id, e)}
                    onLevel={(l) => setLevel(agent.agent_id, l)}
                  />
                );
              })}
            </div>
          </div>

          {/* AI */}
          <div className="bg-ocean-900/50 border border-ocean-800/60 rounded-lg p-3">
            <div className="text-xs font-semibold text-cyan-300 mb-2.5 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse inline-block" />
              AI 에이전트
              {apiStatus === "fallback" && <span className="text-amber-400 text-xs font-normal">(fallback 모드)</span>}
              {apiStatus === "ok" && <span className="text-green-400 text-xs font-normal">✓ Claude 연결됨</span>}
            </div>
            <div className="space-y-2">
              {(aiStatuses.length > 0 ? aiStatuses : Object.entries(AGENT_META).filter(([,m]) => m.type === "ai").map(([id]) => ({ agent_id: id, name: AGENT_META[id].name, agent_type: "ai", level: AGENT_META[id].level, enabled: true }))).map((agent) => {
                const meta = AGENT_META[agent.agent_id];
                const count = logs.filter((l) => l.agent_id === agent.agent_id).length;
                const isActive = logs.some((l) => l.agent_id === agent.agent_id);
                return (
                  <AgentCard
                    key={agent.agent_id}
                    agent={agent}
                    meta={meta}
                    count={count}
                    isActive={isActive}
                    isUpdating={updating === agent.agent_id}
                    onToggle={(e) => toggleAgent(agent.agent_id, e)}
                    onLevel={(l) => setLevel(agent.agent_id, l)}
                  />
                );
              })}
            </div>
          </div>
        </div>

        {/* 필터 */}
        <div className="flex items-center gap-2 flex-wrap">
          {/* 타입 */}
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

          {/* 에이전트별 */}
          <div className="flex gap-1 flex-wrap">
            <button onClick={() => setAgentFilter("all")}
              className={`text-xs px-2.5 py-1 rounded border transition-colors ${
                agentFilter === "all" ? "bg-ocean-700 text-white border-ocean-600" : "text-ocean-500 border-ocean-800 hover:border-ocean-600 hover:text-ocean-300"
              }`}>
              전체 ({logs.length})
            </button>
            {Object.entries(AGENT_META).map(([id, meta]) => {
              const count = logs.filter((l) => l.agent_id === id).length;
              if (count === 0) return null;
              return (
                <button key={id} onClick={() => setAgentFilter(id)}
                  className={`text-xs px-2.5 py-1 rounded border transition-colors ${
                    agentFilter === id
                      ? "text-white border-current"
                      : "text-ocean-500 border-ocean-800 hover:border-ocean-600 hover:text-ocean-300"
                  }`}
                  style={agentFilter === id ? { borderColor: meta.color, color: meta.color, background: `${meta.color}18` } : {}}>
                  {meta.name} ({count})
                </button>
              );
            })}
          </div>

          {logs.length > 0 && (
            <button onClick={clearLogs} className="ml-auto text-xs text-ocean-600 hover:text-red-400 transition-colors">
              초기화
            </button>
          )}
        </div>
      </div>

      {/* 처리 기록 목록 */}
      <div className="flex-1 overflow-auto px-5 py-3 space-y-1.5">
        {filteredLogs.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-48 gap-3 text-ocean-600">
            <div className="text-4xl opacity-20">◈</div>
            <div className="text-sm text-ocean-500">처리 기록 없음</div>
            <div className="text-xs text-ocean-700">에이전트가 경보를 처리하면 여기에 표시됩니다</div>
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

// ── 에이전트 카드 ────────────────────────────────────────────────────────────

function AgentCard({ agent, meta, count, isActive, isUpdating, onToggle, onLevel }: {
  agent: { agent_id: string; agent_type: string; level: string; enabled: boolean };
  meta?: typeof AGENT_META[string];
  count: number;
  isActive: boolean;
  isUpdating: boolean;
  onToggle: (e: boolean) => void;
  onLevel: (l: string) => void;
}) {
  const color = meta?.color ?? "#7ab8d9";
  const isAI = agent.agent_type === "ai";

  return (
    <div className={`rounded-lg p-2.5 border transition-colors ${
      agent.enabled
        ? "bg-ocean-800/30 border-ocean-700/40"
        : "bg-ocean-900/20 border-ocean-800/30 opacity-50"
    }`}>
      <div className="flex items-center gap-2">
        {/* 상태 표시 */}
        <span className={`w-2 h-2 rounded-full flex-shrink-0 transition-colors ${
          !agent.enabled ? "bg-ocean-700" :
          isActive       ? isAI ? "bg-cyan-400 animate-pulse" : "bg-green-400"
                         : "bg-ocean-600"
        }`} />

        {/* 이름 */}
        <span className="text-xs font-medium flex-1" style={{ color: agent.enabled ? color : "#4a7a9b" }}>
          {meta?.name ?? agent.agent_id}
        </span>

        {/* 처리 건수 */}
        {count > 0 && (
          <span className="text-xs font-mono px-1.5 py-0.5 rounded" style={{ color, background: `${color}18` }}>
            {count}건
          </span>
        )}

        {/* 레벨 */}
        {isAI ? (
          <select value={agent.level} onChange={(e) => onLevel(e.target.value)} disabled={isUpdating}
            className="text-xs bg-ocean-900 border border-ocean-700 text-ocean-200 rounded px-1.5 py-0.5 disabled:opacity-40 cursor-pointer">
            <option value="L1">L1</option>
            <option value="L2">L2</option>
            <option value="L3">L3</option>
          </select>
        ) : (
          <span className="text-xs text-ocean-500 font-mono">{agent.level}</span>
        )}

        {/* ON/OFF */}
        <button onClick={() => onToggle(!agent.enabled)} disabled={isUpdating}
          className={`text-xs px-2.5 py-1 rounded-md font-medium transition-colors disabled:opacity-40 ${
            agent.enabled
              ? "bg-ocean-700 text-white hover:bg-ocean-600"
              : "bg-ocean-800 text-ocean-500 hover:bg-ocean-700 hover:text-ocean-300"
          }`}>
          {isUpdating ? "..." : agent.enabled ? "ON" : "OFF"}
        </button>
      </div>

      {meta && (
        <div className="mt-1.5 pl-4 text-xs text-ocean-500 leading-snug">{meta.trigger}</div>
      )}
    </div>
  );
}

// ── 처리 기록 카드 ────────────────────────────────────────────────────────────

function LogCard({ log, expanded, onToggle, getPlatformName }: {
  log: ActivityLogEntry;
  expanded: boolean;
  onToggle: () => void;
  getPlatformName: (id: string) => string;
}) {
  const meta  = AGENT_META[log.agent_id];
  const color = meta?.color ?? "#7ab8d9";
  const isAI  = isAIAgent(log.agent_id);
  const isFallback = log.model?.includes("fallback");

  return (
    <div className={`rounded-lg border-l-2 bg-ocean-900/40 border border-ocean-800/40 overflow-hidden ${SEVERITY_BORDER[log.severity] ?? "border-l-ocean-600"}`}>
      {/* 요약 행 */}
      <div className="px-3 py-2.5 cursor-pointer hover:bg-ocean-800/20 transition-colors" onClick={onToggle}>
        <div className="flex items-center gap-2">
          {/* 에이전트 */}
          <span className="text-xs font-semibold flex-shrink-0" style={{ color }}>
            {meta?.name ?? log.agent_id}
          </span>

          {/* 타입 배지 */}
          <span className={`text-xs px-1.5 py-0.5 rounded flex-shrink-0 ${
            isAI ? "bg-cyan-900/50 text-cyan-300 border border-cyan-800/60" : "bg-ocean-800/60 text-ocean-400 border border-ocean-700/40"
          }`}>
            {isAI ? "AI" : "Rule"}
          </span>

          {/* 경보 유형 */}
          <span className="text-xs bg-ocean-800/60 text-ocean-300 px-1.5 py-0.5 rounded border border-ocean-700/40">
            {ALERT_TYPE_KR[log.alert_type] ?? log.alert_type}
          </span>

          {/* 심각도 */}
          <span className={`text-xs font-bold flex-shrink-0 ${SEVERITY_TEXT[log.severity] ?? "text-ocean-400"}`}>
            {log.severity === "critical" ? "위험" : log.severity === "warning" ? "주의" : "정보"}
          </span>

          {isFallback && (
            <span className="text-xs text-amber-400/70 flex-shrink-0">fallback</span>
          )}

          <span className="ml-auto text-xs text-ocean-500 flex-shrink-0">
            {formatDistanceToNow(new Date(log.timestamp), { addSuffix: true, locale: ko })}
          </span>
        </div>

        {/* 메시지 */}
        <div className="mt-1.5 text-xs text-ocean-200 leading-snug line-clamp-2 pl-0">
          {log.message}
        </div>

        {/* 관련 선박 */}
        {log.platform_ids.length > 0 && (
          <div className="flex gap-1 mt-1.5 flex-wrap">
            {log.platform_ids.map((id) => (
              <span key={id} className="text-xs px-1.5 py-0.5 bg-ocean-800 text-ocean-300 rounded font-mono border border-ocean-700/40">
                {getPlatformName(id)}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* 확장 — 상세 */}
      {expanded && (
        <div className="px-3 pb-3 border-t border-ocean-800/40 pt-2.5 space-y-2.5">
          {/* 발생 시각 */}
          <div className="text-xs text-ocean-500">
            {format(new Date(log.timestamp), "yyyy/MM/dd HH:mm:ss")}
            {log.model && (
              <span className="ml-3 px-1.5 py-0.5 bg-ocean-800 text-ocean-400 rounded">
                {log.model}
              </span>
            )}
          </div>

          {/* AI 권고 또는 Rule 상세 */}
          {log.recommendation ? (
            <div className="bg-ocean-950/60 rounded-lg p-3 border border-ocean-800/40">
              <div className="text-xs text-ocean-400 mb-2 flex items-center gap-1.5">
                {isAI ? <><span>⬡</span><span>AI 분석 · 권고사항</span></> : <span>처리 결과</span>}
                {isFallback && <span className="text-amber-400/70">(API key 미설정 — fallback)</span>}
              </div>
              <div className="text-xs text-ocean-100 leading-relaxed whitespace-pre-wrap">{log.recommendation}</div>
            </div>
          ) : (
            <div className="text-xs text-ocean-500 italic">
              {isAI
                ? `AI 권고 없음 — ${meta?.level === "L1" || log.agent_id === "distress-agent" ? "L1 모드 (권고 생성 비활성)" : "LLM 호출 실패"}`
                : "Rule 에이전트 — 자동 처리"}
            </div>
          )}

          {/* 에이전트 역할 */}
          {meta && (
            <div className="text-xs text-ocean-600 border-t border-ocean-800/40 pt-2 grid grid-cols-2 gap-2">
              <div><span className="text-ocean-500">역할: </span>{meta.role}</div>
              <div><span className="text-ocean-500">트리거: </span>{meta.trigger}</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
