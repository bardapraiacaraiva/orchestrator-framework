/**
 * Demo Data — Static sample data used when YAML files are unavailable (Vercel deployment).
 * This allows the SaaS to demonstrate functionality without local filesystem access.
 */

export const demoTasks = {
  active: [
    { id: 'DEMO-001', title: 'Audit homepage performance', project: 'acme-corp', status: 'in_progress', priority: 'high', assignee: 'worker-cwv-fix', created: '2026-04-20', sla_deadline: '2026-04-22T18:00:00' },
    { id: 'DEMO-002', title: 'Create SEO content strategy', project: 'acme-corp', status: 'todo', priority: 'medium', assignee: 'worker-seo-audit', created: '2026-04-21' },
    { id: 'DEMO-003', title: 'Design landing page wireframe', project: 'techstart', status: 'in_review', priority: 'high', assignee: 'worker-funnel', created: '2026-04-19' },
    { id: 'DEMO-004', title: 'Fix mobile responsive issues', project: 'acme-corp', status: 'backlog', priority: 'low', assignee: null, created: '2026-04-22' },
    { id: 'DEMO-005', title: 'Implement schema markup', project: 'techstart', status: 'todo', priority: 'medium', assignee: 'worker-seo-schema', created: '2026-04-22' },
  ],
  done: [
    { id: 'DEMO-D01', title: 'Initial site audit', project: 'acme-corp', status: 'done', priority: 'high', quality_score: 92, created: '2026-04-15' },
    { id: 'DEMO-D02', title: 'Setup analytics tracking', project: 'techstart', status: 'done', priority: 'medium', quality_score: 88, created: '2026-04-16' },
  ],
  total: 7,
  byStatus: { backlog: 1, todo: 2, in_progress: 1, in_review: 1, done: 2, blocked: 0 },
};

export const demoBudget = {
  month: '2026-04',
  total_tokens_used: 8500000,
  limit: 50000000,
  percentage: 17,
  by_project: { 'acme-corp': 5200000, 'techstart': 2800000, 'internal': 500000 },
  by_skill: { 'seo-audit': 3100000, 'cwv-fix': 2400000, 'funnel': 1800000, 'content': 1200000 },
  by_model: { opus: 5100000, sonnet: 2900000, haiku: 500000 },
  alert_80_sent: false,
  alert_95_sent: false,
};

export const demoQuality = {
  global_avg: 86.4,
  total_scored: 12,
  skills: [
    { name: 'seo-audit', score: 94, executions: 5, revision_rate: 0.05, tier: 'A', best_score: 97, worst_score: 88 },
    { name: 'cwv-fix', score: 91, executions: 4, revision_rate: 0.08, tier: 'A', best_score: 95, worst_score: 85 },
    { name: 'funnel', score: 87, executions: 3, revision_rate: 0.12, tier: 'A', best_score: 92, worst_score: 80 },
    { name: 'content', score: 82, executions: 4, revision_rate: 0.15, tier: 'B', best_score: 90, worst_score: 72 },
    { name: 'brand', score: 78, executions: 2, revision_rate: 0.2, tier: 'B', best_score: 85, worst_score: 70 },
  ],
  playbooks: ['agency', 'saas', 'ecommerce'],
  tier_a: 3,
  tier_b: 2,
  unscored: 0,
};

export const demoAgents = {
  agents: [
    { id: 'dario-ceo', name: 'D.A.R.I.O.', title: 'Chief Executive Officer', type: 'orchestrator', reports_to: null, capabilities: ['strategic_planning', 'task_decomposition', 'budget_allocation', 'quality_assurance'], adapter: 'dario-v2-digital-ceo', heartbeat: { interval_minutes: 30, enable_assignment_wakeup: true } },
    { id: 'diva-vp', name: 'D.I.V.A.', title: 'VP Architecture & Design', type: 'orchestrator', reports_to: 'dario-ceo', capabilities: ['architecture_design', 'interior_design', 'construction_management'], adapter: 'diva-v1-design-architect', heartbeat: { interval_minutes: 60, enable_assignment_wakeup: true } },
    { id: 'lucas-vp', name: 'L.U.C.A.S.', title: 'VP Operations & Intelligence', type: 'orchestrator', reports_to: 'dario-ceo', capabilities: ['operations_management', 'quality_control', 'analytics'], adapter: null, heartbeat: { interval_minutes: 30, enable_assignment_wakeup: true } },
    { id: 'dir-marketing', name: 'Director Marketing', title: 'Director of Marketing & Growth', type: 'agent', reports_to: 'dario-ceo', capabilities: ['marketing_strategy', 'campaign_management'], adapter: null, heartbeat: null },
    { id: 'dir-technical', name: 'Director Technical', title: 'Director of Technical', type: 'agent', reports_to: 'dario-ceo', capabilities: ['web_development', 'performance'], adapter: null, heartbeat: null },
    { id: 'dir-seo', name: 'Director SEO', title: 'Director of SEO', type: 'agent', reports_to: 'dario-ceo', capabilities: ['seo_strategy', 'content_optimization'], adapter: null, heartbeat: null },
  ],
  workers: [
    { id: 'worker-brand', skill: 'dario-brand', type: 'worker', reports_to: 'dir-marketing', capabilities: ['brand_positioning', 'messaging'] },
    { id: 'worker-funnel', skill: 'dario-funnel', type: 'worker', reports_to: 'dir-marketing', capabilities: ['funnel_design', 'lead_magnet'] },
    { id: 'worker-cwv-fix', skill: 'dario-cwv-fix', type: 'worker', reports_to: 'dir-technical', capabilities: ['core_web_vitals', 'performance'] },
    { id: 'worker-seo-audit', skill: 'seo-audit', type: 'worker', reports_to: 'dir-seo', capabilities: ['technical_seo', 'site_audit'] },
    { id: 'worker-seo-schema', skill: 'seo-schema', type: 'worker', reports_to: 'dir-seo', capabilities: ['schema_markup', 'structured_data'] },
  ],
  hierarchy: {},
  total_agents: 6,
  total_workers: 5,
  total: 11,
};

