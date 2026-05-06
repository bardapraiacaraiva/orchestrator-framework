#!/usr/bin/env python3
"""Export all tested skill outputs to individual Markdown files in Obsidian."""
from db import DB
from pathlib import Path

db = DB()
output_dir = Path.home() / "OneDrive" / "Documents" / "D.A.R.I.O" / "05 - Claude - IA" / "Outputs" / "DARIO-Skills-Tests"
output_dir.mkdir(parents=True, exist_ok=True)

with db._conn() as conn:
    rows = conn.execute("""
        SELECT id, title, skill, quality_score, actual_tokens, completion_comment
        FROM tasks
        WHERE quality_score > 0 AND completion_comment IS NOT NULL AND length(completion_comment) > 100
        ORDER BY skill, id
    """).fetchall()

    count = 0
    for r in rows:
        d = dict(r)
        safe_skill = d["skill"].replace("/", "-")
        filename = f'{d["id"]} - {safe_skill}.md'

        content = f"""---
task: {d["id"]}
title: "{d["title"]}"
skill: {d["skill"]}
score: {d["quality_score"]}/100
tokens: {d["actual_tokens"]}
date: 2026-05-05
project: vivenda-test
---

{d["completion_comment"]}
"""
        filepath = output_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        count += 1
        chars = len(d["completion_comment"])
        print(f"  {filename:<45} {chars:>6}ch  score:{d['quality_score']}")

print(f"\n{count} ficheiros exportados para:")
print(f"  {output_dir}")
