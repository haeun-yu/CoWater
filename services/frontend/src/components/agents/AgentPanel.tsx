"use client";

import { useEffect, useState } from "react";
import { useAgentStore } from "@/stores/agentStore";
import type { AgentInfo, AgentLevel } from "@/types";

const API_URL = process.env.NEXT_PUBLIC_AGENTS_URL ?? "http://localhost:8001";

const LEVEL_COLORS: Record<AgentLevel, string> = {
  L1: "text-blue-400",
  L2: "text-yellow-400",
  L3: "text-red-400",
};

const LEVEL_DESC: Record<AgentLevel, string> = {
  L1: "감지·알람",
  L2: "분석·권고",
  L3: "자동 실행",
};

export default function AgentPanel() {
  const agents = useAgentStore((s) => s.agents);
  const setAll = useAgentStore((s) => s.setAll);
  const setEnabled = useAgentStore((s) => s.setEnabled);
  const setLevel = useAgentStore((s) => s.setLevel);
  const [loading, setLoading] = useState(false);

  // Agent 목록 로드
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

  return (
    <div className="flex flex-col overflow-hidden" style={{ maxHeight: "40%" }}>
      <div className="px-3 py-2 border-b border-ocean-800 flex-shrink-0">
        <span className="text-xs font-bold text-ocean-200 tracking-wider">에이전트</span>
      </div>
      <div className="flex-1 overflow-y-auto">
        {agents.length === 0 ? (
          <div className="flex items-center justify-center h-16 text-ocean-600 text-xs">
            Agent Runtime 연결 대기 중...
          </div>
        ) : (
          <>
            <AgentGroup label="Rule" agents={ruleAgents} onToggle={toggleAgent} onLevel={changeLevel} />
            <AgentGroup label="AI" agents={aiAgents} onToggle={toggleAgent} onLevel={changeLevel} />
          </>
        )}
      </div>
    </div>
  );
}

function AgentGroup({
  label,
  agents,
  onToggle,
  onLevel,
}: {
  label: string;
  agents: AgentInfo[];
  onToggle: (a: AgentInfo) => void;
  onLevel: (a: AgentInfo, level: AgentLevel) => void;
}) {
  if (agents.length === 0) return null;
  return (
    <div>
      <div className="px-3 py-1 text-xs text-ocean-600 bg-ocean-900 uppercase tracking-wider">
        {label}
      </div>
      {agents.map((agent) => (
        <div
          key={agent.agent_id}
          className="px-3 py-2 border-b border-ocean-900 flex items-center gap-2"
        >
          {/* 활성화 토글 */}
          <button
            onClick={() => onToggle(agent)}
            className={`w-8 h-4 rounded-full transition-colors flex-shrink-0 relative ${
              agent.enabled ? "bg-ocean-500" : "bg-ocean-800"
            }`}
          >
            <span
              className={`absolute top-0.5 w-3 h-3 rounded-full bg-white transition-all ${
                agent.enabled ? "left-4" : "left-0.5"
              }`}
            />
          </button>

          {/* 이름 */}
          <div className="flex-1 min-w-0">
            <div
              className={`text-xs truncate ${
                agent.enabled ? "text-ocean-200" : "text-ocean-600"
              }`}
            >
              {agent.name}
            </div>
          </div>

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
      ))}
    </div>
  );
}
