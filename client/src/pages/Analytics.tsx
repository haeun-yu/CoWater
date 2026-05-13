import { useEffect, useState } from 'react';
import { PageCard } from '../components/layout/PageCard';
import { StatCard } from '../components/layout/StatCard';
import { fetchJson } from '../services/api';

interface MissionStats { [key: string]: number; }
interface Report {
  report_id?: string;
  id?: string;
  type: string;
  title?: string;
  summary?: string;
  created_at?: string;
}

export function AnalyticsPage() {
  const [stats, setStats] = useState<MissionStats>({});
  const [statsLoading, setStatsLoading] = useState(true);
  const [reports, setReports] = useState<Report[]>([]);
  const [reportsLoading, setReportsLoading] = useState(true);

  useEffect(() => {
    fetchJson<MissionStats>('/missions/stats')
      .then(setStats).catch(() => setStats({})).finally(() => setStatsLoading(false));
    fetchJson<Report[]>('/reports')
      .then(d => setReports(Array.isArray(d) ? d : [])).catch(() => setReports([])).finally(() => setReportsLoading(false));
  }, []);

  const total = Object.values(stats).reduce((sum, v) => sum + v, 0);
  const completed = stats.COMPLETED || 0;
  const inProgress = stats.IN_PROGRESS || 0;
  const failed = stats.FAILED || 0;
  const successRate = total > 0 ? Math.round((completed / total) * 100) : 0;

  return (
    <div className="grid gap-5 xl:grid-cols-2">
      {/* Mission Stats */}
      <PageCard title="Mission Analytics">
        {statsLoading ? (
          <p className="text-[#8da8b5]">Loading statistics...</p>
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <StatCard label="Total" value={String(total)} hint="all missions" />
              <StatCard label="Success Rate" value={`${successRate}%`} hint="completed / total" />
            </div>
            <div className="rounded-lg border border-white/10 bg-white/5 p-3 space-y-2">
              {[
                { label: 'Completed', value: completed, color: 'text-green-400' },
                { label: 'In Progress', value: inProgress, color: 'text-blue-400' },
                { label: 'Failed', value: failed, color: 'text-red-400' },
                { label: 'Other', value: total - completed - inProgress - failed, color: 'text-gray-400' },
              ].map(({ label, value, color }) => (
                <div key={label} className="flex items-center justify-between text-sm">
                  <span className="text-[#8da8b5]">{label}</span>
                  <div className="flex items-center gap-3">
                    <div className="w-24 h-1.5 rounded-full bg-white/10 overflow-hidden">
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: total > 0 ? `${(value / total) * 100}%` : '0%',
                          background: color.includes('green') ? '#10b981' : color.includes('blue') ? '#3b82f6' : color.includes('red') ? '#ef4444' : '#6b7280',
                        }}
                      />
                    </div>
                    <strong className={`w-6 text-right ${color}`}>{value}</strong>
                  </div>
                </div>
              ))}
            </div>
            <p className="text-xs text-[#64748b]">
              Statistics from Registry. Anomaly trends visible in Event Log.
            </p>
          </div>
        )}
      </PageCard>

      {/* Reports */}
      <PageCard title="Reports">
        {reportsLoading ? (
          <p className="text-[#8da8b5]">Loading reports...</p>
        ) : reports.length === 0 ? (
          <div className="space-y-3">
            <p className="text-sm text-[#8da8b5]">No reports generated yet.</p>
            <p className="text-xs text-[#64748b]">Reports are auto-generated on mission completion by InsightReporter.</p>
            <div className="rounded-lg border border-white/10 bg-white/5 p-3 space-y-1 text-xs text-[#64748b]">
              <p className="font-semibold text-[#8da8b5]">Report types</p>
              <p>• MISSION_REPORT — per-mission summary</p>
              <p>• DAILY_REPORT — daily aggregation</p>
              <p>• DEVICE_REPORT — per-device health</p>
              <p>• EVENT_REPORT — anomaly trends</p>
            </div>
          </div>
        ) : (
          <div className="space-y-2 max-h-80 overflow-y-auto">
            {reports.map((report, idx) => (
              <div
                key={report.report_id ?? report.id ?? idx}
                className="rounded-lg border border-white/10 bg-white/5 p-3 space-y-1"
              >
                <div className="flex items-start justify-between gap-2">
                  <strong className="text-sm">{report.title ?? report.type}</strong>
                  <span className="text-xs text-[#64748b] whitespace-nowrap">{report.type}</span>
                </div>
                {report.summary && (
                  <p className="text-xs text-[#8da8b5]">{report.summary}</p>
                )}
                {report.created_at && (
                  <p className="text-xs text-[#64748b]">{new Date(report.created_at).toLocaleString()}</p>
                )}
              </div>
            ))}
          </div>
        )}
      </PageCard>
    </div>
  );
}
