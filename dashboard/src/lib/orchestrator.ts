/**
 * Orchestrator Data Layer — Reads real YAML files from ~/.claude/orchestrator/
 * Falls back to demo data when running on Vercel (no filesystem access).
 * This is the single source of truth for all dashboard data.
 */

import fs from 'fs';
import path from 'path';
import yaml from 'js-yaml';
import os from 'os';
import * as demo from './demo-data';

const HOME = os.homedir();
const ORCH = path.join(HOME, '.claude', 'orchestrator');
const SKILLS = path.join(HOME, '.claude', 'skills');

// Detect if running on Vercel (no local YAML files available)
const IS_CLOUD = process.env.VERCEL === '1' || !fs.existsSync(ORCH);

function loadYaml(filePath: string): any {
  try {
    const content = fs.readFileSync(filePath, 'utf8');
    return yaml.load(content) || {};
  } catch {
    return {};
  }
}

function globYamls(dir: string): any[] {
  try {
    if (!fs.existsSync(dir)) return [];
    return fs.readdirSync(dir)
      .filter(f => f.endsWith('.yaml') || f.endsWith('.yml'))
      .map(f => {
        const data = loadYaml(path.join(dir, f));
        return data && typeof data === 'object' ? data : null;
      })
      .filter(Boolean);
  } catch {
    return [];
  }
}

// === TASKS ===
export function getTasks() {
  if (IS_CLOUD) return demo.demoTasks;
  const active = globYamls(path.join(ORCH, 'tasks', 'active'));
  const done = globYamls(path.join(ORCH, 'tasks', 'done'));
  return {
    active,
    done,
    total: active.length + done.length,
    byStatus: {
      backlog: active.filter(t => t.status === 'backlog').length,
      todo: active.filter(t => t.status === 'todo').length,
      in_progress: active.filter(t => t.status === 'in_progress').length,
      in_review: active.filter(t => t.status === 'in_review').length,
      done: active.filter(t => t.status === 'done').length + done.length,
      blocked: active.filter(t => t.status === 'blocked').length,
    }
  };
}

// === BUDGET ===
export function getBudget(month?: string) {
  if (IS_CLOUD) return demo.demoBudget;
  const m = month || new Date().toISOString().slice(0, 7);
  const data = loadYaml(path.join(ORCH, 'budgets', `${m}.yaml`));
  return {
    month: m,
    total_tokens_used: data.total_tokens_used || 0,
    limit: data.limit || 50000000,
    percentage: data.percentage || 0,
    by_project: data.by_project || {},
    by_skill: data.by_skill || {},
    by_model: data.by_model || { opus: 0, sonnet: 0, haiku: 0 },
    alert_80_sent: data.alert_80_sent || false,
    alert_95_sent: data.alert_95_sent || false,
  };
}

// === QUALITY ===
export function getQuality() {
  if (IS_CLOUD) return demo.demoQuality;
  const data = loadYaml(path.join(ORCH, 'quality', 'skill-metrics.yaml'));
  const skills = data.skills || {};
  const playbooks = data.domain_playbooks || {};

  const scored = Object.entries(skills)
    .filter(([_, v]: [string, any]) => v && typeof v === 'object' && v.avg_quality_score)
    .map(([name, v]: [string, any]) => ({
      name,
      score: v.avg_quality_score || 0,
      executions: v.total_executions || 0,
      revision_rate: v.revision_rate || 0,
      tier: v.tier || 'unscored',
      best_score: v.best_score || 0,
      worst_score: v.worst_score || 0,
    }))
    .sort((a, b) => b.score - a.score);

  return {
    global_avg: data.global_avg_quality || 0,
    total_scored: data.total_tasks_scored || 0,
    skills: scored,
    playbooks: Object.keys(playbooks),
    tier_a: scored.filter(s => s.score >= 85).length,
    tier_b: scored.filter(s => s.score >= 70 && s.score < 85).length,
    unscored: scored.filter(s => s.score === 0).length,
  };
}

