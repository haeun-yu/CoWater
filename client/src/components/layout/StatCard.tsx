export function StatCard({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <article className="grid gap-1.5 rounded-2xl border border-white/10 bg-white/5 p-4">
      <span className="text-sm text-[#8da8b5]">{label}</span>
      <strong className="text-[1.1rem]">{value}</strong>
      <small className="text-[#8da8b5]">{hint}</small>
    </article>
  );
}

