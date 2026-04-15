import type { ReactNode } from "react";

export default function PageHeader({
  kicker,
  title,
  subtitle,
  actions,
  stats,
  className = "",
}: {
  kicker?: string;
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  stats?: ReactNode;
  className?: string;
}) {
  return (
    <div className={`page-header flex-shrink-0 px-5 py-4 ${className}`.trim()}>
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div>
          {kicker ? <div className="page-kicker">{kicker}</div> : null}
          <h1 className="page-title mt-1">{title}</h1>
          {subtitle ? <p className="page-subtitle mt-1">{subtitle}</p> : null}
        </div>
        {(actions || stats) ? (
          <div className="flex w-full flex-col gap-3 xl:w-auto xl:items-end">
            {actions ? <div className="flex flex-wrap items-center gap-2 xl:justify-end">{actions}</div> : null}
            {stats ? <div className="grid grid-cols-2 gap-2 xl:flex xl:flex-wrap xl:justify-end">{stats}</div> : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}
