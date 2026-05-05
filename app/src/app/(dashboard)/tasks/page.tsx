import { getTasks } from '@/lib/orchestrator';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

const COLUMNS = [
  { key: 'backlog', label: 'Backlog' },
  { key: 'todo', label: 'Todo' },
  { key: 'in_progress', label: 'In Progress' },
  { key: 'in_review', label: 'In Review' },
  { key: 'done', label: 'Done' },
] as const;

const priorityColors: Record<string, string> = {
  critical: 'bg-red-500/20 text-red-400',
  high: 'bg-amber-500/20 text-amber-400',
  medium: 'bg-blue-500/20 text-blue-400',
  low: 'bg-gray-500/20 text-gray-400',
};

export default function TasksPage() {
  const { active, done, byStatus } = getTasks();

  // Group tasks by status
  const grouped: Record<string, any[]> = {
    backlog: active.filter((t: any) => t.status === 'backlog'),
    todo: active.filter((t: any) => t.status === 'todo'),
    in_progress: active.filter((t: any) => t.status === 'in_progress'),
    in_review: active.filter((t: any) => t.status === 'in_review'),
    done: [
      ...active.filter((t: any) => t.status === 'done'),
      ...done,
    ],
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Tasks</h1>

      <div className="grid grid-cols-5 gap-4">
        {COLUMNS.map(({ key, label }) => {
          const items = grouped[key] || [];
          return (
            <div key={key} className="flex flex-col gap-3">
              {/* Column header */}
              <div className="flex items-center justify-between rounded-lg bg-[#111827] px-3 py-2">
                <span className="text-sm font-medium text-gray-300">{label}</span>
                <span className="rounded-full bg-[#00e5ff]/15 px-2 py-0.5 text-xs font-medium text-[#00e5ff]">
                  {items.length}
                </span>
              </div>

              {/* Task cards */}
              <div className="flex flex-col gap-2">
                {items.map((task: any, i: number) => (
                  <Card
                    key={task.id || i}
                    className="border-0 bg-[#111827]"
                    size="sm"
                  >
                    <CardContent className="space-y-2">
                      <p className="text-xs text-gray-500">{task.id || `#${i + 1}`}</p>
                      <p className="truncate text-sm font-medium text-white">
                        {task.title || task.description?.slice(0, 50) || 'Untitled'}
                      </p>
                      <div className="flex items-center justify-between">
                        <Badge
                          className={`${priorityColors[task.priority] || priorityColors.low} border-0 text-[10px]`}
                        >
                          {task.priority || 'low'}
                        </Badge>
                        <span className="text-[10px] text-gray-500">
                          {task.assignee || 'unassigned'}
                        </span>
                      </div>
                    </CardContent>
                  </Card>
                ))}
                {items.length === 0 && (
                  <p className="py-4 text-center text-xs text-gray-600">
                    No tasks
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
