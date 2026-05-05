#!/usr/bin/env python3
"""
DARIO API Executor — Direct Claude API execution (THE GAME CHANGER).
=====================================================================
Invokes Claude API directly via Anthropic SDK. No Claude session needed.
Runtime can execute tasks 24/7 autonomously.

Model routing:
    - Haiku:  simple tasks, quality scoring (cheap, fast)
    - Sonnet: standard tasks (best cost/quality ratio)
    - Opus:   critical tasks, complex chains (max quality)

Features:
    - Prompt caching (system prompt reused across tasks of same skill)
    - Real token metering (from API response, not estimates)
    - Streaming support (partial output in real-time)
    - Cost tracking (per-model pricing)
    - Retry with exponential backoff

Usage:
    python api_executor.py --task MNB-002                    # Execute task (auto model)
    python api_executor.py --task MNB-002 --model sonnet     # Force model
    python api_executor.py --task MNB-002 --dry-run          # Show prompt without calling API
    python api_executor.py --score MNB-002 --output "..."    # Score output via Haiku
    python api_executor.py --pulse                           # Full autonomous pulse
    python api_executor.py --json

Exit codes:
    0 = success
    1 = error
    2 = blocked by guardrails
    3 = failed, replanned
"""

import argparse
import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ORCH_DIR = Path.home() / ".claude" / "orchestrator"
sys.path.insert(0, str(ORCH_DIR))

from db import DB

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("api_exec")

PYTHON = sys.executable

# Model config (pricing per million tokens as of 2026)
MODELS = {
    "haiku": {
        "id": "claude-haiku-4-5-20251001",
        "input_cost": 0.80,   # $/M input tokens
        "output_cost": 4.00,  # $/M output tokens
        "max_tokens": 8192,
        "use_for": ["scoring", "simple", "classification"],
    },
    "sonnet": {
        "id": "claude-sonnet-4-6",
        "input_cost": 3.00,
        "output_cost": 15.00,
        "max_tokens": 16384,
        "use_for": ["standard", "default", "analysis", "content"],
    },
    "opus": {
        "id": "claude-opus-4-6",
        "input_cost": 15.00,
        "output_cost": 75.00,
        "max_tokens": 32768,
        "use_for": ["critical", "complex", "strategy", "financial"],
    },
}

# System prompts per skill category (cached across tasks)
SYSTEM_PROMPTS = {
    "dario": "You are a senior digital marketing strategist for a Portuguese agency. Deliver specific, actionable outputs. Always reference the client by name. Portuguese market context.",
    "seo": "You are an expert SEO consultant. Provide technically precise, data-backed recommendations. Include implementation-ready code (schema, config) where applicable.",
    "diva": "You are a senior architect and interior designer specializing in Portuguese construction. Reference RJUE/RGEU regulations. Use ProNIC pricing. Metric system.",
    "default": "You are a skilled professional executing a specific task. Be precise, specific to the project, and actionable.",
}


def select_model(task: dict) -> str:
    """Select optimal model based on task priority and policy."""
    policy = task.get("execution_policy", "default")
    priority = task.get("priority", "medium")

    if policy in ("critical", "financial") or priority == "critical":
        return "opus"
    elif policy == "client_facing" or priority == "high":
        return "sonnet"
    elif priority == "low":
        return "haiku"
    return "sonnet"  # default


def get_system_prompt(skill: str) -> str:
    """Get cached system prompt for skill category."""
    if skill.startswith("dario-") or skill.startswith("dario_"):
        return SYSTEM_PROMPTS["dario"]
    elif skill.startswith("seo"):
        return SYSTEM_PROMPTS["seo"]
    elif skill.startswith("diva-"):
        return SYSTEM_PROMPTS["diva"]
    return SYSTEM_PROMPTS["default"]


def calculate_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    """Calculate cost in USD."""
    config = MODELS.get(model, MODELS["sonnet"])
    cost = (input_tokens / 1_000_000 * config["input_cost"] +
            output_tokens / 1_000_000 * config["output_cost"])
    return round(cost, 6)


