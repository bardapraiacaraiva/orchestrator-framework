---
name: example-audit
description: "Example skill — shows the structure every skill should follow. Covers a basic website audit. Replace this with your own skills."
license: MIT
---

# Example Skill — Website Audit

This is a template skill. Use it as a starting point for creating your own skills.

## When to activate

- User asks for a website audit
- Called by orchestrator during a diagnostic pipeline
- Invoked via `/example-audit`

## Workflow

1. Gather: URL, access credentials, client goals
2. Run checks: performance, SEO, security, content, mobile
3. Score each category (0-10)
4. Prioritize findings: CRITICAL / IMPORTANT / OPTIMIZATION
5. Generate report with actionable next steps

## Output Template

```markdown
# Website Audit — <Client>

## Score: XX/100

### Performance — X/10
- [findings]
- **FIX:** [action]

### SEO — X/10
- [findings]

### Security — X/10
- [findings]

## Priority Actions
1. [CRITICAL] ...
2. [IMPORTANT] ...
3. [OPTIMIZATION] ...
```

## Save location
Save via your Obsidian save skill or output inline.

## Red Flags

- Never audit without checking the site is accessible first
- Never skip mobile testing — most traffic is mobile
- Always include specific, actionable fixes (not just "improve performance")
- Never present findings without prioritization
