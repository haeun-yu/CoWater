"use client";

import { useEffect, useState } from "react";
import { getAgentsApiUrl } from "@/lib/publicUrl";
import { useAgentStore } from "@/stores/agentStore";
import { usePlatformStore } from "@/stores/platformStore";
import { useAlertStore } from "@/stores/alertStore";
import type { AgentInfo, AgentLevel } from "@/types";
import StatusBadge from "@/components/ui/StatusBadge";
import EmptyState from "@/components/ui/EmptyState";

const LEVEL_COLORS: Record<AgentLevel, string> = {
  L1: "text-blue-400",
  L2: "text-yellow-400",
  L3: "text-red-400",
};

// 각 에이전트의 역할 설명 (input → output)
const AGENT_DESC: Record<
  string,
  { role: string; input: string; output: string }
> = {
  // ── 기존 에이전트들 ──────────────────────────────────────────────────────
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

  // ── 이벤트 드리븐 아키텍처 (Detection Service) ──────────────────────────
  "detection-cpa": {
    role: "Redis CPA 감지",
    input: "platform.report.* → Haversine 계산",
    output: "detect.cpa 이벤트",
  },
  "detection-anomaly": {
    role: "Redis 이상 감지",
    input: "platform.report.* → ROT/Speed 변화",
    output: "detect.anomaly 이벤트",
  },
  "detection-zone": {
    role: "Redis 구역 침입",
    input: "platform.report.* → PostGIS 공간 쿼리",
    output: "detect.zone 이벤트",
  },
  "detection-distress": {
    role: "Redis 조난 감지",
    input: "platform.report.* → nav_status 확인",
    output: "detect.distress 이벤트",
  },

  // ── 이벤트 드리븐 아키텍처 (Analysis Service) ──────────────────────────
  "analysis-anomaly-ai": {
    role: "Redis 이상 분석",
    input: "detect.anomaly 이벤트 → Claude API",
    output: "analyze.anomaly 이벤트",
  },
  "analysis-report": {
    role: "Redis 보고서",
    input: "detect.* / analyze.* 이벤트",
    output: "learn.report 이벤트",
  },

  // ── 이벤트 드리븐 아키텍처 (Response Service) ──────────────────────────
  "response-alert-creator": {
    role: "Redis 경보 생성",
    input: "analyze.* 이벤트 → Core API",
    output: "respond.alert 이벤트",
  },

  // ── 이벤트 드리븐 아키텍처 (Supervision Service) ──────────────────────
  "supervision-supervisor": {
    role: "Redis 헬스 모니터링",
    input: "system.heartbeat.* → 타임아웃 확인",
    output: "system.alert 이벤트",
  },

  // ── 이벤트 드리븐 아키텍처 (Learning Service) ──────────────────────────
  "learning-agent": {
    role: "Redis 거짓경보 학습",
    input: "system.ack.* 피드백 → 통계 계산",
    output: "learn.feedback 이벤트",
  },
};

const LEVEL_DESC: Record<AgentLevel, string> = {
  L1: "감지·알람만",
  L2: "분석·권고 포함",
  L3: "자동 실행",
};

const LEVEL_LONG_DESC: Record<AgentLevel, string> = {
  L1: "규칙 감지와 경보 발행만 수행합니다. 외부 자동 조치는 실행하지 않습니다.",
  L2: "L1 + AI 분석/권고를 생성합니다. 운영자 확인 후 조치하는 반자동 모드입니다.",
  L3: "L2 + 자동 실행(예: 자동 통보/자동 처리)을 수행합니다. 운영 정책 검증 후 사용 권장.",
};

