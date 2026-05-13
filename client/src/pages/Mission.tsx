import { useState, useEffect } from 'react';
import { PageCard } from '../components/layout/PageCard';
import { useMission } from '../hooks/useMission';
import { fetchJson, REGISTRY_URL } from '../services/api';
import type { Task } from '../types';

const STATUS_COLOR: Record<string, string> = {
  COMPLETED: 'text-green-400 bg-green-400/10',
  IN_PROGRESS: 'text-blue-400 bg-blue-400/10',
  FAILED: 'text-red-400 bg-red-400/10',
  READY: 'text-yellow-400 bg-yellow-400/10',
  CANCELLED: 'text-gray-400 bg-gray-400/10',
};

export function MissionPage() {
  const { missions, isLoading } = useMission();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [tasksLoading, setTasksLoading] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [filterStatus, setFilterStatus] = useState<string>('ALL');

  const selectedMission = missions.find(
    m => m.mission_id === selectedId || m.id === selectedId
  ) ?? null;

  useEffect(() => {
    const id = selectedMission?.mission_id;
    if (!id) { setTasks([]); return; }
    setTasksLoading(true);
    fetchJson<Task[]>(`/missions/${id}/tasks`)
      .then(setTasks)
      .catch(() => setTasks([]))
      .finally(() => setTasksLoading(false));
  }, [selectedMission?.mission_id]);

  const handleCancel = async () => {
    if (!selectedMission?.mission_id) return;
    setCancelling(true);
    try {
      await fetch(`${REGISTRY_URL}/missions/${selectedMission.mission_id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...selectedMission, status: 'CANCELLED' }),
      });
      setSelectedId(null);
    } catch (err) {
      console.error('Cancel failed:', err);
    } finally {
      setCancelling(false);
    }
  };

  const statusOptions = ['ALL', 'READY', 'IN_PROGRESS', 'COMPLETED', 'FAILED', 'CANCELLED'];
  const filteredMissions = filterStatus === 'ALL'
    ? missions
    : missions.filter(m => m.status === filterStatus);

  return (
    <div className="grid gap-5 xl:grid-cols-2">
      {/* Left: Mission list */}
      <PageCard title="Missions">
        {/* Filter */}
        <div className="flex gap-1 flex-wrap mb-3">
          {statusOptions.map(s => (
            <button
              key={s}
              onClick={() => setFilterStatus(s)}
              className={`px-2 py-0.5 text-xs rounded transition ${
                filterStatus === s
                  ? 'bg-blue-500/20 text-blue-300 border border-blue-500/30'
                  : 'text-[#64748b] hover:text-[#8da8b5]'
              }`}
            >
              {s}
            </button>
          ))}
        </div>

        {isLoading ? (
          <p className="text-sm text-[#8da8b5]">Loading...</p>
        ) : filteredMissions.length === 0 ? (
          <p className="text-sm text-[#8da8b5]">No missions found</p>
        ) : (
          <div className="space-y-2 max-h-96 overflow-y-auto">
            {filteredMissions.map(mission => {
              const id = mission.mission_id ?? mission.id;
              return (
                <button
                  key={id}
                  onClick={() => setSelectedId(prev => prev === id ? null : (id ?? null))}
                  className={`w-full text-left rounded-lg border p-3 transition ${
                    selectedId === id
                      ? 'border-blue-500/40 bg-blue-500/10'
                      : 'border-white/10 bg-white/5 hover:bg-white/8'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2 mb-1">
                    <strong className="text-sm leading-tight">{mission.title}</strong>
                    <span className={`text-xs px-1.5 py-0.5 rounded whitespace-nowrap ${STATUS_COLOR[mission.status] ?? 'text-gray-400'}`}>
                      {mission.status}
                    </span>
                  </div>
                  {mission.priority && (
                    <p className="text-xs text-[#64748b]">Priority: {mission.priority}</p>
                  )}
                  {mission.created_at && (
                    <p className="text-xs text-[#64748b] mt-1">
                      {new Date(mission.created_at).toLocaleString()}
                    </p>
                  )}
                </button>
              );
            })}
          </div>
        )}
      </PageCard>

      {/* Right: Mission detail */}
      <PageCard title="Mission Detail">
        {!selectedMission ? (
          <div className="space-y-3">
            <p className="text-sm text-[#8da8b5]">Select a mission to view details and tasks.</p>
            <div className="rounded-lg border border-white/10 bg-white/5 p-3 text-xs text-[#64748b] space-y-1">
              <p className="font-semibold text-[#8da8b5]">Status legend</p>
              {Object.entries(STATUS_COLOR).map(([s, c]) => (
                <div key={s} className="flex items-center gap-2">
                  <span className={`px-1.5 py-0.5 rounded text-xs ${c}`}>{s}</span>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Info */}
            <div className="space-y-2 border-b border-white/10 pb-4">
              <strong className="text-lg block">{selectedMission.title}</strong>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div>
                  <p className="text-xs text-[#64748b]">Status</p>
                  <span className={`text-xs px-1.5 py-0.5 rounded inline-block ${STATUS_COLOR[selectedMission.status] ?? 'text-gray-400'}`}>
                    {selectedMission.status}
                  </span>
                </div>
                {selectedMission.priority && (
                  <div>
                    <p className="text-xs text-[#64748b]">Priority</p>
                    <p className="text-sm text-[#8da8b5]">{selectedMission.priority}</p>
                  </div>
                )}
              </div>
              {selectedMission.target_area && (
                <div>
                  <p className="text-xs text-[#64748b]">Target Area</p>
                  <p className="text-sm text-[#8da8b5]">{selectedMission.target_area}</p>
                </div>
              )}
              <div>
                <p className="text-xs text-[#64748b]">Mission ID</p>
                <p className="text-xs font-mono text-[#64748b] break-all">{selectedMission.mission_id}</p>
              </div>
            </div>

            {/* Tasks */}
            <div>
              <p className="text-sm font-semibold text-[#8da8b5] mb-2">Tasks ({tasks.length})</p>
              {tasksLoading ? (
                <p className="text-xs text-[#64748b]">Loading tasks...</p>
              ) : tasks.length === 0 ? (
                <p className="text-xs text-[#64748b]">No tasks assigned yet</p>
              ) : (
                <div className="space-y-1.5 max-h-48 overflow-y-auto">
                  {tasks.map(task => (
                    <div key={task.task_id} className="rounded border border-white/5 bg-white/3 px-3 py-2 text-xs">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-[#8da8b5] font-medium">{task.type}</span>
                        <span className={`${STATUS_COLOR[task.status] ?? 'text-gray-400'} px-1.5 py-0.5 rounded text-xs`}>
                          {task.status}
                        </span>
                      </div>
                      {task.device_id && (
                        <p className="text-[#64748b] mt-1">Device: {task.device_id.substring(0, 16)}...</p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Actions */}
            {['READY', 'IN_PROGRESS'].includes(selectedMission.status) && (
              <div className="border-t border-white/10 pt-3 space-y-2">
                <button
                  onClick={handleCancel}
                  disabled={cancelling}
                  className="w-full px-4 py-2 bg-red-600/80 text-white text-sm rounded hover:bg-red-600 disabled:opacity-50"
                >
                  {cancelling ? 'Cancelling...' : '✕ Cancel Mission'}
                </button>
                <p className="text-xs text-[#64748b] text-center">
                  Cancellation is permanent and notifies all assigned devices.
                </p>
              </div>
            )}

            {selectedMission.status === 'FAILED' && (
              <div className="border-t border-white/10 pt-3 space-y-2">
                <p className="text-xs font-semibold text-red-300">Mission failed. Options:</p>
                <p className="text-xs text-[#64748b]">
                  Create a new proposal via Chat to replan with same or alternate devices.
                </p>
              </div>
            )}
          </div>
        )}
      </PageCard>
    </div>
  );
}
