import { PageCard } from '../components/layout/PageCard';
import { missionsFallback } from '../data';
import { useParams, useSearchParams } from 'react-router-dom';

export function MissionPage() {
  const params = useParams();
  const [searchParams] = useSearchParams();
  const missionId = searchParams.get('id') || params.missionId;

  return (
    <div className="grid gap-5 xl:grid-cols-2">
      <PageCard title="Mission">
        {missionId ? <p className="mb-3 rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-[#8da8b5]">Selected mission: {missionId}</p> : null}
        <div className="grid gap-3">
          {missionsFallback.map((mission) => (
            <article key={mission.id} className="rounded-2xl border border-white/10 bg-white/5 p-4">
              <div className="flex items-center justify-between gap-3">
                <strong>{mission.title}</strong>
                <span className="text-sm text-[#8da8b5]">{mission.status}</span>
              </div>
              <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/10">
                <div className="h-full rounded-full bg-gradient-to-r from-[#5bc0be] to-[#7dd3fc]" style={{ width: `${mission.progress}%` }} />
              </div>
            </article>
          ))}
        </div>
      </PageCard>

      <PageCard title="Task Lifecycle">
        <ul className="list-disc space-y-2 pl-5 text-[#8da8b5]">
          <li>SYS_TASK_DISPATCHED marks the dispatch boundary.</li>
          <li>SYS_TASK_COMPLETED and SYS_TASK_FAILED are canonical task results.</li>
          <li>SYS_MISSION_COMPLETED closes the mission loop.</li>
        </ul>
      </PageCard>
    </div>
  );
}