// === SKILLS ===
export function getSkills() {
  if (IS_CLOUD) return demo.demoSkills;
  const groups: Record<string, { name: string; lines: number; description: string }[]> = {
    dario: [], diva: [], lucas: [], seo: [], a360: [], other: []
  };

  if (!fs.existsSync(SKILLS)) return { groups, total: 0 };

  for (const dir of fs.readdirSync(SKILLS)) {
    const skillMd = path.join(SKILLS, dir, 'SKILL.md');
    if (!fs.existsSync(skillMd)) continue;

    const content = fs.readFileSync(skillMd, 'utf8');
    const lines = content.split('\n').length;

    let description = '';
    const descMatch = content.match(/description:\s*["']?(.+?)["']?\s*\n/);
    if (descMatch) description = descMatch[1].slice(0, 80);

    const entry = { name: dir, lines, description };

    if (dir.startsWith('dario')) groups.dario.push(entry);
    else if (dir.startsWith('diva')) groups.diva.push(entry);
    else if (dir.startsWith('lucas')) groups.lucas.push(entry);
    else if (dir.startsWith('seo')) groups.seo.push(entry);
    else if (dir.includes('a360')) groups.a360.push(entry);
    else groups.other.push(entry);
  }

  const total = Object.values(groups).reduce((sum, g) => sum + g.length, 0);
  return { groups, total };
}

// === HEALTH ===
export function getHealth() {
  if (IS_CLOUD) return demo.demoHealth;
  const checks: { name: string; status: 'up' | 'down' | 'warning'; detail: string }[] = [];

  // Company.yaml
  const companyPath = path.join(ORCH, 'company.yaml');
  if (fs.existsSync(companyPath) && fs.statSync(companyPath).size > 0) {
    const comp = loadYaml(companyPath);
    const agents = Object.keys(comp.agents || {}).length;
    const workers = Object.keys(comp.workers || {}).length;
    checks.push({ name: 'Company Config', status: 'up', detail: `${agents} agents, ${workers} workers` });
  } else {
    checks.push({ name: 'Company Config', status: 'down', detail: 'company.yaml missing' });
  }

  // Budget
  const budget = getBudget();
  checks.push({
    name: 'Budget Tracker',
    status: budget.percentage > 95 ? 'down' : budget.percentage > 80 ? 'warning' : 'up',
    detail: `${budget.percentage}% used`
  });

  // Tasks
  const tasks = getTasks();
  checks.push({ name: 'Taskboard', status: 'up', detail: `${tasks.active.length} active, ${tasks.done.length} done` });

  // Quality
  const quality = getQuality();
  checks.push({ name: 'Quality Scorer', status: 'up', detail: `avg ${quality.global_avg}/100, ${quality.skills.length} scored` });

  // Skills
  const skills = getSkills();
  checks.push({ name: 'Skills', status: 'up', detail: `${skills.total} installed` });

  // Audit
  const auditDir = path.join(ORCH, 'audit');
  if (fs.existsSync(auditDir)) {
    const files = fs.readdirSync(auditDir).filter(f => f.endsWith('.yaml'));
    checks.push({ name: 'Audit Trail', status: 'up', detail: `${files.length} days logged` });
  } else {
    checks.push({ name: 'Audit Trail', status: 'warning', detail: 'No audit directory' });
  }

  const overall = checks.every(c => c.status === 'up') ? 'healthy' :
                  checks.some(c => c.status === 'down') ? 'unhealthy' : 'degraded';

  return { checks, overall };
}

// === CONFIG ===
export function getConfig() {
  if (IS_CLOUD) return demo.demoConfig;
  const data = loadYaml(path.join(ORCH, 'company.yaml'));
  const company = data.company || {};
  const policies = data.execution_policies || {};
  const pulse = loadYaml(path.join(ORCH, 'last_pulse.yaml'));

  return {
    company: {
      name: company.name || 'Not configured',
      owner: company.owner || '',
      budget_limit: company.budget?.monthly_limit_tokens || 50000000,
      alert_threshold: company.budget?.alert_threshold || 0.8,
      auto_pause: company.budget?.auto_pause_threshold || 0.95,
    },
    policies,
    pulse: {
      time: pulse.pulse_time || null,
      tasks: pulse.tasks || {},
      budget: pulse.budget || {},
    }
  };
}

// === AGENTS ===
export function getAgents() {
  if (IS_CLOUD) return demo.demoAgents;
  const data = loadYaml(path.join(ORCH, 'company.yaml'));
  const agents: any[] = [];
  const workers: any[] = [];

  // Parse agents section
  for (const [key, val] of Object.entries(data.agents || {})) {
    if (!val || typeof val !== 'object') continue;
    const a = val as any;
    agents.push({
      id: a.id || key,
      name: a.name || key,
      title: a.title || '',
      type: a.type || 'agent',
      reports_to: a.reports_to || null,
      capabilities: a.capabilities || [],
      adapter: a.adapter || null,
      heartbeat: a.heartbeat || null,
    });
  }

  // Parse workers section
  for (const [key, val] of Object.entries(data.workers || {})) {
    if (!val || typeof val !== 'object') continue;
    const w = val as any;
    workers.push({
      id: key,
      skill: w.skill || key,
      type: w.type || 'worker',
      reports_to: w.reports_to || null,
      capabilities: w.capabilities || [],
    });
  }

  // Build hierarchy: group workers by their director
  const hierarchy: Record<string, any[]> = {};
  for (const w of workers) {
    const dir = w.reports_to || 'unassigned';
    if (!hierarchy[dir]) hierarchy[dir] = [];
    hierarchy[dir].push(w);
  }

  return {
    agents,
    workers,
    hierarchy,
    total_agents: agents.length,
    total_workers: workers.length,
    total: agents.length + workers.length,
  };
}

// === NOTIFICATIONS (from audit logs + budget + tasks) ===
export function getNotifications(): { notifications: any[]; total: number; critical: number; warnings: number; info: number } {
  if (IS_CLOUD) return demo.demoNotifications;
  const notifications: { id: string; type: string; severity: 'info' | 'warning' | 'critical'; message: string; timestamp: string; source: string }[] = [];
  let nextId = 1;

  // Budget alerts
  const budget = getBudget();
  if (budget.percentage >= 95) {
    notifications.push({ id: `n${nextId++}`, type: 'budget_critical', severity: 'critical', message: `Budget at ${budget.percentage}% — all execution stopped`, timestamp: new Date().toISOString(), source: 'budget' });
  } else if (budget.percentage >= 80) {
    notifications.push({ id: `n${nextId++}`, type: 'budget_warning', severity: 'warning', message: `Budget at ${budget.percentage}% — limiting to 1 parallel worker`, timestamp: new Date().toISOString(), source: 'budget' });
  }

  // SLA warnings from active tasks
  const tasks = getTasks();
  for (const t of tasks.active) {
    if (t.status === 'blocked') {
      notifications.push({ id: `n${nextId++}`, type: 'task_blocked', severity: 'warning', message: `Task ${t.id || 'unknown'} blocked: ${t.blocked_reason || 'no reason'}`, timestamp: t.updated || t.created || '', source: 'taskboard' });
    }
    if (t.status === 'in_progress' && t.sla_deadline) {
      const deadline = new Date(t.sla_deadline).getTime();
      const now = Date.now();
      if (now > deadline) {
        notifications.push({ id: `n${nextId++}`, type: 'sla_breach', severity: 'critical', message: `SLA breach: ${t.id} past deadline ${t.sla_deadline}`, timestamp: t.sla_deadline, source: 'taskboard' });
      } else if (deadline - now < 3600000) {
        notifications.push({ id: `n${nextId++}`, type: 'sla_warning', severity: 'warning', message: `SLA warning: ${t.id} deadline in <1h`, timestamp: t.sla_deadline, source: 'taskboard' });
      }
    }
  }

  // Recent audit events (last 2 days, only warnings/criticals)
  const logs = getLogs(2);
  for (const day of logs) {
    if (!Array.isArray(day.entries)) continue;
    for (const e of day.entries) {
      const action = e.action || '';
      let severity: 'info' | 'warning' | 'critical' = 'info';
      if (action.includes('escalat') || action.includes('breach') || action.includes('critical') || action.includes('dead_letter')) severity = 'critical';
      else if (action.includes('warning') || action.includes('revision') || action.includes('blocked') || action.includes('stale')) severity = 'warning';
      notifications.push({
        id: `n${nextId++}`,
        type: action,
        severity,
        message: typeof e.details === 'string' ? e.details : JSON.stringify(e.details || ''),
        timestamp: e.timestamp || '',
        source: e.actor || 'system',
      });
    }
  }

  // Sort by severity (critical first), then by timestamp
  const severityOrder = { critical: 0, warning: 1, info: 2 };
  notifications.sort((a, b) => severityOrder[a.severity] - severityOrder[b.severity] || b.timestamp.localeCompare(a.timestamp));

  return {
    notifications,
    total: notifications.length,
    critical: notifications.filter(n => n.severity === 'critical').length,
    warnings: notifications.filter(n => n.severity === 'warning').length,
    info: notifications.filter(n => n.severity === 'info').length,
  };
}

// === PROJECTS (derived from budget + tasks) ===
export function getProjects() {
  if (IS_CLOUD) return demo.demoProjects;
  const budget = getBudget();
  const tasks = getTasks();
  const allTasks = [...tasks.active, ...tasks.done];

  // Collect unique projects from tasks and budget
  const projectMap: Record<string, { name: string; tasks_total: number; tasks_done: number; tasks_active: number; tokens_used: number; statuses: Record<string, number> }> = {};

  for (const t of allTasks) {
    const proj = t.project || 'unassigned';
    if (!projectMap[proj]) projectMap[proj] = { name: proj, tasks_total: 0, tasks_done: 0, tasks_active: 0, tokens_used: 0, statuses: {} };
    projectMap[proj].tasks_total++;
    if (t.status === 'done') projectMap[proj].tasks_done++;
    else projectMap[proj].tasks_active++;
    const s = t.status || 'unknown';
    projectMap[proj].statuses[s] = (projectMap[proj].statuses[s] || 0) + 1;
  }

  // Merge budget data
  for (const [proj, tokens] of Object.entries(budget.by_project || {})) {
    if (!projectMap[proj]) projectMap[proj] = { name: proj, tasks_total: 0, tasks_done: 0, tasks_active: 0, tokens_used: 0, statuses: {} };
    projectMap[proj].tokens_used = typeof tokens === 'number' ? tokens : 0;
  }

  const projects = Object.values(projectMap).sort((a, b) => b.tasks_active - a.tasks_active || b.tasks_total - a.tasks_total);

  return {
    projects,
    total: projects.length,
    total_tasks: allTasks.length,
    total_tokens: budget.total_tokens_used,
  };
}

// === LOGS ===
export function getLogs(days: number = 3) {
  if (IS_CLOUD) return demo.demoLogs;
  const auditDir = path.join(ORCH, 'audit');
  if (!fs.existsSync(auditDir)) return [];

  return fs.readdirSync(auditDir)
    .filter(f => f.endsWith('.yaml'))
    .sort()
    .reverse()
    .slice(0, days)
    .map(f => ({
      date: f.replace('.yaml', ''),
      entries: loadYaml(path.join(auditDir, f))
    }))
    .filter(d => Array.isArray(d.entries));
}
