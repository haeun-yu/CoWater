export function PageCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-[20px] border border-[rgba(120,178,196,0.18)] bg-[rgba(11,27,39,0.82)] p-[18px] shadow-[0_18px_70px_rgba(0,0,0,0.18)] backdrop-blur-xl">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold">{title}</h2>
      </div>
      {children}
    </section>
  );
}