def run_engine(script: str, args: list) -> dict:
    """Run orchestrator engine."""
    path = ORCH_DIR / script
    if not path.exists():
        return {"error": f"{script} not found"}
    try:
        r = subprocess.run([PYTHON, str(path)] + args,
                           capture_output=True, text=True, timeout=15, cwd=str(ORCH_DIR))
        if r.stdout.strip():
            try:
                return json.loads(r.stdout.strip())
            except json.JSONDecodeError:
                return {"raw": r.stdout.strip()[:300]}
        return {"exit_code": r.returncode}
    except Exception as e:
        return {"error": str(e)[:200]}


# =============================================================================
# CORE: Execute task via Claude API
# =============================================================================

def execute_task(task_id: str, model_override: str = None, dry_run: bool = False) -> dict:
    """Full lifecycle: guardrails → context → prompt → API call → score → advance."""
    db = DB()
    result = {"task_id": task_id, "steps": [], "status": "pending"}

    # Load task from DB
    task = db.get_task(task_id)
    if not task:
        result["status"] = "error"
        result["error"] = "Task not found"
        return result

    skill = task.get("skill", "")
    project = task.get("project", "")

    # 1. Guardrails
    guard = run_engine("guardrails.py", ["--task", task_id, "--json"])
    verdict = guard.get("verdict", "FAIL")
    result["steps"].append({"step": "guardrails", "verdict": verdict})

    if verdict == "FAIL":
        result["status"] = "blocked"
        result["error"] = f"Guardrails: {guard.get('errors', [])}"
        return result

    # 2. Context injection
    context = run_engine("context_injector.py", ["--task", task_id, "--json"])
    context_block = context.get("context_block", "")
    result["steps"].append({"step": "context", "sources": context.get("sources_used", 0)})

    # 3. Adaptive rubric
    rubric = run_engine("adaptive_rubric.py", ["--task", task_id, "--json"])
    result["steps"].append({"step": "rubric", "dimensions": rubric.get("dimensions_count", 5)})

    # 4. Build prompt
    from executor import build_execution_prompt
    prompt = build_execution_prompt(task, context_block, rubric)

    # 5. Select model
    model = model_override or select_model(task)
    model_config = MODELS.get(model, MODELS["sonnet"])
    result["model"] = model
    result["model_id"] = model_config["id"]
    result["steps"].append({"step": "model_selected", "model": model})

    # 6. Trace start
    run_engine("tracer.py", ["--start", "--task", task_id, "--skill", skill,
                              "--worker", task.get("assignee", ""), "--project", project])

    if dry_run:
        result["status"] = "dry_run"
        result["prompt_preview"] = prompt[:500]
        result["prompt_tokens_est"] = len(prompt) // 4
        return result

    # 7. Atomic checkout
    if not db.checkout_task(task_id):
        result["status"] = "already_running"
        return result

    # 8. CALL CLAUDE API
    result["steps"].append({"step": "api_call_start"})
    api_result = call_claude_api(prompt, skill, model)
    result["steps"].append({"step": "api_call_end", "success": api_result.get("success", False)})

    if api_result.get("success"):
        output = api_result["output"]
        input_tokens = api_result["input_tokens"]
        output_tokens = api_result["output_tokens"]
        total_tokens = input_tokens + output_tokens
        cost = api_result["cost"]

        # 9. Auto-score via Haiku
        score_result = auto_score_output(output, rubric, task)
        score = score_result.get("score", 0)

        result["steps"].append({"step": "scored", "score": score, "cost": cost})

        # 10. Record in quality scorer
        run_engine("quality_scorer.py", [
            "--task", task_id, "--score", str(score),
            "--skill", skill, "--project", project, "--json"
        ])

        # 11. Trace end
        run_engine("tracer.py", ["--end", "--task", task_id, "--status", "success",
                                  "--tokens", str(total_tokens), "--score", str(score),
                                  "--output", output[:200]])

        # 12. Complete task in DB
        final_status = "done" if score >= 60 else "in_review"
        db.complete_task(task_id, score=score, tokens=total_tokens,
                         output=output[:1000], status=final_status)

        # 13. Audit
        db.log_event("api-executor", "task_completed", task_id=task_id,
                     details=f"model={model} score={score} tokens={total_tokens} cost=${cost:.4f}")

        result["status"] = final_status
        result["output_preview"] = output[:300]
        result["tokens"] = {"input": input_tokens, "output": output_tokens, "total": total_tokens}
        result["cost"] = cost
        result["score"] = score

    else:
        error = api_result.get("error", "Unknown API error")

        # Trace end (failed)
        run_engine("tracer.py", ["--end", "--task", task_id, "--status", "failed",
                                  "--error", error[:200]])

        # Replan
        replan = run_engine("replanner.py", [
            "--task", task_id, "--failure", "agent_timeout", "--error", error[:200], "--json"
        ])

        result["status"] = "failed"
        result["error"] = error
        result["replan"] = replan.get("action", "escalate")

        db.log_event("api-executor", "task_failed", task_id=task_id,
                     details=f"error={error[:100]} replan={replan.get('action','?')}")

    return result


