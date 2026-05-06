#!/usr/bin/env python3
"""
DARIO Suspend/Resume — Tasks survive server restart (Mastra-inspired).
=======================================================================
Serializes full execution state to SQLite after each step. On restart,
restartAllActiveTasks() resumes from last checkpoint.

States: in_progress → SUSPENDED (on shutdown) → in_progress (on restart)

Usage:
    python suspend_resume.py --suspend-all          # Suspend all in_progress tasks
    python suspend_resume.py --restart-all          # Resume all suspended tasks
    python suspend_resume.py --suspend TASK-001     # Suspend specific task
    python suspend_resume.py --resume TASK-001      # Resume specific task
    python suspend_resume.py --list-suspended       # Show suspended tasks
    python suspend_resume.py --checkpoint TASK-001 --data '{"step": 3, "output": "..."}'

Integration:
    - session_boot.py calls --restart-all on startup
    - runtime.py shutdown hook calls --suspend-all
    - executor.py calls --checkpoint after each step
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
log = logging.getLogger("suspend_resume")

from db import DB

# License enforcement
try:
    from license_manager import require_license
    require_license()
except (ImportError, SystemExit):
    pass  # License check skipped (dev mode)


def save_checkpoint(task_id: str, checkpoint_data: dict) -> dict:
    """Save execution checkpoint for a task."""
    db = DB()
    task = db.get_task(task_id)
    if not task:
        return {"error": f"Task {task_id} not found"}

    checkpoint = {
        "task_id": task_id,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "step_index": checkpoint_data.get("step_index", 0),
        "partial_output": checkpoint_data.get("partial_output", ""),
        "accumulated_tokens": checkpoint_data.get("tokens", 0),
        "context_snapshot": checkpoint_data.get("context", ""),
        "model_used": checkpoint_data.get("model", ""),
        "filter_state": checkpoint_data.get("filter_state", {}),
        "chain_id": checkpoint_data.get("chain_id", ""),
    }

    # Store in blocked_reason field (dual-purpose: checkpoint storage)
    with db._conn() as conn:
        conn.execute(
            "UPDATE tasks SET blocked_reason = ? WHERE id = ?",
            (json.dumps(checkpoint), task_id)
        )

    return {"success": True, "task_id": task_id, "checkpoint": checkpoint}


def suspend_task(task_id: str) -> dict:
    """Suspend an in_progress task, preserving state."""
    db = DB()
    task = db.get_task(task_id)
    if not task:
        return {"error": f"Task {task_id} not found"}

    status = task.get("status", "")
    if status != "in_progress":
        return {"error": f"Task {task_id} is '{status}', can only suspend in_progress"}

    with db._conn() as conn:
        # Read existing checkpoint data
        existing = task.get("blocked_reason", "")
        checkpoint = {}
        try:
            checkpoint = json.loads(existing) if existing else {}
        except json.JSONDecodeError:
            pass

        checkpoint["suspended_at"] = datetime.now(timezone.utc).isoformat()
        checkpoint["previous_status"] = "in_progress"

        conn.execute(
            "UPDATE tasks SET status = ?, blocked_reason = ? WHERE id = ?",
            ("suspended", json.dumps(checkpoint), task_id)
        )

    db.log_event("suspend_resume", "task_suspended", task_id=task_id)
    log.info(f"[SUSPEND] {task_id}")
    return {"success": True, "task_id": task_id, "status": "suspended"}


def resume_task(task_id: str) -> dict:
    """Resume a suspended task from its last checkpoint."""
    db = DB()
    task = db.get_task(task_id)
    if not task:
        return {"error": f"Task {task_id} not found"}

    status = task.get("status", "")
    if status != "suspended":
        return {"error": f"Task {task_id} is '{status}', can only resume suspended"}

    # Load checkpoint
    checkpoint = {}
    try:
        checkpoint = json.loads(task.get("blocked_reason", "{}"))
    except json.JSONDecodeError:
        pass

    checkpoint["resumed_at"] = datetime.now(timezone.utc).isoformat()

    with db._conn() as conn:
        conn.execute(
            "UPDATE tasks SET status = ?, blocked_reason = ? WHERE id = ?",
            ("todo", json.dumps(checkpoint), task_id)  # Back to todo for re-dispatch
        )

    db.log_event("suspend_resume", "task_resumed", task_id=task_id,
                details=f"Resumed from step {checkpoint.get('step_index', 0)}")
    log.info(f"[RESUME] {task_id} from step {checkpoint.get('step_index', 0)}")

    return {
        "success": True,
        "task_id": task_id,
        "status": "todo",
        "resume_from_step": checkpoint.get("step_index", 0),
        "checkpoint": checkpoint,
    }


def suspend_all() -> dict:
    """Suspend all in_progress tasks (called on shutdown)."""
    db = DB()
    tasks = db.get_tasks(status="in_progress")
    suspended = []

    for task in tasks:
        result = suspend_task(task["id"])
        if result.get("success"):
            suspended.append(task["id"])

    log.info(f"[SUSPEND ALL] {len(suspended)} tasks suspended")
    return {"suspended": len(suspended), "task_ids": suspended}


def restart_all() -> dict:
    """Resume all suspended tasks (called on startup)."""
    db = DB()
    tasks = db.get_tasks(status="suspended")
    resumed = []

    for task in tasks:
        result = resume_task(task["id"])
        if result.get("success"):
            resumed.append(task["id"])

    log.info(f"[RESTART ALL] {len(resumed)} tasks resumed")
    return {"resumed": len(resumed), "task_ids": resumed}


def list_suspended() -> list[dict]:
    """List all suspended tasks."""
    db = DB()
    tasks = db.get_tasks(status="suspended")

    result = []
    for task in tasks:
        checkpoint = {}
        try:
            checkpoint = json.loads(task.get("blocked_reason", "{}"))
        except json.JSONDecodeError:
            pass

        result.append({
            "task_id": task["id"],
            "title": task.get("title", ""),
            "skill": task.get("skill", ""),
            "project": task.get("project", ""),
            "suspended_at": checkpoint.get("suspended_at", ""),
            "step_index": checkpoint.get("step_index", 0),
            "model_used": checkpoint.get("model_used", ""),
        })

    return result


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="DARIO Suspend/Resume — Survive restarts")
    parser.add_argument("--suspend", help="Suspend a specific task")
    parser.add_argument("--resume", help="Resume a specific task")
    parser.add_argument("--suspend-all", action="store_true", help="Suspend all in_progress tasks")
    parser.add_argument("--restart-all", action="store_true", help="Resume all suspended tasks")
    parser.add_argument("--list-suspended", action="store_true", help="List suspended tasks")
    parser.add_argument("--checkpoint", help="Save checkpoint for task")
    parser.add_argument("--data", default="{}", help="Checkpoint data (JSON)")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.suspend_all:
        result = suspend_all()
        print(json.dumps(result, indent=2) if args.json else f"Suspended {result['suspended']} tasks")
        return 0

    if args.restart_all:
        result = restart_all()
        print(json.dumps(result, indent=2) if args.json else f"Resumed {result['resumed']} tasks")
        return 0

    if args.suspend:
        result = suspend_task(args.suspend)
        print(json.dumps(result, indent=2))
        return 0 if result.get("success") else 1

    if args.resume:
        result = resume_task(args.resume)
        print(json.dumps(result, indent=2))
        return 0 if result.get("success") else 1

    if args.list_suspended:
        suspended = list_suspended()
        if args.json:
            print(json.dumps(suspended, indent=2))
        else:
            if not suspended:
                print("No suspended tasks")
            else:
                for t in suspended:
                    print(f"  [{t['task_id']}] {t['skill']} (step {t['step_index']}) — suspended {t['suspended_at'][:19]}")
        return 0

    if args.checkpoint:
        data = json.loads(args.data)
        result = save_checkpoint(args.checkpoint, data)
        print(json.dumps(result, indent=2))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