export const demoHealth = {
  checks: [
    { name: 'Company Config', status: 'up' as const, detail: '6 agents, 5 workers' },
    { name: 'Budget Tracker', status: 'up' as const, detail: '17% used' },
    { name: 'Taskboard', status: 'up' as const, detail: '5 active, 2 done' },
    { name: 'Quality Scorer', status: 'up' as const, detail: 'avg 86.4/100, 5 scored' },
    { name: 'Skills', status: 'up' as const, detail: '15 installed' },
    { name: 'Audit Trail', status: 'up' as const, detail: '3 days logged' },
  ],
  overall: 'healthy' as const,
};

export const demoSkills = {
  groups: {
    dario: [
      { name: 'dario-brand', lines: 220, description: 'Brand positioning and archetype mapping' },
      { name: 'dario-funnel', lines: 180, description: 'Sales funnel design and optimization' },
      { name: 'dario-offer', lines: 195, description: 'Irresistible offer creation framework' },
    ],
    diva: [
      { name: 'diva-briefing', lines: 150, description: 'Architecture project briefing' },
      { name: 'diva-budget', lines: 130, description: 'Construction budget estimation' },
    ],
    lucas: [
      { name: 'lucas-heartbeat', lines: 680, description: 'System pulse and health monitoring' },
      { name: 'lucas-autopilot', lines: 780, description: 'Autonomous task execution engine' },
    ],
    seo: [
      { name: 'seo-audit', lines: 340, description: 'Comprehensive SEO site audit' },
      { name: 'seo-schema', lines: 200, description: 'Schema markup generation' },
      { name: 'seo-technical', lines: 280, description: 'Technical SEO analysis' },
    ],
    a360: [
      { name: 'a360-nicho-explorer', lines: 250, description: 'Niche market research and validation' },
      { name: 'a360-offer-builder', lines: 230, description: 'Business offer construction' },
    ],
    other: [],
  },
  total: 12,
};

export const demoConfig = {
  company: {
    name: 'Demo Agency',
    owner: 'demo',
    budget_limit: 50000000,
    alert_threshold: 0.8,
    auto_pause: 0.95,
  },
  policies: {
    default: { sla_hours: 4, review_required: false, approval_required: false, revision_max_loops: 3 },
    critical: { sla_hours: 2, review_required: true, approval_required: true, revision_max_loops: 5 },
  },
  pulse: { time: '2026-04-27T14:30:00', tasks: { scanned: 7, dispatched: 2 }, budget: { percentage: 17 } },
};

export const demoLogs = [
  {
    date: '2026-04-27',
    entries: [
      { timestamp: '2026-04-27T14:30:00', actor: 'lucas', action: 'pulse_executed', details: 'Pulse scan: 7 tasks, 2 dispatched' },
      { timestamp: '2026-04-27T13:15:00', actor: 'dario', action: 'task_completed', details: 'DEMO-D01: Initial site audit — score 92/100' },
      { timestamp: '2026-04-27T10:00:00', actor: 'system', action: 'budget_update', details: 'Monthly tokens: 8.5M / 50M (17%)' },
    ],
  },
];

export const demoNotifications = {
  notifications: [
    { id: 'n1', type: 'pulse_executed', severity: 'info' as const, message: 'Pulse scan: 7 tasks, 2 dispatched', timestamp: '2026-04-27T14:30:00', source: 'lucas' },
    { id: 'n2', type: 'task_completed', severity: 'info' as const, message: 'DEMO-D01 completed with score 92/100', timestamp: '2026-04-27T13:15:00', source: 'dario' },
  ],
  total: 2,
  critical: 0,
  warnings: 0,
  info: 2,
};

export const demoProjects = {
  projects: [
    { name: 'acme-corp', tasks_total: 4, tasks_done: 1, tasks_active: 3, tokens_used: 5200000, statuses: { in_progress: 1, todo: 1, backlog: 1, done: 1 } },
    { name: 'techstart', tasks_total: 3, tasks_done: 1, tasks_active: 2, tokens_used: 2800000, statuses: { in_review: 1, todo: 1, done: 1 } },
  ],
  total: 2,
  total_tasks: 7,
  total_tokens: 8500000,
};
