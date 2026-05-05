import { getSkills } from '@/lib/orchestrator';

const groupColors: Record<string, string> = {
  dario: 'text-cyan-400 border-cyan-400/30 bg-cyan-400/10',
  diva: 'text-purple-400 border-purple-400/30 bg-purple-400/10',
  lucas: 'text-green-400 border-green-400/30 bg-green-400/10',
  seo: 'text-amber-400 border-amber-400/30 bg-amber-400/10',
  a360: 'text-blue-400 border-blue-400/30 bg-blue-400/10',
  other: 'text-gray-400 border-gray-400/30 bg-gray-400/10',
};

export default function SkillsPage() {
  const data = getSkills();

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-2xl font-bold">Skill Marketplace</h1>
        <div className="text-sm text-gray-400">{data.total} skills installed</div>
      </div>

      {/* Group badges */}
      <div className="flex gap-3 mb-8 flex-wrap">
        {Object.entries(data.groups).map(([group, skills]) => (
          skills.length > 0 && (
            <span key={group} className={`px-4 py-2 rounded-xl border text-sm font-semibold ${groupColors[group] || groupColors.other}`}>
              {group.toUpperCase()} ({skills.length})
            </span>
          )
        ))}
      </div>

      {/* Skills grid by group */}
      {Object.entries(data.groups).map(([group, skills]) => {
        if (skills.length === 0) return null;
        const colors = groupColors[group] || groupColors.other;
        return (
          <div key={group} className="mb-8">
            <h2 className={`text-lg font-bold mb-4 ${colors.split(' ')[0]}`}>{group.toUpperCase()}</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {skills.map(s => {
                const quality = s.lines >= 100 ? 'border-green-400/20' : s.lines >= 50 ? 'border-amber-400/20' : 'border-red-400/20';
                const qualityLabel = s.lines >= 100 ? 'Complete' : s.lines >= 50 ? 'Partial' : 'Stub';
                const qualityColor = s.lines >= 100 ? 'text-green-400' : s.lines >= 50 ? 'text-amber-400' : 'text-red-400';
                return (
                  <div key={s.name} className={`bg-[#1a2235] border ${quality} rounded-xl p-4 hover:border-cyan-400/30 transition-colors`}>
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-semibold text-white">/{s.name}</span>
                      <span className={`text-xs ${qualityColor}`}>{s.lines}L • {qualityLabel}</span>
                    </div>
                    <p className="text-xs text-gray-400 line-clamp-2 leading-relaxed">{s.description || 'No description'}</p>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
