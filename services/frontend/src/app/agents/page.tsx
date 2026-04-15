"use client";

import React, { useEffect, useState } from "react";
import { getCoreApiUrl } from "@/lib/publicUrl";
import { useAuthStore } from "@/stores/authStore";
import PageHeader from "@/components/ui/PageHeader";
import MetricCard from "@/components/ui/MetricCard";
import EmptyState from "@/components/ui/EmptyState";
import { formatDistanceToNow } from "date-fns";
import { ko } from "date-fns/locale";
import { CONTAINERS, ContainerDef } from "@/config/containers";

const ROLE_ORDER = { viewer: 0, operator: 1, admin: 2 } as const;

// ── Types ──────────────────────────────────────────────────────────────────────

interface HealthStatus {
  status: "ok" | "degraded" | "error";
  dependencies?: Record<string, string>;
}

interface Agent {
  id: string;
  name: string;
  status: "healthy" | "unhealthy";
  lastSeen?: string;
}

function buildFallbackAgents(container: ContainerDef): Agent[] {
  return container.agents.map((name) => ({
    id: name.toLowerCase().replace(" ", "-"),
    name,
    status: "healthy",
  }));
}

function parseAgentsResponse(container: ContainerDef, data: unknown): Agent[] {
  if (!data || typeof data !== "object") {
    return buildFallbackAgents(container);
  }

  if ("agents" in data && data.agents && typeof data.agents === "object") {
    return Object.entries(data.agents as Record<string, unknown>).map(
      ([id, status]) => ({
        id,
        name:
          container.agents.find(
            (agentName) =>
              agentName.toLowerCase().replace(" ", "-") === id.toLowerCase()
          ) || id,
        status: status === "healthy" ? "healthy" : "unhealthy",
        lastSeen: new Date().toLocaleString(),
      })
    );
  }

  if (Array.isArray(data)) {
    return data.map((item, index) => {
      if (typeof item === "string") {
        return {
          id: item.toLowerCase().replace(" ", "-"),
          name: item,
          status: "healthy" as const,
          lastSeen: new Date().toLocaleString(),
        };
      }

      if (item && typeof item === "object") {
        const entry = item as Record<string, unknown>;
        const id =
          typeof entry.agent_id === "string"
            ? entry.agent_id
            : typeof entry.id === "string"
              ? entry.id
              : `${container.id}-${index}`;
        const name =
          typeof entry.name === "string"
            ? entry.name
            : container.agents.find(
                (agentName) =>
                  agentName.toLowerCase().replace(" ", "-") === id.toLowerCase()
              ) || id;
        const status =
          entry.status === "healthy" || entry.status === "ok"
            ? "healthy"
            : "unhealthy";

        return {
          id,
          name,
          status,
          lastSeen: new Date().toLocaleString(),
        };
      }

      return {
        id: `${container.id}-${index}`,
        name: container.agents[index] || `${container.name} Agent ${index + 1}`,
        status: "healthy" as const,
      };
    });
  }

  return buildFallbackAgents(container);
}

interface ContainerStatus {
  container: ContainerDef;
  health: HealthStatus | null;
  agents: Agent[];
  loading: boolean;
  error: string | null;
}

interface SelectedAgent {
  containerId: string;
  agentId: string;
  agentName: string;
}

// ── Event Pipeline Visualization ──────────────────────────────────────────────

