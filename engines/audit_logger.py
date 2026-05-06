#!/usr/bin/env python3
"""
DARIO Audit Logger — Unified, append-only audit trail.
=======================================================
Single entry point for ALL orchestrator events. Writes structured YAML
entries to daily log files. Immutable once written.

Usage:
    # Log an event
    python audit_logger.py --actor worker-brand --action task_completed --entity task --id MNB-001 --details "Brand delivered, score 92"

    # Log from another engine (shorthand)
    python audit_logger.py -a dario-dispatch -A task_assigned -e task -i MNB-002 -d "→ worker-naming"

    # Show today's log
    python audit_logger.py --today

    # Show last N entries
    python audit_logger.py --tail 20

    # Consolidate per-engine logs into unified trail
    python audit_logger.py --consolidate

    # JSON output
    python audit_logger.py --today --json

Principles:
    - Append-only (never edit/delete entries)
    - Structured (actor, action, entity, details, timestamp)
    - Daily files (easy to archive/grep)
    - Called by all engines after mutations
"""

import argparse
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

    def dump_yaml_list(data, path):
        yaml_engine_list = YAML()
        yaml_engine_list.default_flow_style = False
        yaml_engine_list.width = 200
        with open(path, 'w', encoding='utf-8') as f:
            yaml_engine_list.dump(data, f)
