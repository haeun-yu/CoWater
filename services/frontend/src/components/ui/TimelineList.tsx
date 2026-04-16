/**
 * TimelineList: 타임라인 형태의 이벤트/경보 리스트
 * - 날짜 구분선, 수직 타임라인, 컬러 인디케이터
 */

import { ReactNode } from "react";

export interface TimelineItem {
  id: string;
  timestamp: Date | string;
  severity?: "critical" | "warning" | "info" | "neutral";
  title: string;
  subtitle?: string;
  icon?: ReactNode;
  actions?: ReactNode;
  onClick?: () => void;
}

interface TimelineListProps {
  items: TimelineItem[];
  groupByDate?: boolean;
  showRelativeTime?: boolean;
  selectedId?: string;
  onItemClick?: (id: string) => void;
  className?: string;
  emptyMessage?: string;
}

function formatRelativeTime(date: Date | string): string {
  const d = typeof date === "string" ? new Date(date) : date;
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);

  if (minutes < 1) return "방금 전";
  if (minutes < 60) return `${minutes}분 전`;
  if (hours < 24) return `${hours}시간 전`;
  if (days < 7) return `${days}일 전`;

  return d.toLocaleDateString("ko-KR", {
    month: "short",
    day: "numeric",
  });
}

function formatDate(date: Date | string): string {
  const d = typeof date === "string" ? new Date(date) : date;
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);

  const dateOnly = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const todayOnly = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const yesterdayOnly = new Date(
    yesterday.getFullYear(),
    yesterday.getMonth(),
    yesterday.getDate()
  );

  if (dateOnly.getTime() === todayOnly.getTime()) return "오늘";
  if (dateOnly.getTime() === yesterdayOnly.getTime()) return "어제";

  return d.toLocaleDateString("ko-KR", {
    month: "long",
    day: "numeric",
  });
}

function getSeverityColors(severity?: string) {
  switch (severity) {
    case "critical":
      return {
        dot: "bg-red-500",
        dotShadow: "shadow-[0_0_6px_rgba(239,68,68,0.4)]",
        dotBorder: "border-red-500/50",
        line: "bg-red-500/20",
      };
    case "warning":
      return {
        dot: "bg-amber-500",
        dotShadow: "shadow-[0_0_6px_rgba(245,158,11,0.4)]",
        dotBorder: "border-amber-500/50",
        line: "bg-amber-500/20",
      };
    case "info":
      return {
        dot: "bg-blue-500",
        dotShadow: "shadow-[0_0_6px_rgba(59,130,246,0.4)]",
        dotBorder: "border-blue-500/50",
        line: "bg-blue-500/20",
      };
    default:
      return {
        dot: "bg-ocean-600",
        dotShadow: "shadow-[0_0_6px_rgba(46,141,212,0.2)]",
        dotBorder: "border-ocean-600/50",
        line: "bg-ocean-600/10",
      };
  }
}

function getSelectedBorderClass(severity?: string): string {
  switch (severity) {
    case "critical":
      return "border-red-500/30";
    case "warning":
      return "border-amber-500/30";
    case "info":
      return "border-blue-500/30";
    default:
      return "border-ocean-600/30";
  }
}

export default function TimelineList({
  items,
  groupByDate = true,
  showRelativeTime = true,
  selectedId,
  onItemClick,
  className = "",
  emptyMessage = "항목이 없습니다",
}: TimelineListProps) {
  if (!items || items.length === 0) {
    return (
      <div className={`flex items-center justify-center py-8 text-ocean-500 text-xs ${className}`}>
        {emptyMessage}
      </div>
    );
  }

  // 날짜별 그룹핑
  const groupedItems: Record<string, TimelineItem[]> = {};
  if (groupByDate) {
    items.forEach((item) => {
      const dateStr = formatDate(item.timestamp);
      if (!groupedItems[dateStr]) {
        groupedItems[dateStr] = [];
      }
      groupedItems[dateStr].push(item);
    });
  } else {
    groupedItems[""] = items;
  }

  return (
    <div className={`space-y-0 ${className}`}>
      {Object.entries(groupedItems).map(([dateLabel, dateItems], groupIndex) => (
        <div key={dateLabel || groupIndex}>
          {/* 날짜 구분선 */}
          {groupByDate && dateLabel && (
            <div className="relative h-6 flex items-center my-2">
              <div className="absolute inset-x-0 h-px bg-ocean-700/30" />
              <div className="relative ml-2 px-2 bg-ocean-950 text-[10px] font-semibold uppercase tracking-wider text-ocean-500">
                {dateLabel}
              </div>
            </div>
          )}

          {/* 타임라인 아이템들 */}
          <div className="relative">
            {/* 수직선 */}
            <div className="absolute left-3.5 top-0 bottom-0 w-px bg-ocean-700/20" />

            {/* 항목 리스트 */}
            <div className="space-y-2">
              {dateItems.map((item, index) => {
                const colors = getSeverityColors(item.severity);
                const isSelected = item.id === selectedId;

                return (
                  <button
                    key={item.id}
                    onClick={() => {
                      onItemClick?.(item.id);
                      item.onClick?.();
                    }}
                    className={`w-full text-left pl-9 pr-3 py-2.5 rounded-lg transition-colors relative ${
                      isSelected
                        ? `${colors.line} border ${getSelectedBorderClass(item.severity)}`
                        : "hover:bg-ocean-900/30"
                    }`}
                  >
                    {/* 타임라인 도트 */}
                    <div
                      className={`absolute left-0 top-1/2 -translate-y-1/2 w-7 h-7 flex items-center justify-center`}
                    >
                      <div
                        className={`w-3 h-3 rounded-full border-2 ${colors.dot} ${colors.dotBorder} ${colors.dotShadow}`}
                      />
                    </div>

                    {/* 내용 */}
                    <div className="flex items-start justify-between gap-2 pb-1">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          {item.icon && (
                            <div className="flex-shrink-0">{item.icon}</div>
                          )}
                          <h4 className="text-sm font-medium text-ocean-100 truncate">
                            {item.title}
                          </h4>
                        </div>
                        {item.subtitle && (
                          <p className="text-xs text-ocean-400 mt-0.5 truncate">
                            {item.subtitle}
                          </p>
                        )}
                      </div>

                      {/* 시간 */}
                      {showRelativeTime && (
                        <span className="flex-shrink-0 text-[10px] text-ocean-500 whitespace-nowrap">
                          {formatRelativeTime(item.timestamp)}
                        </span>
                      )}
                    </div>

                    {/* 액션 버튼 */}
                    {item.actions && (
                      <div className="mt-2 flex items-center gap-1">
                        {item.actions}
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
