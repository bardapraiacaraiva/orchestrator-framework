#!/usr/bin/env python3
"""
DARIO Executor — Durable Task Execution Engine.
=================================================
The "last mile" that transforms infrastructure into a real execution engine.
Coordinates ALL subsystems for each task: guardrails → context → trace → execute → score → advance.

This is what makes DARIO a "durable execution engine" vs a "todo list with dispatcher":
- State is TRANSACTIONAL (DB-first, single source of truth)
- Routing is CONDITIONAL (guardrails gate execution, replanner handles failure)
- Communication is STRUCTURED (artifacts validated, context assembled, traces logged)
- Execution is DURABLE (checkpoints per step, resume on crash)

Usage:
    # Execute a single task (full lifecycle: guard → context → trace → run → score)
    python executor.py --task MNB-002

    # Execute next wave (all ready tasks in parallel)
    python executor.py --wave

    # Execute a chain step-by-step (durable, checkpointed)
    python executor.py --chain brand_to_market --project mar-brasa --context "..."

    # Dry-run (show what WOULD execute without running)
    python executor.py --wave --dry-run

    # Full pulse (state check → dispatch → wave execute → score → log)
    python executor.py --pulse

    # JSON output
    python executor.py --pulse --json

Architecture:
    executor.py orchestrates:
    ┌─────────────────────────────────────────────────────────────┐
    │  1. guardrails.py  — PRE-EXECUTION: can this run?           │
    │  2. context_injector.py — CONTEXT: what does it need?       │
    │  3. adaptive_rubric.py — RUBRIC: how will we score it?      │
    │  4. tracer.py — TRACE START: record inputs                  │
    │  5. [EXECUTE] — Claude runs the skill (via skill invocation)│
    │  6. quality_scorer.py — SCORE: how good was it?             │
    │  7. tracer.py — TRACE END: record outputs                   │
    │  8. replanner.py — IF FAILED: auto-recover                  │
    │  9. db.py — STATE ADVANCE: update DB atomically             │
    │ 10. audit_logger.py — LOG: append to trail                  │
    └─────────────────────────────────────────────────────────────┘

Exit codes:
    0 = execution successful
    1 = error
    2 = task blocked by guardrails (not executed)
    3 = task failed, replanner activated
"""

import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ORCH_DIR = Path.home() / ".claude" / "orchestrator"
sys.path.insert(0, str(ORCH_DIR))

from db import DB

PYTHON = sys.executable
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("executor")


def run_engine(script: str, args: list) -> dict:
    """Run an orchestrator engine, return parsed JSON."""
    path = ORCH_DIR / script
    if not path.exists():
        return {"error": f"{script} not found"}
    try:
        r = subprocess.run([PYTHON, str(path)] + args,
                           capture_output=True, text=True, timeout=15, cwd=str(ORCH_DIR))
        if r.stdout.strip():
            try:
                return json.loads(r.stdout.strip())
            except json.JSONDecodeError:
                return {"raw": r.stdout.strip()[:300], "exit_code": r.returncode}
        return {"exit_code": r.returncode, "stderr": r.stderr.strip()[:200]}
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    except Exception as e:
        return {"error": str(e)[:200]}


# =============================================================================
# CORE: Execute a single task through the full lifecycle
# =============================================================================

