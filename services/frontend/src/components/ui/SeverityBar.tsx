/**
 * SeverityBar: 가로 스택바로 심각도 비율 시각화
 * - critical / warning / info 건수를 한 눈에 파악
 */

interface SeverityBarProps {
  critical: number;
  warning: number;
  info: number;
  height?: string;
  showLabels?: boolean;
  className?: string;
}

export default function SeverityBar({
  critical,
  warning,
  info,
  height = "h-2",
  showLabels = true,
  className = "",
}: SeverityBarProps) {
  const total = critical + warning + info;
  if (total === 0) {
    return (
      <div className={`${height} bg-ocean-900 rounded-full ${className}`} />
    );
  }

  const criticalPct = (critical / total) * 100;
  const warningPct = (warning / total) * 100;
  const infoPct = (info / total) * 100;

  return (
    <div>
      <div
        className={`flex rounded-full overflow-hidden border border-ocean-700 ${height} ${className}`}
      >
        {critical > 0 && (
          <div
            className="bg-red-500"
            style={{ width: `${criticalPct}%` }}
            title={`위험: ${critical}`}
          />
        )}
        {warning > 0 && (
          <div
            className="bg-amber-500"
            style={{ width: `${warningPct}%` }}
            title={`주의: ${warning}`}
          />
        )}
        {info > 0 && (
          <div
            className="bg-blue-500"
            style={{ width: `${infoPct}%` }}
            title={`정보: ${info}`}
          />
        )}
      </div>
      {showLabels && (
        <div className="mt-1.5 flex gap-3 text-xs">
          {critical > 0 && (
            <div className="flex items-center gap-1">
              <div className="w-1.5 h-1.5 bg-red-500 rounded-full" />
              <span className="text-red-400">{critical}</span>
            </div>
          )}
          {warning > 0 && (
            <div className="flex items-center gap-1">
              <div className="w-1.5 h-1.5 bg-amber-500 rounded-full" />
              <span className="text-amber-400">{warning}</span>
            </div>
          )}
          {info > 0 && (
            <div className="flex items-center gap-1">
              <div className="w-1.5 h-1.5 bg-blue-500 rounded-full" />
              <span className="text-blue-400">{info}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
