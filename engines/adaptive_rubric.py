#!/usr/bin/env python3
"""
DARIO Adaptive Rubrics — Contextual scoring per task type.
============================================================
Generates scoring criteria dynamically based on task description,
skill type, execution policy, and project domain. Not fixed 5 dimensions.

Inspired by AdaRubric (2026): score what MATTERS for THIS specific task.

Usage:
    python adaptive_rubric.py --task MNB-002                  # Generate rubric for task
    python adaptive_rubric.py --skill dario-brand --policy client_facing
    python adaptive_rubric.py --task MNB-002 --json

Returns a rubric with:
    - Dimensions (3-7, context-dependent)
    - Weights per dimension (sum to 1.0)
    - Pass/fail criteria specific to the task
    - Scoring guide per dimension

Exit codes:
    0 = rubric generated
    1 = error
"""

import argparse
import json
import logging
import sys
from pathlib import Path

try:
    from ruamel.yaml import YAML
    yaml_engine = YAML()
    yaml_engine.preserve_quotes = True
    def load_yaml(path):
        with open(path, 'r', encoding='utf-8') as f:
            return yaml_engine.load(f)
except ImportError:
    import yaml
    def load_yaml(path):
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)


ORCH_DIR = Path.home() / ".claude" / "orchestrator"
TASKS_DIR = ORCH_DIR / "tasks" / "active"

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("rubric")


# =============================================================================
# DIMENSION LIBRARY — pool of possible dimensions
# =============================================================================

DIMENSION_POOL = {
    # Universal dimensions (always available)
    "specificity": {
        "name": "Specificity",
        "desc": "Output is specific to THIS client/project, not generic",
        "scoring": "1.0=names client, uses their data | 0.5=somewhat specific | 0=could be anyone",
    },
    "actionability": {
        "name": "Actionability",
        "desc": "Client can act on this immediately with clear next steps",
        "scoring": "1.0=concrete steps, no ambiguity | 0.5=some steps clear | 0=vague",
    },
    "completeness": {
        "name": "Completeness",
        "desc": "All requirements from task description are covered",
        "scoring": "1.0=all covered | 0.5=most covered | 0=significant gaps",
    },
    "accuracy": {
        "name": "Accuracy",
        "desc": "Facts, data, recommendations are correct and verifiable",
        "scoring": "1.0=verified/sourced | 0.5=mostly correct | 0=contains errors",
    },
    "tone": {
        "name": "Tone & Format",
        "desc": "Matches expected brand voice and deliverable format",
        "scoring": "1.0=client-ready | 0.5=minor edits needed | 0=wrong tone/format",
    },

    # Domain-specific dimensions
    "creativity": {
        "name": "Creative Quality",
        "desc": "Original, memorable, distinctive from competitors",
        "scoring": "1.0=highly original | 0.5=competent but safe | 0=generic/cliché",
    },
    "technical_depth": {
        "name": "Technical Depth",
        "desc": "Demonstrates deep technical understanding, not surface-level",
        "scoring": "1.0=expert-level analysis | 0.5=competent overview | 0=superficial",
    },
    "data_backed": {
        "name": "Data-Backed",
        "desc": "Claims supported by numbers, benchmarks, or evidence",
        "scoring": "1.0=all claims with data | 0.5=some data | 0=opinions only",
    },
    "pt_compliance": {
        "name": "Portuguese Compliance",
        "desc": "Adheres to PT regulations (RGPD, AT, labor law, building codes)",
        "scoring": "1.0=fully compliant | 0.5=mostly | 0=non-compliant or ignores",
    },
    "client_readiness": {
        "name": "Client-Ready",
        "desc": "Can be delivered directly to client without internal edits",
        "scoring": "1.0=send immediately | 0.5=light formatting | 0=needs rewrite",
    },
    "strategic_coherence": {
        "name": "Strategic Coherence",
        "desc": "Aligned with broader project strategy and previous decisions",
        "scoring": "1.0=perfectly aligned | 0.5=mostly | 0=contradicts strategy",
    },
    "seo_impact": {
        "name": "SEO Impact",
        "desc": "Will measurably improve search visibility/rankings",
        "scoring": "1.0=high impact, clear KPIs | 0.5=moderate | 0=no SEO value",
    },
    "financial_accuracy": {
        "name": "Financial Accuracy",
        "desc": "Numbers are correct, formulas valid, assumptions stated",
        "scoring": "1.0=auditable | 0.5=reasonable estimates | 0=numbers don't add up",
    },
    "visual_quality": {
        "name": "Visual/Spatial Quality",
        "desc": "Design decisions are well-justified, proportions correct",
        "scoring": "1.0=professional quality | 0.5=competent | 0=poor spatial awareness",
    },
}


