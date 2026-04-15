export default function EmptyState({
  title,
  description,
  compact = false,
}: {
  title: string;
  description?: string;
  compact?: boolean;
}) {
  return (
    <div className={`flex flex-col items-center justify-center text-center ${compact ? "h-24 gap-1 px-3" : "h-32 gap-2 px-4"}`}>
      <div className={`${compact ? "text-xs" : "text-sm"} text-ocean-300`}>{title}</div>
      {description ? <div className="text-xs text-ocean-500">{description}</div> : null}
    </div>
  );
}