function EventPipelineVisualization() {
  return (
    <div className="mb-8 overflow-x-auto">
      <div className="flex items-center gap-2 min-w-max p-4 bg-gradient-to-r from-ocean-950 to-ocean-900 rounded-lg border border-ocean-800/50">
        {/* Step 1: platform.report.* */}
        <div className="px-3 py-2 bg-ocean-800 rounded text-center">
          <div className="text-xs font-bold text-ocean-300">moth-bridge</div>
          <div className="text-[10px] text-ocean-400">platform.report.*</div>
        </div>

        {/* Arrow */}
        <div className="text-ocean-600">→</div>

        {/* Step 2: Detection */}
        <div
          className="px-3 py-2 rounded text-center border"
          style={{ borderColor: "#2e8dd4", backgroundColor: "#1e3a5f" }}
        >
          <div className="text-xs font-bold" style={{ color: "#2e8dd4" }}>
            Detection
          </div>
          <div className="text-[10px] text-ocean-400">detect.*</div>
        </div>

        {/* Arrow */}
        <div className="text-ocean-600">→</div>

        {/* Step 3: Analysis */}
        <div
          className="px-3 py-2 rounded text-center border"
          style={{ borderColor: "#a78bfa", backgroundColor: "#2d1b4e" }}
        >
          <div className="text-xs font-bold" style={{ color: "#a78bfa" }}>
            Analysis
          </div>
          <div className="text-[10px] text-ocean-400">analyze.*</div>
        </div>

        {/* Arrow */}
        <div className="text-ocean-600">→</div>

        {/* Step 4: Response */}
        <div
          className="px-3 py-2 rounded text-center border"
          style={{ borderColor: "#f87171", backgroundColor: "#4d1f26" }}
        >
          <div className="text-xs font-bold" style={{ color: "#f87171" }}>
            Response
          </div>
          <div className="text-[10px] text-ocean-400">respond.*</div>
        </div>

        {/* Arrow */}
        <div className="text-ocean-600">→</div>

        {/* Step 5: Report & Learning */}
        <div className="flex gap-2">
          <div
            className="px-3 py-2 rounded text-center border"
            style={{ borderColor: "#34d399", backgroundColor: "#1d3a2a" }}
          >
            <div className="text-xs font-bold" style={{ color: "#34d399" }}>
              Report
            </div>
            <div className="text-[10px] text-ocean-400">report.*</div>
          </div>
          <div
            className="px-3 py-2 rounded text-center border"
            style={{ borderColor: "#fbbf24", backgroundColor: "#3a2d1a" }}
          >
            <div className="text-xs font-bold" style={{ color: "#fbbf24" }}>
              Learning
            </div>
            <div className="text-[10px] text-ocean-400">learn.*</div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Container Card ────────────────────────────────────────────────────────────

function ContainerCard({
  status,
  onSelectAgent,
}: {
  status: ContainerStatus;
  onSelectAgent: (agent: SelectedAgent) => void;
}) {
  const container = status.container;
  const healthColor =
    status.health?.status === "ok"
      ? "#10b981"
      : status.health?.status === "degraded"
        ? "#f59e0b"
        : "#ef4444";

  return (
    <div
      className="rounded-lg border p-4 bg-gradient-to-br from-ocean-900 to-ocean-950"
      style={{ borderColor: container.color + "40" }}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <span className="text-2xl">{container.icon}</span>
          <div>
            <h3 className="text-lg font-bold" style={{ color: container.color }}>
              {container.name}
            </h3>
            <div className="text-xs text-ocean-400">:{container.port}</div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div
            className="w-3 h-3 rounded-full"
            style={{ backgroundColor: healthColor }}
          />
          <span className="text-xs text-ocean-300">
            {status.loading
              ? "로딩..."
              : status.error
                ? "오류"
                : status.health?.status === "ok"
                  ? "정상"
                  : "주의"}
          </span>
        </div>
      </div>

      {/* Agents */}
      {status.loading && (
        <div className="text-xs text-ocean-400">에이전트 로딩 중...</div>
      )}

      {status.error && (
        <div className="text-xs text-red-400">
          오류: {status.error}
        </div>
      )}

      {!status.loading && !status.error && (
        <div className="space-y-2">
          {status.agents.length > 0 ? (
            status.agents.map((agent) => (
              <button
                key={agent.id}
                onClick={() =>
                  onSelectAgent({
                    containerId: container.id,
                    agentId: agent.id,
                    agentName: agent.name,
                  })
                }
                className="w-full text-left px-3 py-2 rounded text-sm transition-colors"
                style={{
                  backgroundColor: container.color + "15",
                  borderLeft: `3px solid ${container.color}`,
                  color: agent.status === "healthy" ? "#e0e7ff" : "#fca5a5",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = container.color + "25";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = container.color + "15";
                }}
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium">{agent.name}</span>
                  <span className="text-xs">
                    {agent.status === "healthy" ? "✓" : "✗"}
                  </span>
                </div>
                {agent.lastSeen && (
                  <div className="text-xs text-ocean-400 mt-1">
                    {agent.lastSeen}
                  </div>
                )}
              </button>
            ))
          ) : (
            <div className="text-xs text-ocean-500">에이전트 없음</div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Agent Detail Drawer ────────────────────────────────────────────────────────

function AgentDetailDrawer({
  selected,
  onClose,
}: {
  selected: SelectedAgent | null;
  onClose: () => void;
}) {
  if (!selected) return null;

  const container = CONTAINERS.find((c) => c.id === selected.containerId);
  if (!container) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/60 z-40"
        onClick={onClose}
      />

      {/* Drawer */}
      <div className="fixed right-0 top-0 h-full w-96 bg-ocean-950 border-l border-ocean-800 z-50 overflow-y-auto shadow-2xl">
        <div className="p-6">
          {/* Close Button */}
          <button
            onClick={onClose}
            className="absolute top-4 right-4 text-ocean-400 hover:text-ocean-200 transition-colors"
          >
            ✕
          </button>

          {/* Header */}
          <div className="mb-6 pr-6">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-3xl">{container.icon}</span>
              <div>
                <h2
                  className="text-xl font-bold"
                  style={{ color: container.color }}
                >
                  {container.name}
                </h2>
                <p className="text-sm text-ocean-400">{selected.agentName}</p>
              </div>
            </div>
          </div>

          {/* Sections */}
          <div className="space-y-6">
            {/* Published Events */}
            <div>
              <h3 className="text-sm font-bold text-ocean-300 mb-2 uppercase tracking-wider">
                발행 이벤트
              </h3>
              <div className="space-y-2">
                {getPublishedEvents(selected.containerId).map((event) => (
                  <div
                    key={event}
                    className="px-3 py-2 bg-ocean-900 rounded text-xs text-ocean-300 font-mono"
                  >
                    {event}
                  </div>
                ))}
              </div>
            </div>

            {/* Configuration */}
            <div>
              <h3 className="text-sm font-bold text-ocean-300 mb-2 uppercase tracking-wider">
                설정
              </h3>
              <div className="bg-ocean-900 rounded p-3 text-xs text-ocean-300 font-mono">
                <div>port: {container.port}</div>
                <div>agents: {container.agents.join(", ")}</div>
              </div>
            </div>

            {/* Description */}
            <div>
              <h3 className="text-sm font-bold text-ocean-300 mb-2 uppercase tracking-wider">
                설명
              </h3>
              <p className="text-xs text-ocean-400 leading-relaxed">
                {getContainerDescription(selected.containerId)}
              </p>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

// ── Helper Functions ──────────────────────────────────────────────────────────

function getPublishedEvents(containerId: string): string[] {
  const eventMap: Record<string, string[]> = {
    detection: ["detect.cpa", "detect.anomaly", "detect.zone", "detect.distress"],
    analysis: ["analyze.anomaly", "analyze.distress"],
    response: ["respond.critical", "respond.warning"],
    report: ["report.{report_id}"],
    control: ["command.{agent_id}"],
    learning: ["learn.rule_update.*"],
    supervision: ["system.health", "system.alert"],
  };
  return eventMap[containerId] || [];
}

function getContainerDescription(containerId: string): string {
  const descMap: Record<string, string> = {
    detection: "Rule 기반의 실시간 위험 감지. platform.report.* 구독 → detect.* 발행",
    analysis: "AI 기반 심층 분석. detect.* 구독 → analyze.* 발행",
    response: "경보 생성 및 대응. analyze.* 구독 → respond.* 발행",
    report: "AI 리포트 생성. respond.* 구독 → report.* 발행",
    control: "사용자 제어 에이전트. 실시간 대화 및 명령 처리",
    learning: "피드백 기반 학습. user.*, respond.* 구독 → learn.rule_update.* 발행",
    supervision: "전체 시스템 모니터링 및 Heartbeat 추적",
  };
  return descMap[containerId] || "";
}

// ── Main Component ────────────────────────────────────────────────────────────

export default function AgentsPage() {
  const role = useAuthStore((s) => s.role);
  const [containerStatuses, setContainerStatuses] = useState<ContainerStatus[]>(
    CONTAINERS.map((c) => ({
      container: c,
      health: null,
      agents: [],
      loading: true,
      error: null,
    }))
  );

  const [selectedAgent, setSelectedAgent] = useState<SelectedAgent | null>(null);

  // Fetch health and agents for each container
  useEffect(() => {
    const fetchContainerStatus = async (container: ContainerDef) => {
      try {
        // Fetch health
        const healthRes = await fetch(`${container.url}/health`);
        const health = healthRes.ok
          ? await healthRes.json()
          : { status: "error" };

        // Fetch agents (if endpoint exists)
        let agents: Agent[] = buildFallbackAgents(container);
        if (container.hasAgentsEndpoint) {
          try {
            const agentsRes = await fetch(`${container.url}/agents`);
            if (agentsRes.ok) {
              const data = await agentsRes.json();
              agents = parseAgentsResponse(container, data);
            }
          } catch {
            agents = buildFallbackAgents(container);
          }
        }

        setContainerStatuses((prev) =>
          prev.map((s) =>
            s.container.id === container.id
              ? {
                  ...s,
                  health,
                  agents,
                  loading: false,
                  error: null,
                }
              : s
          )
        );
      } catch (error) {
        const errorMsg =
          error instanceof Error ? error.message : "알 수 없는 오류";
        setContainerStatuses((prev) =>
          prev.map((s) =>
            s.container.id === container.id
              ? {
                  ...s,
                  loading: false,
                  error: errorMsg,
                }
              : s
          )
        );
      }
    };

    // Fetch all containers in parallel (initial load)
    Promise.all(CONTAINERS.map(fetchContainerStatus)).catch((error) => {
      console.error("Failed to fetch initial container status:", error);
    });

    // Poll every 5 seconds
    const interval = setInterval(() => {
      Promise.all(CONTAINERS.map(fetchContainerStatus)).catch((error) => {
        console.error("Failed to fetch container status during polling:", error);
      });
    }, 5000);

    return () => clearInterval(interval);
  }, []);

  if (role && ROLE_ORDER[role as keyof typeof ROLE_ORDER] < ROLE_ORDER.operator) {
    return (
      <div className="p-6">
        <PageHeader title="에이전트" subtitle="시스템 에이전트 상태" />
        <EmptyState
          title="권한 부족"
          description="operator 이상의 권한이 필요합니다"
        />
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <PageHeader title="에이전트" subtitle="마이크로서비스 아키텍처" />

      {/* Event Pipeline */}
      <EventPipelineVisualization />

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard
          label="전체 컨테이너"
          value={CONTAINERS.length}
          detail="개"
        />
        <MetricCard
          label="정상 상태"
          value={
            containerStatuses.filter((s) => s.health?.status === "ok").length
          }
          detail="개"
          tone="success"
        />
        <MetricCard
          label="주의"
          value={
            containerStatuses.filter((s) => s.health?.status === "degraded")
              .length
          }
          detail="개"
          tone="warning"
        />
        <MetricCard
          label="오류"
          value={
            containerStatuses.filter((s) => s.health?.status === "error").length
          }
          detail="개"
          tone="critical"
        />
      </div>

      {/* Container Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {containerStatuses.map((status) => (
          <ContainerCard
            key={status.container.id}
            status={status}
            onSelectAgent={setSelectedAgent}
          />
        ))}
      </div>

      {/* Agent Detail Drawer */}
      <AgentDetailDrawer
        selected={selectedAgent}
        onClose={() => setSelectedAgent(null)}
      />
    </div>
  );
}
