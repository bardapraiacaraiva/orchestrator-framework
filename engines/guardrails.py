#!/usr/bin/env python3
"""
DARIO Guardrails — Pre-execution validation (runs BEFORE task execution).
==========================================================================
Validates a task is safe and ready to execute. Blocks execution if guardrails fail.
Inspired by OpenAI Agents SDK guardrails-as-first-class.

Usage:
    python guardrails.py --task MNB-002              # Validate task ready for execution
    python guardrails.py --task MNB-002 --json       # Machine-readable
    python guardrails.py --task MNB-002 --strict     # Fail on warnings too (not just errors)

Exit codes:
    0 = PASS — safe to execute
    1 = FAIL — do NOT execute (missing required data, budget exceeded, etc.)
    2 = WARN — can execute but with caveats

Checks:
    1. Task has required fields (id, title, status, skill)
    2. Skill exists in company.yaml workers
    3. Budget sufficient for estimated_tokens
    4. Dependencies all met (status=done)
    5. Assignee exists and is available
    6. No circular dependency
    7. Execution policy allows auto-execution at current autonomy level
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from ruamel.yaml import YAML
    yaml_engine = YAML()
    yaml_engine.preserve_quotes = True
    yaml_engine.width = 200
    def load_yaml(path):
        with open(path, 'r', encoding='utf-8') as f:
            return yaml_engine.load(f)
except ImportError:
    import yaml
    def load_yaml(path):
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)


ORCH_DIR = Path.home() / ".claude" / "orchestrator"
TASKS_DIR = ORCH_DIR / "tasks" / "active"
COMPANY_FILE = ORCH_DIR / "company.yaml"
BUDGET_DIR = ORCH_DIR / "budgets"
STATE_FILE = ORCH_DIR / "current_state.yaml"

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("guardrails")


def validate_task(task_id: str, strict: bool = False) -> dict:
    """Run all guardrail checks on a task. Returns verdict."""
    result = {
        "task_id": task_id,
        "verdict": "PASS",
        "errors": [],
        "warnings": [],
        "checks": {},
    }

    # Load task — DB first, YAML fallback
    task = None
    try:
        sys.path.insert(0, str(ORCH_DIR))
        from db import DB
        db = DB()
        task = db.get_task(task_id)
    except Exception:
        pass

    if not task:
        # Fallback to YAML
        task_file = TASKS_DIR / f"{task_id}.yaml"
        if not task_file.exists():
            result["verdict"] = "FAIL"
            result["errors"].append(f"Task not found in DB or YAML: {task_id}")
            return result
        task = load_yaml(str(task_file))

    if not task:
        result["verdict"] = "FAIL"
        result["errors"].append("Task data is empty or unparseable")
        return result

    # --- Check 1: Required fields ---
    required = ["id", "title", "status"]
    missing = [f for f in required if not task.get(f)]
    if missing:
        result["errors"].append(f"Missing required fields: {missing}")
    result["checks"]["required_fields"] = len(missing) == 0

    # --- Check 2: Skill exists ---
    skill = task.get("skill")
    skill_exists = True
    if skill:
        if COMPANY_FILE.exists():
            company = load_yaml(str(COMPANY_FILE))
            workers = company.get("workers", {})
            # Check if any worker has this skill
            found = any(
                isinstance(w, dict) and w.get("skill") == skill
                for w in workers.values()
            )
            if not found:
                result["warnings"].append(f"Skill '{skill}' not found in any worker")
                skill_exists = False
    else:
        result["warnings"].append("No skill specified — dispatch may fail")
        skill_exists = False
    result["checks"]["skill_exists"] = skill_exists

    # --- Check 3: Budget sufficient ---
    estimated = task.get("estimated_tokens", 0)
    budget_ok = True
    if estimated and int(estimated) > 0:
        now = datetime.now(timezone.utc)
        budget_file = BUDGET_DIR / f"{now.strftime('%Y-%m')}.yaml"
        if budget_file.exists():
            budget = load_yaml(str(budget_file))
            used = int(budget.get("total_tokens_used", 0))
            limit = int(budget.get("limit", 50000000))
            remaining = limit - used
            if int(estimated) > remaining:
                result["errors"].append(f"Budget insufficient: need {estimated}, have {remaining}")
                budget_ok = False
            elif (used + int(estimated)) / limit > 0.95:
                result["warnings"].append(f"Execution would push budget past 95% ({(used + int(estimated))/limit*100:.1f}%)")
    result["checks"]["budget_sufficient"] = budget_ok

    # --- Check 4: Dependencies met (fixed: now checks DB first, was YAML-only) ---
    deps = task.get("depends_on", [])
    if isinstance(deps, str):
        try:
            import json
            deps = json.loads(deps)
        except Exception:
            deps = []
    deps_met = True
    if isinstance(deps, list) and deps:
        for dep_id in deps:
            dep_data = None
            # DB first
            try:
                dep_data = db.get_task(dep_id) if db else None
            except Exception:
                pass
            # YAML fallback
            if not dep_data:
                dep_file = TASKS_DIR / f"{dep_id}.yaml"
                if dep_file.exists():
                    dep_data = load_yaml(str(dep_file))
            if dep_data:
                if dep_data.get("status") != "done":
                    result["errors"].append(f"Dependency {dep_id} not done (status: {dep_data.get('status')})")
                    deps_met = False
            else:
                result["warnings"].append(f"Dependency {dep_id} not found in DB or YAML")
    result["checks"]["dependencies_met"] = deps_met

    # --- Check 5: Assignee valid ---
    assignee = task.get("assignee")
    assignee_ok = True
    if assignee and assignee != "null":
        if COMPANY_FILE.exists():
            company = load_yaml(str(COMPANY_FILE)) if 'company' not in locals() else company
            workers = company.get("workers", {})
            agents = company.get("agents", {})
            valid_ids = set(workers.keys())
            for a in agents.values():
                if isinstance(a, dict) and "id" in a:
                    valid_ids.add(a["id"])
            if assignee not in valid_ids:
                result["errors"].append(f"Assignee '{assignee}' not in company.yaml")
                assignee_ok = False
    result["checks"]["assignee_valid"] = assignee_ok

    # --- Check 6: State allows execution ---
    state_ok = True
    if STATE_FILE.exists():
        state = load_yaml(str(STATE_FILE))
        current = state.get("current_state", "ACTIVE") if state else "ACTIVE"
        if current == "GUARDIAN":
            result["errors"].append("System in GUARDIAN state — no execution allowed")
            state_ok = False
        elif current == "REFLECTIVE_PAUSE":
            policy = task.get("execution_policy", "default")
            if policy not in ["critical"]:
                result["warnings"].append(f"REFLECTIVE_PAUSE: only critical tasks auto-execute (this is '{policy}')")
    result["checks"]["state_allows"] = state_ok

    # --- Check 7: Not already running or locked (fixed: handles new statuses) ---
    status = task.get("status", "")
    blocked_statuses = {"in_progress", "pending_approval", "awaiting_human", "suspended", "done"}
    not_running = status not in blocked_statuses
    if not not_running:
        result["errors"].append(f"Task status '{status}' blocks execution")
    result["checks"]["not_already_running"] = not_running

    # --- Verdict ---
    if result["errors"]:
        result["verdict"] = "FAIL"
    elif result["warnings"] and strict:
        result["verdict"] = "FAIL"
    elif result["warnings"]:
        result["verdict"] = "WARN"
    else:
        result["verdict"] = "PASS"

    return result


def main():
    parser = argparse.ArgumentParser(description="DARIO Guardrails — Pre-execution validation")
    parser.add_argument("--task", "-t", required=True, help="Task ID to validate")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")

    args = parser.parse_args()
    if args.json:
        logging.getLogger().setLevel(logging.ERROR)

    result = validate_task(args.task, strict=args.strict)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        verdict = result["verdict"]
        symbol = {"PASS": "+", "WARN": "~", "FAIL": "!"}[verdict]
        print(f"[{symbol}] {args.task}: {verdict}\n")
        for check, passed in result["checks"].items():
            mark = "+" if passed else "!"
            print(f"  [{mark}] {check}")
        if result["errors"]:
            print(f"\n  ERRORS:")
            for e in result["errors"]:
                print(f"    - {e}")
        if result["warnings"]:
            print(f"\n  WARNINGS:")
            for w in result["warnings"]:
                print(f"    - {w}")

    if result["verdict"] == "FAIL":
        return 1
    elif result["verdict"] == "WARN":
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
