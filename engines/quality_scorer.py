#!/usr/bin/env python3
"""
LUCAS Quality Scorer — Records and tracks skill quality scores.
================================================================
The persistence layer for quality evaluation. Claude evaluates quality
using the 5-dimension rubric; this script records the decision and
maintains metrics.

Usage:
    # Record a score for a task
    python quality_scorer.py --task MNB-001 --score 85 --dimensions '{"specificity":0.9,"actionability":0.8,"completeness":0.85,"accuracy":0.9,"tone":0.7}'

    # Record with skill override (if task doesn't specify)
    python quality_scorer.py --task MNB-001 --score 72 --skill dario-brand --project wave74

    # Show score history for a skill
    python quality_scorer.py --history dario-brand

    # Show dashboard (all skills, tiers, trends)
    python quality_scorer.py --dashboard

    # Reset simulated data (mark as simulation)
    python quality_scorer.py --reset-simulated

    # JSON output
    python quality_scorer.py --task X --score 85 --json

Exit codes:
    0 = scored, action=ship
    1 = error
    2 = scored, action=revision (score < 60)
    3 = scored, action=success_pattern (score >= 90)
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

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
TASKS_DIR = ORCH_DIR / "tasks" / "active"
QUALITY_FILE = ORCH_DIR / "quality" / "skill-metrics.yaml"

# Thresholds
SHIP_THRESHOLD = 60
SUCCESS_THRESHOLD = 90
REVISION_MAX = 3

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("quality")


# =============================================================================
# SCORE RECORDING
# =============================================================================

def determine_action(score: int, revision_count: int = 0) -> str:
    """Determine what happens after scoring."""
    if score >= SUCCESS_THRESHOLD:
        return "success_pattern"
    elif score >= SHIP_THRESHOLD:
        return "ship"
    elif revision_count >= REVISION_MAX:
        return "escalate"
    else:
        return "revision"


def determine_tier(avg_score: float, revision_rate: float) -> str:
    """Assign tier based on average score and revision rate."""
    if avg_score >= 85 and revision_rate < 0.10:
        return "A"
    elif avg_score >= 75 and revision_rate < 0.25:
        return "B"
    elif avg_score >= 60:
        return "C"
    else:
        return "D"


def record_score(task_id: str, score: int, skill: str = None,
                 project: str = None, dimensions: dict = None,
                 source: str = "live") -> dict:
    """
    Record a quality score for a task. Updates task YAML + skill-metrics.
    Returns action dict.
    """
    result = {
        "task_id": task_id,
        "score": score,
        "skill": skill,
        "action": "ship",
        "tier": "?",
        "dimensions": dimensions,
        "source": source,
    }

    # 1. Update task YAML (if exists)
    task_file = TASKS_DIR / f"{task_id}.yaml"
    revision_count = 0
    if task_file.exists():
        task_data = load_yaml(str(task_file))
        if task_data:
            task_data["quality_score"] = score
            task_data["scored_at"] = datetime.now(timezone.utc).isoformat()
            if dimensions:
                task_data["quality_dimensions"] = dimensions
            # Get skill from task if not provided
            if not skill:
                skill = task_data.get("skill")
            if not project:
                project = task_data.get("project")
            revision_count = int(task_data.get("revision_count", 0) or 0)
            dump_yaml(task_data, str(task_file))

    # 2. Determine action
    action = determine_action(score, revision_count)
    result["action"] = action
    result["skill"] = skill

    # 3. Update skill-metrics.yaml + audit trail
    if skill:
        update_skill_metrics(skill, score, project, source)
        # Log to unified audit
        import subprocess
        subprocess.run([
            sys.executable, str(ORCH_DIR.parent / "orchestrator" / "audit_logger.py"),
            "-a", "lucas-quality", "-A", "task_scored",
            "-e", "task", "-i", task_id,
            "-d", f"score={score} skill={skill} action={action} source={source}"
        ], capture_output=True, timeout=5)
        # Get updated tier
        metrics = load_yaml(str(QUALITY_FILE)) if QUALITY_FILE.exists() else {}
        skills = metrics.get("skills", {})
        skill_data = skills.get(skill, {})
        if isinstance(skill_data, dict):
            result["tier"] = skill_data.get("tier", "?")
            result["avg_score"] = skill_data.get("avg_quality_score", score)

    return result


def update_skill_metrics(skill: str, score: int, project: str = None,
                         source: str = "live"):
    """Update skill-metrics.yaml with a new score."""
    QUALITY_FILE.parent.mkdir(parents=True, exist_ok=True)

    if QUALITY_FILE.exists():
        metrics = load_yaml(str(QUALITY_FILE))
    else:
        metrics = {
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "total_tasks_scored": 0,
            "global_avg_quality": 0,
            "skills": {},
        }

    skills = metrics.get("skills", {})
    if not isinstance(skills, dict):
        skills = {}

    # Get or create skill entry
    if skill not in skills or not isinstance(skills.get(skill), dict):
        skills[skill] = {
            "total_executions": 0,
            "avg_quality_score": 0,
            "scores": [],
            "live_scores": [],
            "revision_rate": 0.0,
            "tier": "unscored",
            "best_score": 0,
            "worst_score": 100,
            "best_domain": project or "",
            "improvement_trend": "new",
        }

    sd = skills[skill]

    # Ensure scores list exists
    if not isinstance(sd.get("scores"), list):
        sd["scores"] = []
    if not isinstance(sd.get("live_scores"), list):
        sd["live_scores"] = []

    # Add score with timestamp (fixed: was unbounded + no timestamp)
    sd["scores"].append(score)
    sd["scores"] = sd["scores"][-100:]  # Cap at 100 (prevent unbounded growth)
    if source == "live":
        sd["live_scores"].append(score)
        sd["live_scores"] = sd["live_scores"][-100:]
    sd["total_executions"] = (sd.get("total_executions") or 0) + 1
    sd["last_scored_at"] = datetime.now(timezone.utc).isoformat()

    # Recalculate averages using RECENT scores only (fixed: was using all-time)
    recent_scores = sd["scores"][-20:]  # Last 20 = current performance
    all_scores = sd["scores"]
    sd["avg_quality_score"] = round(sum(recent_scores) / len(recent_scores), 1)
    sd["avg_quality_alltime"] = round(sum(all_scores) / len(all_scores), 1)
    sd["best_score"] = max(all_scores)
    sd["worst_score"] = min(all_scores)

    # Calculate revision rate (scores < 60 / total)
    revisions = sum(1 for s in all_scores if s < SHIP_THRESHOLD)
    sd["revision_rate"] = round(revisions / len(all_scores), 2)

    # Determine tier
    sd["tier"] = determine_tier(sd["avg_quality_score"], sd["revision_rate"])

    # Improvement trend
    if len(all_scores) >= 4:
        recent = all_scores[-3:]
        older = all_scores[-6:-3] if len(all_scores) >= 6 else all_scores[:3]
        diff = sum(recent)/len(recent) - sum(older)/len(older)
        if diff > 3:
            sd["improvement_trend"] = "improving"
        elif diff < -3:
            sd["improvement_trend"] = "declining"
        else:
            sd["improvement_trend"] = "stable"

    if project:
        sd["best_domain"] = project

    # Update globals
    skills[skill] = sd
    metrics["skills"] = skills
    metrics["last_updated"] = datetime.now(timezone.utc).isoformat()

    # Recalculate global stats
    all_global_scores = []
    total_executions = 0
    for s_data in skills.values():
        if isinstance(s_data, dict):
            scores_list = s_data.get("scores", [])
            if isinstance(scores_list, list):
                all_global_scores.extend(scores_list)
            total_executions += (s_data.get("total_executions") or 0)

    metrics["total_tasks_scored"] = total_executions
    metrics["global_avg_quality"] = round(
        sum(all_global_scores) / len(all_global_scores), 1
    ) if all_global_scores else 0

    dump_yaml(metrics, str(QUALITY_FILE))


# =============================================================================
# RESET SIMULATED DATA
# =============================================================================

def reset_simulated():
    """Mark existing scores as simulated, separate from live data."""
    if not QUALITY_FILE.exists():
        return {"status": "no file"}

    metrics = load_yaml(str(QUALITY_FILE))
    skills = metrics.get("skills", {})
    reset_count = 0

    for skill_name, sd in skills.items():
        if not isinstance(sd, dict):
            continue
        scores = sd.get("scores", [])
        if not isinstance(scores, list) or not scores:
            continue

        # Mark all existing scores as simulated
        sd["simulated_scores"] = scores.copy()
        sd["live_scores"] = []
        sd["scores_source"] = "simulation (Mar & Brasa 2026-04-27)"
        reset_count += 1

    metrics["skills"] = skills
    metrics["data_note"] = "Scores pre-2026-05-05 are from Mar & Brasa simulation. Live scores tracked separately in live_scores field."
    dump_yaml(metrics, str(QUALITY_FILE))

    return {"reset": reset_count, "note": "simulated scores preserved in simulated_scores field"}


# =============================================================================
# DASHBOARD
# =============================================================================

def cmd_dashboard(args):
    """Show quality dashboard."""
    if not QUALITY_FILE.exists():
        print("No quality data yet.")
        return 0

    metrics = load_yaml(str(QUALITY_FILE))
    skills = metrics.get("skills", {})

    # Organize by tier
    tiers = {"A": [], "B": [], "C": [], "D": [], "unscored": []}
    for name, sd in skills.items():
        if not isinstance(sd, dict):
            continue
        tier = sd.get("tier", "unscored")
        tiers.setdefault(tier, []).append((name, sd))

    if args.json:
        result = {
            "total_scored": metrics.get("total_tasks_scored", 0),
            "global_avg": metrics.get("global_avg_quality", 0),
            "tiers": {t: len(s) for t, s in tiers.items()},
            "skills": {},
        }
        for name, sd in skills.items():
            if isinstance(sd, dict):
                result["skills"][name] = {
                    "avg": sd.get("avg_quality_score"),
                    "tier": sd.get("tier"),
                    "executions": sd.get("total_executions"),
                    "live_count": len(sd.get("live_scores", [])),
                    "trend": sd.get("improvement_trend"),
                }
        print(json.dumps(result, indent=2))
    else:
        print(f"=== QUALITY DASHBOARD ===")
        print(f"  Total scored: {metrics.get('total_tasks_scored', 0)}")
        print(f"  Global avg:   {metrics.get('global_avg_quality', 0)}")
        print(f"  Data note:    {metrics.get('data_note', 'live data')}\n")

        for tier in ["A", "B", "C", "D", "unscored"]:
            entries = tiers.get(tier, [])
            if entries:
                print(f"  TIER {tier} ({len(entries)} skills):")
                for name, sd in sorted(entries, key=lambda x: -(x[1].get("avg_quality_score") or 0)):
                    avg = sd.get("avg_quality_score") or 0
                    execs = sd.get("total_executions") or 0
                    live = len(sd.get("live_scores", []))
                    trend = sd.get("improvement_trend", "")
                    print(f"    {name:30s} avg={avg:5.1f} exec={execs} live={live} [{trend}]")
                print()

    return 0


def cmd_history(args):
    """Show score history for a skill."""
    if not QUALITY_FILE.exists():
        print("No quality data.")
        return 1

    metrics = load_yaml(str(QUALITY_FILE))
    skills = metrics.get("skills", {})
    skill_name = args.history

    if skill_name not in skills:
        print(f"Skill '{skill_name}' not found. Available: {list(skills.keys())[:10]}...")
        return 1

    sd = skills[skill_name]
    if not isinstance(sd, dict):
        print(f"Invalid data for {skill_name}")
        return 1

    if args.json:
        print(json.dumps(sd, indent=2, default=str))
    else:
        print(f"=== {skill_name} ===")
        print(f"  Tier:        {sd.get('tier')}")
        print(f"  Avg score:   {sd.get('avg_quality_score')}")
        print(f"  Executions:  {sd.get('total_executions')}")
        print(f"  All scores:  {sd.get('scores', [])}")
        print(f"  Live scores: {sd.get('live_scores', [])}")
        print(f"  Simulated:   {sd.get('simulated_scores', [])}")
        print(f"  Revision %:  {sd.get('revision_rate', 0):.0%}")
        print(f"  Trend:       {sd.get('improvement_trend')}")
        print(f"  Best domain: {sd.get('best_domain')}")

    return 0


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="LUCAS Quality Scorer — Record and track quality scores",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--task", "-t", help="Task ID to score")
    parser.add_argument("--score", type=int, help="Quality score (0-100)")
    parser.add_argument("--skill", help="Skill name (auto-detected from task if omitted)")
    parser.add_argument("--project", help="Project name")
    parser.add_argument("--dimensions", help="JSON dict of dimension scores (0-1 each)")
    parser.add_argument("--dashboard", "-d", action="store_true", help="Show quality dashboard")
    parser.add_argument("--history", help="Show history for a skill")
    parser.add_argument("--reset-simulated", action="store_true", help="Mark existing data as simulated")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")

    args = parser.parse_args()

    if args.json:
        logging.getLogger().setLevel(logging.ERROR)

    if args.dashboard:
        return cmd_dashboard(args)
    elif args.history:
        return cmd_history(args)
    elif args.reset_simulated:
        result = reset_simulated()
        if args.json:
            print(json.dumps(result))
        else:
            print(f"Reset {result['reset']} skills. Simulated scores preserved.")
        return 0
    elif args.task and args.score is not None:
        dimensions = None
        if args.dimensions:
            try:
                dimensions = json.loads(args.dimensions)
            except json.JSONDecodeError:
                log.error("Invalid JSON for --dimensions")
                return 1

        result = record_score(
            task_id=args.task,
            score=args.score,
            skill=args.skill,
            project=args.project,
            dimensions=dimensions,
            source="live",
        )

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"  Task:   {result['task_id']}")
            print(f"  Score:  {result['score']}")
            print(f"  Skill:  {result['skill']}")
            print(f"  Action: {result['action']}")
            print(f"  Tier:   {result['tier']}")

        if result["action"] == "revision":
            return 2
        elif result["action"] == "success_pattern":
            return 3
        return 0
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
