---
name: orch-autopilot
description: "Active heartbeat that EXECUTES. Scans taskboard, auto-dispatches unassigned tasks, executes next wave in parallel, scores completed outputs, enforces budget limits, and self-paces via /loop. Triggers on: 'autopilot', 'auto', 'run all', 'execute all', 'go'."
license: MIT
---

# Autopilot -- Active Heartbeat

The skill that closes the loop. Not a reporter -- an **executor**.

## What this does in ONE invocation

```
1. SCAN     -- Read all tasks in tasks/active/
2. BUDGET   -- Check spend. If >95%, STOP. If >80%, WARN.
3. UNBLOCK  -- Cascade: done tasks unblock dependents -> todo
4. DISPATCH -- Unassigned todo tasks get assigned via company.yaml
5. EXECUTE  -- Launch next wave (max 3 parallel) via Agent tool
6. SCORE    -- Quality-score completed tasks (delegated to orch-quality)
7. LOG      -- Update audit trail + budget + skill metrics
8. PACE     -- If tasks waiting: next pulse in 60-90s
               If idle: next pulse in 1800s (30min)
               If budget critical: STOP loop
```

## When to activate

- Via `/loop /orch-autopilot` -- autonomous self-pacing mode
- Via `/orch-autopilot` -- single pulse execution
- When user says "autopilot", "run all", "execute all"

## Execution Protocol

### Step 1: SCAN
Read every `.yaml` in `tasks/active/`. Build task map grouped by status. Report counts.

### Step 2: BUDGET CHECK
```
>= 95%: STOP autopilot, do NOT execute, do NOT schedule next pulse
>= 80%: WARN, limit to 1 task per pulse
<  80%: Normal operation, max 3 parallel
```
This is a HARD STOP. User must manually approve or increase limit.

### Step 3: UNBLOCK CASCADE
For each `done` task, check dependents. If ALL deps met, transition dependent to `todo`.

### Step 4: AUTO-DISPATCH
For each `todo` task with no assignee: match `task.skill` to worker in `company.yaml`, assign, log.

### Step 5: EXECUTE WAVE
```python
executable = [t for t in tasks if t.status == "todo" and t.assignee and all_deps_done(t)]
executable.sort(by=priority)  # critical > high > medium > low
wave = executable[:max_parallel]

for task in wave:
    task.status = "in_progress"
    task.checked_out_at = now()
    Agent({
        description: "Autopilot: {task.id} -- {task.title}",
        prompt: """
        You are {task.assignee} executing task {task.id}.
        TASK: {task.title}
        SKILL TO USE: /{task.skill}
        PROJECT: {task.project}
        EXECUTION POLICY: {task.execution_policy}
        Execute and provide a substantive completion comment.
        """
    })
```

After each Agent returns: update status, record tokens, update budget.

### Step 6: QUALITY SCORE (delegated to orch-quality)

Quality scoring is **delegated** to `orch-quality` -- NOT embedded in autopilot. This ensures separation of concerns.

```python
for task in just_completed:
    score = invoke_orch_quality(task)
    # Returns: { score: int, dimensions: dict, action: str, feedback: str }
    task.quality_score = score.score

    if score.action == "revision":
        if task.revision_count >= task.revision_max_loops:
            task.status = "blocked"
            task.blocked_reason = f"revision_max_loops exceeded ({task.revision_count} cycles)"
        else:
            task.status = "in_progress"
            task.revision_count += 1
    elif score.action == "success_pattern":
        LOG "EXCELLENT: {task.id} scored {score.score}/100"
```

**Skill-to-Skill Contract:**
```yaml
invoke_orch_quality(task) -> {
    score: int (0-100),
    dimensions: { specificity, actionability, completeness, accuracy, tone },
    action: "ship" | "revision" | "success_pattern" | "escalate",
    feedback: str
}
```

### Step 7: LOG
Append to `audit/YYYY-MM-DD.yaml`. Update `budgets/YYYY-MM.yaml`. Update `quality/skill-metrics.yaml`.

### Step 8: SELF-PACE
```python
if budget_critical:
    STOP  # Do not schedule next pulse
elif remaining_todo > 0 or remaining_in_progress > 0:
    ScheduleWakeup(delaySeconds=90, reason="tasks pending")
else:
    ScheduleWakeup(delaySeconds=1800, reason="idle")
```

## Execution Policies

| Policy | Auto-execute? | Auto-score? | Auto-approve? |
|---|---|---|---|
| `default` | YES | YES | YES (if score >= 75) |
| `client_facing` | YES | YES | NO -- stays in_review |
| `critical` | YES | YES | NO -- asks user |
| `financial` | YES | YES | NO -- asks user |

## Pulse Output

```markdown
## Autopilot Pulse -- HH:MM

### Executed
| Task | Skill | Tokens | Quality | Status |
|---|---|---|---|---|

### Unblocked
- <task IDs moved to todo>

### Budget
- This pulse: N tokens | Month total: X / Y (Z%)

### Next Pulse
- N tasks remaining -> next in 90s / idle -> 30min / budget stop
```

## Safety Rails

1. Budget hard stop at 95%
2. Max 3 parallel tasks
3. Max 3 revision loops per task
4. Critical/financial tasks always need user approval
5. Stale detection: >24h flagged, >48h escalated
6. Coalescing: skip pulse if one already running
7. Audit everything
