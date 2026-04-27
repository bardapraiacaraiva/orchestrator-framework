import { getQuality } from '@/lib/orchestrator';

export default function QualityPage() {
  const data = getQuality();

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold mb-8">Quality Lab</h1>

      {/* Global Score */}
      <div className="flex items-center gap-8 mb-10">
        <div className="text-center">
          <div className="text-6xl font-extrabold text-cyan-400">{data.global_avg.toFixed(1)}</div>
          <div className="text-sm text-gray-400 mt-1">Score Medio /100</div>
        </div>
        <div className="flex gap-4">
          <div className="bg-[#1a2235] border border-[#2a3a5a] rounded-xl px-5 py-3 text-center">
            <div className="text-2xl font-bold text-green-400">{data.tier_a}</div>
            <div className="text-xs text-gray-400">Tier A (≥85)</div>
          </div>
          <div className="bg-[#1a2235] border border-[#2a3a5a] rounded-xl px-5 py-3 text-center">
            <div className="text-2xl font-bold text-amber-400">{data.tier_b}</div>
            <div className="text-xs text-gray-400">Tier B (70-84)</div>
          </div>
          <div className="bg-[#1a2235] border border-[#2a3a5a] rounded-xl px-5 py-3 text-center">
            <div className="text-2xl font-bold text-gray-400">{data.unscored}</div>
            <div className="text-xs text-gray-400">Unscored</div>
          </div>
          <div className="bg-[#1a2235] border border-[#2a3a5a] rounded-xl px-5 py-3 text-center">
            <div className="text-2xl font-bold text-cyan-400">{data.total_scored}</div>
            <div className="text-xs text-gray-400">Tasks Scored</div>
          </div>
        </div>
      </div>

      {/* Playbooks */}
      {data.playbooks.length > 0 && (
        <div className="mb-8">
          <h3 className="text-sm text-gray-400 uppercase tracking-wider mb-3">Domain Playbooks</h3>
          <div className="flex gap-2 flex-wrap">
            {data.playbooks.map(p => (
              <span key={p} className="px-3 py-1 bg-cyan-400/10 border border-cyan-400/20 rounded-full text-xs text-cyan-400 font-medium">{p}</span>
            ))}
          </div>
        </div>
      )}

      {/* Skills Table */}
      <div className="bg-[#1a2235] border border-[#2a3a5a] rounded-xl overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-[#2a3a5a]">
              <th className="text-left text-xs text-gray-400 uppercase tracking-wider px-5 py-3">Skill</th>
              <th className="text-left text-xs text-gray-400 uppercase tracking-wider px-5 py-3">Score</th>
              <th className="text-left text-xs text-gray-400 uppercase tracking-wider px-5 py-3 w-64">Bar</th>
              <th className="text-left text-xs text-gray-400 uppercase tracking-wider px-5 py-3">Executions</th>
              <th className="text-left text-xs text-gray-400 uppercase tracking-wider px-5 py-3">Tier</th>
              <th className="text-left text-xs text-gray-400 uppercase tracking-wider px-5 py-3">Best</th>
              <th className="text-left text-xs text-gray-400 uppercase tracking-wider px-5 py-3">Worst</th>
              <th className="text-left text-xs text-gray-400 uppercase tracking-wider px-5 py-3">Revision %</th>
            </tr>
          </thead>
          <tbody>
            {data.skills.map(s => {
              const color = s.score >= 85 ? 'bg-green-400' : s.score >= 70 ? 'bg-amber-400' : 'bg-red-400';
              const textColor = s.score >= 85 ? 'text-green-400' : s.score >= 70 ? 'text-amber-400' : 'text-red-400';
              const tierColor = s.tier === 'A' ? 'bg-green-400/15 text-green-400 border-green-400/30' :
                               s.tier === 'B' ? 'bg-amber-400/15 text-amber-400 border-amber-400/30' :
                               'bg-gray-400/15 text-gray-400 border-gray-400/30';
              return (
                <tr key={s.name} className="border-b border-[#2a3a5a]/50 hover:bg-white/[.02] transition-colors">
                  <td className="px-5 py-3 text-sm font-medium text-cyan-400">{s.name}</td>
                  <td className={`px-5 py-3 text-sm font-bold ${textColor}`}>{s.score.toFixed(0)}</td>
                  <td className="px-5 py-3">
                    <div className="h-2 bg-[#2a3a5a] rounded-full overflow-hidden">
                      <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${s.score}%` }} />
                    </div>
                  </td>
                  <td className="px-5 py-3 text-sm text-gray-400">{s.executions}</td>
                  <td className="px-5 py-3">
                    <span className={`px-2 py-0.5 rounded text-xs font-semibold border ${tierColor}`}>{s.tier}</span>
                  </td>
                  <td className="px-5 py-3 text-sm text-gray-400">{s.best_score}</td>
                  <td className="px-5 py-3 text-sm text-gray-400">{s.worst_score}</td>
                  <td className="px-5 py-3 text-sm text-gray-400">{(s.revision_rate * 100).toFixed(0)}%</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
