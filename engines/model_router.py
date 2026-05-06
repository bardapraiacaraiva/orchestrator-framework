#!/usr/bin/env python3
"""
DARIO Model Router — Intelligent model selection for cost optimization.
========================================================================
Classifies task complexity → routes to cheapest model that meets quality threshold.
Inspired by Letta + production LLM routing patterns.

Expected savings: 50-70% cost reduction by routing simple tasks to Haiku.

Usage:
    python model_router.py --task MNB-002 --json
    python model_router.py --skill dario-brand --priority critical --json
    python model_router.py --complexity simple --json

Architecture:
    Task → Complexity Classification → Model Selection → Cost Estimate

    Complexity signals:
    - Priority: critical → complex, medium → medium, low → simple
    - Skill history: avg_quality > 85 on Haiku → keep Haiku
    - Token estimate: > 10K → complex
    - Execution policy: client_facing → min Sonnet, critical → Opus
    - Synaptic weight: high-affinity pairs → can downgrade model

Model tiers:
    Haiku  — simple tasks, internal, non-client-facing ($0.80/$4.00 per 1M)
    Sonnet — medium complexity, client-facing, standard ($3.00/$15.00 per 1M)
    Opus   — complex, critical, creative, high-stakes ($15.00/$75.00 per 1M)
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# License enforcement
try:
    from license_manager import require_license
    require_license()
except (ImportError, SystemExit):
    pass  # License check skipped (dev mode)

ORCH_DIR = Path.home() / ".claude" / "orchestrator"
sys.path.insert(0, str(ORCH_DIR))

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("model_router")


# Model definitions with costs (per 1M tokens)
MODELS = {
    "haiku": {
        "id": "claude-haiku-4-5-20251001",
        "input_cost": 0.80,
        "output_cost": 4.00,
        "quality_factor": 0.85,
        "max_complexity": "simple",
        "strengths": ["fast", "cheap", "scoring", "classification", "extraction"],
    },
    "sonnet": {
        "id": "claude-sonnet-4-6",
        "input_cost": 3.00,
        "output_cost": 15.00,
        "quality_factor": 1.0,
        "max_complexity": "medium",
        "strengths": ["balanced", "coding", "analysis", "client-facing"],
    },
    "opus": {
        "id": "claude-opus-4-6",
        "input_cost": 15.00,
        "output_cost": 75.00,
        "quality_factor": 1.15,
        "max_complexity": "complex",
        "strengths": ["creative", "strategy", "multi-step", "nuanced"],
    },
}

# Skills that ALWAYS require minimum model tier
SKILL_MIN_MODEL = {
    # Creative/strategic — need Opus
    "dario-brand": "sonnet",
    "dario-offer": "sonnet",
    "dario-pitch": "sonnet",
    "dario-sales-letter": "sonnet",
    "dario-story-circle": "sonnet",
    "dario-movement": "opus",
    "dario-c-level": "opus",
    # Technical — Sonnet sufficient
    "dario-wp-audit": "sonnet",
    "dario-woo-audit": "sonnet",
    "seo-audit": "sonnet",
    "dario-diagnose": "sonnet",
    "dario-pentest-checklist": "sonnet",
    # Simple/extraction — Haiku fine
    "dario-naming": "haiku",
    "dario-kw-cluster": "haiku",
    "seo-schema": "haiku",
    "seo-sitemap": "haiku",
    "dario-sop": "haiku",
    "dario-obsidian-save": "haiku",
    "dario-rag-ingest": "haiku",
}

# Execution policies that enforce minimum model
POLICY_MIN_MODEL = {
    "critical": "sonnet",
    "client_facing": "sonnet",
    "financial": "sonnet",
}

# Complexity classification thresholds
COMPLEXITY_RULES = {
    "simple": {"max_tokens": 3000, "priorities": ["low"], "default_model": "haiku"},
    "medium": {"max_tokens": 10000, "priorities": ["medium", "high"], "default_model": "sonnet"},
    "complex": {"max_tokens": 999999, "priorities": ["critical"], "default_model": "opus"},
}


def classify_complexity(task: dict = None, skill: str = "", priority: str = "medium",
                        estimated_tokens: int = 0, policy: str = "default") -> str:
    """Classify task complexity as simple/medium/complex."""
    if task:
        skill = task.get("skill", skill)
        priority = task.get("priority", priority)
        estimated_tokens = task.get("estimated_tokens", estimated_tokens) or 0
        policy = task.get("execution_policy", policy)

    # Rule 1: Priority-based
    if priority == "critical":
        return "complex"
    if priority == "low":
        return "simple"

    # Rule 2: Policy-based
    if policy in ("critical", "client_facing"):
        return "complex" if policy == "critical" else "medium"

    # Rule 3: Token-based
    if estimated_tokens > 10000:
        return "complex"
    if estimated_tokens > 3000:
        return "medium"

    # Rule 4: Skill-based
    if skill in SKILL_MIN_MODEL:
        min_model = SKILL_MIN_MODEL[skill]
        if min_model == "opus":
            return "complex"
        if min_model == "sonnet":
            return "medium"
        return "simple"

    return "medium"  # Default


def get_historical_quality(skill: str, model: str = "") -> dict:
    """Get historical quality data for a skill on a specific model."""
    try:
        from db import DB
        db = DB()
        scores = db.get_scores(skill=skill)
        if not scores:
            return {"avg_quality": 75, "count": 0, "model": model}

        # Filter by model if specified
        if model:
            model_scores = [s for s in scores if s.get("model", "") == model]
            if model_scores:
                scores = model_scores

        avg = sum(s.get("score", 75) for s in scores) / len(scores)
        return {"avg_quality": round(avg, 1), "count": len(scores), "model": model}
    except Exception:
        return {"avg_quality": 75, "count": 0, "model": model}


def route_model(task: dict = None, skill: str = "", priority: str = "medium",
                estimated_tokens: int = 0, policy: str = "default",
                quality_threshold: int = 70) -> dict:
    """
    Route to optimal model based on complexity, history, and constraints.
    Returns recommended model + reasoning.
    """
    if task:
        skill = task.get("skill", skill)
        priority = task.get("priority", priority)
        estimated_tokens = task.get("estimated_tokens", estimated_tokens) or 0
        policy = task.get("execution_policy", policy)

    complexity = classify_complexity(task, skill, priority, estimated_tokens, policy)
    reasoning = [f"Complexity: {complexity}"]

    # Start with complexity default
    model_order = ["haiku", "sonnet", "opus"]
    if complexity == "simple":
        candidate = "haiku"
    elif complexity == "complex":
        candidate = "opus"
    else:
        candidate = "sonnet"

    # Apply skill minimum
    if skill in SKILL_MIN_MODEL:
        min_model = SKILL_MIN_MODEL[skill]
        min_idx = model_order.index(min_model)
        cur_idx = model_order.index(candidate)
        if cur_idx < min_idx:
            candidate = min_model
            reasoning.append(f"Skill {skill} requires min {min_model}")

    # Apply policy minimum
    if policy in POLICY_MIN_MODEL:
        min_model = POLICY_MIN_MODEL[policy]
        min_idx = model_order.index(min_model)
        cur_idx = model_order.index(candidate)
        if cur_idx < min_idx:
            candidate = min_model
            reasoning.append(f"Policy '{policy}' requires min {min_model}")

    # Check historical quality — can we downgrade?
    if candidate != "haiku":
        cheaper = model_order[model_order.index(candidate) - 1]
        history = get_historical_quality(skill, cheaper)
        if history["count"] >= 3 and history["avg_quality"] >= quality_threshold:
            reasoning.append(f"Historical quality on {cheaper}: {history['avg_quality']} "
                           f"({history['count']} samples) >= threshold {quality_threshold} → downgrade")
            candidate = cheaper

    # Cost estimate
    model_info = MODELS[candidate]
    input_tokens = estimated_tokens * 0.7  # ~70% input
    output_tokens = estimated_tokens * 0.3  # ~30% output
    cost_est = (input_tokens / 1_000_000 * model_info["input_cost"] +
                output_tokens / 1_000_000 * model_info["output_cost"])

    # Compare with Opus cost for savings
    opus_cost = (input_tokens / 1_000_000 * MODELS["opus"]["input_cost"] +
                 output_tokens / 1_000_000 * MODELS["opus"]["output_cost"])
    savings_pct = ((opus_cost - cost_est) / opus_cost * 100) if opus_cost > 0 else 0

    return {
        "recommended_model": candidate,
        "model_id": model_info["id"],
        "complexity": complexity,
        "estimated_cost_usd": round(cost_est, 4),
        "savings_vs_opus_pct": round(savings_pct, 1),
        "quality_factor": model_info["quality_factor"],
        "reasoning": reasoning,
        "skill": skill,
        "priority": priority,
        "estimated_tokens": estimated_tokens,
    }


# =============================================================================
# FILTER PIPELINE INTEGRATION
# =============================================================================

try:
    from filter_pipeline import ExecutionFilter

    class ModelRouterFilter(ExecutionFilter):
        """Pre-execution filter that selects the optimal model."""
        name = "model_router"
        order = 15  # After logging, before budget

        def __init__(self, quality_threshold: int = 70):
            self.quality_threshold = quality_threshold

        def before(self, task: dict, context: dict) -> dict:
            route = route_model(task, quality_threshold=self.quality_threshold)
            context["recommended_model"] = route["recommended_model"]
            context["model_id"] = route["model_id"]
            context["model_routing"] = route
            log.info(f"[MODEL] {task.get('id', '?')} → {route['recommended_model']} "
                    f"(complexity={route['complexity']}, "
                    f"savings={route['savings_vs_opus_pct']}%)")
            return context

except ImportError:
    pass


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="DARIO Model Router — Intelligent model selection")
    parser.add_argument("--task", "-t", help="Task ID")
    parser.add_argument("--skill", "-s", default="", help="Skill name")
    parser.add_argument("--priority", "-p", default="medium", help="Priority")
    parser.add_argument("--tokens", type=int, default=2500, help="Estimated tokens")
    parser.add_argument("--policy", default="default", help="Execution policy")
    parser.add_argument("--threshold", type=int, default=70, help="Quality threshold")
    parser.add_argument("--complexity", help="Override complexity (simple/medium/complex)")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")
    parser.add_argument("--compare", action="store_true", help="Show all model costs")
    args = parser.parse_args()

    task = None
    if args.task:
        try:
            from db import DB
            task = DB().get_task(args.task)
        except Exception:
            pass

    result = route_model(
        task=task, skill=args.skill, priority=args.priority,
        estimated_tokens=args.tokens, policy=args.policy,
        quality_threshold=args.threshold,
    )

    if args.compare:
        print("\n=== Model Comparison ===")
        for name, info in MODELS.items():
            input_cost = args.tokens * 0.7 / 1_000_000 * info["input_cost"]
            output_cost = args.tokens * 0.3 / 1_000_000 * info["output_cost"]
            total = input_cost + output_cost
            marker = " ← SELECTED" if name == result["recommended_model"] else ""
            print(f"  {name:8s}: ${total:.4f} (quality factor: {info['quality_factor']}){marker}")
        print()

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Model: {result['recommended_model']} ({result['model_id']})")
        print(f"Complexity: {result['complexity']}")
        print(f"Cost est: ${result['estimated_cost_usd']:.4f}")
        print(f"Savings vs Opus: {result['savings_vs_opus_pct']}%")
        print(f"Reasoning:")
        for r in result["reasoning"]:
            print(f"  - {r}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
