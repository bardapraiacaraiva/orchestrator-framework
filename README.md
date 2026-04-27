# Orchestrator AI Framework

**Paperclip-inspired orchestration for Claude Code.** Turn your AI agent from a tool into an autonomous team.

```bash
npx orchestrator-ai-framework init
```

One command. Full orchestration. Any company.

---

## What it does

The Orchestrator AI Framework adds a **management layer** to Claude Code that transforms ad-hoc AI usage into structured, auditable, budget-aware autonomous execution.

| Without Framework | With Framework |
|---|---|
| Ad-hoc skill invocation | Structured task decomposition |
| No tracking across sessions | Persistent YAML taskboard |
| No quality gates | 5-dimension auto-scoring |
| No budget visibility | Real-time token tracking |
| Manual coordination | Autonomous heartbeat execution |
| No audit trail | Append-only audit log |

## Architecture

```
Your Request
    |
    v
[Orchestrator — Control Plane]
    |
    +-- Phase 0: VALIDATE (deps, budget, stale tasks)
    +-- Phase 1: UNDERSTAND (parse intent, check context)
    +-- Phase 2: DECOMPOSE (break into atomic tasks)
    +-- Phase 3: DISPATCH (route to best worker)
    +-- Phase 4: EXECUTE (parallel heartbeat windows)
    +-- Phase 4.5: ERROR RECOVERY (retry, backoff, dead-letter)
    +-- Phase 5: REVIEW (quality gates per policy)
    +-- Phase 6: SYNTHESIZE (combine outputs)
    +-- Phase 7: AUDIT (log everything, update budget)
```

## Core Skills (8 installed)

| Skill | What it does |
|---|---|
| `orch-orchestrator` | Control plane — decomposes, coordinates, synthesizes |
| `orch-taskboard` | Persistent YAML task lifecycle with atomic checkout |
| `orch-dispatch` | Intelligent routing with workload awareness |
| `orch-heartbeat` | Periodic task scanning + SLA enforcement |
| `orch-autopilot` | Autonomous execution loop (scan + dispatch + execute + score) |
| `orch-quality` | 5-dimension quality scoring with learning loop |
| `orch-analytics` | Cross-project patterns, playbooks, performance tracking |
| `orch-status` | System health dashboard with auto-fix |

## Quick Start

### 1. Install

```bash
npx orchestrator-ai-framework init --company "Your Company" --preset agency
```

Available presets: `agency`, `saas`, `studio`, `freelancer`, `custom`

### 2. Add your skills

Create skills in `~/.claude/skills/`:

```markdown
---
name: my-skill
description: "What this skill does"
---

# My Skill

## Workflow
1. Step one
2. Step two

## Red Flags
- Never do X without Y
```

### 3. Register workers

Edit `~/.claude/orchestrator/company.yaml`:

```yaml
workers:
  worker-my-skill:
    type: "worker"
    skill: "my-skill"
    reports_to: "dir-delivery"
    capabilities: [skill_a, skill_b]
```

### 4. Orchestrate

In Claude Code:
```
/orch-orchestrator
> "Audit and improve client X's website"
```

The orchestrator will decompose, dispatch, execute, score, and synthesize.

### 5. Go autonomous

```
/loop /orch-autopilot
```

The autopilot scans the taskboard, executes pending tasks, scores quality, and self-paces.

## Key Features

### Atomic Task Checkout
One agent owns one task at a time. No duplicate work. No conflicts.

### Execution Policies
| Policy | Review | Approval | SLA |
|---|---|---|---|
| `default` | No | No | 8h |
| `critical` | Yes | Yes (user) | 1h |
| `client_facing` | Yes | No | 4h |
| `financial` | Yes | Yes (user) | 2h |

### Budget Tracking
Real-time token accounting with automatic alerts at 80% and hard stop at 95%.

```bash
python3 ~/.claude/orchestrator/budget_tracker.py --report
```

### Quality Scoring (5 dimensions)
| Dimension | What it measures |
|---|---|
| Specificity | Client-specific or generic? |
| Actionability | Clear next steps? |
| Completeness | All requirements met? |
| Accuracy | Facts correct? |
| Tone | Format and voice match? |

Score < 60 = auto-revision. Score >= 90 = success pattern extracted.

### Domain Playbooks
Pre-built skill chains for common project types. Auto-detected by keyword matching.

### Error Recovery
- Retry with exponential backoff (3 attempts)
- Dead-letter queue for permanently failed tasks
- SLA timeout enforcement with auto-escalation
- Crash recovery via session persistence

## File Structure

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
  |   +-- your-skills/...
  +-- orchestrator/
      +-- company.yaml          # Your org chart
      +-- budget_tracker.py     # Token accounting
      +-- notifications.yaml    # Event protocol
      +-- tasks/
      |   +-- active/           # In-progress tasks
      |   +-- done/             # Completed archive
      |   +-- templates/        # Reusable task sets
      +-- audit/                # Daily audit logs
      +-- budgets/              # Monthly token budgets
      +-- quality/
          +-- skill-metrics.yaml    # Performance data
          +-- eval-baseline.yaml    # Scoring calibration
```

## White-Labeling

The framework installs with your company name. No "Orchestrator AI" branding appears in outputs — only your company identity.

```bash
npx orchestrator-ai-framework init --company "Acme Digital" --preset agency --owner "John"
```

Everything generated uses "Acme Digital" as the company name.

## Validation

```bash
npx orchestrator-ai-framework validate
```

Checks: directories exist, skills installed, company.yaml valid, budget tracker present.

## Uninstall

```bash
npx orchestrator-ai-framework uninstall
```

Removes core skills. Preserves your orchestrator data (tasks, audit, budget).

## Requirements

- Claude Code CLI installed
- Python 3.8+ (for budget tracker)
- Node.js 18+ (for installer)

## Inspired By

- [Paperclip AI](https://github.com/paperclipai/paperclip) — Company-as-org-chart, heartbeat model, atomic checkout
- Gawande's Checklist Manifesto — Quality gates
- Brunson's Value Ladder — Execution pipelines

## License

MIT
