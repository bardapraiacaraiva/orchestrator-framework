import { getConfig, getHealth } from '@/lib/orchestrator';

export default function SettingsPage() {
  const config = getConfig();
  const health = getHealth();

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold mb-8">Settings</h1>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Company */}
        <div className="bg-[#1a2235] border border-[#2a3a5a] rounded-xl p-6">
          <h2 className="text-sm font-bold text-gray-400 uppercase tracking-wider mb-4">Company</h2>
          <div className="space-y-3">
            <div className="flex justify-between"><span className="text-sm text-gray-400">Name</span><span className="text-sm font-medium">{config.company.name}</span></div>
            <div className="flex justify-between"><span className="text-sm text-gray-400">Owner</span><span className="text-sm font-medium">{config.company.owner}</span></div>
            <div className="flex justify-between"><span className="text-sm text-gray-400">Monthly Limit</span><span className="text-sm font-medium">{config.company.budget_limit.toLocaleString()} tokens</span></div>
            <div className="flex justify-between"><span className="text-sm text-gray-400">Alert at</span><span className="text-sm font-medium">{(config.company.alert_threshold * 100).toFixed(0)}%</span></div>
            <div className="flex justify-between"><span className="text-sm text-gray-400">Hard Stop at</span><span className="text-sm font-medium">{(config.company.auto_pause * 100).toFixed(0)}%</span></div>
          </div>
        </div>

        {/* Execution Policies */}
        <div className="bg-[#1a2235] border border-[#2a3a5a] rounded-xl p-6">
          <h2 className="text-sm font-bold text-gray-400 uppercase tracking-wider mb-4">Execution Policies</h2>
          <div className="space-y-3">
            {Object.entries(config.policies).map(([name, pol]: [string, any]) => (
              <div key={name} className="flex items-center justify-between py-2 border-b border-[#2a3a5a]/50">
                <span className="text-sm font-medium text-cyan-400">{name}</span>
                <div className="flex gap-3 text-xs text-gray-400">
                  <span>SLA: {pol.sla_hours}h</span>
                  {pol.review_required && <span className="text-amber-400">review</span>}
                  {pol.approval_required && <span className="text-red-400">approval</span>}
                  <span>max {pol.revision_max_loops} revisions</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* System Health */}
        <div className="bg-[#1a2235] border border-[#2a3a5a] rounded-xl p-6">
          <h2 className="text-sm font-bold text-gray-400 uppercase tracking-wider mb-4">System Health</h2>
          <div className="space-y-3">
            {health.checks.map(c => {
              const dotColor = c.status === 'up' ? 'bg-green-400 shadow-green-400/50' : c.status === 'warning' ? 'bg-amber-400 shadow-amber-400/50' : 'bg-red-400 shadow-red-400/50';
              return (
                <div key={c.name} className="flex items-center gap-3">
                  <span className={`w-2.5 h-2.5 rounded-full ${dotColor} shadow-sm`} />
                  <span className="text-sm font-medium flex-1">{c.name}</span>
                  <span className="text-xs text-gray-400">{c.detail}</span>
                </div>
              );
            })}
          </div>
          <div className="mt-4 pt-4 border-t border-[#2a3a5a]">
            <span className={`text-sm font-bold ${health.overall === 'healthy' ? 'text-green-400' : health.overall === 'degraded' ? 'text-amber-400' : 'text-red-400'}`}>
              System: {health.overall.toUpperCase()}
            </span>
          </div>
        </div>

        {/* Last Pulse */}
        <div className="bg-[#1a2235] border border-[#2a3a5a] rounded-xl p-6">
          <h2 className="text-sm font-bold text-gray-400 uppercase tracking-wider mb-4">Last Pulse</h2>
          <div className="space-y-3">
            <div className="flex justify-between"><span className="text-sm text-gray-400">Time</span><span className="text-sm font-medium">{config.pulse.time || 'Never'}</span></div>
            {config.pulse.tasks && typeof config.pulse.tasks === 'object' && Object.entries(config.pulse.tasks).map(([k, v]) => (
              <div key={k} className="flex justify-between"><span className="text-sm text-gray-400">{k}</span><span className="text-sm font-medium">{String(v)}</span></div>
            ))}
            {config.pulse.budget && typeof config.pulse.budget === 'object' && Object.entries(config.pulse.budget).map(([k, v]) => (
              <div key={k} className="flex justify-between"><span className="text-sm text-gray-400">{k}</span><span className="text-sm font-medium">{String(v)}</span></div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
