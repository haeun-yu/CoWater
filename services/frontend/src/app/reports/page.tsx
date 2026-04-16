"use client";

import React, { useEffect, useState } from "react";
import { getCoreApiUrl } from "@/lib/publicUrl";
import { useAuthStore } from "@/stores/authStore";
import PageHeader from "@/components/ui/PageHeader";
import MetricCard from "@/components/ui/MetricCard";
import EmptyState from "@/components/ui/EmptyState";
import FilterChip from "@/components/ui/FilterChip";
import TimelineList, { TimelineItem } from "@/components/ui/TimelineList";
import { formatDistanceToNow, format, isAfter, subDays } from "date-fns";
import { ko } from "date-fns/locale";

const CORE_API_URL = getCoreApiUrl();
const ROLE_ORDER = { viewer: 0, operator: 1, admin: 2 } as const;

// ── Types ──────────────────────────────────────────────────────────────────────

interface Report {
  report_id: string;
  flow_id: string;
  alert_ids: string[];
  report_type: string;
  content: string;
  summary: string | null;
  ai_model: string;
  metadata: Record<string, any>;
  created_at: string;
}

interface ReportsResponse {
  reports: Report[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

interface SelectedReport {
  report: Report;
  index: number;
}

// ── Report Card Component ──────────────────────────────────────────────────────

function ReportCard({
  report,
  index,
  onSelect,
}: {
  report: Report;
  index: number;
  onSelect: (selected: SelectedReport) => void;
}) {
  const createdDate = new Date(report.created_at);
  const typeColors: Record<string, string> = {
    summary: "#38bdf8",
    detailed: "#a78bfa",
    incident: "#f87171",
  };
  const typeLabels: Record<string, string> = {
    summary: "요약",
    detailed: "상세",
    incident: "사건",
  };

  return (
    <button
      onClick={() => onSelect({ report, index })}
      className="text-left p-4 rounded-lg border border-ocean-800/50 bg-gradient-to-br from-ocean-900 to-ocean-950 hover:border-ocean-700 hover:from-ocean-850 transition-all duration-200"
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span
              className="px-2 py-1 rounded text-xs font-bold"
              style={{ backgroundColor: typeColors[report.report_type] + "22", color: typeColors[report.report_type] }}
            >
              {typeLabels[report.report_type] || report.report_type}
            </span>
            <span className="text-xs text-ocean-400">
              {report.alert_ids.length} 경보
            </span>
          </div>
          <div className="text-sm font-mono text-ocean-300 truncate">
            Flow: {report.flow_id.substring(0, 8)}...
          </div>
        </div>
        <div className="text-right ml-4 flex-shrink-0">
          <div className="text-xs text-ocean-400">
            {formatDistanceToNow(createdDate, { locale: ko, addSuffix: true })}
          </div>
          <div className="text-xs text-ocean-500">
            {format(createdDate, "HH:mm:ss")}
          </div>
        </div>
      </div>

      {/* Content Preview */}
      <div className="text-xs text-ocean-400 line-clamp-3 leading-relaxed">
        {report.summary || report.content}
      </div>

      {/* Footer */}
      <div className="mt-3 pt-3 border-t border-ocean-800/30 flex items-center justify-between text-xs text-ocean-500">
        <div>{report.ai_model}</div>
        <div>→</div>
      </div>
    </button>
  );
}

// ── Report Detail Drawer ──────────────────────────────────────────────────────

function ReportDetailDrawer({
  selected,
  onClose,
}: {
  selected: SelectedReport | null;
  onClose: () => void;
}) {
  if (!selected) return null;

  const { report } = selected;
  const createdDate = new Date(report.created_at);
  const typeColors: Record<string, string> = {
    summary: "#38bdf8",
    detailed: "#a78bfa",
    incident: "#f87171",
  };
  const typeLabels: Record<string, string> = {
    summary: "요약",
    detailed: "상세",
    incident: "사건",
  };

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/60 z-40"
        onClick={onClose}
      />

      {/* Drawer */}
      <div className="fixed right-0 top-0 h-full w-[600px] bg-ocean-950 border-l border-ocean-800 z-50 overflow-y-auto shadow-2xl">
        <div className="p-6">
          {/* Close Button */}
          <button
            onClick={onClose}
            className="absolute top-4 right-4 text-ocean-400 hover:text-ocean-200 transition-colors text-lg"
          >
            ✕
          </button>

          {/* Header */}
          <div className="mb-6 pr-6">
            <div className="flex items-center gap-2 mb-3">
              <span
                className="px-3 py-1.5 rounded text-xs font-bold"
                style={{
                  backgroundColor: typeColors[report.report_type] + "22",
                  color: typeColors[report.report_type],
                }}
              >
                {typeLabels[report.report_type] || report.report_type}
              </span>
              <span className="text-xs text-ocean-400">
                {report.alert_ids.length} 경보
              </span>
            </div>
            <div className="mb-2">
              <div className="text-xs text-ocean-400">Flow ID</div>
              <div className="text-sm font-mono text-ocean-200">
                {report.flow_id}
              </div>
            </div>
            <div className="text-xs text-ocean-500">
              {format(createdDate, "yyyy-MM-dd HH:mm:ss", { locale: ko })}
            </div>
          </div>

          {/* Content Sections */}
          <div className="space-y-6">
            {/* Summary */}
            {report.summary && (
              <div>
                <h3 className="text-sm font-bold text-ocean-300 mb-2 uppercase tracking-wider">
                  요약
                </h3>
                <p className="text-xs text-ocean-300 leading-relaxed whitespace-pre-wrap">
                  {report.summary}
                </p>
              </div>
            )}

            {/* Full Content */}
            <div>
              <h3 className="text-sm font-bold text-ocean-300 mb-2 uppercase tracking-wider">
                본문
              </h3>
              <div className="bg-ocean-900/50 rounded p-4 text-xs text-ocean-300 leading-relaxed whitespace-pre-wrap max-h-96 overflow-y-auto">
                {report.content}
              </div>
            </div>

            {/* Alert IDs */}
            <div>
              <h3 className="text-sm font-bold text-ocean-300 mb-2 uppercase tracking-wider">
                포함된 경보
              </h3>
              <div className="space-y-1">
                {report.alert_ids.length > 0 ? (
                  report.alert_ids.map((alertId) => (
                    <div
                      key={alertId}
                      className="px-3 py-2 bg-ocean-900/50 rounded text-xs text-ocean-400 font-mono"
                    >
                      {alertId}
                    </div>
                  ))
                ) : (
                  <div className="text-xs text-ocean-500 italic">
                    경보 없음
                  </div>
                )}
              </div>
            </div>

            {/* Metadata */}
            <div>
              <h3 className="text-sm font-bold text-ocean-300 mb-2 uppercase tracking-wider">
                메타데이터
              </h3>
              <div className="bg-ocean-900/50 rounded p-3 text-xs text-ocean-400 font-mono">
                <div>Model: {report.ai_model}</div>
                <div>Report Type: {report.report_type}</div>
                {Object.entries(report.metadata).map(([key, value]) => (
                  <div key={key}>
                    {key}: {JSON.stringify(value)}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────

export default function ReportsPage() {
  const role = useAuthStore((s) => s.role);

  const [reports, setReports] = useState<Report[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(10);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedReport, setSelectedReport] = useState<SelectedReport | null>(
    null
  );
  const [filterType, setFilterType] = useState<string>("");
  const [filterFlowId, setFilterFlowId] = useState<string>("");
  const [timeRange, setTimeRange] = useState<"all" | "1d" | "7d" | "30d">("all");

  // Fetch reports
  useEffect(() => {
    const fetchReports = async () => {
      setLoading(true);
      setError(null);

      try {
        let url = `${CORE_API_URL}/reports?page=${page}&page_size=${pageSize}`;
        if (filterType) url += `&report_type=${filterType}`;
        if (filterFlowId) url += `&flow_id=${filterFlowId}`;

        const res = await fetch(url);
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }

        const data: ReportsResponse = await res.json();
        setReports(data.reports);
        setTotal(data.total);
      } catch (err) {
        const msg =
          err instanceof Error ? err.message : "보고서 조회 실패";
        setError(msg);
      } finally {
        setLoading(false);
      }
    };

    fetchReports();
  }, [page, pageSize, filterType, filterFlowId]);

  // 기간별 필터링
  const now = new Date();
  const filteredReports = reports.filter((report) => {
    if (timeRange === "all") return true;
    const days = timeRange === "1d" ? 1 : timeRange === "7d" ? 7 : 30;
    return isAfter(new Date(report.created_at), subDays(now, days));
  });

  if (role && ROLE_ORDER[role as keyof typeof ROLE_ORDER] < ROLE_ORDER.viewer) {
    return (
      <div className="p-6">
        <PageHeader
          title="리포트"
          subtitle="AI 생성 분석 보고서"
        />
        <EmptyState
          title="권한 부족"
          description="viewer 이상의 권한이 필요합니다"
        />
      </div>
    );
  }

  const totalPages = Math.ceil(total / pageSize);

  return (
    <div className="p-6 space-y-6">
      <PageHeader
        title="리포트"
        subtitle="AI 생성 분석 보고서 목록"
      />

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard
          label="전체 리포트"
          value={total}
          detail="건"
        />
        <MetricCard
          label="요약"
          value={reports.filter((r) => r.report_type === "summary").length}
          detail="건"
        />
        <MetricCard
          label="상세"
          value={reports.filter((r) => r.report_type === "detailed").length}
          detail="건"
        />
        <MetricCard
          label="사건"
          value={reports.filter((r) => r.report_type === "incident").length}
          detail="건"
          tone="warning"
        />
      </div>

      {/* Filters */}
      <div className="space-y-3">
        {/* 기간 필터 */}
        <div className="flex flex-wrap gap-2">
          {(["all", "1d", "7d", "30d"] as const).map((range) => (
            <FilterChip
              key={range}
              onClick={() => {
                setTimeRange(range);
                setPage(1);
              }}
              active={timeRange === range}
            >
              {range === "all" ? "전체" : range === "1d" ? "어제" : range === "7d" ? "7일" : "30일"}
            </FilterChip>
          ))}
        </div>

        {/* 유형 + Flow ID 필터 */}
        <div className="flex flex-col sm:flex-row gap-3 p-4 bg-ocean-900/30 rounded-lg border border-ocean-800/30">
        <div className="flex-1">
          <label className="text-xs text-ocean-400 uppercase tracking-wider">
            리포트 유형
          </label>
          <select
            value={filterType}
            onChange={(e) => {
              setFilterType(e.target.value);
              setPage(1);
            }}
            className="w-full mt-1 px-3 py-2 rounded text-sm bg-ocean-950 border border-ocean-800 text-ocean-200"
          >
            <option value="">모두</option>
            <option value="summary">요약</option>
            <option value="detailed">상세</option>
            <option value="incident">사건</option>
          </select>
        </div>
        <div className="flex-1">
          <label className="text-xs text-ocean-400 uppercase tracking-wider">
            Flow ID 검색
          </label>
          <input
            type="text"
            value={filterFlowId}
            onChange={(e) => {
              setFilterFlowId(e.target.value);
              setPage(1);
            }}
            placeholder="Flow ID..."
            className="w-full mt-1 px-3 py-2 rounded text-sm bg-ocean-950 border border-ocean-800 text-ocean-200 placeholder-ocean-600"
          />
        </div>
        </div>
      </div>

      {/* Reports Grid */}
      {loading ? (
        <div className="text-center py-12 text-ocean-400">
          리포트 로드 중...
        </div>
      ) : error ? (
        <EmptyState
          title="오류 발생"
          description={error}
        />
      ) : filteredReports.length === 0 ? (
        <EmptyState
          title="리포트 없음"
          description={reports.length > 0 ? "해당 기간에 리포트가 없습니다" : "아직 생성된 리포트가 없습니다"}
        />
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {filteredReports.map((report, idx) => (
              <ReportCard
                key={report.report_id}
                report={report}
                index={idx}
                onSelect={setSelectedReport}
              />
            ))}
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between p-4 bg-ocean-900/30 rounded-lg border border-ocean-800/30">
            <div className="text-sm text-ocean-400">
              총 {total}건 중 {(page - 1) * pageSize + 1}-
              {Math.min(page * pageSize, total)}건
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-3 py-1 rounded text-sm bg-ocean-800 text-ocean-200 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-ocean-700 transition-colors"
              >
                이전
              </button>
              <span className="text-sm text-ocean-400">
                {page} / {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="px-3 py-1 rounded text-sm bg-ocean-800 text-ocean-200 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-ocean-700 transition-colors"
              >
                다음
              </button>
            </div>
          </div>
        </>
      )}

      {/* Detail Drawer */}
      <ReportDetailDrawer
        selected={selectedReport}
        onClose={() => setSelectedReport(null)}
      />
    </div>
  );
}
