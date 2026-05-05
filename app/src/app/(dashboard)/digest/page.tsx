import { getDailyDigest, getQuality, getBudget, getTasks } from '@/lib/orchestrator';

export default function DigestPage() {
  const digest = getDailyDigest();
  const quality = getQuality();
  const budget = getBudget();
  const tasks = getTasks();

  const s = digest.summary;
  const healthColor = s.health_status === 'healthy' ? 'text-green-400' : s.health_status === 'degraded' ? 'text-amber-400' : 'text-red-400';

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-2xl font-bold">Daily Digest</h1>
        <div className="text-sm text-gray-400">{digest.date}</div>
      </div>

      {/* Status Banner */}
      <div className={`mb-8 rounded-xl p-6 border ${
        s.health_status === 'healthy' ? 'bg-green-400/5 border-green-400/20' :
        s.health_status === 'degraded' ? 'bg-amber-400/5 border-amber-400/20' :
        'bg-red-400/5 border-red-400/20'
      }`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <span className={`text-4xl font-extrabold ${healthColor}`}>
              {s.health_status === 'healthy' ? '✓' : s.health_status === 'degraded' ? '⚠' : '✗'}
            </span>
            <div>
              <div className={`text-lg font-bold ${healthColor}`}>System {s.health_status.toUpperCase()}</div>
              <div className="text-sm text-gray-400">{s.health_checks_passing}/{s.health_checks_total} checks passing</div>
            </div>
          </div>
          <div className="text-right">
            <div className="text-sm text-gray-400">Report generated</div>
            <div className="text-sm text-white font-medium">{new Date().toLocaleTimeString('pt-PT', { hour: '2-digit', minute: '2-digit' })}</div>
          </div>
        </div>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <KPICard label="Tasks Active" value={s.tasks_active} color="text-cyan-400" />
        <KPICard label="Completed Today" value={s.tasks_completed_today} color="text-green-400" />
        <KPICard label="Quality Avg" value={s.quality_avg.toFixed(1)} color="text-purple-400" />
        <KPICard label="Budget Used" value={`${s.budget_percentage}%`} color={s.budget_percentage > 80 ? 'text-amber-400' : 'text-cyan-400'} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Tasks Summary */}
        <div className="bg-[#1a2235] border border-[#2a3a5a] rounded-xl p-6">
          <h2 className="text-sm font-bold text-gray-400 uppercase tracking-wider mb-4">Task Pipeline</h2>
          <div className="space-y-3">
            {Object.entries(tasks.byStatus).map(([status, count]) => {
              const color = status === 'done' ? 'bg-green-400' : status === 'in_progress' ? 'bg-amber-400' : status === 'blocked' ? 'bg-red-400' : status === 'in_review' ? 'bg-purple-400' : 'bg-cyan-400';
              const max = Math.max(...Object.values(tasks.byStatus) as number[], 1);
              const pct = ((count as number) / max) * 100;
              return (
                <div key={status}>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-gray-400">{status.replace(/_/g, ' ')}</span>
                    <span className="text-white font-semibold">{count as number}</span>
                  </div>
                  <div className="h-2 bg-[#2a3a5a] rounded-full overflow-hidden">
                    <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${pct}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Quality Breakdown */}
        <div className="bg-[#1a2235] border border-[#2a3a5a] rounded-xl p-6">
          <h2 className="text-sm font-bold text-gray-400 uppercase tracking-wider mb-4">Quality Overview</h2>
          <div className="flex items-center gap-6 mb-4">
            <div className="text-center">
              <div className="text-4xl font-extrabold text-cyan-400">{quality.global_avg.toFixed(1)}</div>
              <div className="text-xs text-gray-500">Score /100</div>
            </div>
            <div className="flex gap-3">
              <div className="text-center">
                <div className="text-xl font-bold text-green-400">{quality.tier_a}</div>
                <div className="text-[10px] text-gray-500">Tier A</div>
              </div>
              <div className="text-center">
                <div className="text-xl font-bold text-amber-400">{quality.tier_b}</div>
                <div className="text-[10px] text-gray-500">Tier B</div>
              </div>
              <div className="text-center">
                <div className="text-xl font-bold text-gray-400">{quality.unscored}</div>
                <div className="text-[10px] text-gray-500">Unscored</div>
              </div>
            </div>
          </div>
          {quality.skills.slice(0, 3).map(s => (
            <div key={s.name} className="flex items-center justify-between py-2 border-b border-[#2a3a5a]/50">
              <span className="text-sm text-white">{s.name}</span>
              <span className={`text-sm font-bold ${s.score >= 85 ? 'text-green-400' : 'text-amber-400'}`}>{s.score.toFixed(0)}</span>
            </div>
          ))}
        </div>

        {/* Budget Status */}
        <div className="bg-[#1a2235] border border-[#2a3a5a] rounded-xl p-6">
          <h2 className="text-sm font-bold text-gray-400 uppercase tracking-wider mb-4">Budget Status</h2>
          <div className="flex items-center gap-4 mb-4">
            <div className="relative w-20 h-20">
              <svg viewBox="0 0 36 36" className="w-20 h-20 -rotate-90">
                <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="#2a3a5a" strokeWidth="3" />
                <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none"
                  stroke={budget.percentage > 80 ? '#ffab00' : '#00e5ff'}
                  strokeWidth="3" strokeDasharray={`${budget.percentage}, 100`} strokeLinecap="round" />
              </svg>
              <span className="absolute inset-0 flex items-center justify-center text-sm font-bold text-white">{budget.percentage}%</span>
            </div>
            <div>
              <div className="text-sm text-gray-400">{(budget.total_tokens_used / 1000000).toFixed(2)}M / {(budget.limit / 1000000).toFixed(0)}M tokens</div>
              <div className="text-xs text-gray-500 mt-1">Month: {budget.month}</div>
            </div>
          </div>
        </div>

        {/* Today's Events */}
        <div className="bg-[#1a2235] border border-[#2a3a5a] rounded-xl p-6">
          <h2 className="text-sm font-bold text-gray-400 uppercase tracking-wider mb-4">
            Today&apos;s Events ({digest.events.length})
            {digest.alerts.length > 0 && <span className="ml-2 text-red-400">({digest.alerts.length} alerts)</span>}
          </h2>
          {digest.events.length === 0 ? (
            <div className="text-gray-500 text-center py-6 text-sm">No events recorded today.</div>
          ) : (
            <div className="space-y-2 max-h-48 overflow-y-auto">
              {digest.events.map((e: any, i: number) => {
                const ts = typeof e.timestamp === 'string' ? e.timestamp.slice(11, 16) : '--:--';
                return (
                  <div key={i} className="flex gap-3 text-xs py-1">
                    <span className="text-gray-600 font-mono w-10 shrink-0">{ts}</span>
                    <span className="text-cyan-400 font-semibold w-20 shrink-0">{e.actor || 'system'}</span>
                    <span className="text-gray-400 flex-1">{typeof e.details === 'string' ? e.details : JSON.stringify(e.details || e.action)}</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function KPICard({ label, value, color }: { label: string; value: string | number; color: string }) {
  return (
    <div className="bg-[#1a2235] border border-[#2a3a5a] rounded-xl p-5 text-center">
      <div className={`text-3xl font-extrabold ${color}`}>{value}</div>
      <div className="text-xs text-gray-400 mt-1">{label}</div>
    </div>
  );
}
