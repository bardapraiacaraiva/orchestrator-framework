import { getNotifications } from '@/lib/orchestrator';

const severityStyles: Record<string, { dot: string; bg: string; text: string; badge: string }> = {
  critical: { dot: 'bg-red-400 shadow-red-400/50', bg: 'bg-red-400/5 border-red-400/20', text: 'text-red-400', badge: 'bg-red-400/15 text-red-400 border-red-400/30' },
  warning: { dot: 'bg-amber-400 shadow-amber-400/50', bg: 'bg-amber-400/5 border-amber-400/20', text: 'text-amber-400', badge: 'bg-amber-400/15 text-amber-400 border-amber-400/30' },
  info: { dot: 'bg-cyan-400 shadow-cyan-400/50', bg: 'bg-[#1a2235] border-[#2a3a5a]', text: 'text-cyan-400', badge: 'bg-cyan-400/15 text-cyan-400 border-cyan-400/30' },
};

export default function NotificationsPage() {
  const data = getNotifications();

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-2xl font-bold">Notifications</h1>
        <div className="flex gap-3">
          {data.critical > 0 && (
            <span className="px-3 py-1 rounded-full text-xs font-semibold border bg-red-400/15 text-red-400 border-red-400/30">
              {data.critical} Critical
            </span>
          )}
          {data.warnings > 0 && (
            <span className="px-3 py-1 rounded-full text-xs font-semibold border bg-amber-400/15 text-amber-400 border-amber-400/30">
              {data.warnings} Warnings
            </span>
          )}
          <span className="px-3 py-1 rounded-full text-xs font-semibold border bg-cyan-400/15 text-cyan-400 border-cyan-400/30">
            {data.total} Total
          </span>
        </div>
      </div>

      {data.total === 0 ? (
        <div className="text-gray-400 text-center py-16">No notifications. All systems running smoothly.</div>
      ) : (
        <div className="space-y-3">
          {data.notifications.map(n => {
            const s = severityStyles[n.severity] || severityStyles.info;
            const ts = n.timestamp ? (typeof n.timestamp === 'string' ? n.timestamp.slice(0, 16).replace('T', ' ') : '') : '';
            return (
              <div key={n.id} className={`border rounded-xl p-4 ${s.bg} transition-colors hover:border-cyan-400/30`}>
                <div className="flex items-start gap-3">
                  <span className={`w-2.5 h-2.5 rounded-full mt-1.5 flex-shrink-0 shadow-sm ${s.dot}`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3 mb-1">
                      <span className={`text-xs font-semibold uppercase tracking-wider ${s.text}`}>{n.type.replace(/_/g, ' ')}</span>
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${s.badge}`}>{n.severity.toUpperCase()}</span>
                      <span className="text-xs text-gray-500 ml-auto flex-shrink-0">{ts}</span>
                    </div>
                    <p className="text-sm text-gray-300 leading-relaxed">{n.message}</p>
                    <div className="mt-1 text-xs text-gray-500">Source: {n.source}</div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
