#!/usr/bin/env python3
"""
DARIO Token Meter — Real token usage capture.
===============================================
Called by PostToolUse hook to capture actual token usage from Agent calls.
Also provides CLI for manual token recording and reporting.

Usage:
    # Record tokens (called by hook or manually)
    python token_meter.py --input 1500 --output 800 --model opus --skill dario-brand --project mar-brasa

    # Show current month usage
    python token_meter.py --report

    # Show usage by skill
    python token_meter.py --by-skill

    # Show usage by model
    python token_meter.py --by-model

    # JSON output
    python token_meter.py --report --json
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ORCH_DIR = Path.home() / ".claude" / "orchestrator"
sys.path.insert(0, str(ORCH_DIR))

from db import DB

# License enforcement
try:
    from license_manager import require_license
    require_license()
except (ImportError, SystemExit):
    pass  # License check skipped (dev mode)

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("meter")

# Cost per million tokens (2026 pricing)
MODEL_COSTS = {
    "opus":   {"input": 15.00, "output": 75.00},
    "sonnet": {"input": 3.00,  "output": 15.00},
    "haiku":  {"input": 0.80,  "output": 4.00},
}


def record_usage(input_tokens: int, output_tokens: int, model: str = "sonnet",
                 skill: str = "", project: str = "", task_id: str = "") -> dict:
    """Record token usage to DB."""
    db = DB()
    total = input_tokens + output_tokens
    costs = MODEL_COSTS.get(model, MODEL_COSTS["sonnet"])
    cost = (input_tokens / 1_000_000 * costs["input"] +
            output_tokens / 1_000_000 * costs["output"])

    # Update budget via DB
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    with db._conn() as conn:
        conn.execute("""
            INSERT INTO budget (month, tokens_used) VALUES (?, ?)
            ON CONFLICT(month) DO UPDATE SET
                tokens_used = tokens_used + ?,
                updated_at = ?
        """, (month, total, total, datetime.now(timezone.utc).isoformat()))

    # Record in audit with full breakdown
    db.log_event("token-meter", "usage_recorded",
                 task_id=task_id,
                 details=f"in={input_tokens} out={output_tokens} model={model} skill={skill} cost=${cost:.4f}")

    return {
        "recorded": True,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total": total,
        "model": model,
        "cost": round(cost, 6),
        "skill": skill,
        "project": project,
    }


def get_report() -> dict:
    """Generate usage report for current month."""
    db = DB()
    budget = db.get_budget()

    # Get breakdown from audit
    entries = db.get_audit(limit=1000, actor="token-meter")
    by_model = {}
    by_skill = {}
    total_cost = 0.0

    for e in entries:
        details = e.get("details", "")
        # Parse "in=X out=Y model=Z skill=W cost=$C"
        parts = {}
        for part in details.split():
            if "=" in part:
                k, v = part.split("=", 1)
                parts[k] = v

        model = parts.get("model", "?")
        skill = parts.get("skill", "?")
        cost_str = parts.get("cost", "$0").replace("$", "")

        try:
            cost = float(cost_str)
        except ValueError:
            cost = 0

        by_model[model] = by_model.get(model, 0) + cost
        if skill and skill != "?":
            by_skill[skill] = by_skill.get(skill, 0) + cost
        total_cost += cost

    return {
        "month": budget.get("month"),
        "total_tokens": budget.get("tokens_used", 0),
        "token_limit": budget.get("token_limit", 50_000_000),
        "percentage": budget.get("percentage", 0),
        "total_cost": round(total_cost, 4),
        "by_model": {k: round(v, 4) for k, v in sorted(by_model.items())},
        "by_skill": {k: round(v, 4) for k, v in sorted(by_skill.items(), key=lambda x: -x[1])[:10]},
        "entries_count": len(entries),
    }


def main():
    parser = argparse.ArgumentParser(description="DARIO Token Meter")
    parser.add_argument("--input", type=int, default=0, help="Input tokens")
    parser.add_argument("--output", type=int, default=0, help="Output tokens")
    parser.add_argument("--model", default="sonnet", help="Model used")
    parser.add_argument("--skill", default="", help="Skill")
    parser.add_argument("--project", default="", help="Project")
    parser.add_argument("--task-id", default="", help="Task ID")
    parser.add_argument("--report", action="store_true", help="Usage report")
    parser.add_argument("--by-skill", action="store_true", help="Usage by skill")
    parser.add_argument("--by-model", action="store_true", help="Usage by model")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")

    args = parser.parse_args()
    if args.json:
        logging.getLogger().setLevel(logging.ERROR)

    if args.report or args.by_skill or args.by_model:
        report = get_report()
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(f"=== TOKEN USAGE — {report['month']} ===\n")
            print(f"  Tokens: {report['total_tokens']:,} / {report['token_limit']:,} ({report['percentage']:.2f}%)")
            print(f"  Cost:   ${report['total_cost']:.4f}")
            if report["by_model"]:
                print(f"\n  By Model:")
                for m, c in report["by_model"].items():
                    print(f"    {m:10s} ${c:.4f}")
            if report["by_skill"]:
                print(f"\n  By Skill (top 10):")
                for s, c in report["by_skill"].items():
                    print(f"    {s:30s} ${c:.4f}")
        return 0

    elif args.input > 0 or args.output > 0:
        result = record_usage(args.input, args.output, args.model,
                              args.skill, args.project, args.task_id)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Recorded: {result['total']:,} tokens ({result['model']}) = ${result['cost']:.4f}")
        return 0

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