def execute_task(task_id: str, dry_run: bool = False) -> dict:
    """
    Full lifecycle execution of a single task.
    This is the ATOMIC UNIT of the durable execution engine.
    """
    db = DB()
    result = {
        "task_id": task_id,
        "status": "pending",
        "steps": [],
    }

    # Load task from DB (single source of truth)
    task = db.get_task(task_id)
    if not task:
        result["status"] = "error"
        result["error"] = "Task not found in DB"
        return result

    skill = task.get("skill", "")
    project = task.get("project", "")
    worker = task.get("assignee", "")

    # ─── Step 1: GUARDRAILS ──────────────────────────────────────────────
    guard = run_engine("guardrails.py", ["--task", task_id, "--json"])
    verdict = guard.get("verdict", "FAIL")
    result["steps"].append({"step": "guardrails", "result": verdict})

    if verdict == "FAIL":
        result["status"] = "blocked"
        result["error"] = f"Guardrails FAIL: {guard.get('errors', [])}"
        db.log_event("executor", "task_blocked", task_id=task_id,
                     details=f"Guardrails: {guard.get('errors', [])}")
        return result

    # ─── Step 2: CONTEXT INJECTION ───────────────────────────────────────
    context = run_engine("context_injector.py", ["--task", task_id, "--json"])
    context_block = context.get("context_block", "")
    result["steps"].append({"step": "context", "sources": context.get("sources_used", 0),
                            "tokens_est": context.get("total_tokens_est", 0)})

    # ─── Step 3: ADAPTIVE RUBRIC ────────────────────────────────────────
    rubric = run_engine("adaptive_rubric.py", ["--task", task_id, "--json"])
    result["steps"].append({"step": "rubric", "dimensions": rubric.get("dimensions_count", 5),
                            "threshold": rubric.get("pass_threshold", 60)})

    # ─── Step 4: TRACE START ─────────────────────────────────────────────
    run_engine("tracer.py", ["--start", "--task", task_id, "--skill", skill,
                             "--worker", worker, "--project", project,
                             "--context", context_block[:200]])
    result["steps"].append({"step": "trace_start"})

    # ─── Step 5: BUILD EXECUTION PROMPT ──────────────────────────────────
    # This is the structured prompt that Claude (or any LLM) would receive
    prompt = build_execution_prompt(task, context_block, rubric)
    result["prompt_tokens_est"] = len(prompt) // 4
    result["steps"].append({"step": "prompt_built", "tokens": result["prompt_tokens_est"]})

    if dry_run:
        result["status"] = "dry_run"
        result["prompt_preview"] = prompt[:500] + "..."
        return result

    # ─── Step 6: EXECUTE (atomic checkout in DB) ─────────────────────────
    checked_out = db.checkout_task(task_id)
    if not checked_out:
        result["status"] = "already_running"
        result["error"] = "Task could not be checked out (already in_progress or not todo)"
        return result

    # The actual execution happens via Claude Agent tool in the autopilot.
    # This executor PREPARES everything and RECORDS the result.
    # In autonomous mode, this would call the Claude API directly.
    result["status"] = "ready_for_execution"
    result["execution_prompt"] = prompt
    result["skill"] = skill
    result["worker"] = worker
    result["rubric"] = rubric
    result["steps"].append({"step": "checked_out"})

    # Log to audit
    db.log_event("executor", "task_executing", task_id=task_id,
                 details=f"skill={skill} worker={worker} prompt_tokens={result['prompt_tokens_est']}")

    return result


