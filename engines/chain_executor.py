#!/usr/bin/env python3
"""
DARIO Chain Executor — Skill chain execution with checkpointing, artifacts, and DAG.
=====================================================================================
Implements LangGraph-style checkpointing + MetaGPT-style structured artifacts +
Devin-style conditional branching for skill chains.

Features:
    - Checkpointing: save state after each step, resume from any point
    - Structured artifacts: typed JSON outputs validated between stages
    - DAG branching: fan-out, fan-in, conditional paths (if score > X → A else → B)
    - Time-travel: inspect state at any historical step

Usage:
    # Execute a chain from scratch
    python chain_executor.py --chain brand_to_market --project mar-brasa --context "Restaurante em Cascais"

    # Resume from checkpoint (after interruption)
    python chain_executor.py --resume chain_run_20260505_0730

    # Inspect chain state
    python chain_executor.py --inspect chain_run_20260505_0730

    # List active/completed chain runs
    python chain_executor.py --list

    # Dry-run (show execution plan without running)
    python chain_executor.py --chain brand_to_market --dry-run

    # JSON output
    python chain_executor.py --chain brand_to_market --dry-run --json

Directory: ~/.claude/orchestrator/chain_runs/{run_id}/
    state.yaml       — Current execution state (step, status, artifacts)
    step_1.yaml      — Checkpoint for step 1 (input, output, score, timing)
    step_2.yaml      — Checkpoint for step 2
    ...
    artifacts.yaml   — All structured artifacts accumulated
    plan.yaml        — Execution plan (DAG with conditions)

Exit codes:
    0 = chain completed successfully
    1 = error
    2 = chain paused (checkpoint saved, needs --resume)
    3 = chain failed (step failed after retries)
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from ruamel.yaml import YAML
    yaml_engine = YAML()
    yaml_engine.preserve_quotes = True
    yaml_engine.width = 200
    def load_yaml(path):
        with open(path, 'r', encoding='utf-8') as f:
            return yaml_engine.load(f)
    def dump_yaml(data, path):
        with open(path, 'w', encoding='utf-8') as f:
            yaml_engine.dump(data, f)
except ImportError:
    import yaml
    def load_yaml(path):
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    def dump_yaml(data, path):
        with open(path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


ORCH_DIR = Path.home() / ".claude" / "orchestrator"
CHAINS_FILE = ORCH_DIR / "skill_chains.yaml"
RUNS_DIR = ORCH_DIR / "chain_runs"
SCHEMAS_FILE = ORCH_DIR / "artifact_schemas.yaml"

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("chain")


# =============================================================================
# ARTIFACT SCHEMAS — Structured outputs between stages
# =============================================================================

# Default schemas per skill (what each skill MUST output as structured data)
DEFAULT_SCHEMAS = {
    "dario-brand": {
        "required": ["archetype", "positioning_statement", "tone_of_voice", "differentiators"],
        "optional": ["tagline", "brand_values", "messaging_hierarchy", "competitor_gaps"],
    },
    "dario-naming": {
        "required": ["recommended_name", "alternatives", "domain_available"],
        "optional": ["linguistic_analysis", "inpi_notes", "social_handles"],
    },
    "dario-offer": {
        "required": ["offer_title", "value_equation", "pricing", "guarantee"],
        "optional": ["bonuses", "urgency_mechanism", "risk_reversal"],
    },
    "dario-sales-letter": {
        "required": ["headline", "lead", "body", "cta"],
        "optional": ["ps_lines", "testimonial_slots", "word_count"],
    },
    "dario-email-seq": {
        "required": ["sequence_type", "email_count", "emails"],
        "optional": ["send_schedule", "segment_rules"],
    },
    "dario-diagnose": {
        "required": ["critico", "importante", "otimizacao", "overall_score"],
        "optional": ["quick_wins", "url_analyzed", "tech_stack"],
    },
    "seo-audit": {
        "required": ["score", "critical_issues", "recommendations"],
        "optional": ["pages_crawled", "schema_gaps", "competitor_comparison"],
    },
    "seo-local": {
        "required": ["gbp_optimized", "nap_format", "citations_list", "review_strategy"],
        "optional": ["schema_jsonld", "competitor_local", "categories"],
    },
    "seo-plan": {
        "required": ["site_architecture", "keyword_map", "content_calendar"],
        "optional": ["link_strategy", "hreflang_plan", "schema_plan"],
    },
    "dario-story-circle": {
        "required": ["origin_story", "about_page_copy", "short_bio"],
        "optional": ["8_beats", "brand_narrative_arc"],
    },
    "diva-briefing": {
        "required": ["requirements", "style_preferences", "budget_range", "timeline"],
        "optional": ["restrictions", "inspiration_refs", "priority_rooms"],
    },
    "diva-budget": {
        "required": ["total_estimate", "phases", "cost_per_m2"],
        "optional": ["contingency", "payment_schedule", "alternatives"],
    },
    "diva-floor-plan": {
        "required": ["layout_description", "areas_m2", "circulation_score"],
        "optional": ["zoning", "natural_light_analysis", "rgeu_compliance"],
    },
}


def validate_artifact(skill: str, artifact: dict) -> dict:
    """Validate an artifact against its skill schema."""
    schema = DEFAULT_SCHEMAS.get(skill, {})
    required = schema.get("required", [])

    missing = [f for f in required if f not in artifact or artifact[f] is None]

    return {
        "valid": len(missing) == 0,
        "missing_required": missing,
        "fields_present": list(artifact.keys()),
        "schema_exists": skill in DEFAULT_SCHEMAS,
    }


def merge_parallel_artifacts(artifacts: dict, wave_skills: list) -> dict:
    """
    Conflict-free merge for parallel wave outputs.
    Each skill writes to its own namespace — no shared keys = no conflicts.
    Fan-in: next wave receives unified context from all parallel outputs.

    Strategy (reducer-alternative):
    - Each skill's artifact is namespaced under its skill name
    - Merge = union of all namespaces
    - If same key exists in 2 skills, prefix with skill name (no data loss)
    """
    merged = {}

    for skill in wave_skills:
        skill_output = artifacts.get(skill, {})
        if not isinstance(skill_output, dict):
            continue

        for key, value in skill_output.items():
            if key in merged:
                # Conflict: namespace it to avoid data loss
                merged[f"{skill}_{key}"] = value
            else:
                merged[key] = value

    return merged


def build_context_for_step(artifacts: dict, step_def: dict) -> str:
    """
    Build input context for a step from accumulated artifacts.
    Uses 'receives' field to select relevant data.
    """
    receives = step_def.get("receives", "")

    # Flatten all artifacts into a single context dict
    flat = {}
    for skill, artifact in artifacts.items():
        if isinstance(artifact, dict):
            for k, v in artifact.items():
                flat[k] = v

    # Build context string with available data
    context_parts = [f"## Input from previous steps\n"]
    context_parts.append(f"**Step expects:** {receives}\n")
    context_parts.append(f"**Available data:**\n")

    for k, v in flat.items():
        if isinstance(v, list):
            context_parts.append(f"- {k}: {', '.join(str(x) for x in v[:5])}")
        elif isinstance(v, str) and len(v) > 100:
            context_parts.append(f"- {k}: {v[:100]}...")
        else:
            context_parts.append(f"- {k}: {v}")

    return "\n".join(context_parts)


# =============================================================================
# DAG PLAN — Execution graph with conditions
# =============================================================================

def build_execution_plan(chain_def: dict, context: dict = None) -> list:
    """
    Build a DAG execution plan from chain definition.
    Returns ordered list of steps with parallel groups and conditions.

    Handles both:
    - Steps WITH 'order' field → group by order (parallel waves)
    - Steps WITHOUT 'order' → sequential (each step = own wave), respecting 'parallel' flag

    Plan format:
    [
        {"wave": 1, "steps": [{"skill": "X", "parallel": False}]},
        {"wave": 2, "steps": [{"skill": "A", "parallel": True}, {"skill": "B", "parallel": True}]},
        {"wave": 3, "steps": [...], "condition": {"if": "step_2_score > 70", "else_skip": True}},
    ]
    """
    steps = chain_def.get("steps", [])
    if not steps:
        return []

    # Check if steps have explicit 'order' field
    has_order = any(isinstance(s, dict) and "order" in s for s in steps)

    if has_order:
        # Group by order (wave) — steps with same order run parallel
        waves = {}
        for step in steps:
            order = step.get("order", 1) if isinstance(step, dict) else 1
            waves.setdefault(order, []).append(step)
    else:
        # Sequential: each step is its own wave, but consecutive parallel=True merge
        waves = {}
        wave_num = 1
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            if i > 0 and step.get("parallel") and steps[i-1].get("parallel"):
                # Merge with previous wave (both parallel)
                waves.setdefault(wave_num, []).append(step)
            else:
                if i > 0:
                    wave_num += 1
                waves.setdefault(wave_num, []).append(step)

    plan = []
    for wave_num in sorted(waves.keys()):
        wave_steps = waves[wave_num]
        plan.append({
            "wave": wave_num,
            "steps": [{
                "skill": s.get("skill", "?"),
                "receives": s.get("receives", ""),
                "produces": s.get("produces", ""),
                "pass_to_next": s.get("pass_to_next", []),
                "parallel": s.get("parallel", False),
                "condition": s.get("condition", None),
            } for s in wave_steps],
        })

    return plan


# =============================================================================
# CHAIN RUN STATE
# =============================================================================

def create_run(chain_name: str, chain_def: dict, project: str, context: str) -> dict:
    """Initialize a new chain run with execution plan."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_id = f"chain_run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True)

    plan = build_execution_plan(chain_def)

    state = {
        "run_id": run_id,
        "chain_name": chain_name,
        "project": project,
        "initial_context": context,
        "status": "running",
        "current_wave": 1,
        "current_step": 0,
        "total_waves": len(plan),
        "total_steps": sum(len(w["steps"]) for w in plan),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
        "artifacts": {},
        "step_scores": [],
        "errors": [],
    }

    # Save state and plan
    dump_yaml(state, str(run_dir / "state.yaml"))
    dump_yaml({"plan": plan, "chain_def": chain_def}, str(run_dir / "plan.yaml"))
    dump_yaml({}, str(run_dir / "artifacts.yaml"))

    return state