except ImportError:
    import yaml
    def load_yaml(path):
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    def dump_yaml_list(data, path):
        with open(path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


AUDIT_DIR = Path.home() / ".claude" / "orchestrator" / "audit"

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("audit")

# Valid actions for structured queries
VALID_ACTIONS = [
    "task_created", "task_assigned", "task_checkout", "task_completed",
    "task_scored", "task_revision", "task_blocked", "task_escalated",
    "dispatch_batch", "state_transition", "autodiag_pass", "autodiag_warn",
    "autodiag_fix", "evolution_cycle", "weight_mutation", "budget_update",
    "session_start", "session_end", "pulse_executed", "error",
]


# =============================================================================
# CORE: Log Entry
# =============================================================================

def get_today_file() -> Path:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return AUDIT_DIR / f"{today}.yaml"


def log_event(actor: str, action: str, entity_type: str = "",
              entity_id: str = "", details: str = "") -> dict:
    """Append a structured event to today's audit log."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor": actor,
        "action": action,
    }
    if entity_type:
        entry["entity_type"] = entity_type
    if entity_id:
        entry["entity_id"] = entity_id
    if details:
        entry["details"] = details

    # Append to daily file
    log_file = get_today_file()

    # Read existing entries
    entries = []
    if log_file.exists():
        try:
            data = load_yaml(str(log_file))
            if isinstance(data, list):
                entries = data
        except Exception:
            pass

    entries.append(entry)
    dump_yaml_list(entries, str(log_file))

    return entry


# =============================================================================
# CONSOLIDATE: Merge per-engine logs
# =============================================================================

def consolidate():
    """Merge today's per-engine logs into the unified trail."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    merged = 0

    # 1. Dispatch log
    dispatch_log = AUDIT_DIR / f"dispatch_{today}.log"
    if dispatch_log.exists():
        for line in dispatch_log.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip():
                continue
            # Parse: [timestamp] TASK_ID → WORKER | reasons
            parts = line.split("]", 1)
            if len(parts) == 2:
                ts = parts[0].strip("[")
                rest = parts[1].strip()
                task_worker = rest.split("|")[0].strip()
                reasons = rest.split("|")[1].strip() if "|" in rest else ""
                log_event("dario-dispatch", "task_assigned", "task", task_worker.split("→")[0].strip(),
                          f"{task_worker} | {reasons}")
                merged += 1

    # 2. State log
    state_log = AUDIT_DIR / f"state_{today}.log"
    if state_log.exists():
        for line in state_log.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip():
                continue
            if "STATE_TRANSITION" in line:
                log_event("state-machine", "state_transition", "system", "operational_state", line.split("|")[-1].strip())
                merged += 1

    # 3. AutoDiag log
    autodiag_log = AUDIT_DIR / "autodiag.log"
    if autodiag_log.exists():
        for line in autodiag_log.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip() or line.startswith("  "):
                continue
            if today in line:
                if "AUTODIAG_OK" in line:
                    log_event("autodiag", "autodiag_pass", "system", "health", "All checks passed")
                elif "AUTODIAG_WARN" in line:
                    log_event("autodiag", "autodiag_warn", "system", "health", line.split("]")[-1].strip())
                merged += 1

    return merged


# =============================================================================
# DISPLAY
# =============================================================================

def show_today(as_json: bool):
    """Show today's unified log."""
    log_file = get_today_file()
    if not log_file.exists():
        print("No entries for today." if not as_json else "[]")
        return

    data = load_yaml(str(log_file))
    if not isinstance(data, list):
        data = []

    if as_json:
        import json
        print(json.dumps(data, indent=2, default=str))
    else:
        print(f"=== AUDIT TRAIL — {datetime.now(timezone.utc).strftime('%Y-%m-%d')} ({len(data)} entries) ===\n")
        for entry in data:
            ts = entry.get("timestamp", "?")
            # Short timestamp
            if "T" in str(ts):
                ts = str(ts).split("T")[1][:8]
            actor = entry.get("actor", "?")
            action = entry.get("action", "?")
            entity = entry.get("entity_id", "")
            details = entry.get("details", "")
            line = f"  [{ts}] {actor}: {action}"
            if entity:
                line += f" ({entity})"
            if details:
                line += f" — {details[:80]}"
            print(line)


def show_tail(n: int, as_json: bool):
    """Show last N entries across all daily files."""
    all_entries = []
    if AUDIT_DIR.exists():
        for f in sorted(AUDIT_DIR.glob("*.yaml"), reverse=True):
            if f.name.startswith("2026"):  # Only daily audit files
                try:
                    data = load_yaml(str(f))
                    if isinstance(data, list):
                        all_entries.extend(data)
                        if len(all_entries) >= n:
                            break
                except Exception:
                    pass

    entries = all_entries[-n:]

    if as_json:
        import json
        print(json.dumps(entries, indent=2, default=str))
    else:
        print(f"=== LAST {len(entries)} AUDIT ENTRIES ===\n")
        for entry in entries:
            ts = str(entry.get("timestamp", "?"))
            if "T" in ts:
                ts = ts[5:16].replace("T", " ")
            actor = entry.get("actor", "?")
            action = entry.get("action", "?")
            entity = entry.get("entity_id", "")
            details = entry.get("details", "")
            line = f"  [{ts}] {actor}: {action}"
            if entity:
                line += f" ({entity})"
            if details:
                line += f" — {details[:80]}"
            print(line)


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="DARIO Audit Logger — Unified event trail")
    parser.add_argument("--actor", "-a", help="Who performed the action")
    parser.add_argument("--action", "-A", help="What was done")
    parser.add_argument("--entity", "-e", help="Entity type (task, system, project)")
    parser.add_argument("--id", "-i", help="Entity ID")
    parser.add_argument("--details", "-d", help="Free-text details")
    parser.add_argument("--today", action="store_true", help="Show today's log")
    parser.add_argument("--tail", type=int, help="Show last N entries")
    parser.add_argument("--consolidate", action="store_true", help="Merge per-engine logs into unified trail")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")

    args = parser.parse_args()

    if args.json:
        logging.getLogger().setLevel(logging.ERROR)

    if args.today:
        show_today(args.json)
        return 0
    elif args.tail:
        show_tail(args.tail, args.json)
        return 0
    elif args.consolidate:
        merged = consolidate()
        if args.json:
            import json
            print(json.dumps({"consolidated": merged}))
        else:
            print(f"Consolidated {merged} entries into unified trail.")
        return 0
    elif args.actor and args.action:
        entry = log_event(
            actor=args.actor,
            action=args.action,
            entity_type=args.entity or "",
            entity_id=args.id or "",
            details=args.details or "",
        )
        if args.json:
            import json
            print(json.dumps(entry, indent=2))
        else:
            print(f"Logged: {entry['actor']}: {entry['action']}")
        return 0
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
