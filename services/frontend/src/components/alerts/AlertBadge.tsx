import { ReactNode } from "react";

export type BadgeVariant =
  | "resolved"
  | "active"
  | "acknowledged"
  | "source"
  | "workflow"
  | "fallback";

interface AlertBadgeProps {
  variant?: BadgeVariant;
  children: ReactNode;
  title?: string;
  className?: string;
}

const variantStyles: Record<BadgeVariant, string> = {
  resolved: "bg-emerald-500/20 text-emerald-300",
  active: "bg-red-500/20 text-red-300",
  acknowledged: "bg-ocean-800/40 text-ocean-300",
  source: "bg-ocean-950/60 text-ocean-400",
  workflow: "bg-violet-500/20 text-violet-300",
  fallback: "bg-amber-500/10 text-amber-300 border border-amber-500/40",
};

export function AlertBadge({
  variant = "source",
  children,
  title,
  className = "",
}: AlertBadgeProps) {
  return (
    <span
      className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${variantStyles[variant]} ${className}`}
      title={title}
    >
      {children}
    </span>
  );
}
