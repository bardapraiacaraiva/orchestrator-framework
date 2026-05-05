import { getAgents } from '@/lib/orchestrator';

const typeColors: Record<string, string> = {
  orchestrator: 'bg-cyan-400/15 text-cyan-400 border-cyan-400/30',
  agent: 'bg-blue-400/15 text-blue-400 border-blue-400/30',
  worker: 'bg-gray-400/15 text-gray-400 border-gray-400/30',
  shared: 'bg-purple-400/15 text-purple-400 border-purple-400/30',
};

export default function AgentsPage() {
  const data = getAgents();

  // Group agents by type
  const orchestrators = data.agents.filter(a => a.type === 'orchestrator');
  const directors = data.agents.filter(a => a.type === 'agent' || a.type === 'director');
  const shared = data.agents.filter(a => a.type === 'shared');

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-2xl font-bold">Agent Network</h1>
        <div className="flex gap-3 text-sm text-gray-400">
          <span className="text-cyan-400 font-semibold">{data.total_agents}</span> agents
          <span className="text-gray-500">+</span>
          <span className="text-green-400 font-semibold">{data.total_workers}</span> workers
          <span className="text-gray-500">=</span>
          <span className="text-white font-bold">{data.total}</span> entities
        </div>
      </div>

      {/* Orchestrators (CEO + VPs) */}
      <div className="mb-8">
        <h2 className="text-sm font-bold text-cyan-400 uppercase tracking-wider mb-4">Executive Layer</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {orchestrators.map(a => (
            <div key={a.id} className="bg-gradient-to-br from-cyan-400/10 to-[#1a2235] border border-cyan-400/20 rounded-xl p-5">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <span className="text-lg font-bold text-white">{a.name}</span>
                  <span className="ml-2 text-xs text-gray-400">{a.title}</span>
                </div>
                <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${typeColors.orchestrator}`}>ORCHESTRATOR</span>
              </div>
              {a.adapter && <div className="text-xs text-gray-500 mb-2">Adapter: {a.adapter}</div>}
              {a.heartbeat && (
                <div className="text-xs text-gray-500 mb-2">
                  Heartbeat: every {a.heartbeat.interval_minutes}min
                  {a.heartbeat.enable_assignment_wakeup && ' + assignment wakeup'}
                </div>
              )}
              <div className="flex flex-wrap gap-1 mt-3">
                {a.capabilities.slice(0, 6).map((c: string) => (
                  <span key={c} className="px-2 py-0.5 bg-cyan-400/10 border border-cyan-400/15 rounded text-[10px] text-cyan-400">{c.replace(/_/g, ' ')}</span>
                ))}
                {a.capabilities.length > 6 && <span className="text-[10px] text-gray-500 px-2 py-0.5">+{a.capabilities.length - 6} more</span>}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Directors */}
      <div className="mb-8">
        <h2 className="text-sm font-bold text-blue-400 uppercase tracking-wider mb-4">Directors ({directors.length})</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {directors.map(a => {
            const h = data.hierarchy as Record<string, any[]>;
            const workerCount = h[a.id]?.length || 0;
            return (
              <div key={a.id} className="bg-[#1a2235] border border-[#2a3a5a] rounded-xl p-4 hover:border-blue-400/30 transition-colors">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-semibold text-white">{a.name || a.id}</span>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${typeColors.agent}`}>DIRECTOR</span>
                </div>
                <div className="text-xs text-gray-400 mb-1">{a.title}</div>
                {a.reports_to && <div className="text-xs text-gray-500">Reports to: {a.reports_to}</div>}
                {workerCount > 0 && <div className="text-xs text-green-400 mt-2">{workerCount} workers</div>}
                <div className="flex flex-wrap gap-1 mt-2">
                  {a.capabilities.slice(0, 4).map((c: string) => (
                    <span key={c} className="px-1.5 py-0.5 bg-blue-400/10 border border-blue-400/15 rounded text-[10px] text-blue-400/70">{c.replace(/_/g, ' ')}</span>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Shared Services */}
      {shared.length > 0 && (
        <div className="mb-8">
          <h2 className="text-sm font-bold text-purple-400 uppercase tracking-wider mb-4">Shared Services ({shared.length})</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
            {shared.map(a => (
              <div key={a.id} className="bg-[#1a2235] border border-purple-400/20 rounded-xl p-4">
                <div className="text-sm font-semibold text-purple-400">{a.name || a.id}</div>
                <div className="text-xs text-gray-400 mt-1">{a.title}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Workers by Director */}
      <div>
        <h2 className="text-sm font-bold text-green-400 uppercase tracking-wider mb-4">Workers ({data.total_workers})</h2>
        <div className="bg-[#1a2235] border border-[#2a3a5a] rounded-xl overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-[#2a3a5a]">
                <th className="text-left text-xs text-gray-400 uppercase tracking-wider px-5 py-3">Worker</th>
                <th className="text-left text-xs text-gray-400 uppercase tracking-wider px-5 py-3">Skill</th>
                <th className="text-left text-xs text-gray-400 uppercase tracking-wider px-5 py-3">Reports To</th>
                <th className="text-left text-xs text-gray-400 uppercase tracking-wider px-5 py-3">Capabilities</th>
              </tr>
            </thead>
            <tbody>
              {data.workers.map(w => (
                <tr key={w.id} className="border-b border-[#2a3a5a]/50 hover:bg-white/[.02] transition-colors">
                  <td className="px-5 py-2.5 text-sm font-medium text-white">{w.id}</td>
                  <td className="px-5 py-2.5 text-sm text-cyan-400">{w.skill}</td>
                  <td className="px-5 py-2.5 text-sm text-gray-400">{w.reports_to || '—'}</td>
                  <td className="px-5 py-2.5">
                    <div className="flex flex-wrap gap-1">
                      {w.capabilities.slice(0, 3).map((c: string) => (
                        <span key={c} className="px-1.5 py-0.5 bg-green-400/10 border border-green-400/15 rounded text-[10px] text-green-400/70">{c.replace(/_/g, ' ')}</span>
                      ))}
                      {w.capabilities.length > 3 && <span className="text-[10px] text-gray-500">+{w.capabilities.length - 3}</span>}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
