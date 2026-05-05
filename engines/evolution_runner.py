#!/usr/bin/env python3
"""
DARIO Evolution Runner — Executes learning, mutation, and checkpoint cycles.
============================================================================
The code that makes the Evolution Engine spec (evolution_engine.yaml) real.

Usage:
    python evolution_runner.py                  # Full evolution cycle (journal + weights + checkpoint)
    python evolution_runner.py --journal        # Generate learning journal only
    python evolution_runner.py --weights        # Update synaptic weights from scores
    python evolution_runner.py --checkpoint     # Create snapshot checkpoint
    python evolution_runner.py --status         # Show evolution status
    python evolution_runner.py --json           # Machine-readable output

Exit codes:
    0 = success
    1 = error
    2 = mutations applied (weights changed)
"""

import argparse
import logging
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from copy import deepcopy

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
EVOLUTION_DIR = ORCH_DIR / "evolution"
JOURNAL_DIR = EVOLUTION_DIR / "journal"
MUTATIONS_DIR = EVOLUTION_DIR / "mutations"
RULES_DIR = EVOLUTION_DIR / "rules"
CHECKPOINTS_DIR = EVOLUTION_DIR / "checkpoints"
QUALITY_FILE = ORCH_DIR / "quality" / "skill-metrics.yaml"
WEIGHTS_FILE = ORCH_DIR / "synaptic_weights.yaml"
STATE_FILE = ORCH_DIR / "current_state.yaml"
CHANGELOG = EVOLUTION_DIR / "CHANGELOG.md"

# Bounds
MAX_MUTATIONS_PER_SESSION = 3
WEIGHT_MIN = 0.1
WEIGHT_MAX = 1.0
WEIGHT_SUCCESS_INCREMENT = 0.05
WEIGHT_FAILURE_DECREMENT = 0.03
SUCCESS_THRESHOLD = 80
FAILURE_THRESHOLD = 50

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("evolution")


# =============================================================================
# LEARNING JOURNAL
# =============================================================================

