#!/usr/bin/env python3
"""
DARIO Checkpoint Interrupt/Resume — Human-in-the-Loop (LangGraph-inspired).
=============================================================================
Tasks can be paused mid-execution awaiting human input. State is serialized
to SQLite. Resume via API with human's response injected.

States: todo → in_progress → AWAITING_HUMAN → in_progress → done

Use cases:
- Approval gates: "This proposal costs €50K. Approve?" → human approves → continue
- Review points: "Here's the brand positioning draft" → human gives feedback → revise
- Decision forks: "3 naming options. Which one?" → human picks → proceed

Usage:
    python checkpoint_interrupt.py --interrupt TASK-001 --reason "Approval needed" --data '{"options": [1,2,3]}'
    python checkpoint_interrupt.py --resume TASK-001 --input '{"choice": 2, "feedback": "option 2 but change color"}'
    python checkpoint_interrupt.py --list-pending
    python checkpoint_interrupt.py --status TASK-001

API Integration (runtime.py):
    POST /tasks/{id}/interrupt — Pause task, serialize state
    POST /tasks/{id}/resume   — Resume with human input
    GET  /tasks/awaiting      — List tasks awaiting human input
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
log = logging.getLogger("checkpoint")

from db import DB

# License enforcement
try:
    from license_manager import require_license
    require_license()
except (ImportError, SystemExit):
    pass  # License check skipped (dev mode)


def interrupt_task(task_id: str, reason: str = "", checkpoint_data: dict = None,
                   pending_input_schema: dict = None, timeout_seconds: int = 0) -> dict:
    """
    Interrupt a running task and save checkpoint.
    Task moves to AWAITING_HUMAN status.
    """
    db = DB()
    task = db.get_task(task_id)

    if not task:
        return {"error": f"Task {task_id} not found"}

    status = task.get("status", "")
    if status not in ("in_progress", "todo"):
        return {"error": f"Task {task_id} is '{status}', can only interrupt in_progress/todo tasks"}

    # Build checkpoint
    checkpoint = {
        "task_id": task_id,
        "interrupted_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "previous_status": status,
        "checkpoint_data": checkpoint_data or {},
        "pending_input_schema": pending_input_schema or {},
        "timeout_seconds": timeout_seconds,
        "skill": task.get("skill", ""),
        "project": task.get("project", ""),
        "step_index": checkpoint_data.get("step_index", 0) if checkpoint_data else 0,
        "partial_output": checkpoint_data.get("partial_output", "") if checkpoint_data else "",
    }

    # Save checkpoint to DB
    # Using the tasks table blocked_reason field for the checkpoint JSON
    with db._conn() as conn:
        conn.execute(
            "UPDATE tasks SET status = ?, blocked_reason = ? WHERE id = ?",
            ("awaiting_human", json.dumps(checkpoint), task_id)
        )

    # Log to audit
    db.log_event("checkpoint", "task_interrupted", task_id=task_id,
                details=f"Reason: {reason}. Awaiting human input.")

    log.info(f"[INTERRUPT] {task_id}: {reason}")

    return {
        "status": "awaiting_human",
        "task_id": task_id,
        "reason": reason,
        "checkpoint": checkpoint,
    }


def resume_task(task_id: str, human_input: dict = None) -> dict:
    """
    Resume an interrupted task with human input.
    Task moves back to in_progress.
    """
    db = DB()
    task = db.get_task(task_id)

    if not task:
        return {"error": f"Task {task_id} not found"}

    status = task.get("status", "")
    if status != "awaiting_human":
        return {"error": f"Task {task_id} is '{status}', can only resume awaiting_human tasks"}

    # Load checkpoint
    checkpoint_json = task.get("blocked_reason", "{}")
    try:
        checkpoint = json.loads(checkpoint_json)
    except json.JSONDecodeError:
        checkpoint = {}

    # Merge human input into checkpoint
    checkpoint["human_input"] = human_input or {}
    checkpoint["resumed_at"] = datetime.now(timezone.utc).isoformat()

    # Move back to in_progress
    with db._conn() as conn:
        conn.execute(
            "UPDATE tasks SET status = ?, blocked_reason = ? WHERE id = ?",
            ("in_progress", json.dumps(checkpoint), task_id)
        )

    # Log to audit
    db.log_event("checkpoint", "task_resumed", task_id=task_id,
                details=f"Human input received. Keys: {list((human_input or {}).keys())}")

    log.info(f"[RESUME] {task_id}: human input received ({len(human_input or {})} fields)")

    return {
        "status": "in_progress",
        "task_id": task_id,
        "checkpoint": checkpoint,
        "human_input": human_input,
        "resume_context": {
            "skill": checkpoint.get("skill", ""),
            "project": checkpoint.get("project", ""),
            "step_index": checkpoint.get("step_index", 0),
            "partial_output": checkpoint.get("partial_output", ""),
        },
    }


def list_awaiting_human() -> list[dict]:
    """List all tasks awaiting human input."""
    db = DB()

    with db._conn() as conn:
        rows = conn.execute(
            "SELECT id, title, skill, project, blocked_reason, updated_at FROM tasks WHERE status = 'awaiting_human' ORDER BY updated_at DESC"
        ).fetchall()

    result = []
    for row in rows:
        checkpoint = {}
        try:
            checkpoint = json.loads(row[4]) if row[4] else {}
        except json.JSONDecodeError:
            pass

        result.append({
            "task_id": row[0],
            "title": row[1],
            "skill": row[2],
            "project": row[3],
            "reason": checkpoint.get("reason", ""),
            "interrupted_at": checkpoint.get("interrupted_at", ""),
            "pending_schema": checkpoint.get("pending_input_schema", {}),
        })

    return result


def get_checkpoint(task_id: str) -> dict:
    """Get the checkpoint data for an interrupted task."""
    db = DB()
    task = db.get_task(task_id)

    if not task:
        return {"error": f"Task {task_id} not found"}

    status = task.get("status", "")
    checkpoint_json = task.get("blocked_reason", "{}")

    try:
        checkpoint = json.loads(checkpoint_json)
    except json.JSONDecodeError:
        checkpoint = {}

    return {
        "task_id": task_id,
        "status": status,
        "is_interrupted": status == "awaiting_human",
        "checkpoint": checkpoint,
    }


# =============================================================================
# INTERRUPT CONDITIONS — define when tasks should auto-interrupt
# =============================================================================

# Skills that ALWAYS require human approval before delivery
APPROVAL_REQUIRED_SKILLS = {
    "dario-proposal",      # Financial commitment
    "dario-contract",      # Legal document
    "dario-sales-letter",  # Client-facing copy
    "diva-contract",       # Construction contract
    "diva-budget",         # Budget > €50K
}

# Execution policies that require approval
APPROVAL_REQUIRED_POLICIES = {
    "critical",
    "client_facing",
    "financial",
}


def should_interrupt(task: dict, output: str = "", score: int = 0) -> dict:
    """
    Check if a task should be auto-interrupted for human review.
    Returns {"interrupt": True/False, "reason": "...", "schema": {...}}
    """
    skill = task.get("skill", "")
    policy = task.get("execution_policy", "default")

    # Rule 1: Skill requires approval
    if skill in APPROVAL_REQUIRED_SKILLS:
        return {
            "interrupt": True,
            "reason": f"Skill '{skill}' requires human approval before delivery",
            "schema": {"approval": "approve|reject", "feedback": "string (optional)"},
        }

    # Rule 2: Policy requires approval
    if policy in APPROVAL_REQUIRED_POLICIES:
        return {
            "interrupt": True,
            "reason": f"Policy '{policy}' requires human review",
            "schema": {"approval": "approve|reject|revise", "notes": "string (optional)"},
        }

    # Rule 3: Low quality score
    if 0 < score < 60:
        return {
            "interrupt": True,
            "reason": f"Quality score {score} below 60 — needs human review",
            "schema": {"action": "approve|reject|retry", "feedback": "string"},
        }

    return {"interrupt": False}


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="DARIO Checkpoint Interrupt/Resume")
    parser.add_argument("--interrupt", help="Task ID to interrupt")
    parser.add_argument("--resume", help="Task ID to resume")
    parser.add_argument("--reason", default="", help="Interrupt reason")
    parser.add_argument("--data", default="{}", help="Checkpoint data (JSON)")
    parser.add_argument("--input", default="{}", help="Human input for resume (JSON)")
    parser.add_argument("--schema", default="{}", help="Pending input schema (JSON)")
    parser.add_argument("--list-pending", action="store_true", help="List tasks awaiting human")
    parser.add_argument("--status", help="Get checkpoint status for task")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.list_pending:
        pending = list_awaiting_human()
        if args.json:
            print(json.dumps(pending, indent=2))
        else:
            if not pending:
                print("No tasks awaiting human input")
            else:
                print(f"{len(pending)} tasks awaiting human input:")
                for p in pending:
                    print(f"  [{p['task_id']}] {p['title']} — {p['reason']}")
        return 0

    if args.status:
        result = get_checkpoint(args.status)
        print(json.dumps(result, indent=2))
        return 0

    if args.interrupt:
        data = json.loads(args.data)
        schema = json.loads(args.schema)
        result = interrupt_task(args.interrupt, reason=args.reason,
                               checkpoint_data=data, pending_input_schema=schema)
        print(json.dumps(result, indent=2))
        return 0 if "error" not in result else 1

    if args.resume:
        human_input = json.loads(args.input)
        result = resume_task(args.resume, human_input=human_input)
        print(json.dumps(result, indent=2))
        return 0 if "error" not in result else 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
