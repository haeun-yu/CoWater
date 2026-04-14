import type { ReactNode } from "react";

type Tone = "neutral" | "warning" | "critical" | "info" | "success";

const TONE_CLASS: Record<Tone, string> = {
  neutral: "text-ocean-100",
  warning: "text-amber-300",
  critical: "text-red-300",
  info: "text-blue-300",
  success: "text-emerald-300",
};

export default function MetricCard({
  label,
  value,
  detail,
  tone = "neutral",
  className = "",
  valueClassName = "text-2xl",
  suffix,
}: {
  label: string;
  value: string | number;
  detail?: string;
  tone?: Tone;
  className?: string;
  valueClassName?: string;
  suffix?: ReactNode;
}) {
  return (
    <div className={`metric-card px-4 py-3 ${className}`.trim()}>
      <div className="text-[11px] uppercase tracking-[0.2em] text-ocean-500">{label}</div>
      <div className={`mt-2 font-mono leading-none ${valueClassName} ${TONE_CLASS[tone]}`.trim()}>
        {value}
      </div>
      {detail || suffix ? (
        <div className="mt-2 flex items-center justify-between gap-2 text-[11px] text-ocean-400">
          <span>{detail}</span>
          {suffix}
        </div>
      ) : null}
    </div>
  );
}
