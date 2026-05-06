#!/usr/bin/env python3
"""
ORCH Skill Store — Install, remove, and manage skills.

Usage:
  python3 skill_store.py list                 List installed skills
  python3 skill_store.py info <skill>         Show skill details
  python3 skill_store.py create <name>        Create new skill from template
  python3 skill_store.py remove <name>        Remove a skill
  python3 skill_store.py search <keyword>     Search installed skills
  python3 skill_store.py verify               Verify all skills are valid
"""

import os
import sys
import shutil
from pathlib import Path
from datetime import datetime

HOME = Path.home()
SKILLS = HOME / ".claude" / "skills"
COMPANY = HOME / ".claude" / "orchestrator" / "company.yaml"

CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
DIM = "\033[90m"
BOLD = "\033[1m"
RESET = "\033[0m"

def list_skills(verbose=False):
    print(f"\n  {BOLD}{CYAN}Installed Skills{RESET}\n")

    if not SKILLS.exists():
        print(f"  {DIM}No skills directory found.{RESET}\n")
        return

    groups = {}
    for d in sorted(SKILLS.iterdir()):
        if not d.is_dir(): continue
        skill_md = d / "SKILL.md"
        if not skill_md.exists(): continue

        name = d.name
        lines = sum(1 for _ in open(skill_md, encoding="utf-8"))

        # Read description from frontmatter
        desc = ""
        try:
            with open(skill_md, "r", encoding="utf-8") as f:
                in_frontmatter = False
                for line in f:
                    if line.strip() == "---":
                        in_frontmatter = not in_frontmatter
                        if not in_frontmatter: break
                        continue
                    if in_frontmatter and line.startswith("description:"):
                        desc = line.split(":", 1)[1].strip().strip('"\'')[:60]
        except:
            pass

        # Categorize
        if name.startswith("dario"): group = "DARIO"
        elif name.startswith("diva"): group = "DIVA"
        elif name.startswith("lucas"): group = "LUCAS"
        elif name.startswith("seo"): group = "SEO"
        elif "a360" in name: group = "A360"
        else: group = "OTHER"

        if group not in groups: groups[group] = []
        groups[group].append({"name": name, "lines": lines, "desc": desc})

    colors = {"DARIO": CYAN, "DIVA": "\033[95m", "LUCAS": GREEN, "SEO": YELLOW, "A360": "\033[96m", "OTHER": DIM}

    total = 0
    for group, skills in sorted(groups.items()):
        color = colors.get(group, DIM)
        print(f"  {color}{BOLD}{group}{RESET} ({len(skills)} skills)")

        if verbose:
            for s in skills:
                quality = GREEN if s["lines"] >= 100 else YELLOW if s["lines"] >= 50 else RED
                print(f"    {s['name']:<30} {quality}{s['lines']:>4} lines{RESET}  {DIM}{s['desc'][:50]}{RESET}")
            print()

        total += len(skills)

    print(f"\n  {BOLD}Total: {total} skills{RESET}\n")

def info_skill(name):
    skill_dir = SKILLS / name
    skill_md = skill_dir / "SKILL.md"

    if not skill_md.exists():
        print(f"  {RED}Skill '{name}' not found.{RESET}")
        return

    print(f"\n  {BOLD}{CYAN}Skill: {name}{RESET}\n")

    lines = sum(1 for _ in open(skill_md, encoding="utf-8"))
    size = skill_md.stat().st_size
    modified = datetime.fromtimestamp(skill_md.stat().st_mtime).strftime("%Y-%m-%d %H:%M")

    # Parse frontmatter
    frontmatter = {}
    try:
        with open(skill_md, "r", encoding="utf-8") as f:
            in_fm = False
            for line in f:
                if line.strip() == "---":
                    in_fm = not in_fm
                    if not in_fm: break
                    continue
                if in_fm and ":" in line:
                    key, val = line.split(":", 1)
                    frontmatter[key.strip()] = val.strip().strip('"\'')
    except:
        pass

    print(f"  Name:        {frontmatter.get('name', name)}")
    print(f"  Lines:       {lines}")
    print(f"  Size:        {size:,} bytes")
    print(f"  Modified:    {modified}")
    print(f"  Description: {frontmatter.get('description', 'N/A')[:80]}")
    print(f"  License:     {frontmatter.get('license', 'N/A')}")
    print(f"  Path:        {skill_dir}")

    # Check sections
    content = skill_md.read_text(encoding="utf-8")
    has_workflow = "## Workflow" in content or "## When to activate" in content
    has_output = "## Output" in content or "## Save location" in content or "## Save Location" in content
    has_redflags = "## Red" in content
    has_integration = "## Integration" in content

    print(f"\n  {BOLD}Sections:{RESET}")
    print(f"    Workflow:    {'✓' if has_workflow else '✗'}")
    print(f"    Output:      {'✓' if has_output else '✗'}")
    print(f"    Red Flags:   {'✓' if has_redflags else '✗'}")
    print(f"    Integration: {'✓' if has_integration else '✗'}")

    quality = "COMPLETE" if lines >= 100 else "PARTIAL" if lines >= 50 else "STUB"
    color = GREEN if quality == "COMPLETE" else YELLOW if quality == "PARTIAL" else RED
    print(f"\n  Quality: {color}{quality}{RESET} ({lines} lines)\n")

