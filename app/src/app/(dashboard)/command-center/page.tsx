import { getTasks, getBudget, getQuality, getHealth, getAgents, getNotifications } from '@/lib/orchestrator';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import Link from 'next/link';
import {
  CheckSquare,
  Wallet,
  Star,
  Activity,
  Users,
  Bell,
} from 'lucide-react';

export default function CommandCenterPage() {
  const tasks = getTasks();
  const budget = getBudget();
  const quality = getQuality();
  const health = getHealth();
  const agents = getAgents();
  const notifs = getNotifications();

  const metrics = [
    {
      label: 'Total Tasks',
      value: tasks.total,
      sub: `${tasks.active.length} active`,
      icon: CheckSquare,
      color: 'text-[#00e5ff]',
    },
    {
      label: 'Budget',
      value: `${budget.percentage}%`,
      sub: `of ${(budget.limit / 1_000_000).toFixed(0)}M tokens`,
      icon: Wallet,
      color: budget.percentage > 80 ? 'text-amber-400' : 'text-emerald-400',
    },
    {
      label: 'Avg Quality',
      value: quality.global_avg,
      sub: `${quality.total_scored} scored`,
      icon: Star,
      color: 'text-yellow-400',
    },
    {
      label: 'System Health',
      value: health.overall === 'healthy' ? 'OK' : health.overall.toUpperCase(),
      sub: `${health.checks.filter(c => c.status === 'up').length}/${health.checks.length} checks`,
      icon: Activity,
      color: health.overall === 'healthy' ? 'text-emerald-400' : 'text-amber-400',
    },
    {
      label: 'Agents',
      value: agents.total,
      sub: `${agents.total_agents} agents, ${agents.total_workers} workers`,
      icon: Users,
      color: 'text-purple-400',
    },
    {
      label: 'Alerts',
      value: notifs.critical + notifs.warnings,
      sub: `${notifs.critical} critical, ${notifs.warnings} warnings`,
      icon: Bell,
      color: notifs.critical > 0 ? 'text-red-400' : notifs.warnings > 0 ? 'text-amber-400' : 'text-emerald-400',
    },
  ];

  // Recent tasks — last 6 from active
  const recentTasks = tasks.active.slice(-6).reverse();

  // Budget by project — top 5
  const projectEntries = Object.entries(budget.by_project as Record<string, number>)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 5);
  const maxProjectTokens = projectEntries.length > 0 ? projectEntries[0][1] : 1;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Command Center</h1>

      {/* Metric cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {metrics.map((m) => (
          <Card key={m.label} className="border-0 bg-[#111827]">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-gray-400">
                {m.label}
              </CardTitle>
              <m.icon className={`h-4 w-4 ${m.color}`} />
            </CardHeader>
            <CardContent>
              <div className={`text-2xl font-bold ${m.color}`}>{m.value}</div>
              <p className="mt-1 text-xs text-gray-500">{m.sub}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Two-column grid */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Recent tasks */}
        <Card className="border-0 bg-[#111827]">
          <CardHeader>
            <CardTitle className="text-white">Recent Tasks</CardTitle>
          </CardHeader>
          <CardContent>
            {recentTasks.length === 0 ? (
              <p className="text-sm text-gray-500">No active tasks</p>
            ) : (
              <div className="space-y-3">
                {recentTasks.map((task: any, i: number) => (
                  <div
                    key={task.id || i}
                    className="flex items-center justify-between rounded-lg bg-[#0a0e1a] px-3 py-2"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-white">
                        {task.title || task.id || `Task ${i + 1}`}
                      </p>
                      <p className="text-xs text-gray-500">
                        {task.assignee || 'unassigned'} &middot; {task.status || 'unknown'}
                      </p>
                    </div>
                    <PriorityBadge priority={task.priority} />
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Budget breakdown */}
        <Card className="border-0 bg-[#111827]">
          <CardHeader>
            <CardTitle className="text-white">Budget by Project</CardTitle>
          </CardHeader>
          <CardContent>
            {projectEntries.length === 0 ? (
              <p className="text-sm text-gray-500">No project data</p>
            ) : (
              <div className="space-y-3">
                {projectEntries.map(([name, tokens]) => (
                  <div key={name}>
                    <div className="mb-1 flex items-center justify-between">
                      <span className="text-sm text-gray-300">{name}</span>
                      <span className="text-xs text-gray-500">
                        {((tokens as number) / 1_000_000).toFixed(1)}M
                      </span>
                    </div>
                    <div className="h-2 rounded-full bg-[#0a0e1a]">
                      <div
                        className="h-2 rounded-full bg-[#00e5ff]"
                        style={{
                          width: `${((tokens as number) / maxProjectTokens) * 100}%`,
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Quick Actions */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {[
          { label: 'Tasks', href: '/tasks', color: 'hover:border-cyan-400/40 hover:bg-cyan-400/5' },
          { label: 'Budget', href: '/budget', color: 'hover:border-emerald-400/40 hover:bg-emerald-400/5' },
          { label: 'Agents', href: '/agents', color: 'hover:border-purple-400/40 hover:bg-purple-400/5' },
          { label: 'Quality', href: '/quality', color: 'hover:border-yellow-400/40 hover:bg-yellow-400/5' },
          { label: 'Projects', href: '/projects', color: 'hover:border-blue-400/40 hover:bg-blue-400/5' },
          { label: 'Reports', href: '/reports', color: 'hover:border-amber-400/40 hover:bg-amber-400/5' },
        ].map(a => (
          <Link key={a.href} href={a.href} className={`block rounded-xl border border-[#2a3a5a] bg-[#111827] px-4 py-3 text-center text-sm font-medium text-gray-300 transition-colors ${a.color}`}>
            {a.label}
          </Link>
        ))}
      </div>
    </div>
  );
}

function PriorityBadge({ priority }: { priority?: string }) {
  const map: Record<string, string> = {
    critical: 'bg-red-500/20 text-red-400',
    high: 'bg-amber-500/20 text-amber-400',
    medium: 'bg-blue-500/20 text-blue-400',
    low: 'bg-gray-500/20 text-gray-400',
  };
  const cls = map[priority || ''] || map.low;
  return (
    <Badge className={`${cls} border-0 text-[10px]`}>
      {priority || 'low'}
    </Badge>
  );
}