def generate_journal() -> dict:
    """Generate a learning journal from current metrics."""
    journal = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M"),
        "tasks_completed": 0,
        "avg_quality_score": 0,
        "skills_used": {},
        "skill_pairs_observed": [],
        "dispatch_accuracy": 100,  # TODO: track actual misroutes
        "fallback_triggered": 0,
        "user_corrections": 0,
        "observations": [],
        "evolutionary_delta": 0,
    }

    # Read skill metrics
    if not QUALITY_FILE.exists():
        journal["observations"].append("No skill-metrics.yaml found — cold start")
        return journal

    metrics = load_yaml(str(QUALITY_FILE))
    skills = metrics.get("skills", {})

    total_executions = 0
    all_scores = []
    skills_used = {}

    for skill_name, skill_data in skills.items():
        if not isinstance(skill_data, dict):
            continue
        executions = skill_data.get("total_executions", 0)
        scores = skill_data.get("scores", [])
        total_executions += executions
        all_scores.extend(scores)
        if executions > 0:
            skills_used[skill_name] = {
                "executions": executions,
                "avg_score": skill_data.get("avg_quality_score", 0),
                "tier": skill_data.get("tier", "?"),
            }

    journal["tasks_completed"] = total_executions
    journal["avg_quality_score"] = round(sum(all_scores) / len(all_scores), 1) if all_scores else 0
    journal["skills_used"] = skills_used

    # Calculate evolutionary delta
    if len(all_scores) >= 10:
        last_half = all_scores[len(all_scores)//2:]
        first_half = all_scores[:len(all_scores)//2]
        delta = round(sum(last_half)/len(last_half) - sum(first_half)/len(first_half), 2)
        journal["evolutionary_delta"] = delta
    elif len(all_scores) >= 4:
        mid = len(all_scores) // 2
        last = all_scores[mid:]
        first = all_scores[:mid]
        delta = round(sum(last)/len(last) - sum(first)/len(first), 2)
        journal["evolutionary_delta"] = delta

    # Auto-observations
    for skill_name, skill_data in skills.items():
        if not isinstance(skill_data, dict):
            continue
        avg = skill_data.get("avg_quality_score") or 0
        revision_rate = skill_data.get("revision_rate") or 0

        if avg >= 90:
            journal["observations"].append(f"STAR: {skill_name} avg={avg} — top performer")
        elif avg < 70 and skill_data.get("total_executions", 0) >= 3:
            journal["observations"].append(f"WEAK: {skill_name} avg={avg} — needs improvement")

        if revision_rate > 0.25:
            journal["observations"].append(f"HIGH_REVISION: {skill_name} rate={revision_rate:.0%} — quality issue")

    # Detect skill pairs from domain co-occurrence
    domain_skills = {}
    for skill_name, skill_data in skills.items():
        if not isinstance(skill_data, dict):
            continue
        domain = skill_data.get("best_domain", "")
        if domain:
            domain_skills.setdefault(domain, []).append(skill_name)

    for domain, skill_list in domain_skills.items():
        if len(skill_list) >= 2:
            for i, s1 in enumerate(skill_list):
                for s2 in skill_list[i+1:]:
                    journal["skill_pairs_observed"].append(f"{s1} + {s2} (domain: {domain})")

    return journal


def save_journal(journal: dict) -> Path:
    """Save journal to file."""
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"learn_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}_{journal['session_id']}.yaml"
    filepath = JOURNAL_DIR / filename
    dump_yaml(journal, str(filepath))
    return filepath


# =============================================================================
# SYNAPTIC WEIGHTS UPDATE
# =============================================================================

def update_weights() -> dict:
    """Update synaptic weights based on quality data."""
    if not WEIGHTS_FILE.exists() or not QUALITY_FILE.exists():
        return {"mutations": 0, "reason": "missing files"}

    weights_data = load_yaml(str(WEIGHTS_FILE))
    metrics = load_yaml(str(QUALITY_FILE))
    skills = metrics.get("skills", {})

    affinity = weights_data.get("affinity_graph", {})
    mutations = []
    mutation_count = 0

    for pair_key, pair_data in affinity.items():
        if not isinstance(pair_data, dict):
            continue
        if mutation_count >= MAX_MUTATIONS_PER_SESSION:
            break

        # Parse skill pair from key (format: "skill-a + skill-b")
        parts = pair_key.split(" + ")
        if len(parts) != 2:
            continue
        skill_a, skill_b = parts[0].strip(), parts[1].strip()

        # Get scores for both skills
        data_a = skills.get(skill_a, {})
        data_b = skills.get(skill_b, {})

        if not isinstance(data_a, dict) or not isinstance(data_b, dict):
            continue

        exec_a = data_a.get("total_executions", 0)
        exec_b = data_b.get("total_executions", 0)
        avg_a = data_a.get("avg_quality_score", 0)
        avg_b = data_b.get("avg_quality_score", 0)

        # Only update if both skills have been used
        if exec_a == 0 or exec_b == 0:
            continue

        # Calculate combined score
        combined_avg = round((avg_a + avg_b) / 2, 1)
        old_weight = float(pair_data.get("weight", 0.5))
        new_weight = old_weight

        # Check if they share a domain (co-activation proxy)
        domain_a = data_a.get("best_domain", "")
        domain_b = data_b.get("best_domain", "")
        co_activated = (domain_a == domain_b and domain_a != "") or (exec_a >= 2 and exec_b >= 2)

        if co_activated:
            # Update co_activations
            old_co = int(pair_data.get("co_activations", 0))
            new_co = min(old_co + 1, exec_a + exec_b)  # Estimate from total executions
            pair_data["co_activations"] = new_co
            pair_data["avg_combined_score"] = combined_avg

            # Apply reinforcement
            if combined_avg >= SUCCESS_THRESHOLD:
                new_weight = min(WEIGHT_MAX, old_weight + WEIGHT_SUCCESS_INCREMENT)
            elif combined_avg < FAILURE_THRESHOLD:
                new_weight = max(WEIGHT_MIN, old_weight - WEIGHT_FAILURE_DECREMENT)

        if new_weight != old_weight:
            pair_data["weight"] = round(new_weight, 3)
            mutation_count += 1
            mutations.append({
                "pair": pair_key,
                "old_weight": old_weight,
                "new_weight": round(new_weight, 3),
                "combined_avg": combined_avg,
                "reason": "reinforcement" if combined_avg >= SUCCESS_THRESHOLD else "penalty",
            })

    # Save updated weights
    if mutations:
        dump_yaml(weights_data, str(WEIGHTS_FILE))

        # Log mutations
        MUTATIONS_DIR.mkdir(parents=True, exist_ok=True)
        mutation_log = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "synaptic_weight_update",
            "count": len(mutations),
            "mutations": mutations,
        }
        log_file = MUTATIONS_DIR / f"mut_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.yaml"
        dump_yaml(mutation_log, str(log_file))

    return {
        "mutations": len(mutations),
        "details": mutations,
    }


# =============================================================================
# CHECKPOINT
# =============================================================================

def create_checkpoint() -> str:
    """Snapshot current state for rollback capability."""
    CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)
    ckpt_name = f"ckpt_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}"
    ckpt_dir = CHECKPOINTS_DIR / ckpt_name

    if ckpt_dir.exists():
        return f"Checkpoint {ckpt_name} already exists"

    ckpt_dir.mkdir(parents=True)

    # Copy key files
    files_to_snapshot = [
        WEIGHTS_FILE,
        ORCH_DIR / "operational_states.yaml",
        ORCH_DIR / "composite_modes.yaml",
        ORCH_DIR / "autodiag.yaml",
        ORCH_DIR / "fallback_matrix.yaml",
        STATE_FILE,
    ]

    copied = 0
    for f in files_to_snapshot:
        if f.exists():
            shutil.copy2(str(f), str(ckpt_dir / f.name))
            copied += 1

    # Write checkpoint metadata
    meta = {
        "created": datetime.now(timezone.utc).isoformat(),
        "files_captured": copied,
        "trigger": "evolution_runner",
    }
    dump_yaml(meta, str(ckpt_dir / "meta.yaml"))

    return ckpt_name


