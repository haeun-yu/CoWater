"use client";

import { useEffect, useMemo } from "react";
import { useEventStore } from "@/stores/eventStore";
import { useEventWebSocket } from "@/hooks/useEventWebSocket";
import PageHeader from "@/components/ui/PageHeader";
import MetricCard from "@/components/ui/MetricCard";
import DetailSection from "@/components/ui/DetailSection";

const EVENT_ICONS: Record<string, string> = {
  detect: "🔍",
  analyze: "🧠",
  respond: "⚠️",
  learn: "📚",
  system: "⚙️",
};

const EVENT_COLORS: Record<string, string> = {
  "detect.cpa": "bg-red-950 border-red-600",
  "detect.anomaly": "bg-orange-950 border-orange-600",
  "detect.zone": "bg-blue-950 border-blue-600",
  "detect.distress": "bg-purple-950 border-purple-600",
  "analyze.anomaly": "bg-blue-900 border-blue-500",
  "respond.alert": "bg-green-900 border-green-600",
  "learn.feedback": "bg-cyan-900 border-cyan-600",
};

export default function EventsPage() {
  useEventWebSocket();

  const events = useEventStore((s) => s.events);

  const stats = useMemo(() => {
    const eventTypes = new Map<string, number>();
    const agents = new Map<string, number>();
    let criticalCount = 0;

    events.forEach((event) => {
      eventTypes.set(
        event.type,
        (eventTypes.get(event.type) ?? 0) + 1,
      );
      agents.set(
        event.agent_id,
        (agents.get(event.agent_id) ?? 0) + 1,
      );

      if (
        event.payload?.severity === "critical" ||
        event.payload?.severity === "warning"
      ) {
        criticalCount++;
      }
    });

    return {
      total: events.length,
      types: Array.from(eventTypes.entries())
        .sort((a, b) => b[1] - a[1])
        .slice(0, 5),
      agents: Array.from(agents.entries())
        .sort((a, b) => b[1] - a[1])
        .slice(0, 5),
      criticalCount,
    };
  }, [events]);

  const flowGroups = useMemo(() => {
    const groups = new Map<string, typeof events>();
    events.forEach((event) => {
      if (!groups.has(event.flow_id)) {
        groups.set(event.flow_id, []);
      }
      groups.get(event.flow_id)?.unshift(event);
    });
    return Array.from(groups.values())
      .sort((a, b) => (b[0]?.timestamp ?? 0) - (a[0]?.timestamp ?? 0))
      .slice(0, 10);
  }, [events]);

  const eventIcon = (type: string) => {
    const prefix = type.split(".")[0];
    return EVENT_ICONS[prefix] || "📌";
  };

  return (
    <div className="min-h-screen bg-ocean-950 text-white p-4 md:p-8">
      <PageHeader
        title="이벤트 모니터링"
        description="실시간 이벤트 흐름 및 서비스 상태 추적"
      />

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <MetricCard
          label="전체 이벤트"
          value={stats.total}
          trend={stats.total > 0 ? "up" : "neutral"}
        />
        <MetricCard
          label="심각 이벤트"
          value={stats.criticalCount}
          trend={stats.criticalCount > 0 ? "down" : "neutral"}
        />
        <MetricCard
          label="활성 에이전트"
          value={stats.agents.length}
          trend={stats.agents.length > 0 ? "up" : "neutral"}
        />
        <MetricCard
          label="이벤트 유형"
          value={stats.types.length}
          trend="neutral"
        />
      </div>

      {/* Event Flows */}
      {flowGroups.length > 0 && (
        <DetailSection title="이벤트 흐름 (최근 10개)" className="mb-8">
          <div className="space-y-4">
            {flowGroups.map((flow, idx) => (
              <div
                key={idx}
                className="bg-ocean-900 border border-ocean-700 rounded-lg p-4"
              >
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono text-ocean-400">
                      {flow[0]?.flow_id.slice(0, 8)}...
                    </span>
                    <span className="text-xs px-2 py-1 bg-ocean-800 rounded">
                      {flow.length} 이벤트
                    </span>
                  </div>
                  <span className="text-xs text-ocean-400">
                    {new Date(flow[0]?.timestamp ?? 0).toLocaleTimeString()}
                  </span>
                </div>

                <div className="flex flex-wrap gap-2">
                  {flow.map((event, eventIdx) => (
                    <div key={eventIdx} className="flex items-center gap-1">
                      <div
                        className={`px-3 py-1.5 rounded text-xs font-medium border ${
                          EVENT_COLORS[event.type] ||
                          "bg-ocean-800 border-ocean-600"
                        }`}
                      >
                        <span className="mr-1">{eventIcon(event.type)}</span>
                        {event.type.split(".")[1]}
                      </div>
                      {eventIdx < flow.length - 1 && (
                        <span className="text-ocean-600">→</span>
                      )}
                    </div>
                  ))}
                </div>

                {/* Event details on hover/expand */}
                <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-2 text-xs text-ocean-300">
                  {flow.map((event) => (
                    <div
                      key={event.id}
                      className="bg-ocean-950 p-2 rounded border border-ocean-700"
                    >
                      <div className="flex justify-between mb-1">
                        <span className="font-mono text-ocean-400">
                          {event.agent_id}
                        </span>
                        <span className="text-ocean-500">
                          {event.type.split(".")[0]}
                        </span>
                      </div>
                      {event.payload?.platform_name && (
                        <div className="text-ocean-400">
                          Platform: {event.payload.platform_name}
                        </div>
                      )}
                      {event.payload?.severity && (
                        <div
                          className={
                            event.payload.severity === "critical"
                              ? "text-red-400"
                              : event.payload.severity === "warning"
                                ? "text-orange-400"
                                : "text-green-400"
                          }
                        >
                          Severity: {event.payload.severity}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </DetailSection>
      )}

      {/* Event Type Distribution */}
      {stats.types.length > 0 && (
        <DetailSection title="이벤트 유형 분포" className="mb-8">
          <div className="space-y-2">
            {stats.types.map(([type, count]) => (
              <div key={type} className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-lg">{eventIcon(type)}</span>
                  <span className="text-sm text-ocean-300">{type}</span>
                </div>
                <div className="flex items-center gap-3">
                  <div className="w-32 bg-ocean-900 rounded-full h-2 border border-ocean-700">
                    <div
                      className="h-full bg-gradient-to-r from-ocean-500 to-ocean-400 rounded-full"
                      style={{ width: `${(count / stats.total) * 100}%` }}
                    />
                  </div>
                  <span className="text-sm font-mono text-ocean-400 w-12 text-right">
                    {count}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </DetailSection>
      )}

      {/* Active Agents */}
      {stats.agents.length > 0 && (
        <DetailSection title="활성 에이전트">
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
            {stats.agents.map(([agent, count]) => (
              <div
                key={agent}
                className="bg-ocean-900 border border-ocean-700 rounded p-3 text-center"
              >
                <div className="text-xs text-ocean-400 font-mono mb-1">
                  {agent}
                </div>
                <div className="text-lg font-bold text-ocean-100">{count}</div>
                <div className="text-xs text-ocean-500">events</div>
              </div>
            ))}
          </div>
        </DetailSection>
      )}

      {/* Empty State */}
      {events.length === 0 && (
        <div className="text-center py-16">
          <div className="text-4xl mb-4">🚀</div>
          <p className="text-ocean-400">
            이벤트 대기 중... 실시간 이벤트가 여기에 표시됩니다.
          </p>
        </div>
      )}
    </div>
  );
}
