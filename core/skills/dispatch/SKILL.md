---
name: orch-dispatch
description: "Intelligent routing engine -- maps tasks to the optimal agent, skill, or squad based on capabilities, availability, and company hierarchy. Supports parallel assignment, escalation chains, and cross-division coordination. Triggers on: 'dispatch', 'routing', 'who does this', 'assign'."
license: MIT
---

# Dispatch -- Intelligent Task Routing

The "brain" that decides WHO does WHAT. Maps tasks to the optimal executor using capability matching, workload awareness, and company hierarchy from `company.yaml`.

## When to activate

- Called by `orch-orchestrator` during Phase 3 (Dispatch)
- User asks "who does this?", "who should work on this?"
- Cross-division coordination needed
- Invoked via `/orch-dispatch`

## Routing Algorithm

### Step 1: Parse Task Requirements

From the task, extract:
- **Domain keywords** -- area of expertise needed
- **Skill reference** -- does the task specify a skill directly?
- **Division** -- which division handles this domain?
- **Complexity** -- single skill, multi-skill, or squad-level?
- **Policy** -- what execution policy applies?

### Step 2: Capability Matching + Workload Awareness

Load `~/.claude/orchestrator/company.yaml` and match:

```python
def find_best_executor(task):
    # 1. Direct skill match (fastest path)
    if task.skill:
        worker = find_worker_by_skill(task.skill)
        if worker and is_available(worker):
            return worker
        fallback = find_fallback(task, worker)
        if fallback:
            return fallback
        return None  # Queue for next pulse

    # 2. Capability intersection
    candidates = []
    for worker in all_workers:
        overlap = set(task.required_capabilities) & set(worker.capabilities)
        if overlap:
            load = get_active_task_count(worker)
            candidates.append((worker, len(overlap), load))

    # 3. Sort: capability overlap > lowest workload > division match
    candidates.sort(key=lambda x: (x[1], -x[2], x[0].division == task.division), reverse=True)
    return candidates[0][0] if candidates else escalate_to_manager(task)
```

### Step 2.5: Workload Awareness

A worker is available if they have no `in_progress` tasks. When primary worker is busy, find fallback: first check sibling workers under same director, then escalate to director itself.

**Workload limits:** Worker: max 1 in_progress. Director: max 2. VP/CEO: no limit.

### Step 3: Escalation Chain

```
Worker (skill) -> Director (manager) -> VP (division) -> CEO
```

Each level can accept, delegate down, escalate up, or request a new worker.

### Step 4: Parallel Assignment

**Max 3 parallel workers per heartbeat.** Group independent tasks (no mutual dependencies) into execution waves.

## Routing Tables

Company-specific routing tables are defined in `~/.claude/orchestrator/company.yaml` under the `workers:` and `agents:` sections. Each worker declares:

```yaml
workers:
  worker-example:
    skill: "skill-name"
    capabilities: ["keyword1", "keyword2"]
    reports_to: "dir-division"
    division: "division-name"
```

The dispatch engine matches task keywords against worker capabilities. **Do not hardcode routing tables in this skill** -- they belong in `company.yaml`.

## Taskboard Integration (Bidirectional)

### READ: Get unassigned tasks
```python
def get_dispatchable_tasks():
    tasks = read_all_yamls("tasks/active/")
    return [t for t in tasks if t.status in ["todo", "backlog"] and t.assignee is None and all_deps_done(t)]
```

### WRITE: Record assignments
```python
def write_assignment(task, worker):
    task.assignee = worker.id
    task.assigned_by = "orch-dispatch"
    task.status = "todo"
    task.updated_at = now()
    write_yaml(f"tasks/active/{task.id}.yaml", task)
    append_audit({"actor": "orch-dispatch", "action": "task_assigned", "entity_id": task.id})
```

### CREATE: Cross-division subtasks
When dispatch detects a cross-division task, decompose into division-specific subtasks with IDs like `PROJ-001-A`, `PROJ-001-B`.

### Batch Dispatch
Process all unassigned tasks in one pass, sorted by priority.

## SLA Timeouts per Execution Policy

| Policy | SLA Timeout | Action on Timeout |
|---|---|---|
| `critical` | 1 hour | Auto-escalate + notify watchers |
| `client_facing` | 4 hours | Flag as stale + notify director |
| `financial` | 2 hours | Auto-escalate + block until reviewed |
| `default` | 8 hours | Flag as stale in next heartbeat |

Set `task.sla_deadline = now() + sla_duration[policy]` at assignment time.

## Auto-Playbook Recommendation

When dispatch receives the first task in a new project:

1. **Detect domain** -- scan task + project keywords against known patterns in `company.yaml`
2. **Load playbook** -- check `quality/skill-metrics.yaml` for `domain_playbooks`
3. **Auto-decompose** -- create tasks on taskboard from playbook skill chain
4. **User override** -- user can force a specific playbook or request custom decomposition

### Learning Loop

After project completion, compare actual execution vs playbook prediction. Record feedback in `quality/playbook-feedback.yaml` for analytics to propose updates.

## Red Flags

- Never assign outside declared capabilities
- Never run more than 3 parallel workers
- Never dispatch without checking dependencies
- Never ignore division boundaries -- use cross-division protocol
- Never assign to a busy worker -- check workload first
- Always write back to taskboard -- dispatch without persistence is lost work
- Squad boost is optional -- don't activate for simple tasks
