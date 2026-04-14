import type { ReactNode } from "react";

export default function StatusBadge({
  children,
  tone = "neutral",
  className = "",
}: {
  children: ReactNode;
  tone?: "neutral" | "success" | "warning" | "critical" | "info";
  className?: string;
}) {
  const toneClass =
    tone === "success"
      ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
      : tone === "warning"
        ? "border-amber-500/30 bg-amber-500/10 text-amber-200"
        : tone === "critical"
          ? "border-red-500/30 bg-red-500/10 text-red-200"
          : tone === "info"
            ? "border-blue-500/30 bg-blue-500/10 text-blue-200"
            : "border-ocean-700/80 bg-ocean-900/55 text-ocean-300";

  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] ${toneClass} ${className}`.trim()}>
      {children}
    </span>
  );
}
