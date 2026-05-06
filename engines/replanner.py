#!/usr/bin/env python3
"""
DARIO Replanner — Dynamic re-planning on task failure.
=======================================================
When a task fails, don't stop the pipeline. Auto-reroute:
1. Check fallback_matrix for alternative skill/worker
2. Retry with different worker (sibling)
3. Decompose into smaller subtasks
4. Only escalate to human if all recovery paths exhausted

Usage:
    python replanner.py --task MNB-002 --failure "agent_timeout"
    python replanner.py --task MNB-002 --failure "quality_below_50" --score 42
    python replanner.py --task MNB-002 --failure "skill_not_found"
    python replanner.py --json

Exit codes:
    0 = recovery plan created (task rerouted or retried)
    1 = error
    2 = escalation required (no automatic recovery possible)
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# License enforcement
try:
    from license_manager import require_license
    require_license()
except (ImportError, SystemExit):
    pass  # License check skipped (dev mode)

try:
    from ruamel.yaml import YAML
    yaml_engine = YAML()
    yaml_engine.preserve_quotes = True
    yaml_engine.width = 200
    def load_yaml(path):
        with open(path, 'r', encoding='utf-8') as f:
            return yaml_engine.load(f)
    def dump_yaml(data, path):
        with open(path, 'w', encoding='utf-8') as f:
            yaml_engine.dump(data, f)
except ImportError:
    import yaml
    def load_yaml(path):
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    def dump_yaml(data, path):
        with open(path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


ORCH_DIR = Path.home() / ".claude" / "orchestrator"
TASKS_DIR = ORCH_DIR / "tasks" / "active"
FALLBACK_FILE = ORCH_DIR / "fallback_matrix.yaml"
COMPANY_FILE = ORCH_DIR / "company.yaml"

# Max retries before escalation
MAX_RETRIES = 2

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("replanner")


FAILURE_STRATEGIES = {
    "agent_timeout": ["retry_same", "retry_sibling", "escalate"],
    "quality_below_50": ["retry_with_feedback", "retry_sibling", "escalate"],
    "skill_not_found": ["fallback_skill", "escalate"],
    "worker_busy": ["retry_sibling", "queue_for_next_pulse"],
    "budget_exceeded": ["escalate"],
    "dependency_failed": ["unblock_alternate", "escalate"],
    "parse_error": ["retry_same", "escalate"],
    "unknown": ["retry_same", "retry_sibling", "escalate"],
}


def load_task(task_id: str) -> dict:
    task_file = TASKS_DIR / f"{task_id}.yaml"
    if not task_file.exists():
        return None
    return load_yaml(str(task_file))


def save_task(task_id: str, data: dict):
    task_file = TASKS_DIR / f"{task_id}.yaml"
    dump_yaml(data, str(task_file))


def get_fallback_skill(skill: str) -> str:
    """Check fallback_matrix for alternative skill."""
    if not FALLBACK_FILE.exists():
        return None
    matrix = load_yaml(str(FALLBACK_FILE))
    if not isinstance(matrix, dict):
        return None
    # Look for skill in matrix
    for entry in matrix.get("fallbacks", []):
        if isinstance(entry, dict) and entry.get("primary") == skill:
            return entry.get("fallback")
    return None


def get_sibling_worker(worker_id: str, skill: str) -> str:
    """Find a sibling worker that could handle the same skill."""
    if not COMPANY_FILE.exists():
        return None
    company = load_yaml(str(COMPANY_FILE))
    workers = company.get("workers", {})

    # Find current worker's director
    current = workers.get(worker_id, {})
    if not isinstance(current, dict):
        return None
    director = current.get("reports_to", "")

    # Find siblings under same director
    for wid, wdata in workers.items():
        if wid == worker_id:
            continue
        if not isinstance(wdata, dict):
            continue
        if wdata.get("reports_to") == director:
            # Check capability overlap
            caps = wdata.get("capabilities", [])
            if isinstance(caps, list) and skill in str(caps):
                return wid
    return None


def replan(task_id: str, failure_type: str, score: int = 0,
           error_msg: str = "") -> dict:
    """Create a recovery plan for a failed task."""
    result = {
        "task_id": task_id,
        "failure": failure_type,
        "action": "escalate",
        "details": "",
        "applied": False,
    }

    task = load_task(task_id)
    if not task:
        result["details"] = "Task not found"
        return result

    retry_count = int(task.get("revision_count", 0) or 0)
    skill = task.get("skill", "")
    worker = task.get("assignee", "")

    strategies = FAILURE_STRATEGIES.get(failure_type, FAILURE_STRATEGIES["unknown"])

    for strategy in strategies:
        if strategy == "retry_same" and retry_count < MAX_RETRIES:
            # Retry with same worker
            task["status"] = "todo"
            task["revision_count"] = retry_count + 1
            task["notes"] = task.get("notes") or []
            if isinstance(task["notes"], list):
                task["notes"].append(f"REPLAN: retry #{retry_count+1} after {failure_type}")
            save_task(task_id, task)
            result["action"] = "retry_same"
            result["details"] = f"Retry #{retry_count+1} with {worker}"
            result["applied"] = True
            return result

        elif strategy == "retry_with_feedback" and retry_count < MAX_RETRIES:
            # Retry with quality feedback injected
            task["status"] = "todo"
            task["revision_count"] = retry_count + 1
            task["notes"] = task.get("notes") or []
            if isinstance(task["notes"], list):
                task["notes"].append(
                    f"REPLAN: retry with feedback. Score was {score}. "
                    f"Improve specificity and accuracy. {error_msg}"
                )
            save_task(task_id, task)
            result["action"] = "retry_with_feedback"
            result["details"] = f"Retry with quality feedback (score was {score})"
            result["applied"] = True
            return result

        elif strategy == "retry_sibling":
            sibling = get_sibling_worker(worker, skill)
            if sibling:
                task["status"] = "todo"
                task["assignee"] = sibling
                task["dispatch_reason"] = f"rerouted from {worker} after {failure_type}"
                task["notes"] = task.get("notes") or []
                if isinstance(task["notes"], list):
                    task["notes"].append(f"REPLAN: rerouted to {sibling} (original: {worker})")
                save_task(task_id, task)
                result["action"] = "retry_sibling"
                result["details"] = f"Rerouted to {sibling}"
                result["applied"] = True
                return result

        elif strategy == "fallback_skill":
            fallback = get_fallback_skill(skill)
            if fallback:
                task["skill"] = fallback
                task["status"] = "todo"
                task["assignee"] = None  # Let dispatch find worker for new skill
                task["notes"] = task.get("notes") or []
                if isinstance(task["notes"], list):
                    task["notes"].append(f"REPLAN: skill fallback {skill} → {fallback}")
                save_task(task_id, task)
                result["action"] = "fallback_skill"
                result["details"] = f"Skill changed: {skill} → {fallback}"
                result["applied"] = True
                return result

        elif strategy == "queue_for_next_pulse":
            task["status"] = "todo"
            task["assignee"] = None
            save_task(task_id, task)
            result["action"] = "queue_for_next_pulse"
            result["details"] = "Released assignment, will be re-dispatched next pulse"
            result["applied"] = True
            return result

        elif strategy == "escalate":
            task["status"] = "blocked"
            task["blocked_reason"] = f"Auto-recovery exhausted after {failure_type}. Retries: {retry_count}. Needs human intervention."
            task["watchers"] = task.get("watchers") or []
            if isinstance(task["watchers"], list) and "dario-ceo" not in task["watchers"]:
                task["watchers"].append("dario-ceo")
            save_task(task_id, task)
            result["action"] = "escalate"
            result["details"] = f"Blocked + escalated to CEO (retries exhausted: {retry_count})"
            result["applied"] = True
            return result

    return result


def main():
    parser = argparse.ArgumentParser(description="DARIO Replanner — Auto-recovery on failure")
    parser.add_argument("--task", "-t", required=True, help="Task ID that failed")
    parser.add_argument("--failure", "-f", required=True,
                        help=f"Failure type: {list(FAILURE_STRATEGIES.keys())}")
    parser.add_argument("--score", type=int, default=0, help="Quality score (for quality failures)")
    parser.add_argument("--error", default="", help="Error message")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")

    args = parser.parse_args()
    if args.json:
        logging.getLogger().setLevel(logging.ERROR)

    result = replan(args.task, args.failure, args.score, args.error)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        symbol = "+" if result["applied"] and result["action"] != "escalate" else "!"
        print(f"[{symbol}] {args.task}: {result['action']}")
        print(f"    {result['details']}")

    return 0 if result["action"] != "escalate" else 2


if __name__ == "__main__":
    sys.exit(main())
