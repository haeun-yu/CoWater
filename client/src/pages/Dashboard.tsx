import { Suspense, lazy } from 'react';
import { PageCard } from '../components/layout/PageCard';
import { StatCard } from '../components/layout/StatCard';
import { useRegistryPreview } from '../hooks/useRegistryPreview';
import { connectionsFallback, devicesFallback, eventsFallback, missionsFallback, proposalsFallback } from '../data';
import type { Connection, Device, EventItem, Meta, Mission, Proposal } from '../types';

const SceneCanvas = lazy(() => import('../components/visualization/SceneCanvas').then((module) => ({ default: module.SceneCanvas })));

function toList<T>(value: T | undefined, fallback: T) {
  return Array.isArray(value) ? value : fallback;
}

export function DashboardPage() {
  const meta = useRegistryPreview<Meta>('/meta', {});
  const devices = useRegistryPreview<Device[]>('/devices', devicesFallback);
  const events = useRegistryPreview<EventItem[]>('/events', eventsFallback);
  const proposals = useRegistryPreview<Proposal[]>('/mission-proposals', proposalsFallback);
  const missions = useRegistryPreview<Mission[]>('/missions', missionsFallback);
  const connections = useRegistryPreview<Connection[]>('/agent-connections', connectionsFallback);

  const deviceList = toList(devices.data, devicesFallback);
  const eventList = toList(events.data, eventsFallback);
  const proposalList = toList(proposals.data, proposalsFallback);
  const missionList = toList(missions.data, missionsFallback);
  const connectionList = toList(connections.data, connectionsFallback);

  return (
    <div className="grid gap-5">
      <section className="grid gap-5 rounded-[20px] border border-[rgba(120,178,196,0.18)] bg-[rgba(11,27,39,0.82)] p-[18px] shadow-[0_18px_70px_rgba(0,0,0,0.18)] backdrop-blur-xl xl:grid-cols-[1.35fr_1fr]">
        <div className="grid gap-4">
          <div>
            <p className="text-sm text-[#8da8b5]">Live system overview</p>
            <h2 className="mt-1 text-[clamp(1.7rem,3vw,2.8rem)] font-semibold">System, device, and client views aligned to docs.</h2>
            <p className="mt-3 max-w-2xl text-[#8da8b5]">
              Heartbeat is 1 second, offline is 10 seconds, and battery policy follows 30% warning / 10% auto-return.
            </p>
          </div>
          <Suspense
            fallback={
              <div className="grid h-[380px] place-items-center rounded-[20px] border border-white/10 bg-white/5 text-sm text-[#8da8b5]">
                Loading 3D scene...
              </div>
            }
          >
            <SceneCanvas />
          </Suspense>
        </div>

        <div className="grid gap-3">
          <StatCard
            label="Registry"
            value={meta.data?.server ? `${meta.data.server.host ?? '127.0.0.1'}:${meta.data.server.port ?? 8280}` : '127.0.0.1:8280'}
            hint="registration service"
          />
          <StatCard label="Devices" value={`${deviceList.length}`} hint="tracked devices" />
          <StatCard label="Active proposals" value={`${proposalList.filter((item) => item.status === 'PROPOSED' || item.status === 'APPROVED').length}`} hint="proposal pipeline" />
          <StatCard label="Connections" value={`${connectionList.filter((item) => !item.deleted_at).length}`} hint="active relay graph" />
        </div>
      </section>

      <div className="grid gap-5 xl:grid-cols-2">
        <PageCard title="Fleet Overview">
          <div className="grid gap-3">
            {deviceList.map((device) => (
              <article key={device.id} className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <strong className="block">{device.name}</strong>
                    <p className="text-sm text-[#8da8b5]">{device.type}</p>
                  </div>
                  <span className="rounded-full px-3 py-1 text-sm bg-white/10">{device.status}</span>
                </div>
                <div className="mt-3 flex flex-wrap justify-between gap-2 text-sm text-[#8da8b5]">
                  <span>Battery {device.battery}%</span>
                  <span>{device.connection}</span>
                  <span>Agent {device.device_agent_id ?? 'unassigned'}</span>
                </div>
              </article>
            ))}
          </div>
        </PageCard>

        <PageCard title="Recent Events">
          <div className="grid gap-3">
            {eventList.map((event) => (
              <div key={`${event.type}-${event.at}`} className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-white/10 bg-white/5 p-4">
                <span className="rounded-full px-3 py-1 text-sm bg-white/10">{event.type}</span>
                <strong>{event.title}</strong>
                <span className="text-sm text-[#8da8b5]">{event.at}</span>
              </div>
            ))}
          </div>
        </PageCard>
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <PageCard title="Mission Snapshot">
          <div className="grid gap-3">
            {missionList.length === 0 ? (
              <p className="text-sm text-[#8da8b5]">No active missions</p>
            ) : (
              missionList.map((mission) => (
                <article key={mission.id || mission.mission_id} className="rounded-2xl border border-white/10 bg-white/5 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <strong>{mission.title}</strong>
                    <span className={`text-sm ${
                      mission.status === 'COMPLETED' ? 'text-green-400' :
                      mission.status === 'IN_PROGRESS' ? 'text-blue-400' :
                      mission.status === 'FAILED' ? 'text-red-400' :
                      'text-gray-400'
                    }`}>{mission.status}</span>
                  </div>
                  {mission.progress !== undefined && (
                    <>
                      <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/10">
                        <div className="h-full rounded-full bg-gradient-to-r from-[#5bc0be] to-[#7dd3fc]" style={{ width: `${mission.progress}%` }} />
                      </div>
                      <small className="mt-2 block text-[#8da8b5]">{mission.progress}% complete</small>
                    </>
                  )}
                </article>
              ))
            )}
          </div>
        </PageCard>

        <PageCard title="Connection Graph">
          <div className="grid gap-3">
            {connectionList.map((connection) => (
              <article key={connection.connection_id} className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <div className="flex items-center justify-between gap-3">
                  <strong>{connection.agent_a_id}</strong>
                  <span className="text-sm text-[#8da8b5]">{connection.connection_type}</span>
                </div>
                <div className="mt-2 flex items-center justify-between gap-3 text-sm text-[#8da8b5]">
                  <span>→ {connection.agent_b_id}</span>
                  <span>{connection.deleted_at ? 'SOFT_DELETED' : 'ACTIVE'}</span>
                </div>
              </article>
            ))}
          </div>
        </PageCard>
      </div>
    </div>
  );
}