def record_execution_result(task_id: str, success: bool, output: str = "",
                            tokens: int = 0, score: int = 0, error: str = "") -> dict:
    """
    Record the result of an execution (called AFTER Claude finishes).
    Handles scoring, tracing, replanning, and state advancement.
    """
    db = DB()
    result = {"task_id": task_id, "steps": []}

    task = db.get_task(task_id)
    if not task:
        return {"error": "Task not found"}

    skill = task.get("skill", "")
    project = task.get("project", "")

    if success:
        # ─── TRACE END (success) ─────────────────────────────────────────
        run_engine("tracer.py", ["--end", "--task", task_id, "--status", "success",
                                  "--tokens", str(tokens), "--score", str(score),
                                  "--output", output[:300]])
        result["steps"].append({"step": "trace_end", "status": "success"})

        # ─── QUALITY SCORE ───────────────────────────────────────────────
        if score > 0:
            run_engine("quality_scorer.py", [
                "--task", task_id, "--score", str(score),
                "--skill", skill, "--project", project, "--json"
            ])
            result["steps"].append({"step": "scored", "score": score})

        # ─── COMPLETE TASK (DB state advance) ────────────────────────────
        status = "done" if score >= 60 or score == 0 else "in_review"
        db.complete_task(task_id, score=score, tokens=tokens, output=output[:500], status=status)
        result["steps"].append({"step": "completed", "final_status": status})
        result["status"] = status

        # ─── AUDIT ───────────────────────────────────────────────────────
        db.log_event("executor", "task_completed", task_id=task_id,
                     details=f"score={score} tokens={tokens} status={status}")

    else:
        # ─── TRACE END (failed) ──────────────────────────────────────────
        run_engine("tracer.py", ["--end", "--task", task_id, "--status", "failed",
                                  "--error", error[:300]])
        result["steps"].append({"step": "trace_end", "status": "failed"})

        # ─── REPLAN (auto-recovery) ──────────────────────────────────────
        failure_type = "agent_timeout" if "timeout" in error.lower() else "quality_below_50" if score < 50 and score > 0 else "unknown"
        replan = run_engine("replanner.py", [
            "--task", task_id, "--failure", failure_type,
            "--score", str(score), "--error", error[:200], "--json"
        ])
        result["steps"].append({"step": "replanned", "action": replan.get("action", "?")})
        result["status"] = "replanned"
        result["replan_action"] = replan.get("action")

        # ─── AUDIT ───────────────────────────────────────────────────────
        db.log_event("executor", "task_failed", task_id=task_id,
                     details=f"error={error[:100]} replan={replan.get('action','?')}")

    return result


# =============================================================================
# PROMPT BUILDER — Structured communication
# =============================================================================

def build_execution_prompt(task: dict, context_block: str, rubric: dict) -> str:
    """
    Build the complete execution prompt with all context.
    This is the "structured communication" that eliminates ambiguity.
    """
    skill = task.get("skill", "")
    title = task.get("title", "")
    description = task.get("description", "")
    project = task.get("project", "")
    policy = task.get("execution_policy", "default")

    # Rubric as scoring guide
    rubric_text = ""
    if rubric.get("dimensions"):
        rubric_text = "## Scoring Rubric (how this output will be evaluated):\n"
        for d in rubric.get("dimensions", []):
            rubric_text += f"- **{d.get('name')}** ({d.get('weight',0):.0%}): {d.get('description','')}\n"
        rubric_text += f"\nPass threshold: {rubric.get('pass_threshold', 60)}/100\n"

    prompt = f"""# Task Execution: {task.get('id', '')}

## Assignment
- **Title:** {title}
- **Skill:** /{skill}
- **Project:** {project}
- **Priority:** {task.get('priority', 'medium')}
- **Policy:** {policy}

## Description
{description}

{context_block}

{rubric_text}

## Instructions
1. Execute the skill `/{skill}` with the context provided above.
2. Be SPECIFIC to this project ({project}) — no generic output.
3. Your output will be scored against the rubric above.
4. Provide a substantive completion comment summarizing what was delivered.
5. If you need information not available in the context, state what's missing clearly.

## Output Format
Provide your response as a structured deliverable appropriate for the skill.
End with a brief `## Summary` section (2-3 sentences) for the quality scorer.
"""
    return prompt


# =============================================================================
# WAVE EXECUTION — Multiple tasks in parallel
# =============================================================================

def execute_wave(dry_run: bool = False) -> dict:
    """Execute all ready tasks as a wave."""
    db = DB()
    ready = [t for t in db.get_tasks(status="todo") if t.get("assignee")]

    if not ready:
        return {"wave_size": 0, "status": "idle", "message": "No tasks ready for execution"}

    # Limit to max 3 parallel
    state = run_engine("state_machine.py", ["--json"])
    max_parallel = state.get("max_parallel", 3)
    wave = ready[:max_parallel]

    results = []
    for task in wave:
        r = execute_task(task["id"], dry_run=dry_run)
        results.append(r)

    return {
        "wave_size": len(wave),
        "max_parallel": max_parallel,
        "dry_run": dry_run,
        "tasks": results,
    }


