/**
 * DonutRing: SVG 기반 도넛 링 차트
 * - 비율 시각화, 경보 심각도 분포, 상태 분포 등
 * - 의존성 없음
 */

interface DonutSegment {
  value: number;
  color: string;
  label?: string;
}

interface DonutRingProps {
  segments: DonutSegment[];
  size?: number;
  strokeWidth?: number;
  showLabels?: boolean;
  className?: string;
}

export default function DonutRing({
  segments,
  size = 120,
  strokeWidth = 12,
  showLabels = true,
  className = "",
}: DonutRingProps) {
  if (!segments || segments.length === 0) {
    return null;
  }

  const total = segments.reduce((sum, s) => sum + s.value, 0);
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const center = size / 2;

  // 각 세그먼트의 시작 각도 계산
  let currentDashoffset = 0;
  const arcs = segments.map((segment) => {
    const percentage = segment.value / total;
    const arcLength = percentage * circumference;
    const dashoffset = currentDashoffset;
    currentDashoffset += arcLength;

    return {
      ...segment,
      percentage,
      arcLength,
      dashoffset,
    };
  });

  return (
    <div className={`flex flex-col items-center gap-3 ${className}`}>
      {/* SVG 도넛 */}
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        className="transform -rotate-90"
      >
        {arcs.map((arc, index) => (
          <circle
            key={index}
            cx={center}
            cy={center}
            r={radius}
            fill="none"
            stroke={arc.color}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            strokeDasharray={arc.arcLength}
            strokeDashoffset={-arc.dashoffset}
            opacity="0.9"
          />
        ))}
      </svg>

      {/* 레이블 */}
      {showLabels && (
        <div className="flex flex-wrap gap-3 justify-center">
          {segments.map((segment, index) => (
            <div key={index} className="flex items-center gap-1.5">
              <div
                className="w-2 h-2 rounded-full"
                style={{ backgroundColor: segment.color }}
              />
              <span className="text-xs text-ocean-300">
                {segment.label || segment.value}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
