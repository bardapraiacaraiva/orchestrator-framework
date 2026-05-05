import { getProjects } from '@/lib/orchestrator';

export default function ProjectsPage() {
  const data = getProjects();

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-2xl font-bold">Projects</h1>
        <div className="flex gap-4 text-sm">
          <span className="text-gray-400"><span className="text-cyan-400 font-semibold">{data.total}</span> projects</span>
          <span className="text-gray-400"><span className="text-white font-semibold">{data.total_tasks}</span> tasks</span>
          <span className="text-gray-400"><span className="text-amber-400 font-semibold">{(data.total_tokens / 1000000).toFixed(1)}M</span> tokens</span>
        </div>
      </div>

      {data.projects.length === 0 ? (
        <div className="text-gray-400 text-center py-16">No projects found. Tasks will appear here when assigned to projects.</div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {data.projects.map(p => {
            const progress = p.tasks_total > 0 ? (p.tasks_done / p.tasks_total) * 100 : 0;
            const healthColor = progress >= 80 ? 'text-green-400' : progress >= 40 ? 'text-amber-400' : 'text-gray-400';
            const barColor = progress >= 80 ? 'bg-green-400' : progress >= 40 ? 'bg-amber-400' : 'bg-gray-400';
            return (
              <div key={p.name} className="bg-[#1a2235] border border-[#2a3a5a] rounded-xl p-5 hover:border-cyan-400/30 transition-colors">
                {/* Header */}
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-base font-semibold text-white">{p.name}</h3>
                  <span className={`text-sm font-bold ${healthColor}`}>{progress.toFixed(0)}%</span>
                </div>

                {/* Progress bar */}
                <div className="h-2 bg-[#2a3a5a] rounded-full overflow-hidden mb-4">
                  <div className={`h-full ${barColor} rounded-full transition-all`} style={{ width: `${progress}%` }} />
                </div>

                {/* Stats grid */}
                <div className="grid grid-cols-3 gap-3 mb-4">
                  <div className="text-center">
                    <div className="text-lg font-bold text-white">{p.tasks_total}</div>
                    <div className="text-[10px] text-gray-500 uppercase">Total</div>
                  </div>
                  <div className="text-center">
                    <div className="text-lg font-bold text-green-400">{p.tasks_done}</div>
                    <div className="text-[10px] text-gray-500 uppercase">Done</div>
                  </div>
                  <div className="text-center">
                    <div className="text-lg font-bold text-cyan-400">{p.tasks_active}</div>
                    <div className="text-[10px] text-gray-500 uppercase">Active</div>
                  </div>
                </div>

                {/* Token usage */}
                {p.tokens_used > 0 && (
                  <div className="flex justify-between text-xs pt-3 border-t border-[#2a3a5a]">
                    <span className="text-gray-500">Tokens used</span>
                    <span className="text-amber-400 font-medium">{(p.tokens_used / 1000000).toFixed(2)}M</span>
                  </div>
                )}

                {/* Status breakdown */}
                <div className="flex flex-wrap gap-1.5 mt-3">
                  {Object.entries(p.statuses).map(([status, count]) => {
                    const sc = status === 'done' ? 'text-green-400 bg-green-400/10 border-green-400/20' :
                               status === 'in_progress' ? 'text-cyan-400 bg-cyan-400/10 border-cyan-400/20' :
                               status === 'blocked' ? 'text-red-400 bg-red-400/10 border-red-400/20' :
                               status === 'in_review' ? 'text-purple-400 bg-purple-400/10 border-purple-400/20' :
                               'text-gray-400 bg-gray-400/10 border-gray-400/20';
                    return (
                      <span key={status} className={`px-2 py-0.5 rounded text-[10px] font-medium border ${sc}`}>
                        {status.replace(/_/g, ' ')} ({count})
                      </span>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