def save_checkpoint(run_id: str, wave: int, step_index: int,
                    skill: str, input_ctx: str, output_artifact: dict,
                    score: int = 0, status: str = "success", error: str = "") -> dict:
    """Save checkpoint after a step completes."""
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        return {"error": "Run not found"}

    checkpoint = {
        "wave": wave,
        "step_index": step_index,
        "skill": skill,
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "input_context_preview": input_ctx[:300] if input_ctx else "",
        "output_artifact": output_artifact,
        "score": score,
        "error": error,
    }

    # Validate artifact against schema
    validation = validate_artifact(skill, output_artifact)
    checkpoint["artifact_valid"] = validation["valid"]
    checkpoint["artifact_missing"] = validation["missing_required"]

    # Save step checkpoint
    step_file = run_dir / f"step_{wave}_{step_index}.yaml"
    dump_yaml(checkpoint, str(step_file))

    # Update accumulated artifacts
    artifacts_file = run_dir / "artifacts.yaml"
    artifacts = load_yaml(str(artifacts_file)) or {}
    artifacts[skill] = output_artifact
    dump_yaml(artifacts, str(artifacts_file))

    # Update run state
    state_file = run_dir / "state.yaml"
    state = load_yaml(str(state_file))
    state["current_wave"] = wave
    state["current_step"] = step_index
    state["artifacts"] = artifacts
    state["step_scores"].append({"skill": skill, "score": score, "wave": wave})

    if status == "failed":
        state["errors"].append({"skill": skill, "wave": wave, "error": error})

    dump_yaml(state, str(state_file))

    return checkpoint