def call_claude_api(prompt: str, skill: str, model: str, retries: int = 2) -> dict:
    """Call Claude API with retry and cost tracking."""
    try:
        import anthropic
    except ImportError:
        return {"success": False, "error": "anthropic SDK not installed"}

    client = anthropic.Anthropic()
    model_config = MODELS.get(model, MODELS["sonnet"])
    system_prompt = get_system_prompt(skill)

    for attempt in range(retries + 1):
        try:
            response = client.messages.create(
                model=model_config["id"],
                max_tokens=model_config["max_tokens"],
                system=[{
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},  # Prompt caching
                }],
                messages=[{"role": "user", "content": prompt}],
            )

            output = response.content[0].text
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            cost = calculate_cost(input_tokens, output_tokens, model)

            # Check for cache hits
            cache_read = getattr(response.usage, 'cache_read_input_tokens', 0)
            cache_creation = getattr(response.usage, 'cache_creation_input_tokens', 0)

            return {
                "success": True,
                "output": output,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost": cost,
                "model": model,
                "cache_read": cache_read,
                "cache_creation": cache_creation,
            }

        except anthropic.RateLimitError:
            if attempt < retries:
                wait = 2 ** (attempt + 1)
                log.warning(f"Rate limited, retry in {wait}s (attempt {attempt+1}/{retries})")
                time.sleep(wait)
                continue
            return {"success": False, "error": "Rate limited after retries"}

        except anthropic.APIError as e:
            if attempt < retries and e.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            return {"success": False, "error": f"API error: {e.message}"}

        except Exception as e:
            return {"success": False, "error": str(e)[:300]}

    return {"success": False, "error": "Max retries exceeded"}


# =============================================================================
# AUTO-SCORING via Haiku (LLM-as-Judge)
# =============================================================================

def auto_score_output(output: str, rubric: dict, task: dict) -> dict:
    """Score task output using Haiku as judge. Cheap, fast, consistent."""
    try:
        import anthropic
    except ImportError:
        return {"score": 0, "error": "SDK not installed"}

    dimensions_text = ""
    for d in rubric.get("dimensions", []):
        dimensions_text += f"- {d.get('name')} ({d.get('weight',0):.0%}): {d.get('description','')}\n"

    threshold = rubric.get("pass_threshold", 60)

    scoring_prompt = f"""Score this task output on a 0-100 scale.

TASK: {task.get('title', '')}
SKILL: {task.get('skill', '')}
PROJECT: {task.get('project', '')}

RUBRIC DIMENSIONS:
{dimensions_text}
Pass threshold: {threshold}/100

OUTPUT TO SCORE:
{output[:3000]}

Respond with ONLY a JSON object:
{{"score": <0-100>, "feedback": "<one sentence>", "dimensions": {{"<name>": <0.0-1.0>, ...}}}}"""

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=MODELS["haiku"]["id"],
            max_tokens=256,
            messages=[{"role": "user", "content": scoring_prompt}],
        )

        text = response.content[0].text.strip()
        # Extract JSON from response
        if "{" in text:
            json_str = text[text.index("{"):text.rindex("}") + 1]
            return json.loads(json_str)
        return {"score": 0, "error": "No JSON in response"}

    except Exception as e:
        log.warning(f"Auto-score failed: {e}")
        return {"score": 0, "error": str(e)[:200]}


# =============================================================================
# AUTONOMOUS PULSE — Full cycle via API
# =============================================================================

