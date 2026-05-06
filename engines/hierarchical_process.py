#!/usr/bin/env python3
"""
DARIO Hierarchical Process — Director-level task delegation (CrewAI-inspired).
================================================================================
Squad leaders (directors) can dynamically decompose complex tasks into subtasks
and delegate to the best available worker using synaptic weights.

Instead of flat dispatch (task → worker), hierarchical mode:
1. Task arrives at director level
2. Director decomposes into subtasks
3. Each subtask dispatched to best worker (using affinity weights)
4. Director aggregates results
5. Parent task completed with merged output

Usage:
    python hierarchical_process.py --task COMPLEX-001 --decompose --json
    python hierarchical_process.py --task COMPLEX-001 --delegate --json
    python hierarchical_process.py --task COMPLEX-001 --aggregate --json
    python hierarchical_process.py --list-directors

Integration:
    Used by executor.py when task.process_type == "hierarchical" or
    when task complexity is "complex" and a director is available.
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ORCH_DIR = Path.home() / ".claude" / "orchestrator"
sys.path.insert(0, str(ORCH_DIR))

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("hierarchical")

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

COMPANY_FILE = ORCH_DIR / "company.yaml"
WEIGHTS_FILE = ORCH_DIR / "synaptic_weights.yaml"


# =============================================================================
# DECOMPOSITION TEMPLATES
# =============================================================================

# Common task decomposition patterns by domain
DECOMPOSITION_TEMPLATES = {
    "brand_launch": {
        "description": "Full brand launch — positioning to market",
        "subtasks": [
            {"skill": "dario-brand", "title": "Brand Positioning", "order": 1},
            {"skill": "dario-naming", "title": "Naming + Domain", "order": 1},
            {"skill": "dario-story-circle", "title": "Brand Story", "order": 2, "depends_on": ["dario-brand"]},
            {"skill": "dario-offer", "title": "Grand Slam Offer", "order": 2, "depends_on": ["dario-brand"]},
            {"skill": "dario-sales-letter", "title": "Sales Copy", "order": 3, "depends_on": ["dario-offer"]},
        ],
    },
    "client_onboard": {
        "description": "New client onboarding — diagnose to proposal",
        "subtasks": [
            {"skill": "dario-diagnose", "title": "Diagnostic", "order": 1},
            {"skill": "dario-wp-audit", "title": "WordPress Audit", "order": 1},
            {"skill": "seo-audit", "title": "SEO Audit", "order": 1},
            {"skill": "dario-proposal", "title": "Proposal", "order": 2, "depends_on": ["dario-diagnose"]},
        ],
    },
    "seo_full": {
        "description": "Full SEO pipeline",
        "subtasks": [
            {"skill": "seo-technical", "title": "Technical Audit", "order": 1},
            {"skill": "seo-content", "title": "Content Audit", "order": 1},
            {"skill": "seo-local", "title": "Local SEO", "order": 1},
            {"skill": "seo-schema", "title": "Schema Markup", "order": 2},
            {"skill": "seo-plan", "title": "SEO Strategy", "order": 2, "depends_on": ["seo-technical", "seo-content"]},
        ],
    },
    "diva_project": {
        "description": "Full architecture/design project",
        "subtasks": [
            {"skill": "diva-briefing", "title": "Client Briefing", "order": 1},
            {"skill": "diva-diagnose", "title": "Site Diagnostic", "order": 1},
            {"skill": "diva-moodboard", "title": "Design Concept", "order": 2, "depends_on": ["diva-briefing"]},
            {"skill": "diva-floor-plan", "title": "Floor Plan", "order": 2, "depends_on": ["diva-briefing"]},
            {"skill": "diva-budget", "title": "Budget Estimate", "order": 3, "depends_on": ["diva-floor-plan"]},
            {"skill": "diva-timeline", "title": "Project Timeline", "order": 3, "depends_on": ["diva-budget"]},
        ],
    },
}


def get_directors() -> dict:
    """Load directors from company.yaml."""
    if not COMPANY_FILE.exists():
        return {}

    company = load_yaml(str(COMPANY_FILE))
    agents = company.get("agents", {})
    workers = company.get("workers", {})

    directors = {}
    for agent_id, agent in agents.items():
        if not isinstance(agent, dict):
            continue
        role = agent.get("role", "")
        if "director" in role.lower() or "dir-" in agent_id.lower():
            # Find workers under this director
            team = [
                {"id": wid, "skill": w.get("skill", ""), "reports_to": w.get("reports_to", "")}
                for wid, w in workers.items()
                if isinstance(w, dict) and w.get("reports_to") == agent_id
            ]
            directors[agent_id] = {
                "role": role,
                "team": team,
                "team_skills": [w["skill"] for w in team if w["skill"]],
            }

    return directors


def get_synaptic_affinity(skill_a: str, skill_b: str) -> float:
    """Get synaptic weight between two skills (affinity score)."""
    if not WEIGHTS_FILE.exists():
        return 0.5

    weights = load_yaml(str(WEIGHTS_FILE))
    if not weights:
        return 0.5

    # Read from affinity_graph (correct key)
    affinity = weights.get("affinity_graph", {})
    if not affinity:
        return 0.5

    # Try both orderings: "skill_a + skill_b" and "skill_b + skill_a"
    key1 = f"{skill_a} + {skill_b}"
    key2 = f"{skill_b} + {skill_a}"
    pair = affinity.get(key1) or affinity.get(key2)

    if pair and isinstance(pair, dict):
        return float(pair.get("weight", 0.5))

    return 0.5


def find_best_worker(skill: str, directors: dict = None) -> dict:
    """Find the best AVAILABLE worker for a skill (fixed: now checks workload)."""
    if directors is None:
        directors = get_directors()

    # Get current workload to check availability
    workload = {}
    try:
        from db import DB
        db = DB()
        active = db.get_tasks(status="in_progress")
        for t in active:
            a = t.get("assignee", "")
            if a:
                workload[a] = workload.get(a, 0) + 1
    except Exception:
        pass

    candidates = []
    for dir_id, director in directors.items():
        for worker in director["team"]:
            if worker["skill"] == skill:
                busy = workload.get(worker["id"], 0)
                candidates.append({
                    "worker_id": worker["id"],
                    "skill": skill,
                    "director": dir_id,
                    "affinity": 1.0,
                    "busy": busy,
                })

    # If no direct match, find workers with high affinity
    if not candidates:
        for dir_id, director in directors.items():
            for worker in director["team"]:
                affinity = get_synaptic_affinity(skill, worker["skill"])
                if affinity > 0.6:
                    busy = workload.get(worker["id"], 0)
                    candidates.append({
                        "worker_id": worker["id"],
                        "skill": worker["skill"],
                        "director": dir_id,
                        "affinity": affinity,
                        "busy": busy,
                    })

    # Sort by: available first, then highest affinity
    candidates.sort(key=lambda c: (-c["busy"], -c["affinity"]))
    # Prefer available workers (busy < 1)
    available = [c for c in candidates if c["busy"] < 1]
    if available:
        return available[0]
    return candidates[0] if candidates else {}


def decompose_task(task: dict, template_name: str = "") -> list[dict]:
    """
    Decompose a complex task into subtasks.
    Uses template if available, otherwise infers from skill.
    """
    from db import DB
    db = DB()

    task_id = task.get("id", "")
    project = task.get("project", "")
    priority = task.get("priority", "medium")
    directors = get_directors()

    # Find matching template
    template = None
    if template_name and template_name in DECOMPOSITION_TEMPLATES:
        template = DECOMPOSITION_TEMPLATES[template_name]
    else:
        # Auto-detect template from task skill/description
        skill = task.get("skill", "")
        desc = (task.get("description", "") + " " + task.get("title", "")).lower()
        for tname, tmpl in DECOMPOSITION_TEMPLATES.items():
            if skill in [s["skill"] for s in tmpl["subtasks"]]:
                template = tmpl
                break
            if tname.replace("_", " ") in desc:
                template = tmpl
                break

    if not template:
        log.warning(f"No decomposition template for task {task_id}")
        return []

    # Create subtasks
    subtasks = []
    for i, step in enumerate(template["subtasks"]):
        sub_id = f"{task_id}-SUB-{i+1}"

        # Find best worker
        worker = find_best_worker(step["skill"], directors)
        assignee = worker.get("worker_id", "")

        # Resolve dependencies
        deps = []
        for dep_skill in step.get("depends_on", []):
            # Find the subtask ID for this dependency
            for prev in subtasks:
                if prev.get("skill") == dep_skill:
                    deps.append(prev["id"])

        subtask = {
            "id": sub_id,
            "title": step["title"],
            "description": f"Subtask of {task_id}. {template['description']}",
            "project": project,
            "skill": step["skill"],
            "priority": priority,
            "status": "todo",
            "assignee": assignee,
            "depends_on": json.dumps(deps) if deps else "[]",
            "parent": task_id,
            "execution_policy": task.get("execution_policy", "default"),
            "estimated_tokens": 0,
        }

        subtasks.append(subtask)

    return subtasks


def delegate_subtasks(task: dict, template_name: str = "") -> dict:
    """Decompose and create all subtasks in DB."""
    from db import DB
    db = DB()

    subtasks = decompose_task(task, template_name)
    created = []

    for sub in subtasks:
        try:
            db.create_task(sub)
            created.append(sub["id"])
            log.info(f"  [DELEGATED] {sub['id']}: {sub['skill']} → {sub.get('assignee', '?')}")
        except Exception as e:
            log.error(f"  [ERROR] {sub['id']}: {e}")

    # Log to audit
    db.log_event("hierarchical", "task_decomposed", task_id=task.get("id", ""),
                details=f"Created {len(created)} subtasks: {created}")

    return {
        "parent_task": task.get("id", ""),
        "template": template_name,
        "subtasks_created": len(created),
        "subtask_ids": created,
        "subtasks": subtasks,
    }


def check_subtasks_complete(parent_id: str) -> dict:
    """Check if all subtasks of a parent are done. For aggregation."""
    from db import DB
    db = DB()

    subtasks = db.get_tasks(parent=parent_id)
    total = len(subtasks)
    done = sum(1 for t in subtasks if t.get("status") == "done")
    scores = [t.get("quality_score", 0) for t in subtasks if t.get("quality_score")]
    avg_score = sum(scores) / len(scores) if scores else 0

    return {
        "parent_id": parent_id,
        "total_subtasks": total,
        "completed": done,
        "all_done": done == total and total > 0,
        "avg_score": round(avg_score, 1),
        "subtasks": [{"id": t["id"], "skill": t.get("skill", ""), "status": t.get("status", "")} for t in subtasks],
    }


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="DARIO Hierarchical Process — Director delegation")
    parser.add_argument("--task", "-t", help="Task ID")
    parser.add_argument("--template", help="Decomposition template name")
    parser.add_argument("--decompose", action="store_true", help="Show decomposition plan (dry-run)")
    parser.add_argument("--delegate", action="store_true", help="Create subtasks in DB")
    parser.add_argument("--aggregate", action="store_true", help="Check if subtasks are done")
    parser.add_argument("--list-directors", action="store_true", help="List all directors and teams")
    parser.add_argument("--list-templates", action="store_true", help="List decomposition templates")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.list_directors:
        directors = get_directors()
        if args.json:
            print(json.dumps(directors, indent=2))
        else:
            for did, d in directors.items():
                print(f"\n  {did} ({d['role']})")
                for w in d["team"]:
                    print(f"    → {w['id']}: {w['skill']}")
        return 0

    if args.list_templates:
        for name, tmpl in DECOMPOSITION_TEMPLATES.items():
            print(f"\n  {name}: {tmpl['description']}")
            for s in tmpl["subtasks"]:
                deps = f" (after: {s.get('depends_on', [])})" if s.get("depends_on") else ""
                print(f"    [{s['order']}] {s['skill']}: {s['title']}{deps}")
        return 0

    if args.task:
        try:
            from db import DB
            task = DB().get_task(args.task)
            if not task:
                print(f"Task {args.task} not found")
                return 1

            if args.decompose:
                subtasks = decompose_task(task, args.template or "")
                if args.json:
                    print(json.dumps(subtasks, indent=2))
                else:
                    print(f"Decomposition: {len(subtasks)} subtasks")
                    for s in subtasks:
                        print(f"  → {s['id']}: {s['skill']} assigned to {s.get('assignee', '?')}")

            elif args.delegate:
                result = delegate_subtasks(task, args.template or "")
                if args.json:
                    print(json.dumps(result, indent=2))
                else:
                    print(f"Delegated {result['subtasks_created']} subtasks")

            elif args.aggregate:
                result = check_subtasks_complete(args.task)
                if args.json:
                    print(json.dumps(result, indent=2))
                else:
                    status = "READY" if result["all_done"] else f"{result['completed']}/{result['total_subtasks']}"
                    print(f"Parent {args.task}: {status} (avg score: {result['avg_score']})")
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
