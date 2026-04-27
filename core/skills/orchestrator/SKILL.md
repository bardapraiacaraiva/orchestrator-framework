---
name: orch-orchestrator
description: "Control plane for multi-agent orchestration. Coordinates agents, skills, squads, and services using heartbeats, atomic task checkout, execution policies, and budget controls. Triggers on: 'orchestrate', 'plan', 'decompose', 'coordinate', 'delegate', 'control plane', 'who does what', 'organize work'."
license: MIT
---

# Orchestrator — Control Plane

The central nervous system of the {{COMPANY}} agent ecosystem. Transforms ad-hoc skill invocation into structured, auditable, budget-aware orchestration.

## Core Principles

1. **Orchestration, not execution** -- The orchestrator coordinates; workers execute
2. **Discrete heartbeats** -- Work in bounded execution windows, not continuous loops
3. **Atomic task checkout** -- One agent owns a task at a time; no duplicate work
4. **Execution policies** -- Quality gates enforced at runtime
5. **Transparency** -- Every action logged; every delegation explained
6. **Budget awareness** -- Token spend tracked per project and agent

## When to activate

- Complex, multi-step project (not a single tactical task)
- User says "orchestrate", "plan", "decompose", "coordinate", "delegate"
- Invoked via `/orch-orchestrator`

## Architecture Overview

```
User Request
    |
    v
[Orchestrator — Control Plane]
    |
    +-- 0. VALIDATE  -- Pre-flight checks (deps, workers, budget, dirs, stale)
    +-- 1. UNDERSTAND -- Parse intent, gather context
    +-- 2. DECOMPOSE  -- Break into atomic tasks
    +-- 3. DISPATCH   -- Route each task to right agent/skill
    +-- 4. EXECUTE    -- Workers run in heartbeat windows
    +-- 5. REVIEW     -- Execution policies enforced
    +-- 6. SYNTHESIZE -- Combine outputs into deliverable
    +-- 7. AUDIT      -- Log everything, update budget
```

## Phase 0: VALIDATE (Pre-flight Checks)

**1. Circular Dependency Detection:**
For each task, walk the `depends_on` graph. If any task is visited twice, ABORT and report the full cycle chain.

**2. Worker Availability Check:**
For each task to dispatch, look up the worker in `company.yaml`. Count active `in_progress` tasks for that worker. If busy, queue or find fallback.

**3. Budget Pre-check:**
Read `~/.claude/orchestrator/budgets/YYYY-MM.yaml`:
- `>= 95%`: ABORT -- budget exceeded
- `>= 80%`: WARN -- limit to 1 parallel worker
- File missing: CREATE with defaults from `company.yaml`

**4. File Initialization:**
Ensure required paths exist: `tasks/active/`, `tasks/done/`, `tasks/templates/`, `audit/`, `budgets/`, `quality/`.

**5. Stale Task Recovery:**
Scan `tasks/active/` for tasks `in_progress` for >24h. Set to `blocked` with reason.

## Phase 1: UNDERSTAND

1. Parse the user request -- goal, scope, constraints
2. Check knowledge base (if available) for relevant context
3. Check agent memory for existing project context
4. Load `~/.claude/orchestrator/company.yaml` for available agents and capabilities
5. Identify constraints -- budget, timeline, dependencies, blockers

Output: **Mission Brief** -- structured understanding of what needs to happen.

## Phase 2: DECOMPOSE (Task Breakdown)

Break the mission into atomic tasks. Each task maps to ONE skill invocation. Use the full task schema defined in `orch-taskboard` (includes v2 fields: `revision_max_loops`, `blocked_reason`, `watchers`, `sla_deadline`). Save each task to `tasks/active/PROJ-NNN.yaml`.

## Phase 3: DISPATCH (Intelligent Routing)

Route each task to the best executor. See `company.yaml` for the routing table.

1. Match task capabilities to agent/worker capabilities
2. Check worker availability (atomic checkout -- one task per worker)
3. Plan parallelism (max 3 parallel workers per heartbeat)
4. Tasks with `depends_on` wait for predecessors to reach `done`

Routing logic is defined in `orch-dispatch`. Company-specific routing tables live in `company.yaml`.

## Phase 4: EXECUTE (Heartbeat Windows)

Each execution is a discrete heartbeat -- a bounded work session: claim task, execute via Agent tool, post mandatory completion comment, update status, return control. Max 3 parallel workers. Cooldown: 2 min between heartbeats per worker.

## Phase 4.5: ERROR RECOVERY

- **Retry:** Max 3 retries with exponential backoff (60s, 120s, 240s). After all fail, move to dead-letter queue.
- **Dead-Letter:** Set status `blocked` with error summary in `blocked_reason`. Continue other tasks.
- **Crash Recovery:** Next heartbeat scans for tasks `in_progress` past SLA timeout. Reset to `todo` for re-dispatch.
- **Idempotency:** Before executing, skip if: already `done`, already `in_progress` by another agent, or ran in last 5 minutes.

## Phase 5: REVIEW (Execution Policies)

- **Layer 1 -- Comment:** Worker MUST post a substantive completion comment (always enforced)
- **Layer 2 -- Review:** Director-level agent reviews; can approve, request revision, or escalate
- **Layer 3 -- Approval:** For `critical`/`financial` tasks, user explicitly approves

## Phase 6: SYNTHESIZE

Once all tasks reach `done`: gather outputs, combine into unified deliverable, cross-reference findings, generate executive summary with next steps.

## Phase 7: AUDIT (Logging & Budget)

**Audit Trail:** Every mutation logged to `~/.claude/orchestrator/audit/YYYY-MM-DD.yaml` with timestamp, actor, action, entity_id, details.

**Token Capture Contract:**
1. **Capture** -- After each Agent execution, record `actual_tokens` (from metadata or estimated by output length)
2. **Aggregate** -- Update `~/.claude/orchestrator/budgets/YYYY-MM.yaml` totals (by_project, by_skill, by_model)
3. **Enforce** -- At 80%: reduce to 1 parallel worker. At 95%: STOP all execution

## Notification Protocol

Events trigger notifications via `~/.claude/orchestrator/notifications.yaml`. Key events: `task_completed`, `task_revision`, `task_escalated`, `sla_warning`, `sla_breach`, `budget_warning`, `budget_critical`, `quality_low`, `project_completed`, `stale_task`.

Severity levels: `info` (pulse only), `warning` (pulse + audit), `critical` (pulse + audit + alert).

## Orchestrator Commands

`status`, `next`, `assign <task> to <worker>`, `block <task> reason <text>`, `unblock <task>`, `review <task>`, `approve <task>`, `budget`, `parallel <t1> <t2> [t3]`, `template <name> <project>`, `pause`, `resume`.

## Red Flags

- Never execute without checking `company.yaml` for the right agent
- Never skip the audit log
- Never run more than 3 parallel workers
- Never auto-approve critical or financial tasks
- Never ignore `depends_on` -- respect the dependency graph
- Never assign outside declared capabilities
- If revision loop exceeds `max_loops`, escalate to user immediately
