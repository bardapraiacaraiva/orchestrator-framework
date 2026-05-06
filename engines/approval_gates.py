#!/usr/bin/env python3
"""
DARIO Tool Approval Gates — Fine-grained execution control (OpenAI SDK-inspired).
===================================================================================
Skills can require explicit approval before execution. Supports webhook notifications,
configurable timeouts, and automatic escalation.

Approval levels:
    auto       — Execute immediately (default)
    notify     — Execute but notify reviewer
    approve    — Wait for approval before executing
    dual       — Requires 2 approvers

Usage:
    python approval_gates.py --check TASK-001 --json          # Check if task needs approval
    python approval_gates.py --request TASK-001               # Request approval
    python approval_gates.py --approve TASK-001 --by "barda"  # Approve a task
    python approval_gates.py --reject TASK-001 --by "barda" --reason "Budget too high"
    python approval_gates.py --list-pending                   # List pending approvals
    python approval_gates.py --config                         # Show approval config

Integration:
    Called by executor.py before checkout. If approval required,
    task enters PENDING_APPROVAL state and waits.
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
log = logging.getLogger("approval_gates")

from db import DB

# =============================================================================
# APPROVAL CONFIGURATION
# =============================================================================

# Skills that require approval before execution
SKILL_APPROVAL = {
    # Financial — always approve
    "dario-proposal": "approve",
    "dario-financial-model": "approve",
    "dario-pricing-calculator": "notify",

    # Legal — always approve
    "diva-contract": "approve",
    "dario-legal": "approve",

    # Client-facing — approve
    "dario-sales-letter": "approve",
    "dario-pitch": "approve",
    "dario-email-seq": "notify",

    # High-risk technical — notify
    "dario-pentest-checklist": "notify",
    "dario-wp-audit": "auto",  # Read-only, safe

    # Construction — approve budget-dependent
    "diva-budget": "approve",
    "diva-timeline": "notify",
}

# Execution policies that override skill-level config
POLICY_APPROVAL = {
    "critical": "approve",
    "financial": "approve",
    "client_facing": "notify",
    "default": "auto",
}

# Timeout before auto-action (seconds)
APPROVAL_TIMEOUT = {
    "approve": 3600,   # 1 hour
    "notify": 0,       # No wait
    "dual": 7200,      # 2 hours
}

# What happens on timeout
TIMEOUT_ACTION = {
    "approve": "escalate",   # Escalate to CEO
    "dual": "escalate",
}


def get_approval_level(task: dict) -> dict:
    """Determine what approval level a task needs."""
    skill = task.get("skill", "")
    policy = task.get("execution_policy", "default")
    priority = task.get("priority", "medium")

    # Check skill-specific config
    skill_level = SKILL_APPROVAL.get(skill, "auto")

    # Check policy override (higher wins)
    policy_level = POLICY_APPROVAL.get(policy, "auto")

    # Priority override: critical tasks always get at least notify
    if priority == "critical" and skill_level == "auto":
        skill_level = "notify"

    # Take the stricter level
    levels = {"auto": 0, "notify": 1, "approve": 2, "dual": 3}
    final = skill_level if levels.get(skill_level, 0) >= levels.get(policy_level, 0) else policy_level

    return {
        "level": final,
        "skill_config": skill_level,
        "policy_config": policy_level,
        "timeout_seconds": APPROVAL_TIMEOUT.get(final, 0),
        "needs_approval": final in ("approve", "dual"),
        "needs_notification": final in ("notify", "approve", "dual"),
    }


def request_approval(task_id: str, reason: str = "") -> dict:
    """Request approval for a task. Moves to pending_approval state."""
    db = DB()
    task = db.get_task(task_id)
    if not task:
        return {"error": f"Task {task_id} not found"}

    approval_info = get_approval_level(task)
    if not approval_info["needs_approval"]:
        return {"status": "auto_approved", "task_id": task_id, "level": approval_info["level"]}

    approval_record = {
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "level": approval_info["level"],
        "reason": reason or f"Skill '{task.get('skill', '')}' requires {approval_info['level']} approval",
        "timeout_seconds": approval_info["timeout_seconds"],
        "approvals": [],
        "status": "pending",
    }

    with db._conn() as conn:
        conn.execute(
            "UPDATE tasks SET status = ?, blocked_reason = ? WHERE id = ?",
            ("pending_approval", json.dumps(approval_record), task_id)
        )

    db.log_event("approval_gates", "approval_requested", task_id=task_id,
                details=f"Level: {approval_info['level']}, skill: {task.get('skill', '')}")

    log.info(f"[APPROVAL] Requested for {task_id} (level: {approval_info['level']})")

    return {
        "status": "pending_approval",
        "task_id": task_id,
        "approval": approval_record,
    }


def approve_task(task_id: str, approved_by: str, notes: str = "") -> dict:
    """Approve a pending task."""
    db = DB()
    task = db.get_task(task_id)
    if not task:
        return {"error": f"Task {task_id} not found"}

    if task.get("status") != "pending_approval":
        return {"error": f"Task {task_id} is not pending approval (status: {task.get('status')})"}

    # Load approval record
    record = {}
    try:
        record = json.loads(task.get("blocked_reason", "{}"))
    except json.JSONDecodeError:
        pass

    record["approvals"].append({
        "by": approved_by,
        "at": datetime.now(timezone.utc).isoformat(),
        "decision": "approved",
        "notes": notes,
    })

    # Check if enough approvals (dual needs 2)
    level = record.get("level", "approve")
    needed = 2 if level == "dual" else 1
    has = len(record["approvals"])

    if has >= needed:
        record["status"] = "approved"
        with db._conn() as conn:
            conn.execute(
                "UPDATE tasks SET status = ?, blocked_reason = ? WHERE id = ?",
                ("todo", json.dumps(record), task_id)  # Back to todo for execution
            )
        log.info(f"[APPROVED] {task_id} by {approved_by}")
    else:
        record["status"] = f"partial ({has}/{needed})"
        with db._conn() as conn:
            conn.execute(
                "UPDATE tasks SET blocked_reason = ? WHERE id = ?",
                (json.dumps(record), task_id)
            )
        log.info(f"[PARTIAL] {task_id}: {has}/{needed} approvals")

    db.log_event("approval_gates", "task_approved", task_id=task_id,
                details=f"By: {approved_by}. {has}/{needed} approvals.")

    return {
        "status": record["status"],
        "task_id": task_id,
        "approvals": has,
        "needed": needed,
        "approved_by": approved_by,
    }


def reject_task(task_id: str, rejected_by: str, reason: str = "") -> dict:
    """Reject a pending task."""
    db = DB()
    task = db.get_task(task_id)
    if not task:
        return {"error": f"Task {task_id} not found"}

    record = {}
    try:
        record = json.loads(task.get("blocked_reason", "{}"))
    except json.JSONDecodeError:
        pass

    record["status"] = "rejected"
    record["rejected_by"] = rejected_by
    record["rejected_at"] = datetime.now(timezone.utc).isoformat()
    record["rejection_reason"] = reason

    with db._conn() as conn:
        conn.execute(
            "UPDATE tasks SET status = ?, blocked_reason = ? WHERE id = ?",
            ("blocked", json.dumps(record), task_id)
        )

    db.log_event("approval_gates", "task_rejected", task_id=task_id,
                details=f"By: {rejected_by}. Reason: {reason}")

    log.info(f"[REJECTED] {task_id} by {rejected_by}: {reason}")
    return {"status": "rejected", "task_id": task_id, "by": rejected_by, "reason": reason}


def list_pending_approvals() -> list[dict]:
    """List all tasks pending approval."""
    db = DB()
    tasks = db.get_tasks(status="pending_approval")

    result = []
    for task in tasks:
        record = {}
        try:
            record = json.loads(task.get("blocked_reason", "{}"))
        except json.JSONDecodeError:
            pass

        result.append({
            "task_id": task["id"],
            "title": task.get("title", ""),
            "skill": task.get("skill", ""),
            "project": task.get("project", ""),
            "level": record.get("level", "?"),
            "reason": record.get("reason", ""),
            "requested_at": record.get("requested_at", ""),
            "approvals": len(record.get("approvals", [])),
        })

    return result


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="DARIO Approval Gates")
    parser.add_argument("--check", help="Check approval level for task")
    parser.add_argument("--request", help="Request approval for task")
    parser.add_argument("--approve", help="Approve a task")
    parser.add_argument("--reject", help="Reject a task")
    parser.add_argument("--by", default="system", help="Approver/rejector name")
    parser.add_argument("--reason", default="", help="Reason for rejection")
    parser.add_argument("--list-pending", action="store_true", help="List pending approvals")
    parser.add_argument("--config", action="store_true", help="Show approval config")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.config:
        config = {
            "skill_approvals": SKILL_APPROVAL,
            "policy_approvals": POLICY_APPROVAL,
            "timeouts": APPROVAL_TIMEOUT,
        }
        if args.json:
            print(json.dumps(config, indent=2))
        else:
            print("Skill approvals:")
            for skill, level in sorted(SKILL_APPROVAL.items()):
                print(f"  {skill:35s} → {level}")
            print(f"\nPolicy approvals:")
            for policy, level in sorted(POLICY_APPROVAL.items()):
                print(f"  {policy:20s} → {level}")
        return 0

    if args.list_pending:
        pending = list_pending_approvals()
        if args.json:
            print(json.dumps(pending, indent=2))
        else:
            if not pending:
                print("No pending approvals")
            else:
                for p in pending:
                    print(f"  [{p['task_id']}] {p['skill']} — {p['level']} — {p['reason'][:50]}")
        return 0

    if args.check:
        db = DB()
        task = db.get_task(args.check)
        if not task:
            print(f"Task {args.check} not found")
            return 1
        result = get_approval_level(task)
        print(json.dumps(result, indent=2))
        return 0

    if args.request:
        result = request_approval(args.request, args.reason)
        print(json.dumps(result, indent=2))
        return 0

    if args.approve:
        result = approve_task(args.approve, args.by, args.reason)
        print(json.dumps(result, indent=2))
        return 0

    if args.reject:
        result = reject_task(args.reject, args.by, args.reason)
        print(json.dumps(result, indent=2))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
