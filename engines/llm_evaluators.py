#!/usr/bin/env python3
"""
DARIO LLM-as-Judge Evaluators — Objective quality scoring (Haystack-inspired).
================================================================================
Automated evaluators that run post-execution on RAG-dependent skills:
- FaithfulnessEvaluator: Is output grounded in injected context?
- ContextRelevanceEvaluator: Did we retrieve the right chunks?
- CompletenessEvaluator: Does output cover all required points?
- ToneEvaluator: Is tone appropriate for the deliverable type?

Uses Haiku for evaluation (~$0.001/eval) to keep costs minimal.

Usage:
    python llm_evaluators.py --evaluate --output "..." --context "..." --skill dario-brand --json
    python llm_evaluators.py --faithfulness --output "..." --context "..."
    python llm_evaluators.py --relevance --query "..." --context "..."
    python llm_evaluators.py --completeness --output "..." --skill dario-brand

Integration:
    Called by quality_scorer.py and executor.py for objective scoring.
    Scores stored in SQLite alongside the 5D rubric scores.
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
log = logging.getLogger("llm_evaluators")


# =============================================================================
# EVALUATION PROMPTS (kept minimal for Haiku cost efficiency)
# =============================================================================

FAITHFULNESS_PROMPT = """Rate the faithfulness of the OUTPUT to the CONTEXT on a scale of 0-100.
Faithfulness = the output only contains claims supported by the context.

CONTEXT:
{context}

OUTPUT:
{output}

Score 0-100 and briefly explain. Respond ONLY as JSON:
{{"score": <int>, "explanation": "<1 sentence>"}}"""

CONTEXT_RELEVANCE_PROMPT = """Rate how relevant the CONTEXT is to the QUERY on a scale of 0-100.
Relevance = the context contains information needed to answer the query.

QUERY:
{query}

CONTEXT:
{context}

Score 0-100. Respond ONLY as JSON:
{{"score": <int>, "explanation": "<1 sentence>"}}"""

COMPLETENESS_PROMPT = """Rate how complete the OUTPUT is for a {skill} deliverable on a scale of 0-100.
Expected sections: {expected_sections}

OUTPUT:
{output}

Score 0-100 based on coverage of expected sections. Respond ONLY as JSON:
{{"score": <int>, "missing": [<list of missing sections>], "explanation": "<1 sentence>"}}"""

TONE_PROMPT = """Rate whether the TONE of this output is appropriate for a {deliverable_type} on a scale of 0-100.
Expected tone: {expected_tone}

OUTPUT (first 500 chars):
{output}

