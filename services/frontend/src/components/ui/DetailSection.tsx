import type { ReactNode } from "react";

export function DetailSection({
  title,
  children,
  action,
  className = "",
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <section className={`border-b border-ocean-900 px-4 py-3 ${className}`.trim()}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="text-xs font-medium uppercase tracking-wider text-ocean-500">{title}</div>
        {action}
      </div>
      {children}
    </section>
  );
}

export function DetailField({
  label,
  value,
  mono,
  className = "",
}: {
  label: string;
  value: ReactNode;
  mono?: boolean;
  className?: string;
}) {
  return (
    <div className={`rounded-xl border border-ocean-800/70 bg-ocean-900/55 px-3 py-2 ${className}`.trim()}>
      <div className="text-[10px] uppercase tracking-[0.16em] text-ocean-500">{label}</div>
      <div className={`mt-1 text-sm text-ocean-100 ${mono ? "font-mono" : ""}`.trim()}>{value}</div>
    </div>
  );
}