def create_skill(name):
    skill_dir = SKILLS / name
    if skill_dir.exists():
        print(f"  {RED}Skill '{name}' already exists.{RESET}")
        return

    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / "SKILL.md"

    template = f"""---
name: {name}
description: "Descreva o que esta skill faz."
license: MIT
---

# {name}

## Quando usar

- Descreva quando esta skill deve ser activada
- Que triggers a activam

## Workflow

1. Passo 1
2. Passo 2
3. Passo 3

## Output Template

```markdown
# Resultado — [Cliente]

## Seccao 1
...

## Seccao 2
...
```

## Save Location
`05 - Claude - IA/Outputs/YYYY-MM-DD - [Cliente] - {name}.md`

## Red Flags

- Nunca fazer X sem verificar Y
- Sempre incluir Z no output
- Nunca enviar para cliente sem revisao
"""

    skill_md.write_text(template, encoding="utf-8")
    print(f"\n  {GREEN}✓{RESET} Skill '{name}' created at {skill_dir}")
    print(f"  Edit: {skill_md}")
    print(f"\n  {DIM}Next: register as worker in company.yaml:{RESET}")
    print(f"  {CYAN}worker-{name}:{RESET}")
    print(f"    type: \"worker\"")
    print(f"    skill: \"{name}\"")
    print(f"    reports_to: \"dir-...\"")
    print(f"    capabilities: [...]")
    print()

def remove_skill(name):
    skill_dir = SKILLS / name
    if not skill_dir.exists():
        print(f"  {RED}Skill '{name}' not found.{RESET}")
        return

    confirm = input(f"  {YELLOW}Remove skill '{name}'? This cannot be undone. (yes/no):{RESET} ")
    if confirm.lower() != "yes":
        print(f"  {DIM}Cancelled.{RESET}")
        return

    shutil.rmtree(skill_dir)
    print(f"  {GREEN}✓{RESET} Skill '{name}' removed.\n")

def search_skills(keyword):
    print(f"\n  {BOLD}{CYAN}Search: '{keyword}'{RESET}\n")

    if not SKILLS.exists():
        print(f"  {DIM}No skills found.{RESET}\n")
        return

    results = []
    kw = keyword.lower()

    for d in sorted(SKILLS.iterdir()):
        if not d.is_dir(): continue
        skill_md = d / "SKILL.md"
        if not skill_md.exists(): continue

        name = d.name
        if kw in name.lower():
            results.append((name, "name match"))
            continue

        try:
            content = skill_md.read_text(encoding="utf-8").lower()
            if kw in content:
                results.append((name, "content match"))
        except:
            pass

    if results:
        for name, match_type in results:
            print(f"  {CYAN}✓{RESET} /{name}  {DIM}({match_type}){RESET}")
        print(f"\n  {len(results)} results found.\n")
    else:
        print(f"  {DIM}No skills matching '{keyword}'.{RESET}\n")

def verify_skills():
    print(f"\n  {BOLD}{CYAN}Skill Verification{RESET}\n")

    if not SKILLS.exists():
        print(f"  {RED}No skills directory.{RESET}\n")
        return

    issues = []
    total = 0

    for d in sorted(SKILLS.iterdir()):
        if not d.is_dir(): continue
        skill_md = d / "SKILL.md"
        if not skill_md.exists():
            if d.name not in ("__pycache__", ".git", "node_modules"):
                issues.append((d.name, "Missing SKILL.md"))
            continue

        total += 1
        lines = sum(1 for _ in open(skill_md, encoding="utf-8"))
        content = skill_md.read_text(encoding="utf-8")

        if lines < 50:
            issues.append((d.name, f"STUB ({lines} lines)"))
        if "---" not in content[:10]:
            issues.append((d.name, "Missing frontmatter"))
        if "## Red" not in content and "## Red flags" not in content:
            pass  # Many skills use different format

    if issues:
        print(f"  {YELLOW}Issues found:{RESET}")
        for name, issue in issues:
            print(f"    {YELLOW}!{RESET} {name}: {issue}")
    else:
        print(f"  {GREEN}✓{RESET} All skills valid.")

    print(f"\n  {total} skills verified. {len(issues)} issues.\n")

def main():
    args = sys.argv[1:]
    if not args:
        list_skills()
        return

    cmd = args[0]
    if cmd == "list":
        list_skills(verbose="-v" in args)
    elif cmd == "info" and len(args) > 1:
        info_skill(args[1])
    elif cmd == "create" and len(args) > 1:
        create_skill(args[1])
    elif cmd == "remove" and len(args) > 1:
        remove_skill(args[1])
    elif cmd == "search" and len(args) > 1:
        search_skills(args[1])
    elif cmd == "verify":
        verify_skills()
    else:
        print(f"""
  {BOLD}{CYAN}Skill Store{RESET}

  {BOLD}Commands:{RESET}
    list [-v]           List installed skills (verbose with -v)
    info <skill>        Show skill details
    create <name>       Create new skill from template
    remove <name>       Remove a skill
    search <keyword>    Search skills by name or content
    verify              Verify all skills are valid
""")

if __name__ == "__main__":
    main()
