import type { ReactNode } from "react";

export default function SectionHeading({
  title,
  count,
  tone = "neutral",
  action,
}: {
  title: string;
  count?: string | number;
  tone?: "neutral" | "warning" | "critical";
  action?: ReactNode;
}) {
  const badgeClass =
    tone === "critical"
      ? "bg-red-500/20 text-red-300"
      : tone === "warning"
        ? "bg-amber-500/20 text-amber-300"
        : "bg-ocean-800 text-ocean-400";

  return (
    <div className="mb-2 flex items-center justify-between gap-2">
      <div className="flex items-center gap-2">
        <div className="text-xs font-bold uppercase tracking-wider text-ocean-300">{title}</div>
        {count != null ? (
          <span className={`rounded px-1.5 py-0.5 text-xs font-bold ${badgeClass}`}>{count}</span>
        ) : null}
      </div>
      {action}
    </div>
  );
}
