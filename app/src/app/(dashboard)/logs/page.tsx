import { getLogs } from '@/lib/orchestrator';

const actionColors: Record<string, string> = {
  project_created: 'text-cyan-400',
  tasks_created: 'text-cyan-400',
  task_checkout: 'text-amber-400',
  task_completed: 'text-green-400',
  task_assigned: 'text-blue-400',
  dependency_cascade: 'text-purple-400',
  pulse_executed: 'text-cyan-400',
  budget_update: 'text-amber-400',
};

export default function LogsPage() {
  const logs = getLogs(7);

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold mb-8">Audit Trail</h1>

      {logs.length === 0 ? (
        <div className="text-gray-400 text-center py-16">No audit logs found.</div>
      ) : (
        logs.map(day => (
          <div key={day.date} className="mb-8">
            <h2 className="text-sm font-bold text-cyan-400 uppercase tracking-wider mb-4 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-cyan-400" />
              {day.date}
            </h2>
            <div className="bg-[#1a2235] border border-[#2a3a5a] rounded-xl overflow-hidden">
              {Array.isArray(day.entries) && day.entries.map((entry: any, i: number) => {
                const ts = typeof entry.timestamp === 'string' ? entry.timestamp.slice(11, 16) : '--:--';
                const color = actionColors[entry.action] || 'text-gray-400';
                return (
                  <div key={i} className="flex items-start gap-4 px-5 py-3 border-b border-[#2a3a5a]/50 hover:bg-white/[.02] transition-colors">
                    <span className="text-xs text-gray-500 font-mono w-12 flex-shrink-0 pt-0.5">{ts}</span>
                    <span className="text-xs text-cyan-400 font-semibold w-28 flex-shrink-0 pt-0.5">{entry.actor}</span>
                    <span className={`text-xs font-medium w-36 flex-shrink-0 pt-0.5 ${color}`}>{entry.action}</span>
                    <span className="text-xs text-gray-400 flex-1">{typeof entry.details === 'string' ? entry.details : JSON.stringify(entry.details)}</span>
                  </div>
                );
              })}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
