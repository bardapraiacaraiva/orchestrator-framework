import { getMonitoring } from '@/lib/orchestrator';

const layerColors: Record<string, { bg: string; border: string; text: string; dot: string }> = {
  Watchdog: { bg: 'bg-green-400/5', border: 'border-green-400/20', text: 'text-green-400', dot: 'bg-green-400 shadow-[0_0_8px_rgba(0,230,118,0.5)]' },
  Heartbeat: { bg: 'bg-cyan-400/5', border: 'border-cyan-400/20', text: 'text-cyan-400', dot: 'bg-cyan-400 shadow-[0_0_8px_rgba(0,229,255,0.5)]' },
  'Last Resort': { bg: 'bg-amber-400/5', border: 'border-amber-400/20', text: 'text-amber-400', dot: 'bg-amber-400 shadow-[0_0_8px_rgba(255,171,0,0.5)]' },
};

const statusColors: Record<string, string> = {
  up: 'bg-green-400 shadow-[0_0_6px_rgba(0,230,118,0.5)]',
  degraded: 'bg-amber-400 shadow-[0_0_6px_rgba(255,171,0,0.5)]',
  down: 'bg-red-400 shadow-[0_0_6px_rgba(255,82,82,0.5)]',
};

export default function MonitoringPage() {
  const data = getMonitoring();

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-2xl font-bold">Monitoring</h1>
        <div className="flex gap-3 items-center">
          <span className={`text-sm font-bold ${data.uptime_7d >= 99 ? 'text-green-400' : data.uptime_7d >= 95 ? 'text-amber-400' : 'text-red-400'}`}>
            {data.uptime_7d}% uptime (7d)
          </span>
          <span className="text-xs text-gray-500">{data.total_checks_7d} checks | {data.total_failures_7d} failures</span>
        </div>
      </div>

      {/* 3-Layer Monitoring */}
      <div className="mb-8">
        <h2 className="text-sm font-bold text-gray-400 uppercase tracking-wider mb-4">3-Layer Protection</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {data.layers.map((layer: any) => {
            const c = layerColors[layer.name] || layerColors.Watchdog;
            return (
              <div key={layer.name} className={`${c.bg} border ${c.border} rounded-xl p-5`}>
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <span className={`w-2.5 h-2.5 rounded-full ${c.dot} ${layer.status === 'active' ? 'animate-pulse' : ''}`} />
                    <span className={`text-lg font-bold ${c.text}`}>{layer.name}</span>
                  </div>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${c.border} ${c.text}`}>
                    {layer.status === 'active' ? 'ACTIVE' : 'STANDBY'}
                  </span>
                </div>

                <div className="text-center py-4">
                  <div className={`text-4xl font-extrabold ${c.text}`}>{layer.interval}<span className="text-lg">min</span></div>
                  <div className="text-xs text-gray-500 mt-1">Check interval</div>
                </div>

                <div className="space-y-2 text-xs">
                  <div className="flex justify-between">
                    <span className="text-gray-500">Checks (24h)</span>
                    <span className="text-gray-300 font-medium">{layer.checks_24h}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Failures (24h)</span>
                    <span className={layer.failures_24h > 0 ? 'text-red-400 font-bold' : 'text-green-400'}>{layer.failures_24h}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Uptime</span>
                    <span className={`font-bold ${layer.uptime >= 99 ? 'text-green-400' : 'text-amber-400'}`}>{layer.uptime}%</span>
                  </div>
                </div>

                {/* Visual bar showing layer coverage */}
                <div className="mt-3 pt-3 border-t border-[#2a3a5a]">
                  <div className="flex items-center gap-2">
                    <div className="h-1.5 flex-1 bg-[#2a3a5a] rounded-full overflow-hidden">
                      <div className={`h-full rounded-full ${c.dot.split(' ')[0]}`} style={{ width: `${layer.uptime}%` }} />
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Flow description */}
        <div className="mt-4 flex items-center justify-center gap-3 text-xs text-gray-500">
          <span className="text-green-400 font-semibold">Watchdog (5min)</span>
          <span>→ detects issue →</span>
          <span className="text-cyan-400 font-semibold">Heartbeat (15min)</span>
          <span>→ escalates if unresolved →</span>
          <span className="text-amber-400 font-semibold">Last Resort (30min)</span>
          <span>→ full system recovery</span>
        </div>
      </div>

      {/* Services Grid */}
      <div className="mb-8">
        <h2 className="text-sm font-bold text-gray-400 uppercase tracking-wider mb-4">Services ({data.services.length})</h2>
        <div className="bg-[#1a2235] border border-[#2a3a5a] rounded-xl overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-[#2a3a5a]">
                <th className="text-left text-xs text-gray-400 uppercase tracking-wider px-5 py-3">Service</th>
                <th className="text-left text-xs text-gray-400 uppercase tracking-wider px-5 py-3">Status</th>
                <th className="text-left text-xs text-gray-400 uppercase tracking-wider px-5 py-3">Latency</th>
                <th className="text-left text-xs text-gray-400 uppercase tracking-wider px-5 py-3">Port</th>
              </tr>
            </thead>
            <tbody>
              {data.services.map((s: any) => (
                <tr key={s.name} className="border-b border-[#2a3a5a]/50 hover:bg-white/[.02] transition-colors">
                  <td className="px-5 py-3 text-sm font-medium text-white">{s.name}</td>
                  <td className="px-5 py-3">
                    <div className="flex items-center gap-2">
                      <span className={`w-2 h-2 rounded-full ${statusColors[s.status] || statusColors.up}`} />
                      <span className={`text-xs font-semibold uppercase ${s.status === 'up' ? 'text-green-400' : s.status === 'degraded' ? 'text-amber-400' : 'text-red-400'}`}>
                        {s.status}
                      </span>
                    </div>
                  </td>
                  <td className="px-5 py-3 text-sm text-gray-400">{s.latency}ms</td>
                  <td className="px-5 py-3 text-sm text-gray-500">{s.port || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recovery Stats */}
        <div className="bg-[#1a2235] border border-[#2a3a5a] rounded-xl p-6">
          <h2 className="text-sm font-bold text-gray-400 uppercase tracking-wider mb-4">Recovery Stats</h2>
          <div className="space-y-3">
            <div className="flex justify-between"><span className="text-sm text-gray-400">Mean Recovery Time</span><span className="text-sm font-bold text-cyan-400">{data.mean_recovery_time}</span></div>
            <div className="flex justify-between"><span className="text-sm text-gray-400">Total Checks (7d)</span><span className="text-sm font-medium text-white">{data.total_checks_7d.toLocaleString()}</span></div>
            <div className="flex justify-between"><span className="text-sm text-gray-400">Total Failures (7d)</span><span className={`text-sm font-bold ${data.total_failures_7d > 0 ? 'text-amber-400' : 'text-green-400'}`}>{data.total_failures_7d}</span></div>
            <div className="flex justify-between"><span className="text-sm text-gray-400">Uptime (7d)</span><span className={`text-sm font-bold ${data.uptime_7d >= 99 ? 'text-green-400' : 'text-amber-400'}`}>{data.uptime_7d}%</span></div>
          </div>
        </div>

        {/* Recent Incidents */}
        <div className="bg-[#1a2235] border border-[#2a3a5a] rounded-xl p-6">
          <h2 className="text-sm font-bold text-gray-400 uppercase tracking-wider mb-4">Recent Incidents</h2>
          {data.incidents.length === 0 ? (
            <div className="text-gray-500 text-center py-6 text-sm">No recent incidents. All systems nominal.</div>
          ) : (
            <div className="space-y-3">
              {data.incidents.map((inc: any, i: number) => (
                <div key={i} className="flex items-start gap-3 py-2 border-b border-[#2a3a5a]/50">
                  <span className={`w-2 h-2 rounded-full mt-1.5 ${inc.resolved ? 'bg-green-400' : 'bg-red-400'}`} />
                  <div className="flex-1">
                    <div className="text-sm font-medium text-white">{inc.service}</div>
                    <div className="text-xs text-gray-500">{inc.date} — Duration: {inc.duration} — Resolved by: <span className="text-cyan-400">{inc.layer}</span></div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
