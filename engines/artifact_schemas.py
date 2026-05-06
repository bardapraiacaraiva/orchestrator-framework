#!/usr/bin/env python3
"""
DARIO Artifact Schemas — Schema-validated output per skill (MetaGPT-inspired).
================================================================================
Each skill defines its expected output schema. Output is validated BEFORE passing
to the next step in a chain. Invalid output triggers auto-retry (max 3x).

Eliminates the "telephone game" where bad output propagates through chains.

Usage:
    python artifact_schemas.py --skill dario-brand --validate output.json
    python artifact_schemas.py --skill dario-brand --show-schema
    python artifact_schemas.py --list

Integration with FilterPipeline:
    from artifact_schemas import SchemaValidationFilter
    pipeline.add(SchemaValidationFilter(max_retries=3))
"""

import argparse
import json
import logging
import re
import sys
from pathlib import Path

ORCH_DIR = Path.home() / ".claude" / "orchestrator"
sys.path.insert(0, str(ORCH_DIR))

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("artifact_schemas")


# =============================================================================
# SKILL OUTPUT SCHEMAS
# Each schema defines required_fields, optional_fields, and validators.
# required_fields: must be present in output (as sections, JSON keys, or keywords)
# min_length: minimum output length in characters
# format: expected format type (text, json, markdown, yaml)
# validators: list of callable checks
# =============================================================================

SCHEMAS = {
    # --- MARKETING & BRAND ---
    "dario-brand": {
        "description": "Brand positioning output",
        "format": "markdown",
        "min_length": 500,
        "required_sections": ["posicionamento", "archetype", "diferencia", "tom de voz", "messaging"],
        "forbidden_patterns": ["TODO", "PLACEHOLDER", "[inserir"],
    },
    "dario-offer": {
        "description": "Grand Slam Offer",
        "format": "markdown",
        "min_length": 400,
        "required_sections": ["valor", "bonus", "garantia", "preco", "urgencia"],
    },
    "dario-naming": {
        "description": "Brand naming candidates",
        "format": "markdown",
        "min_length": 200,
        "required_sections": ["candidato", "dominio", "disponibilidade"],
    },
    "dario-pitch": {
        "description": "Pitch deck content",
        "format": "markdown",
        "min_length": 800,
        "required_sections": ["problema", "solucao", "mercado", "modelo", "equipa", "ask"],
    },
    "dario-sales-letter": {
        "description": "Long-form sales letter",
        "format": "markdown",
        "min_length": 1500,
        "required_sections": ["headline", "lead", "historia", "oferta", "cta"],
    },
    "dario-story-circle": {
        "description": "Brand story / origin narrative",
        "format": "markdown",
        "min_length": 500,
        "required_sections": ["protagonista", "desafio", "transformacao"],
    },
    "dario-proposal": {
        "description": "Commercial proposal 3-option",
        "format": "markdown",
        "min_length": 600,
        "required_sections": ["opcao", "scope", "investimento", "timeline"],
    },

    # --- SEO ---
    "seo-audit": {
        "description": "Full SEO audit report",
        "format": "markdown",
        "min_length": 1000,
        "required_sections": ["titulo", "meta", "performance", "mobile", "recomenda"],
    },
    "seo-local": {
        "description": "Local SEO analysis",
        "format": "markdown",
        "min_length": 400,
        "required_sections": ["gbp", "nap", "citation", "review"],
    },
    "seo-schema": {
        "description": "Schema.org structured data",
        "format": "json",
        "min_length": 100,
        "required_sections": ["@type", "@context"],
    },

    # --- TECHNICAL ---
    "dario-wp-audit": {
        "description": "WordPress audit report",
        "format": "markdown",
        "min_length": 800,
        "required_sections": ["performance", "seguranca", "seo", "plugin"],
    },
    "dario-diagnose": {
        "description": "Holistic diagnostic report",
        "format": "markdown",
        "min_length": 500,
        "required_sections": ["critico", "importante", "optimizacao"],
    },
    "dario-sop": {
        "description": "Standard Operating Procedure",
        "format": "markdown",
        "min_length": 300,
        "required_sections": ["objectivo", "passo", "responsavel"],
    },

    # --- DIVA / ARCHITECTURE ---
    "diva-briefing": {
        "description": "Client briefing document",
        "format": "markdown",
        "min_length": 400,
        "required_sections": ["projecto", "cliente", "requisito", "orcamento"],
    },
    "diva-budget": {
        "description": "Construction budget estimate",
        "format": "markdown",
        "min_length": 300,
        "required_sections": ["capitulo", "total", "m2"],
    },
    "diva-moodboard": {
        "description": "Interior design moodboard",
        "format": "markdown",
        "min_length": 300,
        "required_sections": ["estilo", "paleta", "material"],
    },

    # --- FINANCE ---
    "dario-financial-model": {
        "description": "Financial model / P&L",
        "format": "markdown",
        "min_length": 500,
        "required_sections": ["receita", "custo", "margem", "break-even"],
    },
    "dario-saas-metrics": {
        "description": "SaaS metrics dashboard",
        "format": "markdown",
        "min_length": 300,
        "required_sections": ["mrr", "churn", "ltv", "cac"],
    },
}