# =============================================================================
# PATTERN CRYSTALLIZATION
# =============================================================================

def check_crystallization(journal: dict) -> list:
    """Check if any patterns should be crystallized into rules."""
    RULES_DIR.mkdir(parents=True, exist_ok=True)
    new_rules = []

    # Read existing journals for pattern detection
    journals = []
    if JOURNAL_DIR.exists():
        for f in sorted(JOURNAL_DIR.glob("*.yaml")):
            try:
                j = load_yaml(str(f))
                if j:
                    journals.append(j)
            except Exception:
                pass

    if len(journals) < 3:
        return new_rules  # Need at least 3 journals for pattern detection

    # Pattern: Consistent star performers (appear in 3+ journals)
    star_counts = {}
    for j in journals:
        for obs in j.get("observations", []):
            if obs.startswith("STAR:"):
                skill = obs.split(" ")[1]
                star_counts[skill] = star_counts.get(skill, 0) + 1

    for skill, count in star_counts.items():
        if count >= 3:
            rule_file = RULES_DIR / f"rule_star_{skill.replace('-', '_')}.yaml"
            if not rule_file.exists():
                rule = {
                    "type": "crystallized_pattern",
                    "created": datetime.now(timezone.utc).isoformat(),
                    "pattern": f"{skill} consistently scores 90+ across {count} evolution cycles",
                    "action": f"Prefer {skill} for its domain. Increase dispatch confidence.",
                    "evidence_count": count,
                }
                dump_yaml(rule, str(rule_file))
                new_rules.append(rule)

    return new_rules


# =============================================================================
# CHANGELOG
# =============================================================================

def append_changelog(journal: dict, mutations: dict, checkpoint: str, rules: list):
    """Append evolution entry to CHANGELOG."""
    EVOLUTION_DIR.mkdir(parents=True, exist_ok=True)

    entry = f"""
## {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC — Evolution Cycle

- **Tasks scored:** {journal.get('tasks_completed', 0)}
- **Avg quality:** {journal.get('avg_quality_score', 0)}
- **Evo delta:** {journal.get('evolutionary_delta', 0):+.2f}
- **Mutations:** {mutations.get('mutations', 0)} weight updates
- **Checkpoint:** {checkpoint}
- **Rules crystallized:** {len(rules)}
- **Observations:** {len(journal.get('observations', []))}

"""
    with open(str(CHANGELOG), 'a', encoding='utf-8') as f:
        f.write(entry)


# =============================================================================
# COMMANDS
# =============================================================================

