#!/usr/bin/env python3
"""
DARIO Budget Tracker — Automated Token Accounting
Reads completed tasks, calculates token usage, updates monthly budget file.
Called by lucas-heartbeat and lucas-autopilot after each pulse.

Usage:
  python budget_tracker.py                    # Update current month
  python budget_tracker.py --report           # Print budget report
  python budget_tracker.py --check            # Check thresholds only
  python budget_tracker.py --add-tokens 5000 --project mar-brasa --skill dario-brand
"""

import os
import sys
import argparse
import logging
import yaml
import glob
from datetime import datetime, timezone
from pathlib import Path

# === LOGGING ===
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s"
)
log = logging.getLogger("budget_tracker")

# === PATHS ===
ORCH_DIR = Path.home() / ".claude" / "orchestrator"
BUDGET_DIR = ORCH_DIR / "budgets"
TASKS_ACTIVE = ORCH_DIR / "tasks" / "active"
TASKS_DONE = ORCH_DIR / "tasks" / "done"
COMPANY_YAML = ORCH_DIR / "company.yaml"

def get_current_month():
    return datetime.now().strftime("%Y-%m")

def get_budget_path(month=None):
    month = month or get_current_month()
    return BUDGET_DIR / f"{month}.yaml"

def load_company_config():
    """Load company budget limits from company.yaml."""
    if not COMPANY_YAML.exists():
        return {"monthly_limit_tokens": 50_000_000}
    with open(COMPANY_YAML, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("company", {}).get("budget", {"monthly_limit_tokens": 50_000_000})

def load_budget(month=None):
    """Load or initialize the monthly budget file."""
    path = get_budget_path(month)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    # Initialize new budget
    company = load_company_config()
    return {
        "month": month or get_current_month(),
        "company": "BARDA Digital Agency",
        "limit": company.get("monthly_limit_tokens", 50_000_000),
        "total_tokens_used": 0,
        "percentage": 0.0,
        "by_project": {},
        "by_skill": {},
        "by_model": {"opus": 0, "sonnet": 0, "haiku": 0},
        "alert_80_sent": False,
        "alert_95_sent": False,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "pulse_count": 0,
    }

def save_budget(budget, month=None):
    """Write budget to YAML file."""
    BUDGET_DIR.mkdir(parents=True, exist_ok=True)
    path = get_budget_path(month)
    budget["last_updated"] = datetime.now(timezone.utc).isoformat()
    budget["percentage"] = round(
        (budget["total_tokens_used"] / budget["limit"]) * 100, 2
    ) if budget["limit"] > 0 else 0

    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# Budget Tracking — {budget['month']}\n")
        f.write("# LUCAS Cost Control — Agent Orchestrator\n")
        f.write("# Schema v2 — Token Capture Contract compliant\n\n")
        yaml.dump(budget, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

def scan_tasks_for_tokens():
    """Scan all active+done tasks and sum actual_tokens."""
    totals = {"total": 0, "by_project": {}, "by_skill": {}}

    for task_dir in [TASKS_ACTIVE, TASKS_DONE]:
        if not task_dir.exists():
            continue
        for task_file in task_dir.glob("*.yaml"):
            try:
                with open(task_file, "r", encoding="utf-8") as f:
                    task = yaml.safe_load(f)
                if not task:
                    continue
                tokens = task.get("actual_tokens") or 0
                if tokens > 0:
                    project = task.get("project", "unallocated")
                    skill = task.get("skill", "unknown")
                    totals["total"] += tokens
                    totals["by_project"][project] = totals["by_project"].get(project, 0) + tokens
                    totals["by_skill"][skill] = totals["by_skill"].get(skill, 0) + tokens
            except (yaml.YAMLError, IOError, TypeError) as e:
                print(f"Warning: skipping {task_file.name} — {e}", file=sys.stderr)
                continue
    return totals

def add_tokens(budget, tokens, project=None, skill=None, model="opus"):
    """Add tokens to budget from a single execution."""
    budget["total_tokens_used"] += tokens

    if project:
        budget["by_project"][project] = budget["by_project"].get(project, 0) + tokens
    else:
        budget["by_project"]["unallocated"] = budget["by_project"].get("unallocated", 0) + tokens

    if skill:
        budget["by_skill"][skill] = budget["by_skill"].get(skill, 0) + tokens

    if "by_model" not in budget:
        budget["by_model"] = {"opus": 0, "sonnet": 0, "haiku": 0}
    budget["by_model"][model] = budget["by_model"].get(model, 0) + tokens

    budget["pulse_count"] = budget.get("pulse_count", 0) + 1
    return budget

def check_thresholds(budget):
    """Check budget thresholds and return alerts."""
    alerts = []
    pct = budget.get("percentage", 0)

    if pct >= 95 and not budget.get("alert_95_sent"):
        alerts.append({
            "level": "CRITICAL",
            "message": f"Budget CRITICAL: {pct}% used. EXECUTION STOPPED.",
            "action": "stop_all"
        })
        budget["alert_95_sent"] = True
    elif pct >= 80 and not budget.get("alert_80_sent"):
        alerts.append({
            "level": "WARNING",
            "message": f"Budget WARNING: {pct}% used. Limiting to 1 parallel worker.",
            "action": "limit_parallel"
        })
        budget["alert_80_sent"] = True

    return alerts

def estimate_tokens(output_length):
    """Estimate tokens from output character count (fallback when metadata unavailable)."""
    if output_length < 500:
        return 2000
    elif output_length < 3000:
        return 5000
    else:
        return 10000

def print_report(budget):
    """Print a formatted budget report."""
    print(f"\n{'='*50}")
    print(f"  BUDGET REPORT — {budget.get('month', 'N/A')}")
    print(f"{'='*50}")
    print(f"  Total used:  {budget['total_tokens_used']:>12,} tokens")
    print(f"  Limit:       {budget['limit']:>12,} tokens")
    print(f"  Percentage:  {budget.get('percentage', 0):>11.2f}%")
    print(f"  Pulses:      {budget.get('pulse_count', 0):>12}")
    print(f"  Last update: {budget.get('last_updated', 'N/A')}")

    alerts = check_thresholds(budget)
    if alerts:
        print(f"\n  ALERTS:")
        for a in alerts:
            print(f"    [{a['level']}] {a['message']}")
    else:
        print(f"\n  Status: OK")

    if budget.get("by_project"):
        print(f"\n  BY PROJECT:")
        for proj, tokens in sorted(budget["by_project"].items(), key=lambda x: -x[1]):
            print(f"    {proj:<25} {tokens:>10,}")

    if budget.get("by_skill"):
        print(f"\n  BY SKILL (top 10):")
        sorted_skills = sorted(budget["by_skill"].items(), key=lambda x: -x[1])[:10]
        for skill, tokens in sorted_skills:
            print(f"    {skill:<25} {tokens:>10,}")

    if budget.get("by_model"):
        print(f"\n  BY MODEL:")
        for model, tokens in budget["by_model"].items():
            print(f"    {model:<25} {tokens:>10,}")

    print(f"{'='*50}\n")

def build_parser():
    parser = argparse.ArgumentParser(
        description="DARIO Budget Tracker — Automated Token Accounting",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                          # Scan tasks + update budget
  %(prog)s --report                                 # Print budget report
  %(prog)s --check                                  # Check thresholds (exit 1 if critical)
  %(prog)s --add-tokens 5000 --project mar-brasa    # Add tokens manually
  %(prog)s --add-tokens 8000 --skill dario-brand --model opus
        """
    )
    parser.add_argument("--report", action="store_true", help="Print formatted budget report")
    parser.add_argument("--check", action="store_true", help="Check thresholds only (exit 1 if critical)")
    parser.add_argument("--add-tokens", type=int, metavar="N", help="Add N tokens to budget")
    parser.add_argument("--project", type=str, help="Project to attribute tokens to")
    parser.add_argument("--skill", type=str, help="Skill to attribute tokens to")
    parser.add_argument("--model", type=str, default="opus", choices=["opus", "sonnet", "haiku"], help="Model used (default: opus)")
    parser.add_argument("--month", type=str, help="Budget month (default: current, format: YYYY-MM)")
    parser.add_argument("--quiet", action="store_true", help="Suppress non-error output")
    return parser

def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.quiet:
        logging.getLogger("budget_tracker").setLevel(logging.WARNING)

    if args.report:
        budget = load_budget(args.month)
        print_report(budget)
        return

    if args.check:
        budget = load_budget(args.month)
        alerts = check_thresholds(budget)
        if alerts:
            for a in alerts:
                log.warning(f"[{a['level']}] {a['message']}")
            sys.exit(1 if any(a["action"] == "stop_all" for a in alerts) else 0)
        else:
            log.info(f"OK — {budget.get('percentage', 0):.2f}% used")
        return

    if args.add_tokens is not None:
        budget = load_budget(args.month)
        budget = add_tokens(budget, args.add_tokens, args.project, args.skill, args.model)
        save_budget(budget, args.month)

        alerts = check_thresholds(budget)
        save_budget(budget, args.month)

        log.info(f"Added {args.add_tokens:,} tokens. Total: {budget['total_tokens_used']:,} ({budget['percentage']:.2f}%)")
        for a in alerts:
            log.warning(f"[{a['level']}] {a['message']}")
        return

    # Default: full scan + update
    budget = load_budget(args.month)
    task_totals = scan_tasks_for_tokens()

    if task_totals["total"] > 0:
        budget["total_tokens_used"] = max(budget["total_tokens_used"], task_totals["total"])
        for proj, tokens in task_totals["by_project"].items():
            budget["by_project"][proj] = max(budget["by_project"].get(proj, 0), tokens)
        for skill_name, tokens in task_totals["by_skill"].items():
            budget["by_skill"][skill_name] = max(budget["by_skill"].get(skill_name, 0), tokens)

    save_budget(budget, args.month)
    alerts = check_thresholds(budget)
    save_budget(budget, args.month)

    log.info(f"Budget updated: {budget['total_tokens_used']:,} / {budget['limit']:,} ({budget['percentage']:.2f}%)")
    for a in alerts:
        log.warning(f"[{a['level']}] {a['message']}")

if __name__ == "__main__":
    main()