# =============================================================================
# RUBRIC PROFILES — which dimensions matter for which skill type
# =============================================================================

SKILL_PROFILES = {
    # Brand & Copy
    "dario-brand": {
        "dimensions": ["specificity", "creativity", "strategic_coherence", "completeness", "client_readiness"],
        "weights": [0.25, 0.25, 0.20, 0.15, 0.15],
        "pass_threshold": 70,
    },
    "dario-naming": {
        "dimensions": ["creativity", "specificity", "actionability", "completeness"],
        "weights": [0.30, 0.25, 0.25, 0.20],
        "pass_threshold": 65,
    },
    "dario-offer": {
        "dimensions": ["specificity", "actionability", "data_backed", "strategic_coherence", "completeness"],
        "weights": [0.25, 0.20, 0.20, 0.20, 0.15],
        "pass_threshold": 70,
    },
    "dario-sales-letter": {
        "dimensions": ["creativity", "tone", "specificity", "actionability"],
        "weights": [0.30, 0.30, 0.20, 0.20],
        "pass_threshold": 70,
    },
    "dario-email-seq": {
        "dimensions": ["tone", "actionability", "strategic_coherence", "completeness"],
        "weights": [0.25, 0.25, 0.25, 0.25],
        "pass_threshold": 65,
    },

    # Technical
    "dario-wp-audit": {
        "dimensions": ["technical_depth", "completeness", "actionability", "accuracy"],
        "weights": [0.30, 0.25, 0.25, 0.20],
        "pass_threshold": 70,
    },
    "dario-cwv-fix": {
        "dimensions": ["accuracy", "technical_depth", "completeness", "data_backed"],
        "weights": [0.30, 0.30, 0.20, 0.20],
        "pass_threshold": 75,
    },

    # SEO
    "seo-audit": {
        "dimensions": ["technical_depth", "completeness", "actionability", "seo_impact", "accuracy"],
        "weights": [0.25, 0.20, 0.20, 0.20, 0.15],
        "pass_threshold": 70,
    },
    "seo-local": {
        "dimensions": ["specificity", "seo_impact", "actionability", "completeness", "accuracy"],
        "weights": [0.25, 0.25, 0.20, 0.15, 0.15],
        "pass_threshold": 70,
    },
    "seo-plan": {
        "dimensions": ["strategic_coherence", "seo_impact", "actionability", "data_backed", "completeness"],
        "weights": [0.25, 0.25, 0.20, 0.15, 0.15],
        "pass_threshold": 70,
    },

    # Finance
    "dario-financial-model": {
        "dimensions": ["financial_accuracy", "completeness", "data_backed", "actionability"],
        "weights": [0.35, 0.25, 0.25, 0.15],
        "pass_threshold": 80,
    },
    "dario-pricing-calculator": {
        "dimensions": ["financial_accuracy", "accuracy", "completeness", "actionability"],
        "weights": [0.30, 0.30, 0.20, 0.20],
        "pass_threshold": 75,
    },

    # DIVA (Architecture)
    "diva-budget": {
        "dimensions": ["financial_accuracy", "completeness", "pt_compliance", "data_backed"],
        "weights": [0.30, 0.25, 0.25, 0.20],
        "pass_threshold": 75,
    },
    "diva-floor-plan": {
        "dimensions": ["visual_quality", "completeness", "specificity", "pt_compliance"],
        "weights": [0.30, 0.25, 0.25, 0.20],
        "pass_threshold": 70,
    },
    "diva-licensing": {
        "dimensions": ["pt_compliance", "accuracy", "completeness", "actionability"],
        "weights": [0.35, 0.25, 0.20, 0.20],
        "pass_threshold": 80,
    },

    # Diagnose
    "dario-diagnose": {
        "dimensions": ["completeness", "actionability", "accuracy", "specificity", "strategic_coherence"],
        "weights": [0.25, 0.25, 0.20, 0.15, 0.15],
        "pass_threshold": 65,
    },
}

