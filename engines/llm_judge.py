#!/usr/bin/env python3
"""
DARIO LLM-as-Judge — Auto-scoring via Haiku API call.
=======================================================
Cheap, fast, consistent quality scoring without human-in-the-loop.
Uses Claude Haiku as judge — separate from execution model.

Usage:
    # Score a task output against its adaptive rubric
    python llm_judge.py --task MNB-002 --output "3 name candidates: ..."

    # Score raw text with explicit skill
    python llm_judge.py --skill dario-brand --output "Brand positioning: ..." --project mar-brasa

    # Batch score multiple tasks
    python llm_judge.py --batch T-001,T-002,T-003

    # Test mode (no API call, returns mock)
    python llm_judge.py --task MNB-002 --output "test" --mock

Exit codes:
    0 = scored successfully (score >= pass_threshold)
    1 = error
    2 = scored below threshold (needs revision)
"""

import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ORCH_DIR = Path.home() / ".claude" / "orchestrator"
sys.path.insert(0, str(ORCH_DIR))

from db import DB

PYTHON = sys.executable
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("judge")

HAIKU_MODEL = "claude-haiku-4-5-20251001"
HAIKU_INPUT_COST = 0.80   # $/M tokens
HAIKU_OUTPUT_COST = 4.00  # $/M tokens


def get_rubric(task_id: str = "", skill: str = "") -> dict:
    """Get adaptive rubric for scoring."""
    args = []
    if task_id:
        args.extend(["--task", task_id])
    elif skill:
        args.extend(["--skill", skill])
    args.append("--json")

    try:
        r = subprocess.run([PYTHON, str(ORCH_DIR / "adaptive_rubric.py")] + args,
                           capture_output=True, text=True, timeout=10, cwd=str(ORCH_DIR))
        if r.stdout.strip():
            return json.loads(r.stdout.strip())
    except Exception:
        pass

    return {"dimensions": [], "pass_threshold": 60}


def build_judge_prompt(output: str, rubric: dict, task_title: str = "",
                       skill: str = "", project: str = "") -> str:
    """Build the scoring prompt for Haiku."""
    dims = ""
    for d in rubric.get("dimensions", []):
        dims += f"- **{d.get('name')}** (weight: {d.get('weight', 0):.0%}): {d.get('description', '')}\n"
        dims += f"  Scoring: {d.get('scoring_guide', '')}\n"

    threshold = rubric.get("pass_threshold", 60)

    return f"""You are a quality evaluator. Score this task output precisely.

TASK: {task_title}
SKILL: {skill}
PROJECT: {project}

SCORING RUBRIC (score each dimension 0.0 to 1.0):
{dims}
PASS THRESHOLD: {threshold}/100

OUTPUT TO EVALUATE:
---
{output[:8000]}
---

INSTRUCTIONS:
1. First THINK about the quality in <thinking> tags (2-3 sentences)
2. Score each dimension from 0.0 to 1.0 based on the scoring guide
3. Calculate weighted total: score = sum(weight_i * dimension_i) * 100
4. Determine action: score >= {threshold} → "ship", score < {threshold} → "revision"
5. If score >= 90 → "success_pattern"

Response format:
<thinking>Brief reasoning about quality...</thinking>
{{"score": <int 0-100>, "action": "<ship|revision|success_pattern>", "dimensions": {{"<name>": <float 0.0-1.0>}}, "feedback": "<one specific improvement suggestion>"}}"""


def score_via_api(prompt: str) -> dict:
    """Call Haiku API for scoring."""
    try:
        import anthropic
        client = anthropic.Anthropic()

        response = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text.strip()
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost = (input_tokens / 1_000_000 * HAIKU_INPUT_COST +
                output_tokens / 1_000_000 * HAIKU_OUTPUT_COST)

        # Strip <thinking> tags before JSON extraction (fixed: tags could corrupt JSON parse)
        import re
        clean_text = re.sub(r'<thinking>.*?</thinking>', '', text, flags=re.DOTALL).strip()

        # Parse JSON from cleaned response
        if "{" in clean_text:
            json_str = clean_text[clean_text.index("{"):clean_text.rindex("}") + 1]
            result = json.loads(json_str)
            result["judge_tokens"] = {"input": input_tokens, "output": output_tokens}
            result["judge_cost"] = round(cost, 6)
            result["judge_model"] = HAIKU_MODEL
            return result

        return {"score": 0, "error": "No JSON in Haiku response", "raw": text[:200]}

    except Exception as e:
        # Retry once on transient errors (fixed: was no retry)
        if retries > 0 and ("rate" in str(e).lower() or "timeout" in str(e).lower() or "connection" in str(e).lower()):
            import time
            time.sleep(1.5)
            return score_via_api(prompt)
        return {"score": -1, "error": str(e)[:300]}


