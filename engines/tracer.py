#!/usr/bin/env python3
"""
DARIO Tracer — Structured execution tracing per task.
======================================================
Records inputs, outputs, timing, errors for each task execution.
Enables "why did this fail?" debugging that was previously impossible.

Usage:
    # Start a trace (call before execution)
    python tracer.py --start --task MNB-002 --skill dario-naming --worker worker-naming

    # End a trace (call after execution)
    python tracer.py --end --task MNB-002 --status success --tokens 2100 --score 85 --output "3 name candidates..."

    # End with failure
    python tracer.py --end --task MNB-002 --status failed --error "Agent timeout after 120s"

    # View trace for a task
    python tracer.py --view MNB-002

    # List recent traces
    python tracer.py --list

    # JSON output
    python tracer.py --view MNB-002 --json

Traces stored in: ~/.claude/orchestrator/traces/{task_id}.yaml
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


TRACES_DIR = Path.home() / ".claude" / "orchestrator" / "traces"

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("tracer")


def start_trace(task_id: str, skill: str = "", worker: str = "",
                project: str = "", context: str = "") -> dict:
    """Record trace start."""
    TRACES_DIR.mkdir(parents=True, exist_ok=True)
    trace_file = TRACES_DIR / f"{task_id}.yaml"

    # Load existing trace (may have previous executions)
    trace = {"task_id": task_id, "executions": []}
    if trace_file.exists():
        existing = load_yaml(str(trace_file))
        if existing and isinstance(existing, dict):
            trace = existing

    # Add new execution entry
    execution = {
        "attempt": len(trace.get("executions", [])) + 1,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "ended_at": None,
        "duration_seconds": None,
        "skill": skill,
        "worker": worker,
        "project": project,
        "input_context": context[:500] if context else "",
        "status": "running",
        "output_summary": None,
        "tokens_used": None,
        "quality_score": None,
        "error": None,
    }
    trace.setdefault("executions", []).append(execution)
    trace["last_status"] = "running"
    trace["total_attempts"] = len(trace["executions"])

    dump_yaml(trace, str(trace_file))
    return execution


def end_trace(task_id: str, status: str = "success", tokens: int = 0,
              score: int = 0, output: str = "", error: str = "") -> dict:
    """Record trace end."""
    trace_file = TRACES_DIR / f"{task_id}.yaml"
    if not trace_file.exists():
        return {"error": f"No trace found for {task_id}"}

    trace = load_yaml(str(trace_file))
    if not trace or not trace.get("executions"):
        return {"error": "Trace has no executions"}

    # Update last execution
    last = trace["executions"][-1]
    last["ended_at"] = datetime.now(timezone.utc).isoformat()
    last["status"] = status

    # Calculate duration
    try:
        start = datetime.fromisoformat(last["started_at"])
        end = datetime.fromisoformat(last["ended_at"])
        last["duration_seconds"] = round((end - start).total_seconds(), 2)
    except (ValueError, TypeError):
        pass

    if status == "success":
        last["tokens_used"] = tokens
        last["quality_score"] = score
        last["output_summary"] = output[:500] if output else ""
    elif status == "failed":
        last["error"] = error[:500] if error else "Unknown error"

    trace["last_status"] = status
    dump_yaml(trace, str(trace_file))
    return last


def view_trace(task_id: str) -> dict:
    """View trace for a task."""
    trace_file = TRACES_DIR / f"{task_id}.yaml"
    if not trace_file.exists():
        return None
    return load_yaml(str(trace_file))


def list_traces(limit: int = 20) -> list:
    """List recent traces."""
    if not TRACES_DIR.exists():
        return []
    files = sorted(TRACES_DIR.glob("*.yaml"), key=lambda f: f.stat().st_mtime, reverse=True)
    traces = []
    for f in files[:limit]:
        data = load_yaml(str(f))
        if data:
            traces.append({
                "task_id": data.get("task_id"),
                "attempts": data.get("total_attempts", 0),
                "last_status": data.get("last_status"),
                "file": f.name,
            })
    return traces


def main():
    parser = argparse.ArgumentParser(description="DARIO Tracer — Execution tracing")
    parser.add_argument("--start", action="store_true", help="Start a trace")
    parser.add_argument("--end", action="store_true", help="End a trace")
    parser.add_argument("--task", "-t", help="Task ID")
    parser.add_argument("--skill", default="", help="Skill used")
    parser.add_argument("--worker", default="", help="Worker assigned")
    parser.add_argument("--project", default="", help="Project name")
    parser.add_argument("--context", default="", help="Input context")
    parser.add_argument("--status", default="success", help="End status (success/failed)")
    parser.add_argument("--tokens", type=int, default=0, help="Tokens used")
    parser.add_argument("--score", type=int, default=0, help="Quality score")
    parser.add_argument("--output", default="", help="Output summary")
    parser.add_argument("--error", default="", help="Error message (for failed)")
    parser.add_argument("--view", help="View trace for task ID")
    parser.add_argument("--list", action="store_true", help="List recent traces")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")

    args = parser.parse_args()
    if args.json:
        logging.getLogger().setLevel(logging.ERROR)

    if args.start and args.task:
        result = start_trace(args.task, args.skill, args.worker, args.project, args.context)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(f"Trace started: {args.task} (attempt #{result['attempt']})")
        return 0

    elif args.end and args.task:
        result = end_trace(args.task, args.status, args.tokens, args.score, args.output, args.error)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            duration = result.get("duration_seconds", "?")
            print(f"Trace ended: {args.task} — {args.status} ({duration}s)")
        return 0

    elif args.view:
        trace = view_trace(args.view)
        if not trace:
            print(f"No trace for {args.view}")
            return 1
        if args.json:
            print(json.dumps(trace, indent=2, default=str))
        else:
            print(f"=== TRACE: {args.view} ({trace.get('total_attempts', 0)} attempts) ===\n")
            for ex in trace.get("executions", []):
                status_mark = "+" if ex.get("status") == "success" else "!"
                print(f"  [{status_mark}] Attempt #{ex.get('attempt')}: {ex.get('status')}")
                print(f"      Skill: {ex.get('skill')} | Worker: {ex.get('worker')}")
                print(f"      Started: {ex.get('started_at')}")
                print(f"      Duration: {ex.get('duration_seconds', '?')}s | Tokens: {ex.get('tokens_used', '?')}")
                if ex.get("error"):
                    print(f"      ERROR: {ex['error']}")
                if ex.get("output_summary"):
                    print(f"      Output: {ex['output_summary'][:100]}...")
                print()
        return 0

    elif args.list:
        traces = list_traces()
        if args.json:
            print(json.dumps(traces, indent=2))
        else:
            print(f"=== RECENT TRACES ({len(traces)}) ===\n")
            for t in traces:
                mark = "+" if t["last_status"] == "success" else "!" if t["last_status"] == "failed" else "~"
                print(f"  [{mark}] {t['task_id']} — {t['last_status']} ({t['attempts']} attempts)")
        return 0

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