# Policy modifiers
POLICY_MODIFIERS = {
    "critical": {"pass_threshold_boost": 10, "add_dimensions": ["accuracy"]},
    "client_facing": {"pass_threshold_boost": 5, "add_dimensions": ["client_readiness"]},
    "financial": {"pass_threshold_boost": 10, "add_dimensions": ["financial_accuracy"]},
    "default": {"pass_threshold_boost": 0, "add_dimensions": []},
}


# =============================================================================
# RUBRIC GENERATION
# =============================================================================

def generate_rubric(task_id: str = "", skill: str = "", policy: str = "default",
                    project: str = "", description: str = "") -> dict:
    """Generate adaptive rubric for a task."""

    # Load task data if task_id provided
    if task_id:
        task_file = TASKS_DIR / f"{task_id}.yaml"
        if task_file.exists():
            task_data = load_yaml(str(task_file)) or {}
            if not skill:
                skill = task_data.get("skill", "")
            if not policy:
                policy = task_data.get("execution_policy", "default")
            if not project:
                project = task_data.get("project", "")
            if not description:
                description = task_data.get("description", task_data.get("title", ""))

    # Get base profile for skill
    profile = SKILL_PROFILES.get(skill, {
        "dimensions": ["specificity", "actionability", "completeness", "accuracy", "tone"],
        "weights": [0.25, 0.20, 0.20, 0.25, 0.10],
        "pass_threshold": 60,
    })

    dimensions = list(profile["dimensions"])
    weights = list(profile["weights"])
    pass_threshold = profile["pass_threshold"]

    # Apply policy modifiers
    modifier = POLICY_MODIFIERS.get(policy, POLICY_MODIFIERS["default"])
    pass_threshold += modifier["pass_threshold_boost"]

    for dim in modifier["add_dimensions"]:
        if dim not in dimensions:
            dimensions.append(dim)
            # Redistribute weights
            new_weight = 0.10
            scale = (1.0 - new_weight) / sum(weights)
            weights = [w * scale for w in weights]
            weights.append(new_weight)

    # Normalize weights to sum to 1.0
    total = sum(weights)
    weights = [round(w / total, 3) for w in weights]

    # Build rubric
    rubric = {
        "task_id": task_id,
        "skill": skill,
        "policy": policy,
        "project": project,
        "pass_threshold": pass_threshold,
        "dimensions_count": len(dimensions),
        "dimensions": [],
        "formula": "score = sum(weight_i * dimension_score_i) * 100",
    }

    for i, dim_key in enumerate(dimensions):
        dim_def = DIMENSION_POOL.get(dim_key, {
            "name": dim_key.replace("_", " ").title(),
            "desc": dim_key,
            "scoring": "1.0=excellent | 0.5=adequate | 0=poor",
        })
        rubric["dimensions"].append({
            "key": dim_key,
            "name": dim_def["name"],
            "description": dim_def["desc"],
            "weight": weights[i],
            "scoring_guide": dim_def["scoring"],
        })

    return rubric


def main():
    parser = argparse.ArgumentParser(description="DARIO Adaptive Rubrics")
    parser.add_argument("--task", "-t", default="", help="Task ID")
    parser.add_argument("--skill", "-s", default="", help="Skill name")
    parser.add_argument("--policy", "-p", default="default", help="Execution policy")
    parser.add_argument("--project", default="", help="Project name")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")

    args = parser.parse_args()
    if args.json:
        logging.getLogger().setLevel(logging.ERROR)

    rubric = generate_rubric(args.task, args.skill, args.policy, args.project)

    if args.json:
        print(json.dumps(rubric, indent=2))
    else:
        print(f"=== ADAPTIVE RUBRIC: {rubric['skill']} ({rubric['policy']}) ===")
        print(f"  Pass threshold: {rubric['pass_threshold']}/100")
        print(f"  Dimensions: {rubric['dimensions_count']}\n")
        for d in rubric["dimensions"]:
            print(f"  [{d['weight']:.0%}] {d['name']}")
            print(f"       {d['description']}")
            print(f"       Guide: {d['scoring_guide']}")
            print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