def complete_run(run_id: str, final_status: str = "completed"):
    """Mark run as completed."""
    run_dir = RUNS_DIR / run_id
    state_file = run_dir / "state.yaml"
    if not state_file.exists():
        return

    state = load_yaml(str(state_file))
    state["status"] = final_status
    state["completed_at"] = datetime.now(timezone.utc).isoformat()

    # Calculate aggregate score
    scores = [s["score"] for s in state.get("step_scores", []) if s.get("score")]
    state["avg_score"] = round(sum(scores) / len(scores), 1) if scores else 0

    dump_yaml(state, str(state_file))


# =============================================================================
# INSPECT / RESUME / LIST
# =============================================================================

def inspect_run(run_id: str) -> dict:
    """Get full state of a chain run."""
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        return None

    state = load_yaml(str(run_dir / "state.yaml"))
    plan = load_yaml(str(run_dir / "plan.yaml"))

    # Load all step checkpoints
    steps = []
    for f in sorted(run_dir.glob("step_*.yaml")):
        step = load_yaml(str(f))
        if step:
            steps.append(step)

    return {
        "state": state,
        "plan": plan,
        "checkpoints": steps,
    }


def list_runs(limit: int = 20) -> list:
    """List chain runs."""
    if not RUNS_DIR.exists():
        return []
    runs = []
    for d in sorted(RUNS_DIR.iterdir(), reverse=True):
        if d.is_dir() and (d / "state.yaml").exists():
            state = load_yaml(str(d / "state.yaml"))
            if state:
                runs.append({
                    "run_id": state.get("run_id"),
                    "chain": state.get("chain_name"),
                    "project": state.get("project"),
                    "status": state.get("status"),
                    "progress": f"{state.get('current_step', 0)}/{state.get('total_steps', '?')}",
                    "avg_score": state.get("avg_score", 0),
                })
            if len(runs) >= limit:
                break
    return runs