Score 0-100. Respond ONLY as JSON:
{{"score": <int>, "detected_tone": "<2-3 words>", "explanation": "<1 sentence>"}}"""


# Skill → expected tone mapping
SKILL_TONES = {
    "dario-brand": ("brand positioning document", "professional, strategic, confident"),
    "dario-offer": ("sales offer", "persuasive, value-focused, urgent"),
    "dario-sales-letter": ("long-form sales letter", "emotional, storytelling, persuasive"),
    "dario-proposal": ("commercial proposal", "professional, clear, structured"),
    "seo-audit": ("technical audit report", "analytical, data-driven, actionable"),
    "dario-wp-audit": ("WordPress audit", "technical, structured, prioritized"),
    "dario-diagnose": ("diagnostic report", "consultative, thorough, prioritized"),
    "diva-briefing": ("architecture briefing", "professional, detailed, systematic"),
}


# =============================================================================
# EVALUATOR FUNCTIONS
# =============================================================================

def _call_haiku(prompt: str) -> dict:
    """Call Haiku for evaluation. Returns parsed JSON response."""
    try:
        # Try Anthropic API first
        import anthropic
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
    except ImportError:
        # Fallback to mock for testing
        log.warning("Anthropic SDK not available — using mock evaluator")
        return {"score": 75, "explanation": "Mock evaluation (SDK not available)"}
    except Exception as e:
        log.error(f"Haiku call failed: {e}")
        return {"score": -1, "error": str(e)[:100]}

    # Parse JSON response
    try:
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"score": -1, "raw": raw[:200], "error": "Failed to parse JSON"}


def evaluate_faithfulness(output: str, context: str) -> dict:
    """Is the output grounded in the provided context?"""
    if not context or not output:
        return {"evaluator": "faithfulness", "score": -1, "error": "Missing output or context"}

    prompt = FAITHFULNESS_PROMPT.format(
        context=context[:2000],
        output=output[:2000],
    )
    result = _call_haiku(prompt)
    result["evaluator"] = "faithfulness"
    return result


def evaluate_context_relevance(query: str, context: str) -> dict:
    """Did we retrieve the right context chunks for this query?"""
    if not query or not context:
        return {"evaluator": "context_relevance", "score": -1, "error": "Missing query or context"}

    prompt = CONTEXT_RELEVANCE_PROMPT.format(
        query=query[:500],
        context=context[:2000],
    )
    result = _call_haiku(prompt)
    result["evaluator"] = "context_relevance"
    return result


def evaluate_completeness(output: str, skill: str) -> dict:
    """Does the output cover all expected sections for this skill?"""
    from artifact_schemas import SCHEMAS
    schema = SCHEMAS.get(skill)
    if not schema:
        return {"evaluator": "completeness", "score": -1, "error": f"No schema for skill '{skill}'"}

    expected = schema.get("required_sections", [])
    prompt = COMPLETENESS_PROMPT.format(
        skill=skill,
        expected_sections=", ".join(expected),
        output=output[:3000],
    )
    result = _call_haiku(prompt)
    result["evaluator"] = "completeness"
    result["expected_sections"] = expected
    return result


def evaluate_tone(output: str, skill: str) -> dict:
    """Is the tone appropriate for this type of deliverable?"""
    if skill not in SKILL_TONES:
        return {"evaluator": "tone", "score": -1, "error": f"No tone profile for skill '{skill}'"}

    deliverable_type, expected_tone = SKILL_TONES[skill]
    prompt = TONE_PROMPT.format(
        deliverable_type=deliverable_type,
        expected_tone=expected_tone,
        output=output[:500],
    )
    result = _call_haiku(prompt)
    result["evaluator"] = "tone"
    return result


def evaluate_full(output: str, context: str = "", query: str = "", skill: str = "") -> dict:
    """Run all applicable evaluators and return composite score."""
    results = []

    # Always run completeness if skill has schema
    if skill:
        r = evaluate_completeness(output, skill)
        if r.get("score", -1) >= 0:
            results.append(r)

    # Run faithfulness if context provided
    if context:
        r = evaluate_faithfulness(output, context)
        if r.get("score", -1) >= 0:
            results.append(r)

    # Run relevance if both query and context provided
    if query and context:
        r = evaluate_context_relevance(query, context)
        if r.get("score", -1) >= 0:
            results.append(r)

    # Run tone if skill has profile
    if skill and skill in SKILL_TONES:
        r = evaluate_tone(output, skill)
        if r.get("score", -1) >= 0:
            results.append(r)

    # Composite score (weighted average)
    valid_scores = [r["score"] for r in results if r.get("score", -1) >= 0]
    composite = round(sum(valid_scores) / len(valid_scores), 1) if valid_scores else -1

    return {
        "composite_score": composite,
        "evaluators_run": len(results),
        "results": results,
    }


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="DARIO LLM-as-Judge Evaluators")
    parser.add_argument("--evaluate", action="store_true", help="Run full evaluation")
    parser.add_argument("--faithfulness", action="store_true", help="Run faithfulness only")
    parser.add_argument("--relevance", action="store_true", help="Run context relevance only")
    parser.add_argument("--completeness", action="store_true", help="Run completeness only")
    parser.add_argument("--tone", action="store_true", help="Run tone only")
    parser.add_argument("--output", "-o", default="", help="Output text to evaluate")
    parser.add_argument("--context", "-c", default="", help="Context used for generation")
    parser.add_argument("--query", "-q", default="", help="Original query/task description")
    parser.add_argument("--skill", "-s", default="", help="Skill that produced the output")
    parser.add_argument("--file", "-f", help="Read output from file")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")
    args = parser.parse_args()

    output = args.output
    if args.file:
        output = Path(args.file).read_text(encoding="utf-8")

    if args.faithfulness:
        result = evaluate_faithfulness(output, args.context)
    elif args.relevance:
        result = evaluate_context_relevance(args.query, args.context)
    elif args.completeness:
        result = evaluate_completeness(output, args.skill)
    elif args.tone:
        result = evaluate_tone(output, args.skill)
    elif args.evaluate:
        result = evaluate_full(output, context=args.context, query=args.query, skill=args.skill)
    else:
        parser.print_help()
        return 0

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if "composite_score" in result:
            print(f"Composite: {result['composite_score']}/100 ({result['evaluators_run']} evaluators)")
            for r in result.get("results", []):
                print(f"  [{r['evaluator']}] {r.get('score', '?')}/100 — {r.get('explanation', '')}")
        else:
            score = result.get("score", "?")
            print(f"[{result.get('evaluator', '?')}] {score}/100 — {result.get('explanation', '')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