def cmd_full_cycle(args):
    """Run complete evolution cycle."""
    results = {"journal": None, "weights": None, "checkpoint": None, "rules": []}

    # 1. Generate learning journal
    journal = generate_journal()
    journal_path = save_journal(journal)
    results["journal"] = {
        "file": str(journal_path.name),
        "tasks_scored": journal["tasks_completed"],
        "avg_quality": journal["avg_quality_score"],
        "delta": journal["evolutionary_delta"],
        "observations": len(journal.get("observations", [])),
    }

    # 2. Update synaptic weights
    weight_result = update_weights()
    results["weights"] = weight_result

    # 3. Create checkpoint
    ckpt = create_checkpoint()
    results["checkpoint"] = ckpt

    # 4. Check crystallization
    rules = check_crystallization(journal)
    results["rules"] = [r.get("pattern", "") for r in rules]

    # 5. Update changelog + audit trail
    append_changelog(journal, weight_result, ckpt, rules)

    # Log to unified audit trail
    import subprocess
    subprocess.run([
        sys.executable, str(ORCH_DIR / "audit_logger.py"),
        "-a", "evolution-engine", "-A", "evolution_cycle",
        "-e", "system", "-i", ckpt,
        "-d", f"tasks={journal['tasks_completed']} avg={journal['avg_quality_score']} mutations={weight_result['mutations']} delta={journal['evolutionary_delta']:+.2f}"
    ], capture_output=True, timeout=5)

    if args.json:
        import json
        print(json.dumps(results, indent=2))
    else:
        print("=== EVOLUTION CYCLE COMPLETE ===\n")
        print(f"  Journal:      {results['journal']['file']}")
        print(f"  Tasks scored: {journal['tasks_completed']}")
        print(f"  Avg quality:  {journal['avg_quality_score']}")
        print(f"  Evo delta:    {journal['evolutionary_delta']:+.2f}")
        print(f"  Mutations:    {weight_result['mutations']} weight updates")
        print(f"  Checkpoint:   {ckpt}")
        print(f"  Rules:        {len(rules)} crystallized")
        if journal.get("observations"):
            print(f"\n  Observations:")
            for obs in journal["observations"]:
                print(f"    - {obs}")
        if weight_result.get("details"):
            print(f"\n  Weight changes:")
            for m in weight_result["details"]:
                print(f"    - {m['pair']}: {m['old_weight']} → {m['new_weight']} ({m['reason']})")

    return 2 if weight_result.get("mutations", 0) > 0 else 0


def cmd_status(args):
    """Show evolution engine status."""
    # Count journals
    journal_count = len(list(JOURNAL_DIR.glob("*.yaml"))) if JOURNAL_DIR.exists() else 0
    mutation_count = len(list(MUTATIONS_DIR.glob("*.yaml"))) if MUTATIONS_DIR.exists() else 0
    rule_count = len(list(RULES_DIR.glob("*.yaml"))) if RULES_DIR.exists() else 0
    checkpoint_count = len(list(CHECKPOINTS_DIR.iterdir())) if CHECKPOINTS_DIR.exists() else 0

    # Read weights
    non_base_weights = 0
    if WEIGHTS_FILE.exists():
        weights = load_yaml(str(WEIGHTS_FILE))
        for pair_data in weights.get("affinity_graph", {}).values():
            if isinstance(pair_data, dict) and float(pair_data.get("weight", 0.5)) != 0.5:
                non_base_weights += 1

    if args.json:
        import json
        print(json.dumps({
            "journals": journal_count,
            "mutations": mutation_count,
            "rules": rule_count,
            "checkpoints": checkpoint_count,
            "weights_evolved": non_base_weights,
        }, indent=2))
    else:
        print("=== EVOLUTION ENGINE STATUS ===\n")
        print(f"  Journals:        {journal_count}")
        print(f"  Mutations logged: {mutation_count}")
        print(f"  Rules crystallized: {rule_count}")
        print(f"  Checkpoints:     {checkpoint_count}")
        print(f"  Weights evolved: {non_base_weights} (non-base)")

    return 0


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="DARIO Evolution Runner — Execute learning cycles",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--journal", action="store_true", help="Generate learning journal only")
    parser.add_argument("--weights", action="store_true", help="Update synaptic weights only")
    parser.add_argument("--checkpoint", action="store_true", help="Create checkpoint only")
    parser.add_argument("--status", "-s", action="store_true", help="Show evolution status")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")

    args = parser.parse_args()

    if args.json:
        logging.getLogger().setLevel(logging.ERROR)

    if args.status:
        return cmd_status(args)
    elif args.journal:
        journal = generate_journal()
        path = save_journal(journal)
        if args.json:
            import json
            print(json.dumps({"file": str(path.name), "observations": len(journal.get("observations", []))}))
        else:
            print(f"Journal saved: {path.name}")
        return 0
    elif args.weights:
        result = update_weights()
        if args.json:
            import json
            print(json.dumps(result, indent=2))
        else:
            print(f"Mutations: {result['mutations']}")
        return 2 if result["mutations"] > 0 else 0
    elif args.checkpoint:
        ckpt = create_checkpoint()
        if args.json:
            import json
            print(json.dumps({"checkpoint": ckpt}))
        else:
            print(f"Checkpoint: {ckpt}")
        return 0
    else:
        return cmd_full_cycle(args)


if __name__ == "__main__":
    sys.exit(main())
