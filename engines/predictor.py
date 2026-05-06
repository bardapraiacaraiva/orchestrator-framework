#!/usr/bin/env python3
"""
DARIO Predictor — Quality/cost/risk estimates BEFORE execution.
================================================================
Uses historical data to predict outcomes. Enables informed decisions.

Usage:
    python predictor.py --task MNB-002                # Full prediction
    python predictor.py --skill dario-brand           # Predict for skill type
    python predictor.py --skill dario-brand --model opus --json

Returns:
    estimated_quality: predicted score based on skill history
    estimated_tokens:  predicted token usage
    estimated_cost:    predicted cost based on model
    revision_risk:     probability of needing revision
    recommended_model: most cost-effective model for this quality target
"""

import argparse
import json
import logging
import sys
from pathlib import Path

ORCH_DIR = Path.home() / ".claude" / "orchestrator"
sys.path.insert(0, str(ORCH_DIR))

from db import DB

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("predictor")

MODEL_COSTS = {
    "haiku":  {"input": 0.80, "output": 4.00, "quality_factor": 0.85},
    "sonnet": {"input": 3.00, "output": 15.00, "quality_factor": 1.0},
    "opus":   {"input": 15.00, "output": 75.00, "quality_factor": 1.15},
}

# Default estimates when no history available
DEFAULTS = {
    "avg_quality": 75,
    "avg_tokens": 2500,
    "revision_rate": 0.15,
}


def predict(task_id: str = "", skill: str = "", model: str = "sonnet",
            priority: str = "medium") -> dict:
    """Generate predictions based on historical data."""
    db = DB()

    # Get task info
    if task_id:
        task = db.get_task(task_id)
        if task:
            if not skill:
                skill = task.get("skill", "")
            if not priority:
                priority = task.get("priority", "medium")

    # Get historical stats for this skill
    stats = db.get_skill_stats()
    skill_stats = None
    for s in stats:
        if s.get("skill") == skill:
            skill_stats = s
            break

    # Also check YAML metrics for richer history
    try:
        from ruamel.yaml import YAML
        y = YAML()
        qf = ORCH_DIR / "quality" / "skill-metrics.yaml"
        if qf.exists():
            with open(str(qf), 'r', encoding='utf-8') as _qf:
                yaml_metrics = y.load(_qf)
            skill_yaml = (yaml_metrics or {}).get("skills", {}).get(skill, {})
        else:
            skill_yaml = {}
    except Exception:
        skill_yaml = {}

    # Compute predictions
    if skill_stats and skill_stats.get("executions", 0) >= 2:
        avg_quality = skill_stats["avg_score"]
        # Try to get real token avg from DB budget data (fixed: was always 2500)
        avg_tokens = skill_stats.get("avg_tokens") or skill_yaml.get("avg_tokens") or DEFAULTS["avg_tokens"]
        revision_rate = skill_yaml.get("revision_rate") or 0.0
        confidence = min(0.5 + skill_stats["executions"] * 0.05, 0.95)
    elif isinstance(skill_yaml, dict) and skill_yaml.get("total_executions", 0) > 0:
        avg_quality = skill_yaml.get("avg_quality_score") or DEFAULTS["avg_quality"]
        avg_tokens = skill_yaml.get("avg_tokens") or DEFAULTS["avg_tokens"]
        revision_rate = skill_yaml.get("revision_rate") or DEFAULTS["revision_rate"]
        confidence = 0.4
    else:
        avg_quality = DEFAULTS["avg_quality"]
        avg_tokens = DEFAULTS["avg_tokens"]
        revision_rate = DEFAULTS["revision_rate"]
        confidence = 0.2

    # Model quality adjustment
    model_config = MODEL_COSTS.get(model, MODEL_COSTS["sonnet"])
    quality_factor = model_config["quality_factor"]
    predicted_quality = round(min(avg_quality * quality_factor, 100))

    # Cost estimate
    estimated_input = int(avg_tokens * 0.6)
    estimated_output = int(avg_tokens * 0.4)
    estimated_cost = round(
        estimated_input / 1_000_000 * model_config["input"] +
        estimated_output / 1_000_000 * model_config["output"], 4
    )

    # Revision risk
    if predicted_quality >= 85:
        risk = max(0.02, revision_rate * 0.5)
    elif predicted_quality >= 70:
        risk = revision_rate
    else:
        risk = min(revision_rate * 1.5, 0.5)

    # Recommend model (cheapest that meets quality target)
    threshold = 60 if priority in ("low", "medium") else 70 if priority == "high" else 80
    recommended = "haiku"
    for m in ["haiku", "sonnet", "opus"]:
        pred = round(min(avg_quality * MODEL_COSTS[m]["quality_factor"], 100))
        if pred >= threshold:
            recommended = m
            break

    return {
        "task_id": task_id,
        "skill": skill,
        "model": model,
        "predictions": {
            "quality": predicted_quality,
            "tokens": avg_tokens,
            "cost": estimated_cost,
            "revision_risk": round(risk, 2),
        },
        "confidence": round(confidence, 2),
        "data_points": skill_stats.get("executions", 0) if skill_stats else 0,
        "recommended_model": recommended,
        "model_comparison": {
            m: {
                "predicted_quality": round(min(avg_quality * MODEL_COSTS[m]["quality_factor"], 100)),
                "estimated_cost": round(
                    estimated_input / 1_000_000 * MODEL_COSTS[m]["input"] +
                    estimated_output / 1_000_000 * MODEL_COSTS[m]["output"], 4
                ),
            }
            for m in ["haiku", "sonnet", "opus"]
        },
    }


def main():
    parser = argparse.ArgumentParser(description="DARIO Predictor — Pre-execution estimates")
    parser.add_argument("--task", "-t", default="", help="Task ID")
    parser.add_argument("--skill", "-s", default="", help="Skill name")
    parser.add_argument("--model", "-m", default="sonnet", help="Model to estimate")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")

    args = parser.parse_args()
    if args.json:
        logging.getLogger().setLevel(logging.ERROR)

    result = predict(args.task, args.skill, args.model)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        p = result["predictions"]
        print(f"=== PREDICTION: {result['skill']} ({result['model']}) ===")
        print(f"  Confidence: {result['confidence']:.0%} ({result['data_points']} data points)\n")
        print(f"  Quality:    {p['quality']}/100")
        print(f"  Tokens:     ~{p['tokens']:,}")
        print(f"  Cost:       ${p['cost']:.4f}")
        print(f"  Revision:   {p['revision_risk']:.0%} risk")
        print(f"  Recommend:  {result['recommended_model']}\n")
        print(f"  Model comparison:")
        for m, d in result["model_comparison"].items():
            marker = " <--" if m == result["recommended_model"] else ""
            print(f"    {m:8s} quality={d['predicted_quality']:3d}  cost=${d['estimated_cost']:.4f}{marker}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