def autonomous_pulse(dry_run: bool = False, max_tasks: int = 3) -> dict:
    """Complete autonomous pulse: state → dispatch → execute wave via API."""
    db = DB()
    pulse = {"timestamp": datetime.now(timezone.utc).isoformat(), "steps": {}, "tasks_executed": []}

    # State check
    state = run_engine("state_machine.py", ["--evaluate", "--json"])
    pulse["steps"]["state"] = {"state": state.get("state"), "health": state.get("system_health")}
    if state.get("state") == "GUARDIAN":
        pulse["status"] = "guardian_stop"
        return pulse

    # Dispatch
    dispatch = run_engine("dispatch_engine.py", ["--json"])
    pulse["steps"]["dispatch"] = {"dispatched": dispatch.get("dispatched", 0)}

    # AutoDiag
    diag = run_engine("autodiag_runner.py", ["--fix", "--json"])
    pulse["steps"]["autodiag"] = {"passed": diag.get("passed", 0), "total": diag.get("total", 0)}

    # Get ready tasks
    ready = [t for t in db.get_tasks(status="todo") if t.get("assignee")]
    max_parallel = state.get("max_parallel", 3)
    wave = ready[:min(max_parallel, max_tasks)]

    pulse["steps"]["wave_size"] = len(wave)

    # Execute each task via API
    for task in wave:
        task_result = execute_task(task["id"], dry_run=dry_run)
        pulse["tasks_executed"].append({
            "task_id": task["id"],
            "status": task_result.get("status"),
            "score": task_result.get("score"),
            "tokens": task_result.get("tokens", {}).get("total"),
            "cost": task_result.get("cost"),
            "model": task_result.get("model"),
        })

    # Budget summary
    pulse["steps"]["budget"] = db.get_budget()

    # Total cost
    total_cost = sum(t.get("cost", 0) or 0 for t in pulse["tasks_executed"])
    total_tokens = sum((t.get("tokens") or 0) for t in pulse["tasks_executed"])
    pulse["totals"] = {"tasks": len(wave), "tokens": total_tokens, "cost": round(total_cost, 4)}

    pulse["status"] = "ok"

    db.log_event("api-executor", "autonomous_pulse",
                 details=f"tasks={len(wave)} tokens={total_tokens} cost=${total_cost:.4f}")

    return pulse


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="DARIO API Executor — Direct Claude API execution")
    parser.add_argument("--task", "-t", help="Execute single task via API")
    parser.add_argument("--model", "-m", choices=["haiku", "sonnet", "opus"], help="Force model")
    parser.add_argument("--pulse", action="store_true", help="Autonomous pulse (dispatch + execute wave)")
    parser.add_argument("--max-tasks", type=int, default=3, help="Max tasks per pulse")
    parser.add_argument("--dry-run", "-n", action="store_true", help="Show without calling API")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")

    args = parser.parse_args()
    if args.json:
        logging.getLogger().setLevel(logging.ERROR)

    if args.task:
        result = execute_task(args.task, model_override=args.model, dry_run=args.dry_run)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(f"=== EXECUTE: {args.task} → {result['status']} ===\n")
            for s in result.get("steps", []):
                print(f"  [{s.get('step')}] {s}")
            if result.get("score"):
                print(f"\n  Score: {result['score']}/100 | Cost: ${result.get('cost',0):.4f} | Model: {result.get('model')}")
            if result.get("prompt_preview"):
                print(f"\n  Prompt: {result['prompt_preview'][:200]}...")
        return 0 if result["status"] in ("done", "dry_run") else 2 if result["status"] == "blocked" else 3

    elif args.pulse:
        result = autonomous_pulse(dry_run=args.dry_run, max_tasks=args.max_tasks)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(f"=== AUTONOMOUS PULSE ({result.get('status')}) ===\n")
            for name, data in result.get("steps", {}).items():
                print(f"  {name}: {data}")
            print(f"\n  Tasks executed: {len(result.get('tasks_executed', []))}")
            for t in result.get("tasks_executed", []):
                print(f"    [{t.get('status')}] {t['task_id']} — score={t.get('score')} model={t.get('model')} cost=${t.get('cost',0)}")
            totals = result.get("totals", {})
            print(f"\n  Totals: {totals.get('tasks',0)} tasks, {totals.get('tokens',0)} tokens, ${totals.get('cost',0):.4f}")
        return 0

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