def score_mock(rubric: dict) -> dict:
    """Mock scoring for testing without API calls."""
    import random
    dims = {}
    for d in rubric.get("dimensions", []):
        dims[d.get("name", "?")] = round(random.uniform(0.6, 0.95), 2)

    weights = [d.get("weight", 0.2) for d in rubric.get("dimensions", [])]
    values = list(dims.values())
    score = round(sum(w * v for w, v in zip(weights, values)) * 100)

    return {
        "score": score,
        "action": "ship" if score >= rubric.get("pass_threshold", 60) else "revision",
        "dimensions": dims,
        "feedback": "Mock score for testing",
        "judge_tokens": {"input": 0, "output": 0},
        "judge_cost": 0,
        "judge_model": "mock",
    }


def judge_task(task_id: str = "", output: str = "", skill: str = "",
               project: str = "", mock: bool = False) -> dict:
    """Full judging pipeline: rubric → prompt → API → record."""
    db = DB()
    result = {"task_id": task_id, "status": "pending"}

    # Get task info from DB
    task_title = ""
    if task_id:
        task = db.get_task(task_id)
        if task:
            if not skill:
                skill = task.get("skill", "")
            if not project:
                project = task.get("project", "")
            task_title = task.get("title", "")
            if not output:
                output = task.get("completion_comment", "")

    if not output:
        result["status"] = "error"
        result["error"] = "No output to score"
        return result

    # Get adaptive rubric
    rubric = get_rubric(task_id=task_id, skill=skill)
    result["rubric_dimensions"] = rubric.get("dimensions_count", len(rubric.get("dimensions", [])))
    result["pass_threshold"] = rubric.get("pass_threshold", 60)

    # Build prompt and score
    if mock:
        score_result = score_mock(rubric)
    else:
        prompt = build_judge_prompt(output, rubric, task_title, skill, project)
        score_result = score_via_api(prompt)

    # Merge results
    result.update(score_result)
    result["status"] = "scored"

    # Record in DB (fixed: score>=0 not >0 to avoid survivorship bias; model now passed)
    if task_id and score_result.get("score", -1) >= 0:
        db.record_score(task_id, skill, score_result["score"], project,
                        score_result.get("dimensions", {}),
                        model=score_result.get("judge_model", ""))
        db.log_event("llm-judge", "task_scored", task_id=task_id,
                     details=f"score={score_result['score']} model={score_result.get('judge_model','?')} cost=${score_result.get('judge_cost',0):.4f}")

    return result


def main():
    parser = argparse.ArgumentParser(description="DARIO LLM-as-Judge — Auto-scoring via Haiku")
    parser.add_argument("--task", "-t", default="", help="Task ID")
    parser.add_argument("--output", "-o", default="", help="Output text to score")
    parser.add_argument("--skill", "-s", default="", help="Skill name")
    parser.add_argument("--project", "-p", default="", help="Project")
    parser.add_argument("--mock", action="store_true", help="Mock mode (no API call)")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")

    args = parser.parse_args()
    if args.json:
        logging.getLogger().setLevel(logging.ERROR)

    result = judge_task(args.task, args.output, args.skill, args.project, args.mock)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        score = result.get("score", 0)
        action = result.get("action", "?")
        cost = result.get("judge_cost", 0)
        mark = "+" if action == "ship" else "!" if action == "revision" else "*"
        print(f"[{mark}] Score: {score}/100 → {action}")
        if result.get("dimensions"):
            for name, val in result["dimensions"].items():
                print(f"  {name:25s} {val:.2f}")
        if result.get("feedback"):
            print(f"\n  Feedback: {result['feedback']}")
        if cost > 0:
            print(f"  Judge cost: ${cost:.4f}")

    return 0 if result.get("action") != "revision" else 2


if __name__ == "__main__":
    sys.exit(main())
