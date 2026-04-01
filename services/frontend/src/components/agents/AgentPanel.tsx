"use client";

import { useEffect, useState } from "react";
import { useAgentStore } from "@/stores/agentStore";
import { usePlatformStore } from "@/stores/platformStore";
import { useAlertStore } from "@/stores/alertStore";
import type { AgentInfo, AgentLevel } from "@/types";

const API_URL = process.env.NEXT_PUBLIC_AGENTS_URL ?? "http://localhost:7701";

const LEVEL_COLORS: Record<AgentLevel, string> = {
  L1: "text-blue-400",
  L2: "text-yellow-400",
  L3: "text-red-400",
};

// 각 에이전트의 역할 설명 (input → output)
const AGENT_DESC: Record<string, { role: string; input: string; output: string }> = {
  "cpa-agent": {
    role: "충돌 위험 감지",
    input: "모든 선박 위치·속도",
    output: "CPA/TCPA 기준 초과 시 충돌 경보",
  },
  "zone-monitor": {
    role: "구역 침입 감시",
    input: "선박 위치 + 금지/주의 구역",
    output: "구역 진입·이탈 경보",
  },
  "anomaly-rule": {
    role: "이상 행동 탐지",
    input: "선박 AIS 보고",
    output: "AIS 소실·속도급변·ROT 이상 경보",
  },
  "anomaly-ai": {
    role: "AI 이상 분석",
    input: "Rule 에이전트 경보",
    output: "원인 진단 + 대응 권고 (L2 이상)",
  },
  "distress-agent": {
    role: "조난 대응",
    input: "조난 신호·AIS 소실",
    output: "SAR 대응 지침 생성 (L2 이상)",
  },
  "report-agent": {
    role: "사건 보고서",
    input: "사건(Incident) ID",
    output: "AI 종합 보고서 자동 생성",
  },
};

const LEVEL_DESC: Record<AgentLevel, string> = {
  L1: "감지·알람만",
  L2: "분석·권고 포함",
  L3: "자동 실행",
};

export default function AgentPanel() {
  const agents = useAgentStore((s) => s.agents);
  const setAll = useAgentStore((s) => s.setAll);
  const setEnabled = useAgentStore((s) => s.setEnabled);
  const setLevel = useAgentStore((s) => s.setLevel);
  const [loading, setLoading] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const platforms = usePlatformStore((s) => s.platforms);
  const alerts = useAlertStore((s) => s.alerts);

  useEffect(() => {
    fetch(`${API_URL}/agents`)
      .then((r) => r.json())
      .then(setAll)
      .catch(() => {});
  }, [setAll]);

  const toggleAgent = async (agent: AgentInfo) => {
    const endpoint = agent.enabled ? "disable" : "enable";
    setLoading(true);
    try {
      await fetch(`${API_URL}/agents/${agent.agent_id}/${endpoint}`, { method: "PATCH" });
      setEnabled(agent.agent_id, !agent.enabled);
    } finally {
      setLoading(false);
    }
  };

  const changeLevel = async (agent: AgentInfo, level: AgentLevel) => {
    try {
      await fetch(`${API_URL}/agents/${agent.agent_id}/level`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ level }),
      });
      setLevel(agent.agent_id, level);
    } catch {}
  };

  const ruleAgents = agents.filter((a) => a.type === "rule");
  const aiAgents = agents.filter((a) => a.type === "ai");

  // 시스템 요약 통계
  const activePlatforms = Object.keys(platforms).length;
  const newAlerts = alerts.filter((a) => a.status === "new").length;
  const enabledAgents = agents.filter((a) => a.enabled).length;

  return (
    <div className="flex flex-col overflow-hidden" style={{ maxHeight: "55%" }}>
      {/* 헤더 */}
      <div className="px-3 py-2 border-b border-ocean-800 flex-shrink-0">
        <span className="text-xs font-bold text-ocean-200 tracking-wider">에이전트</span>
      </div>

      {/* 시스템 요약 */}
      <div className="px-3 py-2 border-b border-ocean-900 grid grid-cols-3 gap-2 flex-shrink-0">
        <StatCell label="관제 중" value={`${activePlatforms}척`} />
        <StatCell label="미확인 경보" value={`${newAlerts}건`} color={newAlerts > 0 ? "text-yellow-400" : undefined} />
        <StatCell label="활성 에이전트" value={`${enabledAgents}/${agents.length}`} />
      </div>

      <div className="flex-1 overflow-y-auto">
        {agents.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-16 text-ocean-600 text-xs gap-1">
            <span>Agent Runtime 연결 대기 중...</span>
            <span className="text-ocean-700">:{API_URL.split(":").pop()}</span>
          </div>
        ) : (
          <>
            <AgentGroup
              label="Rule 에이전트"
              sublabel="규칙 기반 실시간 분석"
              agents={ruleAgents}
              expandedId={expandedId}
              onExpand={setExpandedId}
              onToggle={toggleAgent}
              onLevel={changeLevel}
            />
            <AgentGroup
              label="AI 에이전트"
              sublabel="Claude 기반 심층 분석"
              agents={aiAgents}
              expandedId={expandedId}
              onExpand={setExpandedId}
              onToggle={toggleAgent}
              onLevel={changeLevel}
            />
          </>
        )}
      </div>
    </div>
  );
}

