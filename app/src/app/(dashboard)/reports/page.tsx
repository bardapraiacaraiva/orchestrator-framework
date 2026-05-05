import { getTasks, getBudget, getQuality, getSkills, getAgents, getLogs } from '@/lib/orchestrator';

export default function ReportsPage() {
  const tasks = getTasks();
  const budget = getBudget();
  const quality = getQuality();
  const skills = getSkills();
  const agents = getAgents();
  const logs = getLogs(7);

  // Compute weekly stats
  const totalLogEntries = logs.reduce((sum, d) => sum + (Array.isArray(d.entries) ? d.entries.length : 0), 0);
  const tasksCompletedThisWeek = logs.reduce((sum, d) => {
    if (!Array.isArray(d.entries)) return sum;
    return sum + d.entries.filter((e: any) => e.action === 'task_completed').length;
  }, 0);

  // Top skills by execution
  const topSkills = quality.skills.slice(0, 5);

  // Budget burn rate
  const daysInMonth = new Date(new Date().getFullYear(), new Date().getMonth() + 1, 0).getDate();
  const dayOfMonth = new Date().getDate();
  const projectedUsage = dayOfMonth > 0 ? (budget.total_tokens_used / dayOfMonth) * daysInMonth : 0;

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-2xl font-bold">Reports</h1>
        <div className="text-sm text-gray-400">Period: {budget.month}</div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <div className="bg-[#1a2235] border border-[#2a3a5a] rounded-xl p-5 text-center">
          <div className="text-3xl font-extrabold text-cyan-400">{tasks.total}</div>
          <div className="text-xs text-gray-400 mt-1">Total Tasks</div>
          <div className="text-[10px] text-gray-500 mt-0.5">{tasks.byStatus.done} done, {tasks.byStatus.in_progress} active</div>
        </div>
        <div className="bg-[#1a2235] border border-[#2a3a5a] rounded-xl p-5 text-center">
          <div className="text-3xl font-extrabold text-green-400">{quality.global_avg.toFixed(1)}</div>
          <div className="text-xs text-gray-400 mt-1">Quality Score</div>
          <div className="text-[10px] text-gray-500 mt-0.5">{quality.tier_a} Tier A, {quality.tier_b} Tier B</div>
        </div>
        <div className="bg-[#1a2235] border border-[#2a3a5a] rounded-xl p-5 text-center">
          <div className={`text-3xl font-extrabold ${budget.percentage > 80 ? 'text-amber-400' : 'text-cyan-400'}`}>{budget.percentage}%</div>
          <div className="text-xs text-gray-400 mt-1">Budget Used</div>
          <div className="text-[10px] text-gray-500 mt-0.5">{(budget.total_tokens_used / 1000000).toFixed(1)}M / {(budget.limit / 1000000).toFixed(0)}M tokens</div>
        </div>
        <div className="bg-[#1a2235] border border-[#2a3a5a] rounded-xl p-5 text-center">
          <div className="text-3xl font-extrabold text-purple-400">{agents.total}</div>
          <div className="text-xs text-gray-400 mt-1">Entities</div>
          <div className="text-[10px] text-gray-500 mt-0.5">{agents.total_agents} agents, {agents.total_workers} workers</div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Weekly Activity */}
        <div className="bg-[#1a2235] border border-[#2a3a5a] rounded-xl p-6">
          <h2 className="text-sm font-bold text-gray-400 uppercase tracking-wider mb-4">Weekly Activity (Last 7 Days)</h2>
          <div className="space-y-3">
            <div className="flex justify-between"><span className="text-sm text-gray-400">Audit Entries</span><span className="text-sm font-bold text-white">{totalLogEntries}</span></div>
            <div className="flex justify-between"><span className="text-sm text-gray-400">Tasks Completed</span><span className="text-sm font-bold text-green-400">{tasksCompletedThisWeek}</span></div>
            <div className="flex justify-between"><span className="text-sm text-gray-400">Days Logged</span><span className="text-sm font-bold text-cyan-400">{logs.length}</span></div>
          </div>

          {/* Daily breakdown */}
          <div className="mt-4 pt-4 border-t border-[#2a3a5a]">
            <h3 className="text-xs text-gray-500 mb-3">Events per Day</h3>
            <div className="flex items-end gap-2 h-24">
              {logs.reverse().map(d => {
                const count = Array.isArray(d.entries) ? d.entries.length : 0;
                const maxH = Math.max(...logs.map(l => Array.isArray(l.entries) ? l.entries.length : 0), 1);
                const height = (count / maxH) * 100;
                return (
                  <div key={d.date} className="flex-1 flex flex-col items-center gap-1">
                    <div className="w-full bg-cyan-400/20 rounded-t relative" style={{ height: `${height}%`, minHeight: count > 0 ? '4px' : '0' }}>
                      <div className="absolute inset-0 bg-cyan-400/40 rounded-t" />
                    </div>
                    <span className="text-[9px] text-gray-500">{d.date.slice(5)}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Budget Projection */}
        <div className="bg-[#1a2235] border border-[#2a3a5a] rounded-xl p-6">
          <h2 className="text-sm font-bold text-gray-400 uppercase tracking-wider mb-4">Budget Analysis</h2>
          <div className="space-y-3">
            <div className="flex justify-between"><span className="text-sm text-gray-400">Current Usage</span><span className="text-sm font-bold text-white">{(budget.total_tokens_used / 1000000).toFixed(2)}M tokens</span></div>
            <div className="flex justify-between"><span className="text-sm text-gray-400">Monthly Limit</span><span className="text-sm font-bold text-gray-300">{(budget.limit / 1000000).toFixed(0)}M tokens</span></div>
            <div className="flex justify-between"><span className="text-sm text-gray-400">Day {dayOfMonth}/{daysInMonth}</span><span className="text-sm font-bold text-cyan-400">{((dayOfMonth / daysInMonth) * 100).toFixed(0)}% of month</span></div>
            <div className="flex justify-between">
              <span className="text-sm text-gray-400">Projected EOM</span>
              <span className={`text-sm font-bold ${projectedUsage > budget.limit ? 'text-red-400' : 'text-green-400'}`}>
                {(projectedUsage / 1000000).toFixed(1)}M tokens
              </span>
            </div>
          </div>

          {/* Model breakdown */}
          <div className="mt-4 pt-4 border-t border-[#2a3a5a]">
            <h3 className="text-xs text-gray-500 mb-3">By Model</h3>
            <div className="space-y-2">
              {Object.entries(budget.by_model).map(([model, tokens]) => {
                const pct = budget.total_tokens_used > 0 ? ((tokens as number) / budget.total_tokens_used) * 100 : 0;
                const color = model === 'opus' ? 'bg-purple-400' : model === 'sonnet' ? 'bg-cyan-400' : 'bg-green-400';
                return (
                  <div key={model}>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-gray-400 capitalize">{model}</span>
                      <span className="text-gray-300">{((tokens as number) / 1000000).toFixed(2)}M ({pct.toFixed(0)}%)</span>
                    </div>
                    <div className="h-1.5 bg-[#2a3a5a] rounded-full overflow-hidden">
                      <div className={`h-full ${color} rounded-full`} style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Top Skills */}
        <div className="bg-[#1a2235] border border-[#2a3a5a] rounded-xl p-6">
          <h2 className="text-sm font-bold text-gray-400 uppercase tracking-wider mb-4">Top Skills by Quality</h2>
          <div className="space-y-3">
            {topSkills.map((s, i) => {
              const color = s.score >= 85 ? 'text-green-400' : s.score >= 70 ? 'text-amber-400' : 'text-red-400';
              const barColor = s.score >= 85 ? 'bg-green-400' : s.score >= 70 ? 'bg-amber-400' : 'bg-red-400';
              return (
                <div key={s.name}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm text-white">
                      <span className="text-gray-500 mr-2">#{i + 1}</span>
                      {s.name}
                    </span>
                    <span className={`text-sm font-bold ${color}`}>{s.score.toFixed(0)}</span>
                  </div>
                  <div className="h-1.5 bg-[#2a3a5a] rounded-full overflow-hidden">
                    <div className={`h-full ${barColor} rounded-full`} style={{ width: `${s.score}%` }} />
                  </div>
                  <div className="flex justify-between text-[10px] text-gray-500 mt-0.5">
                    <span>{s.executions} executions</span>
                    <span>{(s.revision_rate * 100).toFixed(0)}% revision rate</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Skills Inventory */}
        <div className="bg-[#1a2235] border border-[#2a3a5a] rounded-xl p-6">
          <h2 className="text-sm font-bold text-gray-400 uppercase tracking-wider mb-4">Skills Inventory</h2>
          <div className="space-y-3">
            {Object.entries(skills.groups).map(([group, items]) => {
              if (items.length === 0) return null;
              const complete = items.filter(s => s.lines >= 100).length;
              const partial = items.filter(s => s.lines >= 50 && s.lines < 100).length;
              const stub = items.filter(s => s.lines < 50).length;
              const color = group === 'dario' ? 'text-cyan-400' : group === 'diva' ? 'text-purple-400' : group === 'lucas' ? 'text-green-400' : group === 'seo' ? 'text-amber-400' : group === 'a360' ? 'text-blue-400' : 'text-gray-400';
              return (
                <div key={group} className="flex items-center justify-between py-2 border-b border-[#2a3a5a]/50">
                  <span className={`text-sm font-semibold uppercase ${color}`}>{group}</span>
                  <div className="flex gap-3 text-xs">
                    <span className="text-gray-400">{items.length} total</span>
                    {complete > 0 && <span className="text-green-400">{complete} complete</span>}
                    {partial > 0 && <span className="text-amber-400">{partial} partial</span>}
                    {stub > 0 && <span className="text-red-400">{stub} stub</span>}
                  </div>
                </div>
              );
            })}
          </div>
          <div className="mt-4 pt-4 border-t border-[#2a3a5a] flex justify-between">
            <span className="text-sm text-gray-400">Total installed</span>
            <span className="text-sm font-bold text-white">{skills.total} skills</span>
          </div>
        </div>
      </div>
    </div>
  );
}
