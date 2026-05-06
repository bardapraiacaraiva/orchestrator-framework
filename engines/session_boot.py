#!/usr/bin/env python3
"""
DARIO Session Boot — Automatic dispatch + state check at session start.
Called by SessionStart hook. Lightweight, fast, no blocking.

Does:
1. Evaluate state machine (detect if system should be in GUARDIAN/REFLECTIVE)
2. Run dispatch on unassigned tasks
3. Output brief status for session context injection

Outputs JSON to stdout (picked up by hook system).
"""
import subprocess
import sys
import json
from datetime import datetime, timezone
from pathlib import Path

ORCH_DIR = Path.home() / ".claude" / "orchestrator"
PYTHON = sys.executable  # Use same Python that's running this script


def run_engine(script: str, args: list) -> dict:
    """Run an orchestrator engine and return parsed JSON output."""
    script_path = ORCH_DIR / script
    if not script_path.exists():
        return {"error": f"{script} not found"}

    try:
        result = subprocess.run(
            [PYTHON, str(script_path)] + args,
            capture_output=True, text=True, timeout=10
        )
        if result.stdout.strip():
            return json.loads(result.stdout.strip())
        return {"exit_code": result.returncode, "stderr": result.stderr.strip()[:200]}
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    except json.JSONDecodeError:
        return {"error": "invalid_json", "raw": result.stdout[:200]}
    except Exception as e:
        return {"error": str(e)[:200]}


def main():
    output = {"boot": "ok", "state": None, "dispatch": None, "autodiag": None, "wal_recovered": 0}

    # 0. WAL crash recovery (before anything else)
    try:
        from filelock import wal_recover
        recovered = wal_recover()
        output["wal_recovered"] = recovered
    except Exception:
        pass

    # 0.5. Resume suspended tasks from previous session (new: was not wired)
    resume_result = run_engine("suspend_resume.py", ["--restart-all", "--json"])
    output["resumed_tasks"] = resume_result.get("resumed", 0)

    # 1. State machine evaluation
    state_result = run_engine("state_machine.py", ["--evaluate", "--json"])
    output["state"] = state_result

    # 2. AutoDiag (silent, with auto-fix)
    diag_result = run_engine("autodiag_runner.py", ["--fix", "--json"])
    output["autodiag"] = {
        "passed": diag_result.get("passed", 0),
        "total": diag_result.get("total", 0),
        "warnings": diag_result.get("warnings", 0),
        "criticals": diag_result.get("criticals", 0),
    }

    # 3. Dispatch unassigned tasks (skip if GUARDIAN)
    current_state = state_result.get("state", "ACTIVE")
    if current_state != "GUARDIAN":
        dispatch_result = run_engine("dispatch_engine.py", ["--json"])
        output["dispatch"] = dispatch_result
    else:
        output["dispatch"] = {"skipped": "GUARDIAN state — no dispatch allowed"}

    # 4. Brief summary for context
    state_name = state_result.get("state", "?")
    autonomy = state_result.get("autonomy_level", "?")
    health = state_result.get("system_health", 0)
    dispatched = output["dispatch"].get("dispatched", 0) if isinstance(output["dispatch"], dict) else 0
    diag_ok = diag_result.get("passed", 0) == diag_result.get("total", 0)

    summary = f"State: {state_name} | Autonomy: {autonomy} | Health: {health:.2f}"
    diag_label = "OK" if diag_ok else f"{diag_result.get('warnings',0)}W/{diag_result.get('criticals',0)}C"
    summary += f" | Diag: {diag_label}"
    if dispatched > 0:
        summary += f" | Auto-dispatched: {dispatched} tasks"

    output["summary"] = summary

    # 5. Log boot event to unified audit trail
    run_engine("audit_logger.py", [
        "-a", "session-boot", "-A", "session_start",
        "-e", "system", "-i", f"boot-{datetime.now(timezone.utc).strftime('%H%M')}",
        "-d", summary
    ])

    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
