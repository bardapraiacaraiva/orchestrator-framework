#!/usr/bin/env python3
"""
DARIO State Machine — Operational State Management
===================================================
Tracks and enforces system state (ACTIVE/REFLECTIVE_PAUSE/GUARDIAN/EXPANSION).
Evaluates transition triggers based on real metrics. Calculates autonomy level.

Usage:
    python state_machine.py                  # Show current state + autonomy level
    python state_machine.py --evaluate       # Evaluate triggers, transition if needed
    python state_machine.py --transition X   # Force transition to state X
    python state_machine.py --json           # Machine-readable output
    python state_machine.py --history        # Show transition history

Exit codes:
    0 = no transition needed / transition successful
    1 = error (missing files)
    2 = transition occurred (state changed)
    3 = GUARDIAN activated (critical alert)
"""

import argparse
import logging
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# --- YAML handling ---
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


# --- Configuration ---
ORCH_DIR = Path.home() / ".claude" / "orchestrator"
STATE_FILE = ORCH_DIR / "current_state.yaml"
TASKS_DIR = ORCH_DIR / "tasks" / "active"
BUDGET_DIR = ORCH_DIR / "budgets"
QUALITY_FILE = ORCH_DIR / "quality" / "skill-metrics.yaml"
AUDIT_DIR = ORCH_DIR / "audit"

VALID_STATES = ["ACTIVE", "REFLECTIVE_PAUSE", "GUARDIAN", "EXPANSION"]

# State constraints
STATE_CONFIG = {
    "ACTIVE": {
        "max_parallel": 3,
        "allowed_actions": ["dispatch", "execute", "score", "auto_approve"],
    },
    "REFLECTIVE_PAUSE": {
        "max_parallel": 1,
        "allowed_actions": ["dispatch", "score", "audit"],
    },
    "GUARDIAN": {
        "max_parallel": 0,
        "allowed_actions": ["audit", "report"],
    },
    "EXPANSION": {
        "max_parallel": 1,
        "allowed_actions": ["audit", "score", "learn", "optimize"],
    },
}

# Autonomy ladder thresholds
AUTONOMY_LEVELS = {
    "P-A1": {"name": "Supervised", "max_parallel": 1},
    "P-A2": {"name": "Guided", "max_parallel": 2},
    "P-A3": {"name": "Autonomous", "max_parallel": 3},
    "P-A4": {"name": "Full Autonomy", "max_parallel": 3},
}

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("state_machine")


# =============================================================================
# STATE PERSISTENCE
# =============================================================================

def get_default_state():
    """Default state when no state file exists."""
    return {
        "current_state": "ACTIVE",
        "autonomy_level": "P-A2",
        "entered_at": datetime.now(timezone.utc).isoformat(),
        "previous_state": None,
        "transition_reason": "Initial boot — default state",
        "guardian_triggers_30d": 0,
        "history": [],
    }


def load_state() -> dict:
    """Load current state from file, or create default."""
    if STATE_FILE.exists():
        try:
            data = load_yaml(str(STATE_FILE))
            if data and "current_state" in data:
                return data
        except Exception as e:
            log.warning(f"Failed to load state file: {e}")
    return get_default_state()


def save_state(state: dict):
    """Persist state to file with locking."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        from filelock import atomic_yaml_write
        atomic_yaml_write(state, str(STATE_FILE))
    except ImportError:
        dump_yaml(state, str(STATE_FILE))


# =============================================================================
# METRICS COLLECTION
# =============================================================================

def get_budget_percentage() -> float:
    """Get current month's budget usage percentage."""
    now = datetime.now(timezone.utc)
    budget_file = BUDGET_DIR / f"{now.strftime('%Y-%m')}.yaml"
    if budget_file.exists():
        data = load_yaml(str(budget_file))
        return float(data.get("percentage", 0.0))
    return 0.0


def get_quality_metrics() -> dict:
    """Get quality scores from skill-metrics."""
    if not QUALITY_FILE.exists():
        return {"global_avg": 0, "total_scored": 0, "last_scores": []}

    data = load_yaml(str(QUALITY_FILE))
    global_avg = float(data.get("global_avg_quality", 0))
    total_scored = int(data.get("total_tasks_scored", 0))

    # Collect all individual scores
    all_scores = []
    skills = data.get("skills", {})
    for skill_data in skills.values():
        if isinstance(skill_data, dict):
            scores = skill_data.get("scores", [])
            if isinstance(scores, list):
                all_scores.extend(scores)

    # Last N scores (most recent)
    last_10 = all_scores[-10:] if all_scores else []
    last_20 = all_scores[-20:] if all_scores else []

    return {
        "global_avg": global_avg,
        "total_scored": total_scored,
        "last_10_avg": sum(last_10) / len(last_10) if last_10 else 0,
        "last_20_avg": sum(last_20) / len(last_20) if last_20 else 0,
        "last_3_avg": sum(all_scores[-3:]) / len(all_scores[-3:]) if len(all_scores) >= 3 else global_avg,
        "all_scores": all_scores,
    }


