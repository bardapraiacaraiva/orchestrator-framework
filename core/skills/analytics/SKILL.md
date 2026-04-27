---
name: orch-analytics
description: "Analytics and intelligence -- cross-project pattern detection, skill performance dashboard, revenue attribution, knowledge graph queries, and competitive intelligence. The brain that makes the system smarter over time. Triggers on: 'analytics', 'dashboard', 'patterns', 'performance', 'ROI', 'intelligence', 'what worked', 'which skill', 'cross-project'."
license: MIT
---

# Analytics & Intelligence

The intelligence layer that turns data into decisions. Without analytics, the system executes but never learns. With analytics, every project makes the next one better.

## When to activate

- Weekly automated report (via scheduled trigger)
- User asks "what patterns?", "which skill works best?", "ROI?"
- After milestone completion on any project
- When planning a new project (recommend approach based on history)
- Via `/orch-analytics`

## 5 Analytics Modules

### Module 1: Cross-Project Pattern Detection

Scans all completed projects and extracts reusable patterns.

**Data sources:**
- `tasks/done/` -- completed tasks with quality scores
- `quality/success-patterns.yaml` -- what worked
- `quality/failure-patterns.yaml` -- what failed
- Agent memory project files -- domain, stack, outcomes

**Pattern extraction per domain:**
1. Which skills were used?
2. What quality scores did they achieve?
3. What was the optimal execution order?
4. What context improved quality?
5. What common mistakes occurred?

**Output: Domain Playbook**
```yaml
domain: "domain-name"
projects_analyzed: N
avg_quality: 87.5
optimal_skill_chain:
  - skill-a (always first, 92 avg)
  - skill-b (parallel with skill-c)
  - skill-c (critical for domain, 91 avg)
avoid:
  - "skill-x before skill-y -- produces generic output"
estimated_tokens: 35000
estimated_time: "15-20 minutes"
```

### Module 2: Skill Performance Dashboard

Real-time view of every skill's effectiveness.

**Metrics per skill:**
- Success rate (% tasks >= 75 quality)
- Revision rate (% needing revision)
- Average quality score and token usage
- Trend (improving / stable / declining)
- Best and worst use case by domain

**Tiered output:**
- **Tier A** (avg >= 85, revision < 10%): High performers
- **Tier B** (avg 70-84, revision 10-25%): Needs attention
- **Tier C** (avg < 70, revision > 25%): Requires intervention

### Module 3: Revenue Attribution

Track which skills and projects generate measurable value.

```yaml
# analytics/revenue.yaml
clients:
  client-slug:
    monthly_retainer: 1500
    skills_used: [skill-a, skill-b, skill-c]
    total_tokens_invested: 34000
    token_cost_estimate: 3.40
    revenue_to_date: 1500
    roi_multiplier: 441x
```

**Revenue per skill:** projects using it, avg revenue/project, token cost, ROI.

### Module 4: Knowledge Graph Queries

Query relationships between entities across the system.

**Entity types:** Client, Project, Skill, Worker, Competitor, Pattern

**Example queries:**
- "All clients in domain X"
- "Best approach for [domain] project" (returns playbook)
- "Which skills have declining quality?"
- "Clients with stale projects (>30 days no activity)"

### Module 5: Competitive Intelligence

Track and alert on competitor movements (if applicable).

**Monitoring:** keyword rankings, competitor content, market shifts.
**Alerts:** ranking drops, new competitors, trend shifts.

## Weekly Intelligence Report

```markdown
## Intelligence Report -- Week of YYYY-MM-DD

### Portfolio Health
- Active projects: N | Tasks completed: N
- Avg quality: X | Budget used: X%

### Top Insight
"[Key pattern or recommendation based on data]"

### Skill Health
- Improving: [skills with upward trend]
- Declining: [skills needing attention]
- Gap detected: [missing skill capability]

### Cross-Project Patterns
- Confirmed: [patterns with 3+ projects]
- Emerging: [patterns with 2 projects]

### Revenue
- Monthly from orchestrated projects: X
- Token cost: Y | ROI: Zx

### Action Items
1. [Specific improvement recommendations]
```

## Minimum Data Requirements

- Quality trends need minimum 5 data points before declaring "declining"
- Cross-project patterns need minimum 3 projects to be "confirmed"
- Revenue estimates are always approximate -- never present as exact

## Red Flags

- Never report revenue estimates as exact
- Analytics are decision support, not decisions -- user always decides
- Competitive intelligence must use only public data
- Playbook recommendations require sufficient historical data
