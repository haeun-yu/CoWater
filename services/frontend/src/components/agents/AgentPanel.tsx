"use client";

import { useEffect, useState } from "react";
import { usePlatformStore } from "@/stores/platformStore";
import { useAlertStore } from "@/stores/alertStore";
import EmptyState from "@/components/ui/EmptyState";
import { CONTAINERS, type ContainerDef } from "@/config/containers";

// ── Main Component ────────────────────────────────────────────────────────────

export default function AgentPanel() {
  const platforms = usePlatformStore((s) => s.platforms);
  const alerts = useAlertStore((s) => s.alerts);

  const [containerStatus, setContainerStatus] = useState<
    Record<string, "ok" | "degraded" | "error">
  >({});
  const [expandedContainer, setExpandedContainer] = useState<string | null>(
    "detection"
  );

  const activePlatforms = Object.keys(platforms).length;
  const newAlerts = alerts.filter((a) => a.status === "new").length;

  // Poll container health
  useEffect(() => {
    const checkHealth = async () => {
      const status: Record<string, "ok" | "degraded" | "error"> = {};

      await Promise.all(
        CONTAINERS.map(async (container) => {
          try {
            const res = await fetch(`${container.url}/health`);
            const data = await res.json();
            status[container.id] = data.status || "error";
          } catch {
            status[container.id] = "error";
          }
        })
      );

      setContainerStatus(status);
    };

    checkHealth();
    const interval = setInterval(checkHealth, 10000); // Poll every 10s
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex flex-col overflow-hidden" style={{ maxHeight: "55%" }}>
      {/* 헤더 */}
      <div className="px-3 py-2 border-b border-ocean-800 flex-shrink-0">
        <span className="text-xs font-bold text-ocean-200 tracking-wider">
          마이크로서비스
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
          label="정상 서비스"
          value={`${Object.values(containerStatus).filter((s) => s === "ok").length}/${CONTAINERS.length}`}
        />
      </div>

      {/* Containers */}
      <div className="flex-1 overflow-y-auto">
        {CONTAINERS.length === 0 ? (
          <EmptyState
            title="서비스 로드 중..."
            description="마이크로서비스 상태 확인 중"
            compact
          />
        ) : (
          <div className="space-y-2 p-2">
            {CONTAINERS.map((container) => (
              <ContainerRow
                key={container.id}
                container={container}
                status={containerStatus[container.id] || "error"}
                expanded={expandedContainer === container.id}
                onExpand={() =>
                  setExpandedContainer(
                    expandedContainer === container.id ? null : container.id
                  )
                }
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Container Row Component ────────────────────────────────────────────────────

function ContainerRow({
  container,
  status,
  expanded,
  onExpand,
}: {
  container: ContainerDef;
  status: "ok" | "degraded" | "error";
  expanded: boolean;
  onExpand: () => void;
}) {
  const statusColor =
    status === "ok"
      ? "#10b981"
      : status === "degraded"
        ? "#f59e0b"
        : "#ef4444";

  return (
    <div
      className="border rounded text-xs overflow-hidden"
      style={{
        borderColor: status === "ok" ? "#10b98144" : "#f5940b44",
        backgroundColor: "#0c2d3f",
      }}
    >
      {/* Header */}
      <button
        onClick={onExpand}
        className="w-full px-3 py-2 flex items-center gap-2 hover:bg-ocean-800/30 transition-colors"
      >
        <span className="text-lg">{container.icon}</span>
        <div className="flex-1 text-left">
          <div className="font-bold text-ocean-200">{container.name}</div>
          <div className="text-[10px] text-ocean-400">:{container.port}</div>
        </div>
        <div
          className="w-2 h-2 rounded-full"
          style={{ backgroundColor: statusColor }}
        />
        <span className="text-ocean-500">{expanded ? "▼" : "▶"}</span>
      </button>

      {/* Agents (when expanded) */}
      {expanded && (
        <div className="border-t border-ocean-800/50 bg-ocean-950/50">
          {container.agents.map((agent, idx) => (
            <div
              key={idx}
              className="px-4 py-2 border-b border-ocean-900/30 last:border-b-0 text-ocean-300 flex items-center gap-2"
            >
              <span className="w-1 h-1 rounded-full bg-ocean-600" />
              <span>{agent}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Stat Cell Component ────────────────────────────────────────────────────────

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