def validate_artifact(output: str, skill: str, strict: bool = False) -> dict:
    """Validate output against skill schema. Returns verdict + details."""
    result = {
        "skill": skill,
        "valid": True,
        "errors": [],
        "warnings": [],
        "checks": {},
    }

    schema = SCHEMAS.get(skill)
    if not schema:
        result["warnings"].append(f"No schema defined for skill '{skill}' — skipping validation")
        return result

    # Check 1: Minimum length
    output_len = len(output.strip()) if output else 0
    min_len = schema.get("min_length", 0)
    length_ok = output_len >= min_len
    result["checks"]["min_length"] = length_ok
    if not length_ok:
        result["errors"].append(f"Output too short: {output_len} chars (min: {min_len})")

    # Check 2: Required sections
    required = schema.get("required_sections", [])
    output_lower = output.lower() if output else ""
    missing = [s for s in required if s not in output_lower]
    sections_ok = len(missing) == 0
    result["checks"]["required_sections"] = sections_ok
    if not sections_ok:
        result["errors"].append(f"Missing required sections: {missing}")

    # Check 3: Format check
    fmt = schema.get("format", "text")
    format_ok = True
    if fmt == "json":
        try:
            # Try to extract JSON from output
            json_match = re.search(r'```json\s*(.*?)\s*```', output, re.DOTALL)
            if json_match:
                json.loads(json_match.group(1))
            else:
                json.loads(output.strip())
        except (json.JSONDecodeError, AttributeError):
            format_ok = False
            result["errors"].append("Expected JSON format but output is not valid JSON")
    result["checks"]["format"] = format_ok

    # Check 4: Forbidden patterns
    forbidden = schema.get("forbidden_patterns", [])
    found_forbidden = []
    for pattern in forbidden:
        if pattern.lower() in output_lower:
            found_forbidden.append(pattern)
    forbidden_ok = len(found_forbidden) == 0
    result["checks"]["no_forbidden"] = forbidden_ok
    if not forbidden_ok:
        result["warnings"].append(f"Found forbidden patterns: {found_forbidden}")

    # Check 5: Not an error message
    error_ok = True
    if output and output.strip().lower().startswith(("error", "erro", "traceback", "exception")):
        error_ok = False
        result["errors"].append("Output appears to be an error message, not a valid artifact")
    result["checks"]["not_error"] = error_ok

    # Verdict
    if result["errors"]:
        result["valid"] = False
    if result["warnings"] and strict:
        result["valid"] = False

    return result


# =============================================================================
# FILTER PIPELINE INTEGRATION
# =============================================================================

try:
    from filter_pipeline import ExecutionFilter

    class SchemaValidationFilter(ExecutionFilter):
        """Post-execution schema validation. Tripwire on invalid artifacts."""
        name = "schema_validation"
        order = 65  # After execution, before output guardrails

        def __init__(self, strict: bool = False):
            self.strict = strict

        def after(self, task: dict, output: str, context: dict) -> dict:
            skill = task.get("skill", "")
            if not skill:
                return {"output": output}

            result = validate_artifact(output, skill, strict=self.strict)

            if not result["valid"]:
                retry_count = context.get("_retry_count", 0)
                if retry_count < 3:
                    return {
                        "output": output,
                        "tripwire": True,
                        "tripwire_reason": f"Schema validation failed: {result['errors'][0]}",
                        "retry_hint": f"Output failed schema for {skill}. Missing: {result.get('checks', {})}. Retry {retry_count+1}/3.",
                        "schema_result": result,
                    }
                else:
                    log.warning(f"Schema validation failed after 3 retries for {skill} — passing through")

            return {
                "output": output,
                "schema_valid": result["valid"],
                "schema_warnings": result.get("warnings", []),
            }

except ImportError:
    pass


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="DARIO Artifact Schemas — Output validation")
    parser.add_argument("--skill", "-s", required=True, help="Skill name")
    parser.add_argument("--validate", "-v", help="File to validate")
    parser.add_argument("--output", "-o", help="Output text to validate")
    parser.add_argument("--show-schema", action="store_true", help="Show schema for skill")
    parser.add_argument("--list", action="store_true", help="List all schemas")
    parser.add_argument("--strict", action="store_true", help="Strict mode")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.list:
        for name, schema in sorted(SCHEMAS.items()):
            sections = ", ".join(schema.get("required_sections", []))
            print(f"  {name:30s} | min {schema.get('min_length', 0):5d} chars | {sections[:50]}")
        return 0

    if args.show_schema:
        schema = SCHEMAS.get(args.skill)
        if schema:
            print(json.dumps(schema, indent=2))
        else:
            print(f"No schema for '{args.skill}'")
        return 0

    output = args.output or ""
    if args.validate:
        output = Path(args.validate).read_text(encoding="utf-8")

    if not output:
        print("Provide --output or --validate")
        return 1

    result = validate_artifact(output, args.skill, strict=args.strict)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        v = "VALID" if result["valid"] else "INVALID"
        print(f"[{v}] {args.skill}")
        for check, passed in result["checks"].items():
            mark = "+" if passed else "!"
            print(f"  [{mark}] {check}")
        if result["errors"]:
            for e in result["errors"]:
                print(f"  ERROR: {e}")
        if result["warnings"]:
            for w in result["warnings"]:
                print(f"  WARN: {w}")

    return 0 if result["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
