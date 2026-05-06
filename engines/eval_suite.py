#!/usr/bin/env python3
"""
DARIO Eval Suite — Regression testing for skills (Letta + Anthropic-inspired).
================================================================================
Golden test cases per skill. Run on each evolution cycle. Fail if skill regresses.
"Evals as CI" — treats quality evaluation like automated tests.

Each eval case has:
    - input: task description / prompt
    - expected: what a good output looks like (golden reference)
    - skill: which skill is being tested
    - min_score: minimum acceptable score (baseline)
    - evaluator: which evaluator(s) to use

Usage:
    python eval_suite.py --run                      # Run all evals
    python eval_suite.py --run --skill dario-brand  # Run evals for one skill
    python eval_suite.py --list                     # List all eval cases
    python eval_suite.py --add --skill X --input "..." --expected "..." --min-score 70
    python eval_suite.py --baseline                 # Show baselines
    python eval_suite.py --report                   # Show last run results

Integration:
    Called by evolution_runner.py at the end of each evolution cycle.
    If any skill drops below baseline, evolution is flagged as REGRESSION.
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ORCH_DIR = Path.home() / ".claude" / "orchestrator"
EVAL_DIR = ORCH_DIR / "evals"
EVAL_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(ORCH_DIR))

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("eval_suite")


# =============================================================================
# GOLDEN TEST CASES
# =============================================================================

EVAL_CASES = [
    # --- BRAND ---
    {
        "id": "eval-brand-01",
        "skill": "dario-brand",
        "input": "Posicionamento de marca para restaurante de peixe premium em Cascais. Publico: turistas e locais 30-55 anos.",
        "expected_keywords": ["posicionamento", "archetype", "diferencia", "tom de voz", "messaging", "cascais"],
        "min_score": 70,
        "min_length": 500,
    },
    {
        "id": "eval-brand-02",
        "skill": "dario-brand",
        "input": "Brand positioning for SaaS de contabilidade para freelancers portugueses. Diferenciador: IA que faz IVA automatico.",
        "expected_keywords": ["posicionamento", "archetype", "saas", "iva", "freelancer"],
        "min_score": 70,
        "min_length": 500,
    },
    # --- OFFER ---
    {
        "id": "eval-offer-01",
        "skill": "dario-offer",
        "input": "Grand Slam Offer para servico de remodelacao de interiores. Budget medio cliente: 50-100K EUR.",
        "expected_keywords": ["valor", "bonus", "garantia", "preco", "urgencia", "remodelacao"],
        "min_score": 65,
        "min_length": 400,
    },
    # --- SEO ---
    {
        "id": "eval-seo-01",
        "skill": "seo-audit",
        "input": "Auditoria SEO completa para e-commerce de mobiliario em Portugal. URL: mobiliapt.com",
        "expected_keywords": ["titulo", "meta", "performance", "mobile", "recomenda", "schema"],
        "min_score": 70,
        "min_length": 800,
    },
    {
        "id": "eval-seo-02",
        "skill": "seo-local",
        "input": "Local SEO para clinica dentaria em Sintra com 3 localizacoes.",
        "expected_keywords": ["gbp", "nap", "citation", "review", "sintra"],
        "min_score": 65,
        "min_length": 400,
    },
    # --- TECHNICAL ---
    {
        "id": "eval-wp-01",
        "skill": "dario-wp-audit",
        "input": "Auditoria WordPress para site de advogados. WooCommerce inactivo. Elementor + 40 plugins.",
        "expected_keywords": ["performance", "seguranca", "seo", "plugin", "elementor"],
        "min_score": 70,
        "min_length": 600,
    },
    {
        "id": "eval-diagnose-01",
        "skill": "dario-diagnose",
        "input": "Diagnostico holistico para agencia de design grafico que quer migrar para digital. 5 funcionarios, faturacao 200K/ano.",
        "expected_keywords": ["critico", "importante", "optimizacao"],
        "min_score": 65,
        "min_length": 500,
    },
    # --- PROPOSAL ---
    {
        "id": "eval-proposal-01",
        "skill": "dario-proposal",
        "input": "Proposta comercial 3 opcoes para redesign de website + SEO para restaurante em Lisboa. Budget cliente: 5-15K.",
        "expected_keywords": ["opcao", "scope", "investimento", "timeline"],
        "min_score": 70,
        "min_length": 600,
    },
    # --- DIVA ---
    {
        "id": "eval-diva-01",
        "skill": "diva-budget",
        "input": "Orcamento de remodelacao T2 em Lisboa, 75m2, construcao 1960, remodelacao total exceto estrutura.",
        "expected_keywords": ["capitulo", "total", "m2"],
        "min_score": 65,
        "min_length": 300,
    },
    {
        "id": "eval-diva-02",
        "skill": "diva-moodboard",
        "input": "Moodboard para apartamento T3 estilo Japandi, casal jovem, orcamento medio-alto, zona de Oeiras.",
        "expected_keywords": ["estilo", "paleta", "material", "japandi"],
        "min_score": 65,
        "min_length": 300,
    },
    # --- NAMING ---
    {
        "id": "eval-naming-01",
        "skill": "dario-naming",
        "input": "Naming para app de carpooling entre Lisboa e Cascais. Target: profissionais 25-40.",
        "expected_keywords": ["candidato", "dominio", "disponibilidade"],
        "min_score": 65,
        "min_length": 200,
    },
    # --- FINANCIAL ---
    {
        "id": "eval-financial-01",
        "skill": "dario-financial-model",
        "input": "Modelo financeiro para agencia digital. 3 servicos (SEO, Web, Ads). Team de 4. Meta: 30K MRR em 12 meses.",
        "expected_keywords": ["receita", "custo", "margem", "break-even"],
        "min_score": 65,
        "min_length": 400,
    },
]


# =============================================================================
# EVAL RUNNER
# =============================================================================

def run_eval_case(case: dict, actual_output: str = "") -> dict:
    """
    Evaluate a single test case. If no actual_output, uses schema validation only.
    Returns score and pass/fail.
    """
    result = {
        "id": case["id"],
        "skill": case["skill"],
        "passed": False,
        "score": 0,
        "checks": {},
    }

    # If no actual output provided, this is a dry-run (schema check only)
    if not actual_output:
        result["status"] = "no_output"
        return result

    # Check 1: Minimum length
    length_ok = len(actual_output) >= case.get("min_length", 0)
    result["checks"]["length"] = length_ok

    # Check 2: Expected keywords present
    output_lower = actual_output.lower()
    keywords = case.get("expected_keywords", [])
    found = sum(1 for kw in keywords if kw in output_lower)
    keyword_score = (found / len(keywords) * 100) if keywords else 100
    result["checks"]["keywords"] = {"found": found, "total": len(keywords), "score": keyword_score}

    # Check 3: Not an error
    not_error = not actual_output.strip().lower().startswith(("error", "erro", "traceback"))
    result["checks"]["not_error"] = not_error

    # Composite score
    scores = []
    if length_ok:
        scores.append(100)
    else:
        scores.append(max(0, len(actual_output) / case.get("min_length", 1) * 100))
    scores.append(keyword_score)
    scores.append(100 if not_error else 0)

    result["score"] = round(sum(scores) / len(scores), 1)
    result["passed"] = result["score"] >= case.get("min_score", 70) and not_error
    result["min_score"] = case.get("min_score", 70)

    return result


def run_suite(skill_filter: str = "", outputs: dict = None) -> dict:
    """
    Run the full eval suite. `outputs` is a dict of {eval_id: actual_output}.
    Without outputs, reports which evals need to be run.
    """
    outputs = outputs or {}
    cases = EVAL_CASES
    if skill_filter:
        cases = [c for c in cases if c["skill"] == skill_filter]

    results = []
    passed = 0
    failed = 0
    skipped = 0

    for case in cases:
        output = outputs.get(case["id"], "")
        if output:
            r = run_eval_case(case, output)
            results.append(r)
            if r["passed"]:
                passed += 1
            else:
                failed += 1
        else:
            results.append({"id": case["id"], "skill": case["skill"], "status": "skipped"})
            skipped += 1

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total": len(cases),
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "pass_rate": round(passed / max(passed + failed, 1) * 100, 1),
        "regression": failed > 0,
        "results": results,
    }


def get_baselines() -> dict:
    """Get baseline scores per skill from eval cases."""
    baselines = {}
    for case in EVAL_CASES:
        skill = case["skill"]
        if skill not in baselines:
            baselines[skill] = {"cases": 0, "min_score": 100}
        baselines[skill]["cases"] += 1
        baselines[skill]["min_score"] = min(baselines[skill]["min_score"], case.get("min_score", 70))
    return baselines


def save_run(results: dict):
    """Save eval run results for history."""
    runs_dir = EVAL_DIR / "runs"
    runs_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = runs_dir / f"eval_{timestamp}.json"
    path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return str(path)


def last_run() -> dict:
    """Get last eval run results."""
    runs_dir = EVAL_DIR / "runs"
    if not runs_dir.exists():
        return {"error": "No runs found"}
    runs = sorted(runs_dir.glob("eval_*.json"))
    if not runs:
        return {"error": "No runs found"}
    return json.loads(runs[-1].read_text(encoding="utf-8"))


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="DARIO Eval Suite — Skill regression testing")
    parser.add_argument("--run", action="store_true", help="Run eval suite (dry-run without outputs)")
    parser.add_argument("--skill", "-s", default="", help="Filter by skill")
    parser.add_argument("--list", action="store_true", help="List all eval cases")
    parser.add_argument("--baseline", action="store_true", help="Show baselines per skill")
    parser.add_argument("--report", action="store_true", help="Show last run results")
    parser.add_argument("--add", action="store_true", help="Add new eval case (interactive)")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.list:
        cases = EVAL_CASES
        if args.skill:
            cases = [c for c in cases if c["skill"] == args.skill]
        if args.json:
            print(json.dumps(cases, indent=2))
        else:
            print(f"{len(cases)} eval cases:")
            for c in cases:
                kws = ", ".join(c.get("expected_keywords", [])[:4])
                print(f"  [{c['id']}] {c['skill']:25s} min={c.get('min_score',70)} | {kws}...")
        return 0

    if args.baseline:
        baselines = get_baselines()
        if args.json:
            print(json.dumps(baselines, indent=2))
        else:
            print("Baselines per skill:")
            for skill, data in sorted(baselines.items()):
                print(f"  {skill:30s} | {data['cases']} cases | min_score: {data['min_score']}")
        return 0

    if args.run:
        results = run_suite(skill_filter=args.skill)
        path = save_run(results)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print(f"Eval Suite: {results['total']} cases | {results['passed']} passed | {results['failed']} failed | {results['skipped']} skipped")
            print(f"Pass rate: {results['pass_rate']}%")
            print(f"Regression: {'YES' if results['regression'] else 'NO'}")
            print(f"Saved to: {path}")
        return 1 if results["regression"] else 0

    if args.report:
        results = last_run()
        if "error" in results:
            print(results["error"])
            return 1
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print(f"Last run: {results.get('timestamp', '?')}")
            print(f"Results: {results['passed']}/{results['total']} passed ({results['pass_rate']}%)")
            if results.get("regression"):
                print("REGRESSION DETECTED!")
                for r in results.get("results", []):
                    if not r.get("passed") and r.get("status") != "skipped":
                        print(f"  FAIL: {r['id']} ({r['skill']}) — score {r.get('score', '?')}/{r.get('min_score', '?')}")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