def get_resume_context(run_id: str) -> dict:
    """Get context needed to resume a paused chain."""
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        return None

    state = load_yaml(str(run_dir / "state.yaml"))
    plan_data = load_yaml(str(run_dir / "plan.yaml"))
    artifacts = load_yaml(str(run_dir / "artifacts.yaml")) or {}

    return {
        "run_id": run_id,
        "chain_name": state.get("chain_name"),
        "project": state.get("project"),
        "resume_from_wave": state.get("current_wave"),
        "resume_from_step": state.get("current_step") + 1,
        "accumulated_artifacts": artifacts,
        "initial_context": state.get("initial_context"),
        "plan": plan_data.get("plan", []),
    }


# =============================================================================
# DRY RUN
# =============================================================================

def dry_run_chain(chain_name: str) -> dict:
    """Show execution plan without running."""
    chains_data = load_yaml(str(CHAINS_FILE)) if CHAINS_FILE.exists() else {}
    chains = chains_data.get("chains", {})

    if chain_name not in chains:
        return {"error": f"Chain '{chain_name}' not found. Available: {list(chains.keys())}"}

    chain_def = chains[chain_name]
    plan = build_execution_plan(chain_def)

    return {
        "chain": chain_name,
        "description": chain_def.get("description", ""),
        "estimated_tokens": chain_def.get("estimated_tokens", "?"),
        "quality_gate": chain_def.get("quality_gate", "score >= 70"),
        "total_waves": len(plan),
        "total_steps": sum(len(w["steps"]) for w in plan),
        "plan": plan,
        "schemas_available": [
            s["skill"] for w in plan for s in w["steps"]
            if s["skill"] in DEFAULT_SCHEMAS
        ],
    }


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="DARIO Chain Executor — Skill chains with checkpointing + DAG",
    )
    parser.add_argument("--chain", "-c", help="Chain name to execute")
    parser.add_argument("--project", "-p", default="", help="Project name")
    parser.add_argument("--context", default="", help="Initial context/briefing")
    parser.add_argument("--resume", help="Resume a paused chain by run_id")
    parser.add_argument("--inspect", help="Inspect chain run state")
    parser.add_argument("--list", action="store_true", help="List chain runs")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without executing")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")

    # Checkpoint recording (called by autopilot during execution)
    parser.add_argument("--checkpoint", action="store_true", help="Save a step checkpoint")
    parser.add_argument("--run-id", help="Run ID for checkpoint")
    parser.add_argument("--wave", type=int, help="Wave number")
    parser.add_argument("--step", type=int, help="Step index in wave")
    parser.add_argument("--skill", help="Skill that executed")
    parser.add_argument("--input-ctx", default="", help="Input context")
    parser.add_argument("--artifact", default="{}", help="Output artifact as JSON")
    parser.add_argument("--score", type=int, default=0, help="Quality score")
    parser.add_argument("--status", default="success", help="Step status")
    parser.add_argument("--error", default="", help="Error if failed")

    args = parser.parse_args()
    if args.json:
        logging.getLogger().setLevel(logging.ERROR)

    if args.list:
        runs = list_runs()
        if args.json:
            print(json.dumps(runs, indent=2))
        else:
            print(f"=== CHAIN RUNS ({len(runs)}) ===\n")
            for r in runs:
                mark = "+" if r["status"] == "completed" else "~" if r["status"] == "running" else "!"
                print(f"  [{mark}] {r['run_id']} — {r['chain']} ({r['project']}) [{r['status']}] {r['progress']} steps, avg={r['avg_score']}")
        return 0

    elif args.inspect:
        data = inspect_run(args.inspect)
        if not data:
            print(f"Run not found: {args.inspect}")
            return 1
        if args.json:
            print(json.dumps(data, indent=2, default=str))
        else:
            state = data["state"]
            print(f"=== CHAIN RUN: {args.inspect} ===\n")
            print(f"  Chain:    {state.get('chain_name')}")
            print(f"  Project:  {state.get('project')}")
            print(f"  Status:   {state.get('status')}")
            print(f"  Progress: wave {state.get('current_wave')}/{state.get('total_waves')}, step {state.get('current_step')}/{state.get('total_steps')}")
            print(f"  Avg score: {state.get('avg_score', 0)}")
            print(f"\n  Checkpoints:")
            for ckpt in data["checkpoints"]:
                mark = "+" if ckpt.get("status") == "success" else "!"
                valid = "valid" if ckpt.get("artifact_valid") else f"MISSING: {ckpt.get('artifact_missing')}"
                print(f"    [{mark}] W{ckpt['wave']}S{ckpt['step_index']} {ckpt['skill']} — score={ckpt.get('score',0)} artifact={valid}")
            artifacts = state.get("artifacts", {})
            if artifacts:
                print(f"\n  Accumulated artifacts: {list(artifacts.keys())}")
        return 0

    elif args.resume:
        ctx = get_resume_context(args.resume)
        if not ctx:
            print(f"Run not found: {args.resume}")
            return 1
        if args.json:
            print(json.dumps(ctx, indent=2, default=str))
        else:
            print(f"=== RESUME CONTEXT: {args.resume} ===\n")
            print(f"  Chain: {ctx['chain_name']} | Project: {ctx['project']}")
            print(f"  Resume from: wave {ctx['resume_from_wave']}, step {ctx['resume_from_step']}")
            print(f"  Artifacts available: {list(ctx['accumulated_artifacts'].keys())}")
            print(f"\n  Use this context to continue the chain in autopilot.")
        return 0

    elif args.dry_run and args.chain:
        result = dry_run_chain(args.chain)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if "error" in result:
                print(result["error"])
                return 1
            print(f"=== DRY RUN: {args.chain} ===\n")
            print(f"  {result['description']}")
            print(f"  Estimated tokens: {result['estimated_tokens']}")
            print(f"  Quality gate: {result['quality_gate']}")
            print(f"  Waves: {result['total_waves']} | Steps: {result['total_steps']}")
            print(f"  Schemas available: {len(result['schemas_available'])}/{result['total_steps']}")
            print(f"\n  Execution plan:")
            for wave in result["plan"]:
                parallel = " (parallel)" if any(s.get("parallel") for s in wave["steps"]) else ""
                print(f"    Wave {wave['wave']}{parallel}:")
                for s in wave["steps"]:
                    schema = "+" if s["skill"] in DEFAULT_SCHEMAS else "-"
                    cond = f" [IF: {s['condition']}]" if s.get("condition") else ""
                    print(f"      [{schema}] {s['skill']}{cond}")
                    if s.get("produces"):
                        print(f"          produces: {s['produces'][:60]}")
        return 0

    elif args.chain:
        # Initialize a new chain run
        chains_data = load_yaml(str(CHAINS_FILE)) if CHAINS_FILE.exists() else {}
        chains = chains_data.get("chains", {})
        if args.chain not in chains:
            print(f"Chain not found: {args.chain}. Available: {list(chains.keys())}")
            return 1
        state = create_run(args.chain, chains[args.chain], args.project, args.context)
        if args.json:
            print(json.dumps(state, indent=2, default=str))
        else:
            print(f"Chain run initialized: {state['run_id']}")
            print(f"  Chain: {args.chain} | Waves: {state['total_waves']} | Steps: {state['total_steps']}")
            print(f"  Resume with: python chain_executor.py --resume {state['run_id']}")
        return 0

    elif args.checkpoint and args.run_id:
        artifact = {}
        if args.artifact:
            try:
                artifact = json.loads(args.artifact)
            except json.JSONDecodeError:
                artifact = {"raw_output": args.artifact}

        result = save_checkpoint(
            args.run_id, args.wave or 1, args.step or 0,
            args.skill or "", args.input_ctx, artifact,
            args.score, args.status, args.error
        )
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            valid = "VALID" if result.get("artifact_valid") else f"INVALID (missing: {result.get('artifact_missing')})"
            print(f"Checkpoint saved: W{args.wave}S{args.step} {args.skill} — {args.status}, artifact {valid}")
        return 0

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