export default function AgentPanel() {
  const agents = useAgentStore((s) => s.agents);
  const setAll = useAgentStore((s) => s.setAll);
  const setEnabled = useAgentStore((s) => s.setEnabled);
  const setLevel = useAgentStore((s) => s.setLevel);
  const [loading, setLoading] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [manualPlatformId, setManualPlatformId] = useState("");
  const [runningId, setRunningId] = useState<string | null>(null);

  const platforms = usePlatformStore((s) => s.platforms);
  const alerts = useAlertStore((s) => s.alerts);
  const selectedPlatformId = usePlatformStore((s) => s.selectedId);

  useEffect(() => {
    fetch(`${getAgentsApiUrl()}/agents`)
      .then((r) => r.json())
      .then(setAll)
      .catch(() => {});
  }, [setAll]);

  const toggleAgent = async (agent: AgentInfo) => {
    const endpoint = agent.enabled ? "disable" : "enable";
    setLoading(true);
    try {
      await fetch(`${getAgentsApiUrl()}/agents/${agent.agent_id}/${endpoint}`, {
        method: "PATCH",
      });
      setEnabled(agent.agent_id, !agent.enabled);
    } finally {
      setLoading(false);
    }
  };

  const changeLevel = async (agent: AgentInfo, level: AgentLevel) => {
    try {
      await fetch(`${getAgentsApiUrl()}/agents/${agent.agent_id}/level`, {
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

  async function runManually(agent: AgentInfo) {
    const platformId = (manualPlatformId || selectedPlatformId || "").trim();
    setRunningId(agent.agent_id);
    try {
      const payload: Record<string, unknown> = {};
      if (platformId) payload.platform_id = platformId;

      if (agent.agent_id === "report-agent") {
        const newestCritical = alerts.find(
          (a) => a.severity === "critical" && a.status === "new",
        );
        if (newestCritical) {
          payload.alert = {
            alert_id: newestCritical.alert_id,
            alert_type: newestCritical.alert_type,
            severity: newestCritical.severity,
            generated_by: newestCritical.generated_by,
            message: newestCritical.message,
            platform_ids: newestCritical.platform_ids,
            created_at: newestCritical.created_at,
          };
        }
      }

      await fetch(`${getAgentsApiUrl()}/agents/${agent.agent_id}/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    } finally {
      setRunningId(null);
    }
  }

  return (
    <div className="flex flex-col overflow-hidden" style={{ maxHeight: "55%" }}>
      {/* 헤더 */}
      <div className="px-3 py-2 border-b border-ocean-800 flex-shrink-0">
        <span className="text-xs font-bold text-ocean-200 tracking-wider">
          에이전트
        </span>
      </div>

      {/* 시스템 요약 */}
      <div className="px-3 py-2 border-b border-ocean-900 grid grid-cols-3 gap-2 flex-shrink-0">
        <StatCell label="관제 중" value={`${activePlatforms}척`} />
        <StatCell
          label="미확인 경보"
          value={`${newAlerts}건`}
          color={newAlerts > 0 ? "text-yellow-400" : undefined}
        />
        <StatCell
          label="활성 에이전트"
          value={`${enabledAgents}/${agents.length}`}
        />
      </div>

      <div className="px-3 py-2 border-b border-ocean-900 flex items-center gap-2">
        <input
          value={manualPlatformId}
          onChange={(e) => setManualPlatformId(e.target.value)}
          placeholder={
            selectedPlatformId
              ? `기본: ${selectedPlatformId}`
              : "platform_id (선택)"
          }
          className="flex-1 text-xs px-2 py-1 rounded border border-ocean-700 bg-ocean-950 text-ocean-200"
        />
        <span className="text-xs text-ocean-500">수동 실행 대상</span>
      </div>

      <div className="flex-1 overflow-y-auto">
        {agents.length === 0 ? (
          <EmptyState title="Agent Runtime 연결 대기 중..." description={`:${new URL(getAgentsApiUrl()).port}`} compact />
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
              onRun={runManually}
              runningId={runningId}
            />
            <AgentGroup
              label="AI 에이전트"
              sublabel="Claude 기반 심층 분석"
              agents={aiAgents}
              expandedId={expandedId}
              onExpand={setExpandedId}
              onToggle={toggleAgent}
              onLevel={changeLevel}
              onRun={runManually}
              runningId={runningId}
            />
          </>
        )}
      </div>
    </div>
  );
}

function StatCell({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color?: string;
}) {
  return (
    <div className="text-center">
      <div
        className={`text-sm font-mono font-bold ${color ?? "text-ocean-200"}`}
      >
        {value}
      </div>
      <div className="text-xs text-ocean-400">{label}</div>
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
  onRun,
  runningId,
}: {
  label: string;
  sublabel: string;
  agents: AgentInfo[];
  expandedId: string | null;
  onExpand: (id: string | null) => void;
  onToggle: (a: AgentInfo) => void;
  onLevel: (a: AgentInfo, level: AgentLevel) => void;
  onRun: (a: AgentInfo) => void;
  runningId: string | null;
}) {
  if (agents.length === 0) return null;
  return (
    <div>
      <div className="px-3 py-1.5 bg-ocean-900 border-b border-ocean-800">
        <div className="text-xs text-ocean-400 uppercase tracking-wider font-bold">
          {label}
        </div>
        <div className="text-xs text-ocean-500">{sublabel}</div>
      </div>
      {agents.map((agent) => (
        <AgentRow
          key={agent.agent_id}
          agent={agent}
          expanded={expandedId === agent.agent_id}
          onExpand={() =>
            onExpand(expandedId === agent.agent_id ? null : agent.agent_id)
          }
          onToggle={onToggle}
          onLevel={onLevel}
          onRun={onRun}
          running={runningId === agent.agent_id}
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
  onRun,
  running,
}: {
  agent: AgentInfo;
  expanded: boolean;
  onExpand: () => void;
  onToggle: (a: AgentInfo) => void;
  onLevel: (a: AgentInfo, level: AgentLevel) => void;
  onRun: (a: AgentInfo) => void;
  running: boolean;
}) {
  const desc = AGENT_DESC[agent.agent_id];

  return (
    <div
      className={`border-b border-ocean-900 ${!agent.enabled ? "opacity-50" : ""}`}
    >
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
          <div
            className={`text-xs truncate ${agent.enabled ? "text-ocean-200" : "text-ocean-400"}`}
          >
            {agent.name}
          </div>
          {desc && (
            <div className="text-xs text-ocean-400 truncate">{desc.role}</div>
          )}
        </button>

        {/* 레벨 선택 */}
        {agent.enabled && (
          <div className="flex gap-1 flex-shrink-0">
            {(["L1", "L2", "L3"] as AgentLevel[]).map((lvl) => (
              <StatusBadge
                key={lvl}
                tone={lvl === "L3" ? "critical" : lvl === "L2" ? "warning" : "info"}
                className={agent.level === lvl ? "opacity-100" : "opacity-50"}
              >
                <button onClick={() => onLevel(agent, lvl)} title={LEVEL_DESC[lvl]} className="leading-none">
                  {lvl}
                </button>
              </StatusBadge>
            ))}
          </div>
        )}
      </div>

      {/* 확장: input → output 설명 */}
      {expanded && desc && (
        <div className="px-3 pb-2.5 space-y-1.5 bg-ocean-900/40">
          <FlowRow
            icon="→"
            label="입력"
            value={desc.input}
            color="text-ocean-400"
          />
          <FlowRow
            icon="⬡"
            label="출력"
            value={desc.output}
            color="text-green-400"
          />
          <div className="flex gap-1 pt-0.5">
            {(["L1", "L2", "L3"] as AgentLevel[]).map((lvl) => (
              <span
                key={lvl}
                className={`text-xs px-1.5 py-0.5 rounded border ${
                  agent.level === lvl
                    ? `${LEVEL_COLORS[lvl]} border-current bg-ocean-800`
                    : "text-ocean-500 border-ocean-800"
                }`}
              >
                {lvl}: {LEVEL_DESC[lvl]}
              </span>
            ))}
          </div>
          <div className="text-xs text-ocean-500 leading-relaxed">
            {LEVEL_LONG_DESC[agent.level]}
          </div>
          <button
            onClick={() => onRun(agent)}
            disabled={running || !agent.enabled}
            className="text-xs px-2.5 py-1 rounded border border-cyan-600/50 text-cyan-300 disabled:opacity-40"
          >
            {running ? "실행 중..." : "현재 데이터로 수동 실행"}
          </button>
        </div>
      )}
    </div>
  );
}

function FlowRow({
  icon,
  label,
  value,
  color,
}: {
  icon: string;
  label: string;
  value: string;
  color: string;
}) {
  return (
    <div className="flex items-start gap-1.5 text-xs">
      <span className={`${color} flex-shrink-0 mt-0.5`}>{icon}</span>
      <div>
        <span className="text-ocean-400">{label}: </span>
        <span className="text-ocean-300">{value}</span>
      </div>
    </div>
  );
}