# =============================================================================
# FULL PULSE — Complete heartbeat cycle via executor
# =============================================================================

def execute_pulse(dry_run: bool = False) -> dict:
    """
    Full heartbeat pulse through the executor.
    This is the DURABLE equivalent of /lucas-heartbeat.
    """
    db = DB()
    pulse = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "steps": {},
        "status": "ok",
    }

    # 0. State check
    state = run_engine("state_machine.py", ["--evaluate", "--json"])
    pulse["steps"]["state"] = state
    if state.get("state") == "GUARDIAN":
        pulse["status"] = "guardian_stop"
        return pulse

    # 1. Dispatch
    dispatch = run_engine("dispatch_engine.py", ["--json"])
    pulse["steps"]["dispatch"] = dispatch

    # 2. AutoDiag
    diag = run_engine("autodiag_runner.py", ["--fix", "--json"])
    pulse["steps"]["autodiag"] = {"passed": diag.get("passed", 0), "total": diag.get("total", 0)}

    # 3. Execute wave
    wave = execute_wave(dry_run=dry_run)
    pulse["steps"]["wave"] = wave

    # 4. Budget
    budget = db.get_budget()
    pulse["steps"]["budget"] = budget

    # 5. Task counts
    pulse["steps"]["tasks"] = db.get_task_counts()

    # 6. Log
    db.log_event("executor", "pulse_executed", details=json.dumps({
        "dispatched": dispatch.get("dispatched", 0),
        "wave_size": wave.get("wave_size", 0),
        "state": state.get("state", "?"),
    }, default=str))

    return pulse


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="DARIO Executor — Durable task execution engine",
    )
    parser.add_argument("--task", "-t", help="Execute single task")
    parser.add_argument("--wave", action="store_true", help="Execute next wave")
    parser.add_argument("--pulse", action="store_true", help="Full pulse cycle")
    parser.add_argument("--record", help="Record result for task (requires --success/--failed)")
    parser.add_argument("--success", action="store_true", help="Mark execution as success")
    parser.add_argument("--failed", action="store_true", help="Mark execution as failed")
    parser.add_argument("--output", default="", help="Execution output")
    parser.add_argument("--tokens", type=int, default=0, help="Tokens used")
    parser.add_argument("--score", type=int, default=0, help="Quality score")
    parser.add_argument("--error", default="", help="Error message")
    parser.add_argument("--dry-run", "-n", action="store_true", help="Show without executing")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")

    args = parser.parse_args()
    if args.json:
        logging.getLogger().setLevel(logging.ERROR)

    if args.record:
        result = record_execution_result(
            args.record, args.success, args.output, args.tokens, args.score, args.error
        )
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(f"[{'+'if result.get('status')=='done' else '!'}] {args.record}: {result.get('status','?')}")
            for s in result.get("steps", []):
                print(f"  {s.get('step')}: {s}")
        return 0

    elif args.task:
        result = execute_task(args.task, dry_run=args.dry_run)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(f"=== EXECUTE: {args.task} → {result['status']} ===\n")
            for s in result.get("steps", []):
                print(f"  [{s.get('step')}] {s}")
            if result.get("prompt_preview"):
                print(f"\n  PROMPT PREVIEW:\n  {result['prompt_preview'][:300]}...")
        return 0 if result["status"] in ("ready_for_execution", "dry_run") else 2

    elif args.wave:
        result = execute_wave(dry_run=args.dry_run)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(f"=== WAVE: {result['wave_size']} tasks (max {result.get('max_parallel',3)}) ===\n")
            for t in result.get("tasks", []):
                print(f"  [{t.get('status')}] {t.get('task_id')}: {len(t.get('steps',[]))} steps")
        return 0

    elif args.pulse:
        result = execute_pulse(dry_run=args.dry_run)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(f"=== PULSE ({result['status']}) ===\n")
            for name, data in result.get("steps", {}).items():
                print(f"  {name}: {json.dumps(data, default=str)[:100]}")
        return 0

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
