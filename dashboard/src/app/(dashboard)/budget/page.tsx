import { getBudget } from '@/lib/orchestrator';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return String(n);
}

export default function BudgetPage() {
  const budget = getBudget();
  const pct = budget.percentage;

  // Color based on percentage
  const ringColor =
    pct > 95 ? 'text-red-400' : pct > 80 ? 'text-amber-400' : 'text-[#00e5ff]';
  const barColor =
    pct > 95 ? 'bg-red-400' : pct > 80 ? 'bg-amber-400' : 'bg-[#00e5ff]';

  const byProject = Object.entries(budget.by_project as Record<string, number>).sort(
    ([, a], [, b]) => b - a
  );
  const bySkill = Object.entries(budget.by_skill as Record<string, number>).sort(
    ([, a], [, b]) => b - a
  );
  const byModel = Object.entries(budget.by_model as Record<string, number>).sort(
    ([, a], [, b]) => b - a
  );

  const maxProject = byProject.length > 0 ? byProject[0][1] : 1;
  const maxSkill = bySkill.length > 0 ? bySkill[0][1] : 1;
  const maxModel = byModel.length > 0 ? byModel[0][1] : 1;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Budget</h1>

      {/* Usage circle */}
      <Card className="border-0 bg-[#111827]">
        <CardContent className="flex flex-col items-center py-8">
          <div className="relative flex h-40 w-40 items-center justify-center">
            {/* Background ring */}
            <svg className="absolute h-full w-full -rotate-90" viewBox="0 0 120 120">
              <circle
                cx="60"
                cy="60"
                r="52"
                fill="none"
                stroke="currentColor"
                strokeWidth="8"
                className="text-gray-800"
              />
              <circle
                cx="60"
                cy="60"
                r="52"
                fill="none"
                stroke="currentColor"
                strokeWidth="8"
                strokeDasharray={`${(pct / 100) * 327} 327`}
                strokeLinecap="round"
                className={ringColor}
              />
            </svg>
            <div className="text-center">
              <span className={`text-3xl font-bold ${ringColor}`}>{pct}%</span>
              <p className="text-xs text-gray-500">used</p>
            </div>
          </div>
          <p className="mt-4 text-sm text-gray-400">
            {formatTokens(budget.total_tokens_used)} / {formatTokens(budget.limit)} tokens
          </p>
          <p className="text-xs text-gray-600">{budget.month}</p>
        </CardContent>
      </Card>

      {/* Breakdown columns */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <BreakdownCard
          title="By Project"
          entries={byProject}
          max={maxProject}
          barColor={barColor}
        />
        <BreakdownCard
          title="By Skill"
          entries={bySkill}
          max={maxSkill}
          barColor="bg-purple-400"
        />
        <BreakdownCard
          title="By Model"
          entries={byModel}
          max={maxModel}
          barColor="bg-emerald-400"
        />
      </div>
    </div>
  );
}

function BreakdownCard({
  title,
  entries,
  max,
  barColor,
}: {
  title: string;
  entries: [string, number][];
  max: number;
  barColor: string;
}) {
  return (
    <Card className="border-0 bg-[#111827]">
      <CardHeader>
        <CardTitle className="text-white">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {entries.length === 0 ? (
          <p className="text-sm text-gray-500">No data</p>
        ) : (
          <div className="space-y-3">
            {entries.map(([name, tokens]) => (
              <div key={name}>
                <div className="mb-1 flex items-center justify-between">
                  <span className="text-sm text-gray-300">{name}</span>
                  <span className="text-xs text-gray-500">
                    {formatTokens(tokens)}
                  </span>
                </div>
                <div className="h-2 rounded-full bg-[#0a0e1a]">
                  <div
                    className={`h-2 rounded-full ${barColor}`}
                    style={{ width: `${(tokens / max) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
