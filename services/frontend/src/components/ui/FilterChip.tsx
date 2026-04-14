export default function FilterChip({
  active,
  children,
  onClick,
  tone = "neutral",
  className = "",
}: {
  active: boolean;
  children: React.ReactNode;
  onClick: () => void;
  tone?: "neutral" | "warning" | "critical" | "info";
  className?: string;
}) {
  const activeTone =
    tone === "critical"
      ? "border-red-500/50 bg-red-500/15 text-red-200"
      : tone === "warning"
        ? "border-amber-500/50 bg-amber-500/15 text-amber-200"
        : tone === "info"
          ? "border-blue-500/50 bg-blue-500/15 text-blue-200"
          : "border-ocean-500 bg-ocean-700 text-ocean-100";

  return (
    <button
      type="button"
      onClick={onClick}
      className={`filter-chip px-3 py-1 text-xs transition-colors ${active ? activeTone : "text-ocean-400 hover:border-ocean-600 hover:text-ocean-200"} ${className}`.trim()}
    >
      {children}
    </button>
  );
}