function StatCell({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="text-center">
      <div className={`text-sm font-mono font-bold ${color ?? "text-ocean-200"}`}>{value}</div>
      <div className="text-xs text-ocean-600">{label}</div>
    </div>
  );
}

function AgentGroup({
  label,
  sublabel,
  agents,
  expandedId,
  onExpand,
  onToggle,
  onLevel,
}: {
  label: string;
  sublabel: string;
  agents: AgentInfo[];
  expandedId: string | null;
  onExpand: (id: string | null) => void;
  onToggle: (a: AgentInfo) => void;
  onLevel: (a: AgentInfo, level: AgentLevel) => void;
}) {
  if (agents.length === 0) return null;
  return (
    <div>
      <div className="px-3 py-1.5 bg-ocean-900 border-b border-ocean-800">
        <div className="text-xs text-ocean-400 uppercase tracking-wider font-bold">{label}</div>
        <div className="text-xs text-ocean-700">{sublabel}</div>
      </div>
      {agents.map((agent) => (
        <AgentRow
          key={agent.agent_id}
          agent={agent}
          expanded={expandedId === agent.agent_id}
          onExpand={() => onExpand(expandedId === agent.agent_id ? null : agent.agent_id)}
          onToggle={onToggle}
          onLevel={onLevel}
        />
      ))}
    </div>
  );
}

function AgentRow({
  agent,
  expanded,
  onExpand,
  onToggle,
  onLevel,
}: {
  agent: AgentInfo;
  expanded: boolean;
  onExpand: () => void;
  onToggle: (a: AgentInfo) => void;
  onLevel: (a: AgentInfo, level: AgentLevel) => void;
}) {
  const desc = AGENT_DESC[agent.agent_id];

  return (
    <div className={`border-b border-ocean-900 ${!agent.enabled ? "opacity-50" : ""}`}>
      {/* 메인 행 */}
      <div className="px-3 py-2 flex items-center gap-2">
        {/* 토글 */}
        <button
          onClick={() => onToggle(agent)}
          className={`w-8 h-4 rounded-full transition-colors flex-shrink-0 relative ${
            agent.enabled ? "bg-ocean-500" : "bg-ocean-800"
          }`}
          title={agent.enabled ? "비활성화" : "활성화"}
        >
          <span
            className={`absolute top-0.5 w-3 h-3 rounded-full bg-white transition-all ${
              agent.enabled ? "left-4" : "left-0.5"
            }`}
          />
        </button>

        {/* 이름 + 역할 */}
        <button className="flex-1 min-w-0 text-left" onClick={onExpand}>
          <div className={`text-xs truncate ${agent.enabled ? "text-ocean-200" : "text-ocean-600"}`}>
            {agent.name}
          </div>
          {desc && (
            <div className="text-xs text-ocean-600 truncate">{desc.role}</div>
          )}
        </button>

        {/* 레벨 선택 */}
        {agent.enabled && (
          <div className="flex gap-0.5 flex-shrink-0">
            {(["L1", "L2", "L3"] as AgentLevel[]).map((lvl) => (
              <button
                key={lvl}
                onClick={() => onLevel(agent, lvl)}
                title={LEVEL_DESC[lvl]}
                className={`text-xs px-1 py-0.5 rounded transition-colors ${
                  agent.level === lvl
                    ? `${LEVEL_COLORS[lvl]} bg-ocean-800 font-bold`
                    : "text-ocean-600 hover:text-ocean-400"
                }`}
              >
                {lvl}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* 확장: input → output 설명 */}
      {expanded && desc && (
        <div className="px-3 pb-2.5 space-y-1.5 bg-ocean-900/40">
          <FlowRow icon="→" label="입력" value={desc.input} color="text-ocean-400" />
          <FlowRow icon="⬡" label="출력" value={desc.output} color="text-green-400" />
          <div className="flex gap-1 pt-0.5">
            {(["L1", "L2", "L3"] as AgentLevel[]).map((lvl) => (
              <span
                key={lvl}
                className={`text-xs px-1.5 py-0.5 rounded border ${
                  agent.level === lvl
                    ? `${LEVEL_COLORS[lvl]} border-current bg-ocean-800`
                    : "text-ocean-700 border-ocean-800"
                }`}
              >
                {lvl}: {LEVEL_DESC[lvl]}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function FlowRow({ icon, label, value, color }: { icon: string; label: string; value: string; color: string }) {
  return (
    <div className="flex items-start gap-1.5 text-xs">
      <span className={`${color} flex-shrink-0 mt-0.5`}>{icon}</span>
      <div>
        <span className="text-ocean-600">{label}: </span>
        <span className="text-ocean-300">{value}</span>
      </div>
    </div>
  );
}