def get_task_metrics() -> dict:
    """Get task status counts and stale detection (DB-first)."""
    try:
        from task_store import TaskStore
        tasks = TaskStore().get_all()
    except Exception:
        tasks = []
        if TASKS_DIR.exists():
            for f in TASKS_DIR.glob("*.yaml"):
                try:
                    data = load_yaml(str(f))
                    if data:
                        tasks.append(data)
                except Exception:
                    pass

    counts = {"todo": 0, "in_progress": 0, "done": 0, "blocked": 0, "stale": 0}
    for t in tasks:
        status = t.get("status", "")
        if status in counts:
            counts[status] += 1

    # Stale detection: in_progress > 24h without update
    now = datetime.now(timezone.utc)
    for t in tasks:
        if t.get("status") == "in_progress":
            checked_out = t.get("checked_out_at") or t.get("assigned_at")
            if checked_out:
                try:
                    co_time = datetime.fromisoformat(str(checked_out).replace('Z', '+00:00'))
                    if (now - co_time) > timedelta(hours=24):
                        counts["stale"] += 1
                except (ValueError, TypeError):
                    pass

    counts["all_done"] = (counts["todo"] == 0 and counts["in_progress"] == 0)
    return counts


def calculate_system_health(budget_pct: float, quality: dict, tasks: dict) -> float:
    """
    Composite health score (0.0 — 1.0).
    Weighted: quality 40%, budget 30%, task health 30%.
    """
    # Quality component (0-1)
    quality_score = min(quality["global_avg"] / 100.0, 1.0) if quality["global_avg"] > 0 else 0.5

    # Budget component (1.0 at 0%, 0.0 at 100%)
    budget_score = max(0.0, 1.0 - (budget_pct / 100.0))

    # Task health (no stale = 1.0, stale reduces)
    stale_penalty = min(tasks.get("stale", 0) * 0.15, 0.5)
    blocked_penalty = min(tasks.get("blocked", 0) * 0.1, 0.3)
    task_score = max(0.0, 1.0 - stale_penalty - blocked_penalty)

    health = (quality_score * 0.4) + (budget_score * 0.3) + (task_score * 0.3)
    return round(health, 3)


def calculate_evolutionary_delta(quality: dict) -> float:
    """Delta = avg(last_10) - avg(previous_10)."""
    scores = quality.get("all_scores", [])
    if len(scores) < 10:
        return 0.0
    last_10 = scores[-10:]
    prev_10 = scores[-20:-10] if len(scores) >= 20 else scores[:len(scores)-10]
    if not prev_10:
        return 0.0
    return round(sum(last_10)/len(last_10) - sum(prev_10)/len(prev_10), 2)


# =============================================================================
# TRIGGER EVALUATION
# =============================================================================

def evaluate_triggers(state: dict, budget_pct: float, quality: dict,
                      tasks: dict, health: float, delta: float) -> tuple:
    """
    Evaluate all transition triggers.
    Returns (new_state, reason) or (None, None) if no transition needed.
    """
    current = state["current_state"]
    reasons = []

    # --- GUARDIAN triggers (highest priority — immediate stop) ---
    if budget_pct >= 95:
        return "GUARDIAN", f"Budget critical: {budget_pct:.1f}% >= 95%"

    if health < 0.50:
        return "GUARDIAN", f"SystemHealth critical: {health:.3f} < 0.50"

    # --- REFLECTIVE_PAUSE triggers ---
    if current == "ACTIVE":
        if quality["last_3_avg"] > 0 and quality["last_3_avg"] < 60 and quality.get("total_scored", 0) >= 5:
            return "REFLECTIVE_PAUSE", f"Quality regression: last 3 avg = {quality['last_3_avg']:.1f} < 60 (min 5 scored)"

        if 0.50 <= health < 0.70:
            return "REFLECTIVE_PAUSE", f"SystemHealth degraded: {health:.3f} (between 0.50-0.70)"

        if delta < -5 and quality["total_scored"] >= 10:
            return "REFLECTIVE_PAUSE", f"Evolutionary delta negative: {delta} < -5 (over {quality['total_scored']} tasks)"

    # --- Recovery: REFLECTIVE → ACTIVE ---
    if current == "REFLECTIVE_PAUSE":
        if health >= 0.85 and quality["last_3_avg"] >= 60:
            return "ACTIVE", f"Recovery: health={health:.3f} >= 0.85, quality={quality['last_3_avg']:.1f} >= 60"

    # --- Recovery: GUARDIAN → ACTIVE (auto-recovery when conditions improve) ---
    if current == "GUARDIAN":
        if budget_pct < 90 and health >= 0.70:
            return "ACTIVE", f"Auto-recovery: budget={budget_pct:.1f}% < 90%, health={health:.3f} >= 0.70"

    # --- EXPANSION triggers ---
    if current == "ACTIVE" and tasks.get("all_done", False):
        return "EXPANSION", "All tasks done — entering learning cycle"

    # --- EXPANSION → ACTIVE ---
    if current == "EXPANSION" and not tasks.get("all_done", False):
        return "ACTIVE", "New tasks detected — resuming execution"

    return None, None


