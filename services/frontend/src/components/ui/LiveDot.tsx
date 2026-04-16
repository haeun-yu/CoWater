/**
 * LiveDot: 실시간 데이터 수신 표시용 점멸 인디케이터
 * - 주로 시스템 상태, 스트림 수신, 에이전트 활성 상태 표시
 */

interface LiveDotProps {
  color?: "emerald" | "amber" | "red" | "blue" | "ocean";
  size?: "sm" | "md" | "lg";
  label?: string;
}

export default function LiveDot({
  color = "emerald",
  size = "md",
  label,
}: LiveDotProps) {
  const sizeClass = {
    sm: "w-2 h-2",
    md: "w-3 h-3",
    lg: "w-4 h-4",
  }[size];

  const colorClass = {
    emerald: "bg-emerald-500",
    amber: "bg-amber-500",
    red: "bg-red-500",
    blue: "bg-blue-500",
    ocean: "bg-ocean-400",
  }[color];

  const shadowClass = {
    emerald: "shadow-[0_0_6px_rgba(16,185,129,0.4)]",
    amber: "shadow-[0_0_6px_rgba(245,158,11,0.4)]",
    red: "shadow-[0_0_6px_rgba(239,68,68,0.4)]",
    blue: "shadow-[0_0_6px_rgba(59,130,246,0.4)]",
    ocean: "shadow-[0_0_6px_rgba(46,141,212,0.4)]",
  }[color];

  return (
    <div className="flex items-center gap-2">
      <div
        className={`${sizeClass} ${colorClass} rounded-full animate-pulse-slow ${shadowClass}`}
      />
      {label && <span className="text-xs text-ocean-300">{label}</span>}
    </div>
  );
}
