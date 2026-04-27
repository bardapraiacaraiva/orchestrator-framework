---
name: orch-quality
description: "Quality scorer -- evaluates skill outputs against a 5-dimension rubric, tracks quality per skill/worker/project, identifies improvement patterns, and feeds the learning loop. Triggers on: 'quality', 'score', 'evaluate output', 'how good was this', 'skill performance', 'quality dashboard'."
license: MIT
---

# Quality Scorer

Measures what matters. Without quality scoring, the system produces output but never knows if it's good. This skill closes the feedback loop.

## When to activate

- Automatically after every task completion (called by heartbeat/autopilot)
- Manually via `/orch-quality` to review a specific task
- When user asks "how good was this?", "skill performance", "quality dashboard"

## Quality Rubric (5 Dimensions, 20 pts each = 100 total)

| Dimension | What it measures | 20 | 10 | 0 |
|---|---|---|---|---|
| **Specificity** | Specific to THIS client/project? | Mentions client by name, uses their data | Somewhat specific | Could be any client |
| **Actionability** | Can act on this immediately? | Clear next steps, no ambiguity | Some steps clear | Vague recommendations |
| **Completeness** | Covers all task requirements? | All met | Most met | Significant gaps |
| **Accuracy** | Facts, data, recommendations correct? | Verified, sourced | Mostly correct | Contains errors |
| **Tone & Format** | Matches brand voice and format? | Client-ready, polished | Needs minor edits | Wrong tone/format |

## Score Interpretation

| Score | Grade | Action |
|---|---|---|
| 90-100 | Excellent | Ship. Log as success pattern. |
| 75-89 | Good | Minor revision optional, ship. |
| 60-74 | Acceptable | Director review required. May need revision. |
| 40-59 | Poor | Revision required. Analyze why. |
| 0-39 | Fail | Reject. Reassign or escalate. |

## Scoring Process

### Automatic (after every task)
1. Read task YAML (description, success criteria, skill)
2. Read task output (completion_comment + generated files)
3. Score each dimension
4. Calculate total (0-100)
5. Write `quality_score` to task YAML
6. If < 60: flag for revision
7. If >= 90: log as success pattern
8. Update skill performance metrics

### Manual (user override)
```
/orch-quality score PROJ-001 85 "Good but missing competitor analysis"
```
User feedback always takes priority over automatic scoring.

## Skill Performance Tracking

Maintain `~/.claude/orchestrator/quality/skill-metrics.yaml` with per-skill data: `total_executions`, `avg_quality_score`, `scores[]`, `revision_rate`, `avg_tokens`, `best_score`, `worst_score`, `common_weakness`, `improvement_trend` (improving/stable/declining).

## Success Pattern Extraction (score >= 90)

```yaml
# quality/success-patterns.yaml
patterns:
  - skill: "skill-name"
    project: "project-slug"
    score: 92
    what_worked:
      - "Specific technique or approach that scored well"
    client_domain: "domain"
    reuse_for: ["similar-domain-1", "similar-domain-2"]
```

## Failure Pattern Analysis (score < 60)

```yaml
# quality/failure-patterns.yaml
patterns:
  - skill: "skill-name"
    project: "project-slug"
    score: 55
    what_failed:
      - "Specific issue"
    root_cause: "Why it failed"
    fix_suggested: "What to do differently"
```

## Callable Interface (Skill-to-Skill Contract)

This skill is called by other skills (autopilot, heartbeat, orchestrator).

### Input
```yaml
task:
  id: "PROJ-001"
  title: "Task title"
  description: "What was requested"
  skill: "skill-name"
  project: "project-slug"
  execution_policy: "client_facing"
  completion_comment: "The actual output text"
```

### Output
```yaml
score: 88
dimensions:
  specificity: 18
  actionability: 20
  completeness: 16
  accuracy: 18
  tone: 16
action: "ship"          # ship | revision | success_pattern | escalate
feedback: "Human-readable feedback for revision note"
skill_metrics_updated: true
patterns_extracted: 0
```

### Action Rules
| Score | Action | Effect |
|---|---|---|
| 90-100 | `success_pattern` | Ship + extract to success-patterns.yaml |
| 75-89 | `ship` | Ship (minor revision optional) |
| 60-74 | `revision` | Send back to worker with feedback |
| 0-59 | `escalate` | Block task + escalate to director/CEO |

## Quality Dashboard

```markdown
## Quality Dashboard -- YYYY-MM

### Overall
- Tasks scored: N | Avg quality: X/100
- Excellence rate (>=90): X% | Revision rate (<60): X%

### Top Skills (by quality)
| Skill | Avg Score | Executions | Trend |

### Bottom Skills (need improvement)
| Skill | Avg Score | Revision Rate | Issue |

### Action Items
1. Skills needing improvement with specific recommendations
```

## Red Flags

- Never ship a <60 score output without revision
- Never ignore a skill with >30% revision rate
- Automatic scoring is a GUIDE -- user feedback always overrides
- Quality data must persist across sessions (YAML on disk)
- Never embed scoring logic in other skills -- always delegate to this skill