# =============================================================================
# AUTONOMY LEVEL
# =============================================================================

def calculate_autonomy_level(health: float, quality: dict, delta: float,
                             guardian_triggers_30d: int, current_state: str) -> str:
    """Calculate autonomy level from metrics."""
    # Guardian = immediate P-A1
    if current_state == "GUARDIAN":
        return "P-A1"

    # P-A4: Full Autonomy
    if (health >= 0.90 and quality["last_20_avg"] >= 85
            and quality["total_scored"] >= 50 and guardian_triggers_30d == 0):
        return "P-A4"

    # P-A3: Autonomous
    if (health >= 0.85 and quality["last_20_avg"] >= 80
            and quality["total_scored"] >= 20 and delta >= 0):
        return "P-A3"

    # P-A2: Guided
    if health >= 0.70 and quality["last_10_avg"] >= 70:
        return "P-A2"

    # P-A1: Supervised (default)
    return "P-A1"


# =============================================================================
# STATE TRANSITION
# =============================================================================

def transition_state(state: dict, new_state: str, reason: str) -> dict:
    """Execute state transition with audit logging."""
    old_state = state["current_state"]

    # Record in history
    history_entry = {
        "from": old_state,
        "to": new_state,
        "reason": reason,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if "history" not in state:
        state["history"] = []
    state["history"].append(history_entry)

    # Keep last 50 transitions
    state["history"] = state["history"][-50:]

    # Update state
    state["previous_state"] = old_state
    state["current_state"] = new_state
    state["entered_at"] = datetime.now(timezone.utc).isoformat()
    state["transition_reason"] = reason

    # Track guardian triggers
    if new_state == "GUARDIAN":
        state["guardian_triggers_30d"] = state.get("guardian_triggers_30d", 0) + 1

    # Log to audit
    log_transition(old_state, new_state, reason)

    return state


def log_transition(old_state: str, new_state: str, reason: str):
    """Append transition to audit log."""
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_file = AUDIT_DIR / f"state_{today}.log"

    with open(log_file, 'a', encoding='utf-8') as f:
        ts = datetime.now(timezone.utc).isoformat()
        f.write(f"[{ts}] STATE_TRANSITION: {old_state} → {new_state} | {reason}\n")


# =============================================================================
# COMMANDS
# =============================================================================

def cmd_show(args):
    """Show current state and autonomy level."""
    state = load_state()

    budget_pct = get_budget_percentage()
    quality = get_quality_metrics()
    tasks = get_task_metrics()
    health = calculate_system_health(budget_pct, quality, tasks)
    delta = calculate_evolutionary_delta(quality)
    autonomy = calculate_autonomy_level(health, quality, delta,
                                        state.get("guardian_triggers_30d", 0),
                                        state["current_state"])

    # Update autonomy in state
    state["autonomy_level"] = autonomy
    state["system_health"] = health
    save_state(state)

    config = STATE_CONFIG[state["current_state"]]

    if args.json:
        import json
        result = {
            "state": state["current_state"],
            "autonomy_level": autonomy,
            "autonomy_name": AUTONOMY_LEVELS[autonomy]["name"],
            "max_parallel": config["max_parallel"],
            "allowed_actions": config["allowed_actions"],
            "system_health": health,
            "budget_pct": budget_pct,
            "quality_avg": quality["global_avg"],
            "evolutionary_delta": delta,
            "entered_at": state.get("entered_at", ""),
            "transition_reason": state.get("transition_reason", ""),
        }
        print(json.dumps(result, indent=2))
    else:
        print(f"=== DARIO STATE MACHINE ===\n")
        print(f"  State:           {state['current_state']}")
        print(f"  Autonomy:        {autonomy} ({AUTONOMY_LEVELS[autonomy]['name']})")
        print(f"  Max Parallel:    {config['max_parallel']}")
        print(f"  Allowed Actions: {', '.join(config['allowed_actions'])}")
        print(f"  System Health:   {health:.3f}")
        print(f"  Budget:          {budget_pct:.1f}%")
        print(f"  Quality Avg:     {quality['global_avg']:.1f}")
        print(f"  Evo Delta:       {delta:+.2f}")
        print(f"  Entered At:      {state.get('entered_at', 'N/A')}")
        print(f"  Reason:          {state.get('transition_reason', 'N/A')}")

    return 0


def cmd_evaluate(args):
    """Evaluate triggers and transition if needed."""
    state = load_state()

    budget_pct = get_budget_percentage()
    quality = get_quality_metrics()
    tasks = get_task_metrics()
    health = calculate_system_health(budget_pct, quality, tasks)
    delta = calculate_evolutionary_delta(quality)

    new_state, reason = evaluate_triggers(state, budget_pct, quality, tasks, health, delta)

    if new_state and new_state != state["current_state"]:
        old = state["current_state"]
        state = transition_state(state, new_state, reason)

        # Recalculate autonomy after transition
        autonomy = calculate_autonomy_level(health, quality, delta,
                                            state.get("guardian_triggers_30d", 0),
                                            new_state)
        state["autonomy_level"] = autonomy
        state["system_health"] = health
        save_state(state)

        config = STATE_CONFIG[new_state]

        if args.json:
            import json
            print(json.dumps({
                "transitioned": True,
                "from": old,
                "to": new_state,
                "reason": reason,
                "autonomy_level": autonomy,
                "max_parallel": config["max_parallel"],
                "system_health": health,
            }, indent=2))
        else:
            log.info(f"TRANSITION: {old} → {new_state}")
            log.info(f"Reason: {reason}")
            log.info(f"Autonomy: {autonomy} | Max Parallel: {config['max_parallel']}")

        return 3 if new_state == "GUARDIAN" else 2
    else:
        # No transition needed — update metrics
        autonomy = calculate_autonomy_level(health, quality, delta,
                                            state.get("guardian_triggers_30d", 0),
                                            state["current_state"])
        state["autonomy_level"] = autonomy
        state["system_health"] = health
        save_state(state)

        if args.json:
            import json
            print(json.dumps({
                "transitioned": False,
                "state": state["current_state"],
                "autonomy_level": autonomy,
                "max_parallel": STATE_CONFIG[state["current_state"]]["max_parallel"],
                "system_health": health,
            }, indent=2))
        else:
            log.info(f"No transition needed. State: {state['current_state']} | Health: {health:.3f}")

        return 0


def cmd_force_transition(args):
    """Force transition to a specific state."""
    target = args.transition.upper()
    if target not in VALID_STATES:
        log.error(f"Invalid state '{target}'. Valid: {VALID_STATES}")
        return 1

    state = load_state()
    old = state["current_state"]

    if old == target:
        log.info(f"Already in {target} — no transition needed")
        return 0

    reason = f"Manual transition by user (forced {old} → {target})"
    state = transition_state(state, target, reason)

    # Recalculate
    budget_pct = get_budget_percentage()
    quality = get_quality_metrics()
    health = calculate_system_health(budget_pct, quality, get_task_metrics())
    delta = calculate_evolutionary_delta(quality)
    autonomy = calculate_autonomy_level(health, quality, delta,
                                        state.get("guardian_triggers_30d", 0), target)
    state["autonomy_level"] = autonomy
    state["system_health"] = health
    save_state(state)

    if args.json:
        import json
        print(json.dumps({
            "transitioned": True,
            "from": old,
            "to": target,
            "reason": reason,
            "autonomy_level": autonomy,
        }, indent=2))
    else:
        log.info(f"FORCED: {old} → {target}")
        log.info(f"Autonomy: {autonomy}")

    return 2


def cmd_history(args):
    """Show transition history."""
    state = load_state()
    history = state.get("history", [])

    if not history:
        print("No transition history.")
        return 0

    if args.json:
        import json
        print(json.dumps(history, indent=2))
    else:
        print("=== STATE TRANSITION HISTORY ===\n")
        for h in history[-20:]:  # Last 20
            print(f"  [{h.get('timestamp', '?')}] {h.get('from')} → {h.get('to')}")
            print(f"    Reason: {h.get('reason')}")
            print()

    return 0


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="DARIO State Machine — Operational state tracking and transitions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("--evaluate", "-e", action="store_true",
                        help="Evaluate triggers, transition if needed")
    parser.add_argument("--transition", "-t",
                        help="Force transition to state (ACTIVE/REFLECTIVE_PAUSE/GUARDIAN/EXPANSION)")
    parser.add_argument("--history", action="store_true",
                        help="Show transition history")
    parser.add_argument("--json", "-j", action="store_true",
                        help="Machine-readable JSON output")

    args = parser.parse_args()

    if args.json:
        logging.getLogger().setLevel(logging.ERROR)

    if args.transition:
        return cmd_force_transition(args)
    elif args.evaluate:
        return cmd_evaluate(args)
    elif args.history:
        return cmd_history(args)
    else:
        return cmd_show(args)


if __name__ == "__main__":
    sys.exit(main())
