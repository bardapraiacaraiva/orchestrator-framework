---
name: orch-heartbeat
description: "Automatic heartbeat engine -- checks the taskboard, dispatches unassigned tasks, executes waiting waves, detects stale tasks, and enforces budget limits. The autonomous nervous system of the orchestrator. Triggers on: 'heartbeat', 'pulse', 'auto-execute', 'check tasks', 'wake up', 'run next wave'."
license: MIT
---

# Heartbeat Engine

The missing piece that transforms the orchestrator from a planning tool into an autonomous execution system. Without heartbeat, tasks sit in YAML files forever. With heartbeat, the system wakes up, checks the board, and makes things happen.

## When to activate

- Automatically via scheduled trigger (every 30 minutes)
- Manually via `/orch-heartbeat`
- When user says "check tasks", "run next wave", "what's pending"
- Called by `orch-orchestrator` to kickstart execution after decomposition

## Heartbeat Cycle

```
PULSE START
|
+-- 1. SCAN -- Read all tasks in tasks/active/
|   +-- Count by status: backlog, todo, in_progress, in_review, done, blocked
|   +-- Flag: stale (in_progress >24h without update)
|   +-- Flag: SLA breached (in_progress past sla_deadline)
|
+-- 2. BUDGET CHECK -- Read budgets/YYYY-MM.yaml
|   +-- >80%: log warning, limit to 1 parallel worker
|   +-- >95%: PAUSE all execution, alert user
|   +-- Missing: create with 0 spent
|
+-- 3. UNBLOCK CASCADE -- For each done task:
|   +-- Find dependents, check if ALL deps done
|   +-- If yes: transition to "todo" (ready for dispatch)
|
+-- 4. AUTO-DISPATCH -- For unassigned todo tasks:
|   +-- Match capabilities via company.yaml
|   +-- Assign best worker, log to audit
|
+-- 5. WAVE PLANNING -- Group assigned todo tasks:
|   +-- Identify independent tasks (no mutual depends_on)
|   +-- Create waves (max 3 per wave)
|   +-- Execute Wave 1 via Agent tool (parallel)
|
+-- 6. EXECUTE WAVE -- For each task in wave:
|   +-- Set status -> in_progress, checked_out_at -> now
|   +-- Launch Agent with task context + skill
|   +-- On completion: update status, log tokens, update budget
|
+-- 7. STALE DETECTION
|   +-- 0-24h: normal
|   +-- 24-48h: flag STALE, add warning note
|   +-- 48-72h: escalate to director
|   +-- >72h: escalate to CEO, mark blocked
|
+-- 8. REPORT -- Generate pulse summary
|
+-- PULSE END -- Write timestamp to last_pulse.yaml
```

## Configuration (from company.yaml)

```yaml
heartbeat_defaults:
  manager:
    interval_minutes: 30
    cooldown_minutes: 5
    coalesce_if_active: true
  worker:
    interval_minutes: 0     # Workers don't self-wake
    cooldown_minutes: 2
  service:
    interval_minutes: 5
    cooldown_minutes: 1
```

## Budget Enforcement

At each pulse, read `budgets/YYYY-MM.yaml`. Token counting: after each Agent execution, capture usage metadata and add to budget. Budget structure:

```yaml
month: "YYYY-MM"
company: "{{COMPANY}}"
total_tokens_used: 0
limit: 50000000           # from company.yaml
percentage_used: 0.0
by_project: {}
by_agent: {}
by_skill: {}
alert_80_sent: false
alert_95_sent: false
last_updated: "<ISO timestamp>"
```

## SLA Enforcement

Every pulse checks SLA compliance:

| Policy | SLA | Timeout Action |
|---|---|---|
| `critical` | 1h | Auto-escalate + block + notify watchers |
| `client_facing` | 4h | Flag stale + notify director |
| `financial` | 2h | Auto-escalate + block |
| `default` | 8h | Flag stale |

Double SLA breach (2x timeout) = auto-block with reason, release checkout.

## Coalescing

If a heartbeat is already running when a new trigger fires: skip the new pulse, let the active one finish. Prevents duplicate work and runaway token burn.

## Pulse Report Template

```markdown
## Pulse -- YYYY-MM-DD HH:MM

| Metric | Value |
|---|---|
| Tasks scanned | N |
| Executed this pulse | N |
| Waiting (todo) | N |
| In progress | N |
| Stale (>24h) | N |
| Blocked | N |
| Done (total) | N |
| Budget used | X% |
| Next wave | [task IDs] |

### SLA Status
| Task | Policy | Age | SLA | Status |
|---|---|---|---|---|
```

## Scheduling

- **Scheduled:** cron every 30 minutes
- **Loop:** `/loop /orch-heartbeat` (self-pacing: 60s active, 1800s idle)
- **Manual:** `/orch-heartbeat`

## Red Flags

- Never run two heartbeats simultaneously (coalescing prevents this)
- Never execute if budget >95% (hard stop)
- Never skip stale detection
- Never auto-approve critical tasks
- Never ignore SLA breaches
- Double SLA breach = auto-block, no exceptions
