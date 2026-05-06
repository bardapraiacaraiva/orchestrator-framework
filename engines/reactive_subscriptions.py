#!/usr/bin/env python3
"""
DARIO Reactive Subscriptions — Pub/sub task auto-creation (MetaGPT-inspired).
==============================================================================
Workers declare `watches` — skill outputs they react to. When a task completes,
subscribers are checked and downstream tasks auto-created.

This enables EMERGENT WORKFLOWS: instead of manually chaining skills,
workers declare what they react to and the system creates the workflow.

Example in company.yaml:
    worker-moodboard:
      skill: diva-moodboard
      watches: ["dario-brand"]     # Auto-creates moodboard when brand completes
      watch_condition: "score >= 70"  # Only if brand scored well

    worker-bubble:
      skill: bubble-diagram
      watches: ["briefing-complete"]  # Auto-creates bubble when briefing done

Usage:
    python reactive_subscriptions.py --event task_completed --task MNB-001 --json
    python reactive_subscriptions.py --list-watchers
    python reactive_subscriptions.py --list-watchers --skill dario-brand

Integration:
    Called by executor.py after task completion to auto-create downstream tasks.
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ORCH_DIR = Path.home() / ".claude" / "orchestrator"
sys.path.insert(0, str(ORCH_DIR))

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("reactive_subs")

try:
    from ruamel.yaml import YAML
    yaml_engine = YAML()
    yaml_engine.preserve_quotes = True
    def load_yaml(path):
        with open(path, 'r', encoding='utf-8') as f:
            return yaml_engine.load(f)
except ImportError:
    import yaml
    def load_yaml(path):
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

COMPANY_FILE = ORCH_DIR / "company.yaml"


def load_watchers() -> dict:
    """Load all workers that have watches defined. Returns {skill: [watchers]}."""
    if not COMPANY_FILE.exists():
        return {}

    company = load_yaml(str(COMPANY_FILE))
    workers = company.get("workers", {})

    # Build reverse index: skill_output → [watchers]
    watchers = {}
    for worker_id, worker in workers.items():
        if not isinstance(worker, dict):
            continue
        watches = worker.get("watches", [])
        if not watches:
            continue
        for watched_skill in watches:
            if watched_skill not in watchers:
                watchers[watched_skill] = []
            watchers[watched_skill].append({
                "worker_id": worker_id,
                "skill": worker.get("skill", ""),
                "condition": worker.get("watch_condition", ""),
                "reports_to": worker.get("reports_to", ""),
            })

    return watchers


def check_condition(condition: str, ctx: dict) -> bool:
    """Evaluate a watch condition against execution context."""
    if not condition:
        return True  # No condition = always trigger

    try:
        # Simple expression evaluator for conditions like "score >= 70"
        # ctx provides: score, tokens, status, skill, project
        score = ctx.get("score", 0)
        tokens = ctx.get("tokens", 0)
        status = ctx.get("status", "done")

        # Safe eval of simple comparisons
        condition = condition.strip()
        if ">=" in condition:
            field, val = condition.split(">=")
            return float(ctx.get(field.strip(), 0)) >= float(val.strip())
        elif "<=" in condition:
            field, val = condition.split("<=")
            return float(ctx.get(field.strip(), 0)) <= float(val.strip())
        elif ">" in condition:
            field, val = condition.split(">")
            return float(ctx.get(field.strip(), 0)) > float(val.strip())
        elif "<" in condition:
            field, val = condition.split("<")
            return float(ctx.get(field.strip(), 0)) < float(val.strip())
        elif "==" in condition:
            field, val = condition.split("==")
            return str(ctx.get(field.strip(), "")) == val.strip().strip("'\"")

        return True
    except Exception as e:
        log.warning(f"Failed to evaluate condition '{condition}': {e}")
        return True  # On error, default to trigger


def on_task_completed(task: dict, score: int = 0, tokens: int = 0) -> list[dict]:
    """
    React to a completed task. Check watchers and create downstream tasks.
    Returns list of created tasks.
    """
    from db import DB
    db = DB()

    skill = task.get("skill", "")
    project = task.get("project", "")
    task_id = task.get("id", "")

    if not skill:
        return []

    watchers = load_watchers()
    subscribers = watchers.get(skill, [])

    if not subscribers:
        return []

    log.info(f"[REACTIVE] {skill} completed → {len(subscribers)} watchers")

    ctx = {
        "score": score,
        "tokens": tokens,
        "status": "done",
        "skill": skill,
        "project": project,
    }

    created = []
    for sub in subscribers:
        # Check condition
        if not check_condition(sub.get("condition", ""), ctx):
            log.info(f"  [SKIP] {sub['worker_id']}: condition not met ({sub.get('condition', '')})")
            continue

        # Check if similar task already exists for this project
        existing = db.get_tasks(project=project, skill=sub["skill"], status="todo")
        if existing:
            log.info(f"  [SKIP] {sub['worker_id']}: task already exists for {project}/{sub['skill']}")
            continue

        # Create downstream task
        new_id = f"{project[:3].upper()}-AUTO-{len(created)+1}" if project else f"AUTO-{task_id}-{len(created)+1}"
        new_task = {
            "id": new_id,
            "title": f"Auto: {sub['skill']} (triggered by {skill})",
            "description": f"Auto-created by reactive subscription. Triggered by completion of {task_id} ({skill}).",
            "project": project,
            "skill": sub["skill"],
            "priority": task.get("priority", "medium"),
            "status": "todo",
            "assignee": sub["worker_id"],
            "depends_on": json.dumps([task_id]),
            "execution_policy": task.get("execution_policy", "default"),
            "estimated_tokens": 0,
        }

        try:
            db.create_task(new_task)
            created.append(new_task)
            log.info(f"  [CREATED] {new_id}: {sub['skill']} assigned to {sub['worker_id']}")

            # Log to audit
            db.log_event("reactive_subs", "task_auto_created", task_id=new_id,
                        details=f"Triggered by {task_id} ({skill}). Watcher: {sub['worker_id']}")
        except Exception as e:
            log.error(f"  [ERROR] Failed to create task for {sub['worker_id']}: {e}")

    return created


def list_all_watchers() -> dict:
    """List all reactive subscriptions."""
    watchers = load_watchers()
    summary = {}
    for skill, subs in watchers.items():
        summary[skill] = [
            {"worker": s["worker_id"], "produces": s["skill"], "condition": s.get("condition", "")}
            for s in subs
        ]
    return summary


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="DARIO Reactive Subscriptions")
    parser.add_argument("--event", choices=["task_completed"], help="Event type")
    parser.add_argument("--task", help="Task ID that triggered the event")
    parser.add_argument("--score", type=int, default=0, help="Task score")
    parser.add_argument("--tokens", type=int, default=0, help="Tokens used")
    parser.add_argument("--list-watchers", action="store_true", help="List all watchers")
    parser.add_argument("--skill", help="Filter watchers by skill")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.list_watchers:
        watchers = list_all_watchers()
        if args.skill:
            watchers = {k: v for k, v in watchers.items() if k == args.skill}
        if args.json:
            print(json.dumps(watchers, indent=2))
        else:
            if not watchers:
                print("No watchers defined. Add 'watches: [skill]' to workers in company.yaml")
            for skill, subs in watchers.items():
                print(f"\n  {skill} →")
                for s in subs:
                    cond = f" (if {s['condition']})" if s["condition"] else ""
                    print(f"    → {s['worker']} produces {s['produces']}{cond}")
        return 0

    if args.event == "task_completed" and args.task:
        try:
            from db import DB
            task = DB().get_task(args.task)
            if not task:
                print(f"Task {args.task} not found")
                return 1
            created = on_task_completed(task, score=args.score, tokens=args.tokens)
            if args.json:
                print(json.dumps({"created": len(created), "tasks": [t["id"] for t in created]}, indent=2))
            else:
                print(f"Created {len(created)} downstream tasks")
                for t in created:
                    print(f"  → {t['id']}: {t['skill']}")
        except Exception as e:
            print(f"Error: {e}")
            return 1
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
