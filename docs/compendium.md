# Orchestrator AI Framework — Compendium

The definitive guide to installing, configuring, and operating the Orchestrator AI Framework at full capacity.

---

## Chapter 1: Introduction

### What is the Orchestrator AI Framework

The Orchestrator AI Framework is a **management layer for Claude Code** that transforms ad-hoc AI usage into structured, auditable, budget-aware autonomous execution. Inspired by [Paperclip AI](https://github.com/paperclipai/paperclip), it models your organization as an org chart where AI agents fill roles — from CEO down to individual workers — each with defined capabilities, heartbeat schedules, and execution policies.

Without the framework, you invoke skills one at a time with no tracking, no quality gates, and no budget visibility. With it, complex projects are decomposed into atomic tasks, dispatched to the right worker, executed in parallel heartbeat windows, quality-scored, and logged to an append-only audit trail.

### Who is it for

- **Digital agencies** managing multiple client projects with AI
- **SaaS teams** using Claude Code for development and operations
- **Studios and freelancers** who need structured autonomous execution
- **Anyone** who wants Claude Code to operate as a coordinated team, not a single tool

### Core Concepts

| Concept | What it means |
|---|---|
| **Heartbeat** | A bounded execution window. The system wakes up, scans the taskboard, executes a wave of tasks, and goes back to sleep. No continuous loops. |
| **Atomic checkout** | One agent owns one task at a time. No duplicate work. No conflicts. If a task is `in_progress` with agent A, agent B cannot claim it. |
| **Execution policy** | Rules governing how a task is reviewed and approved. Ranges from `default` (auto-approve at score >= 75) to `financial` (requires user approval). |
| **Playbook** | A pre-built skill chain for a common project type (e.g., "WordPress audit"). Auto-detected by keyword matching when the first task in a new project arrives. |

### Architecture Overview

```
User Request
    |
    v
[Orchestrator — Control Plane]
    |
    +-- Phase 0: VALIDATE  (deps, budget, stale tasks, dirs)
    +-- Phase 1: UNDERSTAND (parse intent, gather context)
    +-- Phase 2: DECOMPOSE  (break into atomic tasks)
    +-- Phase 3: DISPATCH   (route to best worker)
    +-- Phase 4: EXECUTE    (parallel heartbeat windows, max 3)
    +-- Phase 4.5: ERROR RECOVERY (retry, backoff, dead-letter)
    +-- Phase 5: REVIEW     (quality gates per policy)
    +-- Phase 6: SYNTHESIZE (combine outputs into deliverable)
    +-- Phase 7: AUDIT      (log everything, update budget)
```

**8 core skills** ship with the framework:

| Skill | Role |
|---|---|
| `orch-orchestrator` | Control plane — decomposes, coordinates, synthesizes |
| `orch-taskboard` | Persistent YAML task lifecycle with atomic checkout |
| `orch-dispatch` | Intelligent routing with workload awareness |
| `orch-heartbeat` | Periodic task scanning + SLA enforcement |
| `orch-autopilot` | Autonomous execution loop (scan + dispatch + execute + score) |
| `orch-quality` | 5-dimension quality scoring with learning loop |
| `orch-analytics` | Cross-project patterns, playbooks, performance tracking |
| `orch-status` | System health dashboard with auto-fix |

---

## Chapter 2: Installation

### Prerequisites

- **Claude Code CLI** installed and authenticated
- **Python 3.8+** (for the budget tracker script)
- **Node.js 18+** (for the npx installer)

### One-command install

```bash
npx orchestrator-ai-framework init --company "Your Company" --preset agency --owner "Your Name"
```

### Available presets

| Preset | Best for | What it sets up |
|---|---|---|
| `agency` | Digital agencies | Multiple divisions (marketing, delivery, ops), client-facing policies |
| `saas` | SaaS product teams | Engineering, product, growth divisions |
| `studio` | Creative studios | Design, content, project management divisions |
| `freelancer` | Solo operators | Minimal structure, single-division setup |
| `custom` | Full control | Empty template, you define everything |

### Verifying installation

```bash
npx orchestrator-ai-framework validate
```

This checks: directories exist, all 8 core skills installed, `company.yaml` is valid, budget tracker present.

### File structure after install

```
~/.claude/
  +-- skills/
  |   +-- orch-orchestrator/SKILL.md
  |   +-- orch-taskboard/SKILL.md
  |   +-- orch-dispatch/SKILL.md
  |   +-- orch-heartbeat/SKILL.md
  |   +-- orch-autopilot/SKILL.md
  |   +-- orch-quality/SKILL.md
  |   +-- orch-analytics/SKILL.md
  |   +-- orch-status/SKILL.md
  +-- orchestrator/
      +-- company.yaml
      +-- budget_tracker.py
      +-- notifications.yaml
      +-- tasks/
      |   +-- active/
      |   +-- done/
      |   +-- templates/
      +-- audit/
      +-- budgets/
      +-- quality/
          +-- skill-metrics.yaml
          +-- eval-baseline.yaml
```

### Uninstalling

```bash
npx orchestrator-ai-framework uninstall
```

Removes core skills but **preserves** your orchestrator data (tasks, audit logs, budget files).

---

## Chapter 3: Configuration

### Understanding company.yaml

The file `~/.claude/orchestrator/company.yaml` is the single source of truth for your organization. It defines who does what, how tasks are reviewed, and what limits apply.

#### Company section

```yaml
company:
  name: "Your Agency Name"
  goal: "Deliver world-class results using AI-powered orchestration"
  owner: "Your Name"
  budget:
    monthly_limit_tokens: 50000000    # 50M tokens/month
    alert_threshold: 0.80             # Warn at 80%
    auto_pause_threshold: 0.95        # Hard stop at 95%
  created: "2026-04-27"
```

#### Agents section (executives, directors)

```yaml
agents:
  ceo:
    id: "ceo"
    name: "CEO"
    type: "orchestrator"
    reports_to: null
    capabilities:
      - strategic_planning
      - task_decomposition
      - budget_allocation
      - cross_division_coordination
      - quality_assurance
    heartbeat:
      enable_timer: true
      interval_minutes: 30
      enable_on_demand: true
      cooldown_minutes: 5

  dir_marketing:
    id: "dir-marketing"
    name: "Marketing Director"
    type: "manager"
    reports_to: "ceo"
    manages: ["worker-brand", "worker-copy", "worker-seo"]
    capabilities: [brand_strategy, copywriting, seo]
```

#### Workers section (skill mapping)

Each worker maps **1:1 to a skill**:

```yaml
workers:
  worker-brand:
    type: "worker"
    skill: "dario-brand"
    reports_to: "dir-marketing"
    capabilities: [brand_strategy, positioning, archetypes]

  worker-seo:
    type: "worker"
    skill: "seo-audit"
    reports_to: "dir-marketing"
    capabilities: [seo, technical_seo, content_audit]
```

#### Execution policies

```yaml
execution_policies:
  default:
    comment_required: true
    review_required: false
    approval_required: false
    revision_max_loops: 3
    sla_hours: 8
    auto_approve_threshold: 75

  critical:
    comment_required: true
    review_required: true
    approval_required: true       # User must explicitly approve
    revision_max_loops: 3
    sla_hours: 1
    auto_approve_threshold: null   # Never auto-approve

  client_facing:
    comment_required: true
    review_required: true
    approval_required: false
    revision_max_loops: 2
    sla_hours: 4
    auto_approve_threshold: 85

  financial:
    comment_required: true
    review_required: true
    approval_required: true
    revision_max_loops: 2
    sla_hours: 2
    auto_approve_threshold: null
```

#### Heartbeat defaults

```yaml
heartbeat_defaults:
  manager:
    interval_minutes: 30          # Wake every 30 min
    cooldown_minutes: 5           # Min 5 min between pulses
    coalesce_if_active: true      # Skip if pulse already running
  worker:
    interval_minutes: 0           # Workers don't self-wake
    cooldown_minutes: 2
  service:
    interval_minutes: 5
    cooldown_minutes: 1
```

### Example: complete agency setup with 3 divisions

```yaml
company:
  name: "Acme Digital"
  owner: "John"
  budget:
    monthly_limit_tokens: 50000000

agents:
  ceo:
    id: "ceo"
    type: "orchestrator"
    reports_to: null

  dir_marketing:
    id: "dir-marketing"
    type: "manager"
    reports_to: "ceo"
    manages: ["worker-brand", "worker-copy", "worker-seo"]

  dir_delivery:
    id: "dir-delivery"
    type: "manager"
    reports_to: "ceo"
    manages: ["worker-wp-audit", "worker-funnel"]

  dir_ops:
    id: "dir-ops"
    type: "manager"
    reports_to: "ceo"
    manages: ["worker-sop", "worker-finance"]

workers:
  worker-brand:
    type: "worker"
    skill: "dario-brand"
    reports_to: "dir-marketing"
    capabilities: [brand_strategy, positioning]

  worker-copy:
    type: "worker"
    skill: "dario-content"
    reports_to: "dir-marketing"
    capabilities: [copywriting, content_production]

  worker-seo:
    type: "worker"
    skill: "seo-audit"
    reports_to: "dir-marketing"
    capabilities: [seo, technical_seo]

  worker-wp-audit:
    type: "worker"
    skill: "dario-wp-audit"
    reports_to: "dir-delivery"
    capabilities: [wordpress, performance, security]

  worker-funnel:
    type: "worker"
    skill: "dario-funnel"
    reports_to: "dir-delivery"
    capabilities: [funnel, conversion, sales]

  worker-sop:
    type: "worker"
    skill: "dario-sop"
    reports_to: "dir-ops"
    capabilities: [documentation, processes]

  worker-finance:
    type: "worker"
    skill: "lucas-finance"
    reports_to: "dir-ops"
    capabilities: [invoicing, accounting, tax]
```

---

## Chapter 4: Creating Skills

### Skill file structure

Every skill lives in its own directory under `~/.claude/skills/` and consists of a single `SKILL.md` file.

```
~/.claude/skills/
  +-- my-skill/
      +-- SKILL.md
```

### SKILL.md anatomy

```markdown
---
name: my-skill
description: "What this skill does. Triggers on: 'keyword1', 'keyword2'."
license: MIT
---

# My Skill — Human-Readable Title

Brief overview of what this skill does and why.

## When to activate

- Conditions that trigger this skill
- Trigger keywords
- Invoked via `/my-skill`

## Workflow

1. Step one — what happens first
2. Step two — what happens next
3. Step three — output generation

## Output

Description of what the skill produces.

## Red Flags

- Never do X without checking Y
- Never skip Z
```

### Frontmatter requirements

| Field | Required | Description |
|---|---|---|
| `name` | Yes | Unique skill ID (kebab-case). Used in `company.yaml` worker mapping. |
| `description` | Yes | One-line description. Include trigger keywords in quotes. |
| `license` | No | License identifier (default: MIT). |

### Registering a skill as a worker

After creating the skill file, register it in `company.yaml`:

```yaml
workers:
  worker-client-report:
    type: "worker"
    skill: "client-report"           # Must match the "name" in SKILL.md frontmatter
    reports_to: "dir-delivery"
    capabilities: [reporting, client_communication, analytics]
```

The dispatch engine matches task keywords against worker `capabilities` to find the right executor.

---

## Chapter 5: Using the Orchestrator

### Starting orchestration

In Claude Code:

```
/orch-orchestrator
> "Audit and improve client X's website — cover SEO, performance, and content"
```

### Phase-by-phase breakdown

**Phase 0 — VALIDATE**
- Circular dependency detection in the task graph
- Worker availability check against `company.yaml`
- Budget pre-check: >= 95% aborts, >= 80% limits to 1 parallel worker
- File initialization: ensures `tasks/`, `audit/`, `budgets/`, `quality/` dirs exist
- Stale task recovery: tasks `in_progress` for >24h are set to `blocked`

**Phase 1 — UNDERSTAND**
Parses the user request into a **Mission Brief**: goal, scope, constraints, available agents, budget, timeline, dependencies, blockers.

**Phase 2 — DECOMPOSE**
Breaks the mission into atomic tasks. Each task maps to exactly ONE skill invocation. Tasks are saved as individual YAML files in `tasks/active/`.

**Phase 3 — DISPATCH**
Routes each task to the best executor using capability matching, workload awareness, and the escalation chain: Worker -> Director -> VP -> CEO.

**Phase 4 — EXECUTE**
Workers run in bounded heartbeat windows. Max 3 parallel workers per heartbeat. Cooldown: 2 min between heartbeats per worker.

**Phase 4.5 — ERROR RECOVERY**
- **Retry**: Max 3 attempts with exponential backoff (60s, 120s, 240s)
- **Dead-letter**: After all retries fail, task goes to `blocked` with error summary
- **Crash recovery**: Next heartbeat detects tasks `in_progress` past SLA timeout and resets to `todo`
- **Idempotency**: Skips if already `done`, already `in_progress` by another agent, or ran within 5 minutes

**Phase 5 — REVIEW**
Three layers of quality enforcement:
1. **Comment** — Worker MUST post a substantive completion comment (always enforced)
2. **Review** — Director-level agent reviews; can approve, request revision, or escalate
3. **Approval** — For `critical`/`financial` tasks, user explicitly approves

**Phase 6 — SYNTHESIZE**
Gathers all outputs, combines into a unified deliverable, cross-references findings, and generates an executive summary with next steps.

**Phase 7 — AUDIT**
Every mutation logged to `~/.claude/orchestrator/audit/YYYY-MM-DD.yaml`. Token usage aggregated in `budgets/YYYY-MM.yaml`.

### Orchestrator commands

| Command | Effect |
|---|---|
| `status` | Show current task state |
| `next` | Execute the next available task |
| `assign <task> to <worker>` | Manual assignment |
| `block <task> reason <text>` | Block a task |
| `unblock <task>` | Remove block |
| `review <task>` | Trigger review |
| `approve <task>` | Approve a reviewed task |
| `budget` | Show budget status |
| `parallel <t1> <t2> [t3]` | Execute tasks in parallel |
| `template <name> <project>` | Create tasks from template |
| `pause` / `resume` | Pause or resume orchestration |

---

## Chapter 6: Task Management

### Task schema (all fields)

```yaml
id: "PROJ-001"                        # Auto-generated: PREFIX-NNN
title: "Descriptive imperative action"
description: "What, why, and success criteria"
project: "project-slug"
status: "todo"                        # backlog | todo | in_progress | in_review | done | blocked
priority: "high"                      # critical | high | medium | low
assignee: null                        # Worker ID from company.yaml
assigned_by: null
parent: null                          # Parent task ID (for decomposition)
children: []                          # Child task IDs
depends_on: []                        # Must complete before this starts
blocks: []                            # Tasks waiting on this one
execution_policy: "default"           # default | critical | client_facing | financial
estimated_tokens: 5000
actual_tokens: null                   # Filled after execution
skill: null                           # Which skill executes this
squad: null
tags: []
created_at: "2026-04-27T10:00:00Z"
updated_at: "2026-04-27T10:00:00Z"
checked_out_at: null                  # When assignee claimed it
completed_at: null
reviewed_by: null
approved_by: null
completion_comment: null              # MANDATORY at completion
revision_count: 0
revision_max_loops: 3                 # Max revisions before forced escalation
blocked_reason: null                  # Required when status is "blocked"
watchers: []                          # Agent IDs notified on status changes
sla_deadline: null                    # Set by dispatch based on policy
notes: []                             # Append-only notes log
```

### Status flow

```
                    +------------------------------+
                    |                              |
backlog --> todo --> in_progress --> in_review --> done
                         |              |
                         |              +--> in_progress (revision)
                         |
                         +--> blocked --> in_progress (unblocked)
```

### Atomic checkout

When a task moves to `in_progress`, it is "checked out" to a specific agent. If another agent tries to claim it, the system returns a **409 conflict**. This guarantees no duplicate work.

### Dependencies and blocking

- `depends_on: ["PROJ-002", "PROJ-003"]` — this task cannot start until PROJ-002 and PROJ-003 are both `done`
- When a task completes, the system runs a **cascading unblock**: finds all dependents, checks if ALL their deps are now `done`, and auto-transitions them to `todo`

### Parent-child tasks and rollup

Parent tasks are grouping nodes — only leaf tasks execute skills. Status rolls up automatically:
- Any child `blocked` -> parent `blocked`
- All children `done` -> parent `done`
- Any child `in_progress` -> parent `in_progress`

### Revision loops

When a reviewer requests revision: `revision_count` increments and the task goes back to `in_progress`. If `revision_count >= revision_max_loops`, the task is blocked and escalated to the user. This prevents infinite revision cycles.

### Stale task detection

| Age | Action |
|---|---|
| 0-24h | Normal |
| 24-48h | Flag STALE, add warning note |
| 48-72h | Escalate to director |
| >72h | Escalate to CEO, mark `blocked` |

---

## Chapter 7: Quality Scoring

### The 5-dimension rubric

Each dimension scores 0-20, total 0-100:

| Dimension | 20 (excellent) | 10 (partial) | 0 (fail) |
|---|---|---|---|
| **Specificity** | Mentions client by name, uses their data | Somewhat specific | Could be any client |
| **Actionability** | Clear next steps, no ambiguity | Some steps clear | Vague recommendations |
| **Completeness** | All requirements met | Most met | Significant gaps |
| **Accuracy** | Verified, sourced | Mostly correct | Contains errors |
| **Tone & Format** | Client-ready, polished | Needs minor edits | Wrong tone/format |

### Score interpretation and actions

| Score | Grade | Action |
|---|---|---|
| 90-100 | Excellent | Ship. Extract to `success-patterns.yaml`. |
| 75-89 | Good | Ship. Minor revision optional. |
| 60-74 | Acceptable | Director review required. May need revision. |
| 40-59 | Poor | Revision required. Analyze root cause. |
| 0-39 | Fail | Reject. Reassign or escalate. |

### Manual override

User feedback always takes priority over automatic scoring:

```
/orch-quality score PROJ-001 85 "Good but missing competitor analysis"
```

### Skill performance tracking

Maintained in `~/.claude/orchestrator/quality/skill-metrics.yaml`:

```yaml
skills:
  dario-brand:
    total_executions: 12
    avg_quality_score: 88
    scores: [85, 90, 92, 88, ...]
    revision_rate: 8.3
    avg_tokens: 6500
    best_score: 95
    worst_score: 72
    common_weakness: "Sometimes missing competitor context"
    improvement_trend: "improving"    # improving | stable | declining
```

Skills are tiered: **Tier A** (avg >= 85, revision < 10%), **Tier B** (avg 70-84), **Tier C** (avg < 70, revision > 25% -- requires intervention).

---

## Chapter 8: Budget Tracking

### How tokens are captured

After each Agent execution, the system captures usage metadata (or estimates by output length) and adds it to the monthly budget file.

### Budget file structure

Located at `~/.claude/orchestrator/budgets/YYYY-MM.yaml`:

```yaml
month: "2026-04"
company: "Your Company"
limit: 50000000
total_tokens_used: 1250000
percentage: 2.5
by_project:
  client-x-audit: 800000
  client-y-brand: 450000
by_skill:
  seo-audit: 500000
  dario-brand: 400000
  dario-wp-audit: 350000
by_model:
  opus: 1000000
  sonnet: 200000
  haiku: 50000
alert_80_sent: false
alert_95_sent: false
last_updated: "2026-04-27T10:00:00Z"
pulse_count: 15
```

### Alert thresholds

| Threshold | Action |
|---|---|
| < 80% | Normal operation (max 3 parallel workers) |
| >= 80% | WARNING: limit to 1 parallel worker per pulse |
| >= 95% | HARD STOP: all execution paused, user must approve or increase limit |

### Using budget_tracker.py

```bash
# Full scan of tasks + update budget
python3 ~/.claude/orchestrator/budget_tracker.py

# Print formatted report
python3 ~/.claude/orchestrator/budget_tracker.py --report

# Check thresholds only (exit code 1 if critical)
python3 ~/.claude/orchestrator/budget_tracker.py --check

# Add tokens manually
python3 ~/.claude/orchestrator/budget_tracker.py --add-tokens 5000 --project client-x --skill dario-brand

# Specify model
python3 ~/.claude/orchestrator/budget_tracker.py --add-tokens 8000 --skill seo-audit --model sonnet

# Check a specific month
python3 ~/.claude/orchestrator/budget_tracker.py --report --month 2026-03
```

---

## Chapter 9: Autonomous Execution

### Heartbeat engine — /orch-heartbeat

The heartbeat is the **periodic scanner**. It wakes up, checks the board, and makes things happen.

```
/orch-heartbeat
```

One pulse cycle:
1. **SCAN** — Read all tasks in `tasks/active/`, count by status, flag stale and SLA breaches
2. **BUDGET CHECK** — Read current month budget, enforce thresholds
3. **UNBLOCK CASCADE** — Completed tasks release their dependents
4. **AUTO-DISPATCH** — Unassigned `todo` tasks get matched to workers via `company.yaml`
5. **WAVE PLANNING** — Group independent tasks into waves (max 3 per wave)
6. **EXECUTE WAVE** — Launch agents in parallel with task context
7. **STALE DETECTION** — Flag and escalate aging tasks
8. **REPORT** — Generate pulse summary with metrics

### Autopilot — /orch-autopilot

The autopilot does everything the heartbeat does **plus** quality scoring and self-pacing:

```
/orch-autopilot
```

Single pulse: SCAN -> BUDGET -> UNBLOCK -> DISPATCH -> EXECUTE -> SCORE -> LOG -> PACE.

Quality scoring is **delegated** to `orch-quality` (separation of concerns). Autopilot receives back a score, dimensions, action, and feedback for each completed task.

### Self-pacing

```
Tasks pending    -> next pulse in 60-90 seconds
Idle (no tasks)  -> next pulse in 30 minutes (1800s)
Budget critical  -> STOP (no more pulses)
```

### Running with /loop for continuous operation

```
/loop /orch-autopilot
```

This creates an autonomous loop. The autopilot self-paces: fast when there is work, slow when idle, full stop when budget is critical.

### Safety rails

1. **Budget hard stop** at 95% — no override without user action
2. **Max 3 parallel tasks** per pulse
3. **Max 3 revision loops** per task before forced escalation
4. **Critical/financial tasks** always need explicit user approval
5. **Stale detection** at 24h (flag), 48h (escalate), 72h (block)
6. **Coalescing** — if a heartbeat is already running, skip the new trigger
7. **Audit everything** — every action logged

---

## Chapter 10: Domain Playbooks

### What is a playbook

A playbook is a pre-built sequence of skills optimized for a specific project type. Instead of manually decomposing every WordPress audit, the system recognizes the domain and auto-creates the right tasks.

### How auto-detection works

When dispatch receives the first task in a new project:
1. Scan task + project keywords against known patterns in `company.yaml`
2. Load matching playbook from `quality/skill-metrics.yaml` (under `domain_playbooks`)
3. Auto-decompose: create tasks on the taskboard from the playbook skill chain
4. User can override or request custom decomposition

### Playbook structure

```yaml
domain: "wordpress-audit"
projects_analyzed: 5
avg_quality: 87.5
optimal_skill_chain:
  - dario-wp-audit (always first, avg 92)
  - seo-audit (parallel with dario-cwv-fix)
  - dario-cwv-fix (critical for domain, avg 91)
avoid:
  - "content audit before technical audit — produces generic output"
estimated_tokens: 35000
estimated_time: "15-20 minutes"
```

### Learning loop

After project completion, the system compares actual execution vs playbook prediction. Feedback is recorded in `quality/playbook-feedback.yaml` for the analytics engine to propose updates to the playbook.

---

## Chapter 11: Notifications & Monitoring

### Event types and severity levels

Defined in `~/.claude/orchestrator/notifications.yaml`:

| Event | Severity | Template |
|---|---|---|
| `task_completed` | info | `[DONE] {task.id}: {task.title} -- score {quality_score}/100` |
| `task_revision` | warning | `[REVISION] {task.id}: score {score}/100 -- {feedback}` |
| `task_escalated` | critical | `[ESCALATED] {task.id}: {reason}` |
| `sla_warning` | warning | `[SLA WARNING] {task.id}: {age}h in progress, SLA is {sla}h` |
| `sla_breach` | critical | `[SLA BREACH] {task.id}: {age}h -- task blocked` |
| `budget_warning` | warning | `[BUDGET WARNING] {pct}% used. Limiting to 1 parallel worker.` |
| `budget_critical` | critical | `[BUDGET CRITICAL] {pct}% used. EXECUTION STOPPED.` |
| `stale_task` | warning | `[STALE] {task.id}: in_progress for {age}h. Escalating.` |
| `dead_letter` | critical | `[DEAD LETTER] {task.id}: failed after {n} retries. Blocked.` |

### Notification channels

| Channel | Type | Description |
|---|---|---|
| `pulse_report` | inline | Shown in heartbeat/autopilot output (always on) |
| `audit_log` | file | Appended to `audit/YYYY-MM-DD.yaml` (always on) |
| `task_note` | task_yaml | Appended to `task.notes[]` array (always on) |

Severity routing: `info` = pulse only. `warning` = pulse + audit. `critical` = pulse + audit + alert.

### Health checks — /orch-status

```
/orch-status
```

Runs a full diagnostic:
1. **Knowledge Base** — HTTP health check (UP/DOWN)
2. **Agent Memory** — File existence and freshness (OK/STALE/MISSING)
3. **Orchestrator Infrastructure** — All required dirs and files
4. **Budget** — Current month percentage
5. **Skills Inventory** — Count by division
6. **External Services** — Any configured integrations

Overall verdict: **HEALTHY** / **DEGRADED** / **DOWN**.

### Auto-fix capabilities

The status skill can automatically fix these issues without user confirmation:

| Issue | Auto-fix |
|---|---|
| Missing orchestrator directories | `mkdir -p` |
| Missing budget file | Create with `percentage: 0` |
| Missing quality directory | `mkdir -p quality/` |
| Empty `company.yaml` | Create minimal template |

Issues requiring manual intervention: KB down, agent memory missing content, budget > 95%, external service unavailable.

---

## Chapter 12: White-Labeling

### How it works

The framework installs with YOUR company name. No "Orchestrator AI" branding appears in outputs. Everything — task reports, pulse summaries, health checks — uses your company identity.

```bash
npx orchestrator-ai-framework init --company "Acme Digital" --preset agency --owner "John"
```

The `{{COMPANY_NAME}}` placeholder in `company.template.yaml` is replaced at install time.

### Adding your own presets

Create a preset configuration file and pass it to the installer. Presets define which divisions, workers, and policies are created by default.

### Distributing to clients

The framework is MIT-licensed. You can install it in client environments with their company name:

```bash
npx orchestrator-ai-framework init --company "Client Corp" --preset custom
```

---

## Appendix A: Task Schema Reference

| Field | Type | Default | Description |
|---|---|---|---|
| `id` | string | auto | Format: `PREFIX-NNN` (e.g., `AUDIT-001`) |
| `title` | string | required | Imperative action (e.g., "Audit homepage performance") |
| `description` | string | required | What, why, and success criteria |
| `project` | string | required | Project slug for grouping |
| `status` | enum | `backlog` | `backlog` / `todo` / `in_progress` / `in_review` / `done` / `blocked` |
| `priority` | enum | `medium` | `critical` / `high` / `medium` / `low` |
| `assignee` | string | null | Worker ID from `company.yaml` |
| `assigned_by` | string | null | Who assigned (agent or user) |
| `parent` | string | null | Parent task ID |
| `children` | list | [] | Child task IDs |
| `depends_on` | list | [] | Task IDs that must complete first |
| `blocks` | list | [] | Task IDs waiting on this one |
| `execution_policy` | enum | `default` | `default` / `critical` / `client_facing` / `financial` |
| `estimated_tokens` | int | 5000 | Token estimate for budgeting |
| `actual_tokens` | int | null | Actual tokens used (filled post-execution) |
| `skill` | string | null | Skill name to execute |
| `squad` | string | null | Optional squad for parallel work |
| `tags` | list | [] | Freeform labels |
| `created_at` | ISO date | auto | Creation timestamp |
| `updated_at` | ISO date | auto | Last modification timestamp |
| `checked_out_at` | ISO date | null | When assignee claimed task |
| `completed_at` | ISO date | null | When task reached `done` |
| `reviewed_by` | string | null | Agent/user who reviewed |
| `approved_by` | string | null | Agent/user who approved |
| `completion_comment` | string | null | Mandatory summary at completion |
| `revision_count` | int | 0 | Number of revision cycles |
| `revision_max_loops` | int | 3 | Max revisions before forced escalation |
| `blocked_reason` | string | null | Required when status is `blocked` |
| `watchers` | list | [] | Agent IDs notified on changes |
| `sla_deadline` | ISO date | null | Set by dispatch per execution policy |
| `notes` | list | [] | Append-only notes log |

---

## Appendix B: Company.yaml Reference

| Section | Purpose |
|---|---|
| `company` | Name, owner, budget limits |
| `company.budget.monthly_limit_tokens` | Total token budget per month |
| `company.budget.alert_threshold` | Percentage that triggers warning (default: 0.80) |
| `company.budget.auto_pause_threshold` | Percentage that triggers hard stop (default: 0.95) |
| `agents` | Executive and manager layer (CEO, directors) |
| `agents.[id].type` | `orchestrator` (CEO), `manager` (director), `service` (shared) |
| `agents.[id].reports_to` | Parent in the org chart |
| `agents.[id].manages` | List of worker IDs this manager oversees |
| `agents.[id].capabilities` | Keywords for capability matching |
| `agents.[id].heartbeat` | Timer settings (interval, cooldown, coalesce) |
| `workers` | Skill-mapped executors |
| `workers.[id].skill` | SKILL.md `name` this worker runs |
| `workers.[id].reports_to` | Manager in the org chart |
| `workers.[id].capabilities` | Keywords for dispatch matching |
| `execution_policies` | Review/approval rules per policy type |
| `heartbeat_defaults` | Default timer settings by agent type |

**Workload limits:** Worker: max 1 `in_progress`. Director: max 2. VP/CEO: no limit.

**Escalation chain:** Worker -> Director -> VP -> CEO. Each level can accept, delegate, escalate, or request a new worker.

---

## Appendix C: Troubleshooting

### Task stuck in `in_progress`

**Cause:** Agent crashed mid-execution, or SLA was not enforced.
**Fix:** Run `/orch-heartbeat`. It detects tasks `in_progress` past SLA and resets them to `todo` for re-dispatch. For tasks >24h old, heartbeat auto-flags as stale.

### Budget shows 0%

**Cause:** Token capture is not running, or tasks lack `actual_tokens`.
**Fix:** Run the budget tracker manually:
```bash
python3 ~/.claude/orchestrator/budget_tracker.py
python3 ~/.claude/orchestrator/budget_tracker.py --report
```
If tasks have no `actual_tokens`, the scanner finds nothing. Add tokens manually:
```bash
python3 ~/.claude/orchestrator/budget_tracker.py --add-tokens 10000 --project my-project --skill seo-audit
```

### Skill not found by dispatch

**Cause:** The skill is not registered as a worker in `company.yaml`, or the `skill:` field does not match the SKILL.md `name`.
**Fix:** Verify the worker entry exists and the `skill` value matches exactly:
```yaml
# In SKILL.md frontmatter:
name: my-skill

# In company.yaml:
workers:
  worker-my-skill:
    skill: "my-skill"        # Must match exactly
    reports_to: "dir-delivery"
    capabilities: [keyword1, keyword2]
```

### Revision loop exceeded

**Cause:** Task quality keeps scoring below threshold after max revisions.
**Fix:** The task is auto-blocked with reason `"revision_max_loops exceeded"`. Review the completion comment and revision notes manually. Either improve the skill, adjust the quality threshold, or manually approve:
```
/orch-orchestrator approve PROJ-001
```

### Circular dependency detected

**Cause:** Task A depends on B, B depends on C, C depends on A.
**Fix:** The orchestrator aborts with the full cycle chain. Edit the task YAML files in `tasks/active/` to remove the circular reference.

### Autopilot stops unexpectedly

**Cause:** Budget hit 95% (hard stop) or no tasks remain.
**Fix:** Check budget:
```bash
python3 ~/.claude/orchestrator/budget_tracker.py --report
```
If budget is critical, either increase `monthly_limit_tokens` in `company.yaml` or wait for the next month. If no tasks remain, the autopilot idles at 30-minute intervals.

### Health check shows DEGRADED

**Cause:** One or more components are STALE or MISSING.
**Fix:** Run `/orch-status`. It auto-fixes what it can (missing dirs, empty files). For issues requiring manual intervention (KB down, memory missing), follow the recommendations in the health report.

---

*Orchestrator AI Framework -- MIT License*
