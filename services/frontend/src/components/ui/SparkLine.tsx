/**
 * SparkLine: SVG 기반 인라인 미니 라인 차트
 * - 추세 표시, 시계열 데이터의 간단한 시각화
 * - 의존성 없음 (recharts/chart.js 불필요)
 */

interface SparkLineProps {
  data: number[];
  width?: number;
  height?: number;
  color?: string;
  strokeWidth?: number;
  filled?: boolean;
  className?: string;
}

export default function SparkLine({
  data,
  width = 120,
  height = 40,
  color = "#2e8dd4",
  strokeWidth = 2,
  filled = false,
  className = "",
}: SparkLineProps) {
  if (!data || data.length === 0) {
    return null;
  }

  // 데이터의 최대값과 최소값 구하기
  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;

  // 포인트 계산
  const padding = 4;
  const chartWidth = width - padding * 2;
  const chartHeight = height - padding * 2;

  const points = data.map((value, index) => {
    const x = padding + (index / (data.length - 1 || 1)) * chartWidth;
    const y =
      padding +
      chartHeight -
      (((value - min) / range) * chartHeight);
    return { x, y };
  });

  // 경로 생성 (polyline)
  const pathData = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ");

  // 영역 채우기 경로 (filled인 경우)
  let areaPath = "";
  if (filled && points.length > 1) {
    const firstPoint = points[0];
    const lastPoint = points[points.length - 1];
    areaPath = `${pathData} L ${lastPoint.x} ${height - padding} L ${firstPoint.x} ${height - padding} Z`;
  }

  return (
    <svg
      width={width}
      height={height}
      className={`inline-block ${className}`}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
    >
      {/* 배경 그라데이션 정의 */}
      {filled && (
        <defs>
          <linearGradient id="sparklineGradient" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor={color} stopOpacity="0.2" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
      )}

      {/* 영역 채우기 */}
      {filled && areaPath && (
        <path d={areaPath} fill="url(#sparklineGradient)" />
      )}

      {/* 라인 */}
      <polyline
        points={points.map((p) => `${p.x},${p.y}`).join(" ")}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      {/* 끝점 마커 */}
      {points.length > 0 && (
        <circle
          cx={points[points.length - 1].x}
          cy={points[points.length - 1].y}
          r="2"
          fill={color}
          opacity="0.8"
        />
      )}
    </svg>
  );
}
