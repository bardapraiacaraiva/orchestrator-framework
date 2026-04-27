---
name: orch-taskboard
description: "Task lifecycle management -- create, assign, checkout, review, approve tasks with atomic ownership and status tracking. Persistent YAML-based taskboard at ~/.claude/orchestrator/tasks/. Triggers on: 'taskboard', 'tasks', 'create task', 'view tasks', 'task status', 'backlog', 'sprint', 'kanban'."
license: MIT
---

# Taskboard -- Task Lifecycle Management

Persistent task management with atomic checkout, dependency tracking, execution policies, and audit logging. The backbone of the orchestrator.

## When to activate

- User asks to see, create, or manage tasks
- Called by `orch-orchestrator` during decomposition and tracking
- User says "taskboard", "tasks", "backlog", "sprint", "kanban"
- Invoked via `/orch-taskboard`

## Storage

```
~/.claude/orchestrator/tasks/
  +-- active/          # Tasks in progress (backlog through in_review)
  +-- done/            # Completed tasks (archived)
  +-- templates/       # Reusable task templates
```

## Task Schema (v2)

```yaml
id: "PROJ-001"
title: "Descriptive imperative action"
description: "What needs to be done, why, and success criteria"
project: "project-slug"
status: "todo"                        # backlog | todo | in_progress | in_review | done | blocked
priority: "high"                      # critical | high | medium | low
assignee: null                        # Worker ID from company.yaml
assigned_by: null                     # Who assigned it
parent: null                          # Parent task ID (for decomposition)
children: []                          # Child task IDs
depends_on: []                        # Must complete before this starts
blocks: []                            # Tasks waiting on this one
execution_policy: "default"           # default | critical | client_facing | financial
estimated_tokens: 5000
actual_tokens: null                   # Filled after execution
skill: null                           # Which skill executes this
squad: null                           # Optional squad for parallel work
tags: []
created_at: "<ISO timestamp>"
updated_at: "<ISO timestamp>"
checked_out_at: null                  # When assignee claimed it
completed_at: null
reviewed_by: null
approved_by: null
completion_comment: null              # Mandatory at completion
revision_count: 0                     # How many revision loops
revision_max_loops: 3                 # Max revisions before forced escalation
blocked_reason: null                  # Required when status is "blocked"
watchers: []                          # Agent IDs notified on status changes
sla_deadline: null                    # Set by dispatch based on execution_policy
notes: []                             # Append-only notes log
```

## Status Flow

```
                    +------------------------------+
                    |                              |
backlog --> todo --> in_progress --> in_review --> done
                         |              |
                         |              +--> in_progress (revision)
                         |
                         +--> blocked --> in_progress (unblocked)
```

## Operations

### CREATE
Generate ID (`<PREFIX>-<NNN>`), set status `backlog` (or `todo` if assignee known), write YAML, log to audit.

### ASSIGN (Atomic Checkout)
Verify task is `todo`/`backlog`, worker capabilities match, all deps `done`. Set assignee + status. If already `in_progress` with different assignee: REJECT (409 conflict).

### START
Verify `todo` with assignee and deps met. Set `in_progress` + `checked_out_at`.

### COMPLETE
Verify `in_progress`, require substantive comment. Set `in_review` (or `done` if no review needed).

### REVIEW
Approve (-> done), revise (increment `revision_count`, -> in_progress), or escalate. Check `revision_max_loops`.

### APPROVE
Set `approved_by`, move to `done/`, unblock dependents.

### BLOCK / UNBLOCK
Block: `blocked_reason` MANDATORY, notify watchers. Unblock: clear reason, status -> `todo`.

### LIST
Output grouped by priority: ID, Task, Assignee, Status, Age, Blocked? Summary line.

## Dependency Resolution

When a task completes:
1. Find all tasks where `depends_on` includes the completed task
2. Check if ALL dependencies are now `done`
3. If yes and task has assignee -> auto-transition to `todo`
4. If yes and no assignee -> flag for dispatch

This creates a **cascading unblock** effect.

## Parent Task Rollup

When a child task changes status:
1. Read parent and ALL children
2. Apply rollup: any blocked -> parent blocked; all done -> parent done; any in_progress -> parent in_progress
3. Parent tasks are grouping nodes -- only leaf tasks execute skills

## Revision Loop Control

When revision requested:
1. Check `revision_count` against `revision_max_loops`
2. If exceeded: status -> `blocked`, `blocked_reason: "revision_max_loops exceeded"`, add CEO to watchers
3. If within limits: increment count, add revision note, status -> `in_progress`

## Cross-Session Persistence

Tasks stored as individual YAML files -- survives session compaction, readable by multiple sessions, human-editable, git-friendly.

## Integration Points

- **orch-orchestrator**: calls taskboard for all task CRUD
- **orch-dispatch**: reads unassigned tasks, writes assignments back
- **Audit trail**: every mutation logged to `audit/YYYY-MM-DD.yaml`

## Red Flags

- Never allow two agents to own the same task simultaneously
- Never mark `done` without a completion comment
- Never skip dependency checks
- Never delete tasks -- archive to `done/` for audit trail
- Never exceed `revision_max_loops` without escalating to user
- Stale tasks (>48h) should trigger an alert
