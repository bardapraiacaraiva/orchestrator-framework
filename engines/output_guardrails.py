#!/usr/bin/env python3
"""
DARIO Output Guardrails — Post-execution validation with Tripwire (OpenAI SDK-inspired).
=========================================================================================
Validates LLM output AFTER execution. Catches:
- Leaked API keys / secrets / PII
- Hallucinated file paths
- Off-topic / empty output
- Format violations (missing required sections)
- Prompt injection attempts in output

When a tripwire fires, the output is QUARANTINED — not delivered downstream.
Instead, the task routes to replanner.py for retry or escalation.

Usage as filter (integrated in FilterPipeline):
    from output_guardrails import OutputGuardrailFilter
    pipeline.add(OutputGuardrailFilter())

Usage standalone:
    python output_guardrails.py --output "..." --skill dario-brand --json
    python output_guardrails.py --file output.txt --skill seo-audit --json
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
log = logging.getLogger("output_guardrails")


# =============================================================================
# GUARDRAIL CHECKS
# =============================================================================

def check_secrets(output: str) -> list[str]:
    """Detect leaked API keys, tokens, passwords in output."""
    issues = []
    patterns = [
        (r'(?:sk|pk|rk)[-_][a-zA-Z0-9_-]{20,}', "API key pattern (sk-/pk-/rk-)"),
        (r'ghp_[a-zA-Z0-9]{36}', "GitHub personal access token"),
        (r'eyJ[a-zA-Z0-9_-]{20,}\.eyJ[a-zA-Z0-9_-]{20,}', "JWT token"),
        (r'AKIA[0-9A-Z]{16}', "AWS access key"),
        (r'(?:password|passwd|pwd)\s*[:=]\s*["\']?[^\s"\']{8,}', "Password in plaintext"),
        (r'-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----', "Private key"),
        (r'(?:supabase_service_role|service_role_key)\s*[:=]', "Supabase service role key"),
        (r'r8_[a-zA-Z0-9]{20,}', "Replicate API token"),
        (r'AIzaSy[a-zA-Z0-9_-]{33}', "Google API key"),
    ]
    for pattern, label in patterns:
        if re.search(pattern, output, re.IGNORECASE):
            issues.append(f"CRITICAL: {label} detected in output")
    return issues


def check_pii(output: str) -> list[str]:
    """Detect potential PII leakage."""
    issues = []
    # Portuguese NIF (9 digits)
    nif_matches = re.findall(r'\b[12345689]\d{8}\b', output)
    if len(nif_matches) > 3:
        issues.append(f"WARNING: Multiple NIF-like numbers ({len(nif_matches)}) in output")

    # Credit card patterns
    if re.search(r'\b(?:\d{4}[-\s]?){3}\d{4}\b', output):
        issues.append("CRITICAL: Credit card number pattern detected")

    # IBAN
    if re.search(r'\b[A-Z]{2}\d{2}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{0,4}\b', output):
        issues.append("WARNING: IBAN pattern detected — verify if intentional")

    return issues


def check_hallucinated_paths(output: str) -> list[str]:
    """Detect file paths that claim to exist but are suspicious."""
    issues = []
    # Paths that look like they're claiming local filesystem access
    sus_patterns = [
        r'(?:C:\\|/home/|/Users/|/root/|/etc/|/var/)[^\s\'"]{10,}',
    ]
    for pattern in sus_patterns:
        matches = re.findall(pattern, output)
        for m in matches:
            # Skip known safe paths (orchestrator, documentation, examples)
            if any(skip in m.lower() for skip in ["example", "your-", "path/to", "username", ".claude/orchestrator", "node_modules", "site-packages"]):
                continue
            issues.append(f"WARNING: Local file path reference: {m[:60]}...")
    return issues


def check_empty_or_error(output: str, skill: str = "") -> list[str]:
    """Detect empty, error-only, or stub outputs."""
    issues = []
    if not output or not output.strip():
        issues.append("CRITICAL: Output is empty")
        return issues

    stripped = output.strip()
    if len(stripped) < 50:
        issues.append(f"WARNING: Output suspiciously short ({len(stripped)} chars)")

    # Check for error-only output
    error_patterns = [
        r'^(?:error|erro|exception|traceback|failed)',
        r'^(?:internal server error|500|404|timeout)',
    ]
    first_line = stripped.split('\n')[0].lower()
    for p in error_patterns:
        if re.match(p, first_line):
            issues.append(f"CRITICAL: Output appears to be an error message: {first_line[:80]}")
            break

    # Check for TODO/placeholder output
    if re.search(r'(?:TODO|FIXME|PLACEHOLDER|lorem ipsum)', output, re.IGNORECASE):
        issues.append("WARNING: Output contains TODO/placeholder markers")

    return issues


def check_format_compliance(output: str, skill: str = "") -> list[str]:
    """Check output format matches expected structure for known skills."""
    issues = []

    # Skill-specific format requirements
    format_rules = {
        "dario-brand": ["posicionamento", "archetype", "diferencia"],
        "dario-offer": ["valor", "bonus", "garantia", "preco"],
        "seo-audit": ["titulo", "meta", "performance", "recomenda"],
        "dario-proposal": ["opcao", "scope", "timeline", "investimento"],
        "dario-wp-audit": ["performance", "seguranca", "seo"],
        "dario-diagnose": ["critico", "importante", "optimizacao"],
        "dario-naming": ["candidato", "dominio"],
        "dario-pitch": ["problema", "solucao", "mercado"],
        "dario-sales-letter": ["headline", "oferta", "cta"],
        "dario-story-circle": ["protagonista", "transformacao"],
        "dario-content": ["titulo", "introducao", "conclusao"],
        "seo-local": ["gbp", "nap", "citation"],
        "seo-schema": ["@type", "json"],
        "seo-plan": ["keyword", "estrategia", "prioridade"],
        "diva-budget": ["capitulo", "total", "m2"],
        "diva-briefing": ["projecto", "cliente", "requisito"],
        "diva-moodboard": ["estilo", "paleta", "material"],
        "diva-timeline": ["fase", "semana", "prazo"],
        "dario-financial-model": ["receita", "custo", "margem"],
        "dario-saas-metrics": ["mrr", "churn", "cac"],
    }

    if skill in format_rules:
        required_keywords = format_rules[skill]
        output_lower = output.lower()
        missing = [kw for kw in required_keywords if kw not in output_lower]
        if missing:
            issues.append(f"WARNING: Output missing expected sections for {skill}: {missing}")

    return issues


def check_prompt_injection(output: str) -> list[str]:
    """Detect potential prompt injection attempts in output (output as attack vector)."""
    issues = []
    injection_patterns = [
        r'ignore (?:all )?previous instructions',
        r'you are now',
        r'system:\s*you',
        r'<\|(?:im_start|system|endoftext)\|>',
        r'\[INST\]',
        r'</?(?:system|instruction|prompt)>',
    ]
    for p in injection_patterns:
        if re.search(p, output, re.IGNORECASE):
            issues.append("CRITICAL: Potential prompt injection detected in output")
            break
    return issues


# =============================================================================
# MAIN VALIDATION
# =============================================================================

def validate_output(output: str, skill: str = "", strict: bool = False) -> dict:
    """Run all output guardrail checks. Returns verdict + issues."""
    result = {
        "verdict": "PASS",
        "tripwire": False,
        "critical": [],
        "warnings": [],
        "checks": {},
    }

    # Run all checks
    checks = [
        ("secrets", check_secrets(output)),
        ("pii", check_pii(output)),
        ("hallucinated_paths", check_hallucinated_paths(output)),
        ("empty_or_error", check_empty_or_error(output, skill)),
        ("format_compliance", check_format_compliance(output, skill)),
        ("prompt_injection", check_prompt_injection(output)),
    ]

    for name, issues in checks:
        result["checks"][name] = len(issues) == 0
        for issue in issues:
            if issue.startswith("CRITICAL"):
                result["critical"].append(issue)
            else:
                result["warnings"].append(issue)

    # Verdict
    if result["critical"]:
        result["verdict"] = "FAIL"
        result["tripwire"] = True
        result["tripwire_reason"] = result["critical"][0]
    elif result["warnings"] and strict:
        result["verdict"] = "WARN"
    elif result["warnings"]:
        result["verdict"] = "WARN"

    return result


# =============================================================================
# FILTER PIPELINE INTEGRATION
# =============================================================================

try:
    from filter_pipeline import ExecutionFilter

    class OutputGuardrailFilter(ExecutionFilter):
        """Post-execution guardrail filter. Tripwire on critical issues."""
        name = "output_guardrails"
        order = 70  # After execution, before quality gate

        def __init__(self, strict: bool = False):
            self.strict = strict

        def after(self, task: dict, output: str, context: dict) -> dict:
            skill = task.get("skill", "")
            result = validate_output(output, skill=skill, strict=self.strict)

            if result["tripwire"]:
                return {
                    "output": output,
                    "tripwire": True,
                    "tripwire_reason": result["tripwire_reason"],
                    "guardrail_issues": result["critical"] + result["warnings"],
                }

            # Pass through with warnings attached
            return {
                "output": output,
                "guardrail_warnings": result["warnings"],
            }

except ImportError:
    pass  # filter_pipeline not available, standalone mode only


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="DARIO Output Guardrails — Post-execution validation")
    parser.add_argument("--output", "-o", help="Output text to validate")
    parser.add_argument("--file", "-f", help="File containing output to validate")
    parser.add_argument("--skill", "-s", default="", help="Skill that produced the output")
    parser.add_argument("--strict", action="store_true", help="Strict mode (warnings = failure)")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")
    args = parser.parse_args()

    output = args.output or ""
    if args.file:
        output = Path(args.file).read_text(encoding="utf-8")

    if not output:
        print("Error: provide --output or --file")
        return 1

    result = validate_output(output, skill=args.skill, strict=args.strict)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        v = result["verdict"]
        t = " [TRIPWIRE]" if result["tripwire"] else ""
        print(f"Verdict: {v}{t}")
        for name, passed in result["checks"].items():
            mark = "+" if passed else "!"
            print(f"  [{mark}] {name}")
        if result["critical"]:
            print("\nCRITICAL:")
            for c in result["critical"]:
                print(f"  - {c}")
        if result["warnings"]:
            print("\nWARNINGS:")
            for w in result["warnings"]:
                print(f"  - {w}")

    return 1 if result["tripwire"] else 0


if __name__ == "__main__":
    sys.exit(main())
