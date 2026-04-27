---
name: orch-status
description: "System health dashboard -- checks all orchestrator services, agent memory, task state, budget, skills inventory, and overall health. Triggers on: 'status', 'system health', 'health check', 'system check'."
license: MIT
---

# Status -- System Health Dashboard

One-command full health check of the {{COMPANY}} orchestrator system.

## When to activate

- Start of session ("how is the system?")
- After changes to infrastructure or configuration
- Periodic health review
- Debugging issues
- Via `/orch-status`

## Health Check Protocol

Run each check in order; collect results into the Health Report.

### 1. Knowledge Base / RAG Engine (if configured)

Check health endpoint defined in `company.yaml`:
- If responds HTTP 200: status = UP
- If connection refused / timeout: status = DOWN
- When UP: report source count, chunk count, last ingest date

### 2. Agent Memory

Check existence and freshness of memory files listed in `company.yaml`:

For each configured agent memory file:
- Present and recent (< 7 days): OK
- Present but old (> 7 days): STALE
- Missing: MISSING (red flag)

### 3. Orchestrator Infrastructure

Check all required directories and files:

| Component | Path |
|---|---|
| Active tasks | `~/.claude/orchestrator/tasks/active/` |
| Done tasks | `~/.claude/orchestrator/tasks/done/` |
| Audit logs | `~/.claude/orchestrator/audit/` |
| Budgets | `~/.claude/orchestrator/budgets/` |
| Quality | `~/.claude/orchestrator/quality/` |
| Company config | `~/.claude/orchestrator/company.yaml` |

For each: check existence, count items where applicable.

**Budget check:** Read current month `budgets/YYYY-MM.yaml`, extract `percentage`. Flag >80% as WARNING, >95% as CRITICAL.

### 4. Skills Inventory

Count and categorize all installed skills. Group by division prefix as defined in `company.yaml`.

### 5. External Services (if configured)

Check any services listed in `company.yaml` under `services:` section (embedding models, APIs, etc.).

## Health Report Template

```markdown
## {{COMPANY}} System Health -- YYYY-MM-DD HH:MM

### Services
| Service | Status | Details |
|---------|--------|---------|
| Knowledge Base | [UP]/[DOWN] | X sources, Y chunks |
| [other services from company.yaml] | [UP]/[DOWN] | details |

### Agent Memory
| Memory File | Status | Last Modified | Size |
|-------------|--------|---------------|------|
| [agent-1] | [OK]/[MISSING]/[STALE] | DATE | X KB |

### Orchestrator
| Component | Status | Details |
|-----------|--------|---------|
| tasks/active | [OK]/[MISSING] | X tasks |
| tasks/done | [OK]/[MISSING] | X tasks |
| audit | [OK]/[MISSING] | -- |
| budgets | [OK]/[MISSING] | Current: X% |
| quality | [OK]/[MISSING] | -- |
| company.yaml | [OK]/[EMPTY]/[MISSING] | -- |

### Skills Inventory
| Division | Count |
|----------|-------|
| [division-1] | X |
| [division-2] | X |
| **Total** | **X** |

### Overall Verdict
- **Status**: HEALTHY / DEGRADED / DOWN
- **Red Flags**: (list any, or "None")
- **Recommendations**: (list any, or "All clear")
```

**Status icons:**
- `[UP]` / `[OK]` -- healthy
- `[DOWN]` / `[MISSING]` -- unreachable or absent
- `[STALE]` -- exists but >7 days without update
- `[EMPTY]` -- exists but zero bytes
- `[WARNING]` -- budget >80%
- `[CRITICAL]` -- budget >95%

## Auto-Fix

Actions the skill can perform automatically without user confirmation:

### Can Auto-Fix
| Issue | Fix |
|---|---|
| Missing orchestrator dirs | `mkdir -p` the required directories |
| Missing budget file | Create with `percentage: 0`, `spent: 0` |
| Missing quality dir | `mkdir -p quality/` |
| Missing agent-memory dirs | Create configured directories |
| Empty company.yaml | Create with minimal template |

### Requires Manual Intervention
| Issue | Why |
|---|---|
| Knowledge base down | Check underlying service logs |
| Agent memory MISSING (content) | Cannot auto-generate accumulated knowledge |
| Budget >95% | Business decision -- cannot auto-extend |
| External service unavailable | Check provider status |

Auto-fix runs silently during health check. If applied, report under **Auto-Fixed**.

## Red Flags

### Critical (Overall = DOWN)
| Condition | Impact |
|---|---|
| All agent memory missing | Complete context loss |
| Budget >= 95% | All execution blocked |
| company.yaml missing/empty | Orchestrator cannot function |

### Warning (Overall = DEGRADED)
| Condition | Impact |
|---|---|
| Budget >= 80% | Limited to 1 task per pulse |
| Any agent memory stale | Operating on outdated context |
| Knowledge base down | No knowledge retrieval |
| Zero active tasks | May indicate stalled pipeline |

### Escalation
1. Print red flags prominently at top of report
2. If auto-fixable, apply fix and re-check
3. If not, include suggested action
4. For CRITICAL: prefix with "ALERT: System requires immediate attention."
