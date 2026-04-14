import type { ReactNode } from "react";

export function DataTable({ children }: { children: ReactNode }) {
  return <div className="content-surface overflow-hidden rounded-2xl">{children}</div>;
}

export function DataTableEmpty({ colSpan, children }: { colSpan: number; children: ReactNode }) {
  return (
    <tr>
      <td colSpan={colSpan} className="py-16 text-center text-ocean-400">
        {children}
      </td>
    </tr>
  );
}
