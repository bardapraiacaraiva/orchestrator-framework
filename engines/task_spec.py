#!/usr/bin/env python3
"""
DARIO Task Specification Engine — TASK-FORMAT-SPEC-V1 (adopted from AIOX).
=========================================================================
Validates, enriches, and enforces task specifications before execution.

Executor types:
    agente  — AI-powered (Claude API), creative/analytical tasks
    worker  — Script-based, deterministic execution
    humano  — Manual human execution, approval gates
    clone   — AI with domain-specific methodology (Hormozi, Kapferer, etc.)

Usage:
    python task_spec.py --validate TASK-ID        # Validate a task
    python task_spec.py --enrich TASK-ID          # Auto-fill missing spec fields
    python task_spec.py --template SKILL          # Generate template for skill
    python task_spec.py --check-pre TASK-ID       # Run pre-conditions
    python task_spec.py --check-post TASK-ID      # Run post-conditions
    python task_spec.py --json
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
log = logging.getLogger("task_spec")

# =============================================================================
# EXECUTOR TYPES
# =============================================================================

EXECUTOR_TYPES = {
    "agente": {
        "description": "AI-powered execution via Claude API",
        "requires_api": True,
        "cost_range": "$0.01-$0.25",
        "duration_range": "5-60s",
        "deterministic": False,
    },
    "worker": {
        "description": "Script-based deterministic execution",
        "requires_api": False,
        "cost_range": "$0-$0.001",
        "duration_range": "<1s",
        "deterministic": True,
    },
    "humano": {
        "description": "Manual human execution with approval gate",
        "requires_api": False,
        "cost_range": "$5-$50/h",
        "duration_range": "minutes-hours",
        "deterministic": False,
    },
    "clone": {
        "description": "AI with domain-specific methodology/heuristics",
        "requires_api": True,
        "cost_range": "$0.02-$0.30",
        "duration_range": "10-90s",
        "deterministic": False,
    },
}

# =============================================================================
# SKILL → DEFAULT SPEC MAPPING
# =============================================================================

SKILL_SPECS = {
    # Marketing skills
    "dario-brand": {
        "executor_type": "clone",
        "methodology": "Kapferer Identity Prism + Archetype Theory",
        "inputs": [
            {"campo": "client_name", "tipo": "string", "obrigatorio": True},
            {"campo": "sector", "tipo": "string", "obrigatorio": True},
            {"campo": "market", "tipo": "string", "obrigatorio": False, "padrao": "Lisboa, Portugal"},
            {"campo": "competitors", "tipo": "array<string>", "obrigatorio": False},
        ],
        "outputs": [
            {"campo": "brand_document", "tipo": "markdown", "destino": "obsidian", "persistido": True},
            {"campo": "identity_prism", "tipo": "object", "destino": "chain_next"},
            {"campo": "archetypes", "tipo": "object", "destino": "chain_next"},
        ],
        "performance": {"duration_expected": 15000, "cost_estimated": 0.06, "cacheable": True},
        "error_handling": {"strategy": "retry", "max_attempts": 2, "fallback": "Generic brand template"},
    },
    "dario-offer": {
        "executor_type": "clone",
        "methodology": "Alex Hormozi Grand Slam Offer",
        "inputs": [
            {"campo": "client_name", "tipo": "string", "obrigatorio": True},
            {"campo": "service_description", "tipo": "string", "obrigatorio": True},
            {"campo": "target_audience", "tipo": "string", "obrigatorio": True},
            {"campo": "price_range", "tipo": "string", "obrigatorio": False},
        ],
        "outputs": [
            {"campo": "offer_document", "tipo": "markdown", "destino": "obsidian", "persistido": True},
            {"campo": "value_equation", "tipo": "object", "destino": "chain_next"},
        ],
        "performance": {"duration_expected": 10000, "cost_estimated": 0.05, "cacheable": True},
        "error_handling": {"strategy": "retry", "max_attempts": 2},
    },
    "dario-story-circle": {
        "executor_type": "clone",
        "methodology": "Dan Harmon Story Circle (8 beats)",
        "inputs": [
            {"campo": "client_name", "tipo": "string", "obrigatorio": True},
            {"campo": "brand_identity", "tipo": "object", "origem": "dario-brand", "obrigatorio": False},
        ],
        "outputs": [
            {"campo": "story_document", "tipo": "markdown", "destino": "obsidian", "persistido": True},
            {"campo": "about_page_copy", "tipo": "string", "destino": "chain_next"},
            {"campo": "gbp_description", "tipo": "string", "destino": "seo-local"},
            {"campo": "social_versions", "tipo": "array<string>", "destino": "dario-social"},
        ],
        "performance": {"duration_expected": 15000, "cost_estimated": 0.06, "cacheable": True},
        "error_handling": {"strategy": "retry", "max_attempts": 2},
    },
    "dario-sales-letter": {
        "executor_type": "clone",
        "methodology": "Gary Halbert / PAS / AIDA",
        "inputs": [
            {"campo": "client_name", "tipo": "string", "obrigatorio": True},
            {"campo": "offer", "tipo": "object", "origem": "dario-offer", "obrigatorio": False},
            {"campo": "target_audience", "tipo": "string", "obrigatorio": True},
        ],
        "outputs": [
            {"campo": "sales_letter", "tipo": "markdown", "destino": "obsidian", "persistido": True},
        ],
        "performance": {"duration_expected": 12000, "cost_estimated": 0.06, "cacheable": True},
        "error_handling": {"strategy": "retry", "max_attempts": 2},
    },
    "dario-email-seq": {
        "executor_type": "clone",
        "methodology": "Russell Brunson SOAP Opera Sequence",
        "inputs": [
            {"campo": "client_name", "tipo": "string", "obrigatorio": True},
            {"campo": "sequence_goal", "tipo": "string", "obrigatorio": True},
            {"campo": "num_emails", "tipo": "number", "obrigatorio": False, "padrao": 5},
        ],
        "outputs": [
            {"campo": "email_sequence", "tipo": "markdown", "destino": "obsidian", "persistido": True},
        ],
        "performance": {"duration_expected": 18000, "cost_estimated": 0.08, "cacheable": True},
        "error_handling": {"strategy": "retry", "max_attempts": 2},
    },
    "dario-diagnose": {
        "executor_type": "agente",
        "inputs": [
            {"campo": "client_name", "tipo": "string", "obrigatorio": True},
            {"campo": "website_url", "tipo": "string", "obrigatorio": False},
            {"campo": "sector", "tipo": "string", "obrigatorio": True},
        ],
        "outputs": [
            {"campo": "diagnostic_report", "tipo": "markdown", "destino": "obsidian", "persistido": True},
            {"campo": "scores_by_area", "tipo": "object", "destino": "chain_next"},
            {"campo": "priority_actions", "tipo": "array<string>", "destino": "chain_next"},
        ],
        "performance": {"duration_expected": 20000, "cost_estimated": 0.09, "cacheable": False},
        "error_handling": {"strategy": "retry", "max_attempts": 2},
    },
    "dario-financial-model": {
        "executor_type": "agente",
        "inputs": [
            {"campo": "client_name", "tipo": "string", "obrigatorio": True},
            {"campo": "business_type", "tipo": "string", "obrigatorio": True},
            {"campo": "revenue_model", "tipo": "string", "obrigatorio": False},
            {"campo": "monthly_costs", "tipo": "object", "obrigatorio": False},
        ],
        "outputs": [
            {"campo": "financial_model", "tipo": "markdown", "destino": "obsidian", "persistido": True},
            {"campo": "pnl_summary", "tipo": "object", "destino": "chain_next"},
        ],
        "performance": {"duration_expected": 20000, "cost_estimated": 0.10, "cacheable": True},
        "error_handling": {"strategy": "retry", "max_attempts": 2},
    },
    # SEO skills
    "seo-audit": {
        "executor_type": "agente",
        "inputs": [
            {"campo": "website_url", "tipo": "string", "obrigatorio": True},
            {"campo": "client_name", "tipo": "string", "obrigatorio": True},
        ],
        "outputs": [
            {"campo": "audit_report", "tipo": "markdown", "destino": "obsidian", "persistido": True},
            {"campo": "issues_list", "tipo": "array<object>", "destino": "chain_next"},
            {"campo": "priority_fixes", "tipo": "array<string>", "destino": "seo-technical"},
        ],
        "performance": {"duration_expected": 30000, "cost_estimated": 0.19, "cacheable": False},
        "error_handling": {"strategy": "retry", "max_attempts": 2},
    },
    "seo-schema": {
        "executor_type": "worker",
        "inputs": [
            {"campo": "website_url", "tipo": "string", "obrigatorio": True},
            {"campo": "business_type", "tipo": "string", "obrigatorio": True},
            {"campo": "business_name", "tipo": "string", "obrigatorio": True},
        ],
        "outputs": [
            {"campo": "jsonld_code", "tipo": "string", "destino": "obsidian", "persistido": True},
            {"campo": "schema_types", "tipo": "array<string>", "destino": "chain_next"},
        ],
        "performance": {"duration_expected": 20000, "cost_estimated": 0.12, "cacheable": True},
        "error_handling": {"strategy": "retry", "max_attempts": 2},
    },
    # DIVA skills
    "diva-moodboard": {
        "executor_type": "clone",
        "methodology": "Interior Design Color Theory + Material Science",
        "inputs": [
            {"campo": "space_type", "tipo": "string", "obrigatorio": True},
            {"campo": "area_m2", "tipo": "number", "obrigatorio": True},
            {"campo": "style", "tipo": "string", "obrigatorio": True},
            {"campo": "budget_range", "tipo": "string", "obrigatorio": False},
            {"campo": "location", "tipo": "string", "obrigatorio": False, "padrao": "Lisboa"},
        ],
        "outputs": [
            {"campo": "moodboard_document", "tipo": "markdown", "destino": "obsidian", "persistido": True},
            {"campo": "color_palette", "tipo": "object", "destino": "chain_next"},
            {"campo": "materials_list", "tipo": "array<object>", "destino": "diva-materials"},
        ],
        "performance": {"duration_expected": 25000, "cost_estimated": 0.14, "cacheable": True},
        "error_handling": {"strategy": "retry", "max_attempts": 2},
    },
    "diva-budget": {
        "executor_type": "agente",
        "inputs": [
            {"campo": "space_type", "tipo": "string", "obrigatorio": True},
            {"campo": "area_m2", "tipo": "number", "obrigatorio": True},
            {"campo": "scope", "tipo": "string", "obrigatorio": True},
            {"campo": "location", "tipo": "string", "obrigatorio": True},
        ],
        "outputs": [
            {"campo": "budget_document", "tipo": "markdown", "destino": "obsidian", "persistido": True},
            {"campo": "total_cost", "tipo": "object", "destino": "chain_next"},
        ],
        "performance": {"duration_expected": 25000, "cost_estimated": 0.16, "cacheable": True},
        "error_handling": {"strategy": "retry", "max_attempts": 2},
    },
    "dario-legal": {
        "executor_type": "agente",
        "inputs": [
            {"campo": "document_type", "tipo": "string", "obrigatorio": True},
            {"campo": "parties", "tipo": "array<string>", "obrigatorio": True},
            {"campo": "jurisdiction", "tipo": "string", "obrigatorio": False, "padrao": "Portugal"},
        ],
        "outputs": [
            {"campo": "legal_document", "tipo": "markdown", "destino": "obsidian", "persistido": True},
        ],
        "performance": {"duration_expected": 25000, "cost_estimated": 0.13, "cacheable": False},
        "error_handling": {"strategy": "fallback", "fallback": "Redirect to licensed lawyer"},
    },
    "dario-sop": {
        "executor_type": "agente",
        "inputs": [
            {"campo": "process_name", "tipo": "string", "obrigatorio": True},
            {"campo": "department", "tipo": "string", "obrigatorio": True},
            {"campo": "roles", "tipo": "array<string>", "obrigatorio": False},
        ],
        "outputs": [
            {"campo": "sop_document", "tipo": "markdown", "destino": "obsidian", "persistido": True},
            {"campo": "checklist", "tipo": "array<string>", "destino": "chain_next"},
        ],
        "performance": {"duration_expected": 40000, "cost_estimated": 0.25, "cacheable": True},
        "error_handling": {"strategy": "retry", "max_attempts": 2},
    },
}

# Default spec for skills not explicitly mapped
DEFAULT_SPEC = {
    "executor_type": "agente",
    "inputs": [
        {"campo": "client_name", "tipo": "string", "obrigatorio": True},
        {"campo": "project_context", "tipo": "string", "obrigatorio": False},
    ],
    "outputs": [
        {"campo": "deliverable", "tipo": "markdown", "destino": "obsidian", "persistido": True},
    ],
    "performance": {"duration_expected": 20000, "cost_estimated": 0.10, "cacheable": True},
    "error_handling": {"strategy": "retry", "max_attempts": 2},
}

# =============================================================================
# PRE/POST CONDITIONS
# =============================================================================

DEFAULT_CHECKLIST = {
    "pre": [
        {"tipo": "required_fields", "blocker": True, "validacao": "title and skill are not empty"},
        {"tipo": "budget_check", "blocker": True, "validacao": "monthly budget < 95%"},
        {"tipo": "dependencies", "blocker": True, "validacao": "all depends_on tasks are done"},
    ],
    "post": [
        {"tipo": "output_not_empty", "blocker": False, "validacao": "completion_comment length > 500"},
        {"tipo": "quality_gate", "blocker": False, "validacao": "quality_score >= 60"},
    ],
    "acceptance": [
        {"tipo": "deliverable_complete", "manual": True, "validacao": "all outputs listed in spec are present"},
    ],
}


# =============================================================================
# VALIDATION
# =============================================================================

def validate_task(task: dict) -> dict:
    """Validate a task against TASK-FORMAT-SPEC-V1."""
    errors = []
    warnings = []

    # Required fields
    for field in ["id", "title", "skill"]:
        if not task.get(field):
            errors.append(f"Missing required field: {field}")

    # Executor type
    etype = task.get("executor_type", "agente")
    if etype not in EXECUTOR_TYPES:
        errors.append(f"Invalid executor_type: {etype}. Must be one of: {list(EXECUTOR_TYPES.keys())}")

    # Inputs validation
    inputs = task.get("inputs")
    if inputs:
        if isinstance(inputs, str):
            try:
                inputs = json.loads(inputs)
            except json.JSONDecodeError:
                errors.append("inputs is not valid JSON")
                inputs = []
        for inp in inputs:
            if not inp.get("campo"):
                warnings.append(f"Input missing 'campo' field")
            if not inp.get("tipo"):
                warnings.append(f"Input '{inp.get('campo', '?')}' missing 'tipo'")

    # Performance
    perf = task.get("performance")
    if perf:
        if isinstance(perf, str):
            try:
                perf = json.loads(perf)
            except json.JSONDecodeError:
                warnings.append("performance is not valid JSON")
                perf = {}
        if not perf.get("duration_expected"):
            warnings.append("performance.duration_expected not set")
        if not perf.get("cost_estimated"):
            warnings.append("performance.cost_estimated not set")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "spec_version": "TASK-FORMAT-SPEC-V1",
    }


def enrich_task(task_id: str) -> dict:
    """Auto-fill missing spec fields from SKILL_SPECS defaults."""
    db = DB()
    task = db.get_task(task_id)
    if not task:
        return {"error": f"Task {task_id} not found"}

    skill = task.get("skill", "")
    spec = SKILL_SPECS.get(skill, DEFAULT_SPEC)

    updates = {}

    # Executor type
    if not task.get("executor_type") or task.get("executor_type") == "agente":
        updates["executor_type"] = spec.get("executor_type", "agente")

    # Inputs (only if empty)
    current_inputs = task.get("inputs", "[]")
    if current_inputs in ("[]", "", None):
        updates["inputs"] = json.dumps(spec.get("inputs", []))

    # Outputs (only if empty)
    current_outputs = task.get("outputs", "[]")
    if current_outputs in ("[]", "", None):
        updates["outputs"] = json.dumps(spec.get("outputs", []))

    # Checklist (only if empty)
    current_cl = task.get("checklist", "{}")
    if current_cl in ("{}", "", None):
        updates["checklist"] = json.dumps(DEFAULT_CHECKLIST)

    # Performance
    current_perf = task.get("performance", "{}")
    if current_perf in ("{}", "", None):
        updates["performance"] = json.dumps(spec.get("performance", {}))

    # Error handling
    current_eh = task.get("error_handling", "{}")
    if current_eh in ("{}", "", None):
        updates["error_handling"] = json.dumps(spec.get("error_handling", {}))

    # Cache key
    if not task.get("cache_key") and spec.get("performance", {}).get("cacheable"):
        project = task.get("project", "")
        updates["cache_key"] = f"{skill}_{project}_{task_id}"

    # Apply updates
    if updates:
        with db._conn() as conn:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [task_id]
            conn.execute(f"UPDATE tasks SET {set_clause} WHERE id = ?", values)
        log.info(f"Enriched {task_id}: {list(updates.keys())}")

    return {
        "task_id": task_id,
        "enriched_fields": list(updates.keys()),
        "executor_type": updates.get("executor_type", task.get("executor_type", "agente")),
        "spec_version": "TASK-FORMAT-SPEC-V1",
    }


def check_preconditions(task_id: str) -> dict:
    """Run pre-conditions for a task. Returns pass/fail with blockers."""
    db = DB()
    task = db.get_task(task_id)
    if not task:
        return {"pass": False, "blockers": [f"Task {task_id} not found"]}

    checklist = task.get("checklist", "{}")
    if isinstance(checklist, str):
        try:
            checklist = json.loads(checklist)
        except json.JSONDecodeError:
            checklist = DEFAULT_CHECKLIST

    results = []
    blockers = []

    for pre in checklist.get("pre", DEFAULT_CHECKLIST["pre"]):
        tipo = pre.get("tipo", "")
        passed = True
        reason = ""

        if tipo == "required_fields":
            if not task.get("title") or not task.get("skill"):
                passed = False
                reason = "title or skill is empty"

        elif tipo == "budget_check":
            try:
                import yaml
                from datetime import datetime
                budget_path = ORCH_DIR / "budgets" / f"{datetime.now().strftime('%Y-%m')}.yaml"
                if budget_path.exists():
                    with open(budget_path) as f:
                        budget = yaml.safe_load(f)
                    if budget.get("percentage", 0) >= 95:
                        passed = False
                        reason = f"Budget at {budget['percentage']}% (>= 95%)"
            except Exception:
                pass  # Budget check non-critical

        elif tipo == "dependencies":
            deps = task.get("depends_on", "[]")
            if isinstance(deps, str):
                try:
                    deps = json.loads(deps)
                except json.JSONDecodeError:
                    deps = []
            for dep_id in deps:
                dep_task = db.get_task(dep_id)
                if dep_task and dep_task.get("status") != "done":
                    passed = False
                    reason = f"Dependency {dep_id} not done (status: {dep_task.get('status')})"
                    break

        results.append({"tipo": tipo, "passed": passed, "reason": reason})
        if not passed and pre.get("blocker", False):
            blockers.append(f"[BLOCKER] {tipo}: {reason}")

    return {
        "pass": len(blockers) == 0,
        "blockers": blockers,
        "results": results,
    }


def check_postconditions(task_id: str) -> dict:
    """Run post-conditions after task execution."""
    db = DB()
    task = db.get_task(task_id)
    if not task:
        return {"pass": False, "issues": [f"Task {task_id} not found"]}

    checklist = task.get("checklist", "{}")
    if isinstance(checklist, str):
        try:
            checklist = json.loads(checklist)
        except json.JSONDecodeError:
            checklist = DEFAULT_CHECKLIST

    results = []
    issues = []

    for post in checklist.get("post", DEFAULT_CHECKLIST["post"]):
        tipo = post.get("tipo", "")
        passed = True
        reason = ""

        if tipo == "output_not_empty":
            comment = task.get("completion_comment", "")
            if not comment or len(comment) < 500:
                passed = False
                reason = f"Output too short ({len(comment or '')} chars, min 500)"

        elif tipo == "quality_gate":
            score = task.get("quality_score")
            if score is not None and score < 60:
                passed = False
                reason = f"Quality score {score} below threshold 60"

        results.append({"tipo": tipo, "passed": passed, "reason": reason})
        if not passed:
            issues.append(f"{tipo}: {reason}")

    return {
        "pass": len(issues) == 0,
        "issues": issues,
        "results": results,
    }


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="DARIO Task Spec Engine (TASK-FORMAT-SPEC-V1)")
    parser.add_argument("--validate", "-v", help="Validate task by ID")
    parser.add_argument("--enrich", "-e", help="Auto-enrich task spec by ID")
    parser.add_argument("--check-pre", help="Run pre-conditions for task ID")
    parser.add_argument("--check-post", help="Run post-conditions for task ID")
    parser.add_argument("--template", "-t", help="Show default spec for a skill")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")

    args = parser.parse_args()
    if args.json:
        logging.getLogger().setLevel(logging.ERROR)

    result = {}

    if args.validate:
        db = DB()
        task = db.get_task(args.validate)
        if task:
            result = validate_task(task)
        else:
            result = {"valid": False, "errors": [f"Task {args.validate} not found"]}

    elif args.enrich:
        result = enrich_task(args.enrich)

    elif args.check_pre:
        result = check_preconditions(args.check_pre)

    elif args.check_post:
        result = check_postconditions(args.check_post)

    elif args.template:
        spec = SKILL_SPECS.get(args.template, DEFAULT_SPEC)
        result = {"skill": args.template, "spec": spec, "version": "TASK-FORMAT-SPEC-V1"}

    else:
        result = {
            "skills_mapped": len(SKILL_SPECS),
            "executor_types": list(EXECUTOR_TYPES.keys()),
            "version": "TASK-FORMAT-SPEC-V1",
        }

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        for k, v in result.items():
            print(f"{k}: {v}")

    return 0 if result.get("valid", True) else 1


if __name__ == "__main__":
    sys.exit(main())
