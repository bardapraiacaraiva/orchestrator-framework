#!/usr/bin/env python3
"""
DARIO Context Injector — Auto-enrich task prompts before execution.
====================================================================
Assembles rich context from multiple sources so skills execute with
full knowledge, not in a vacuum. Eliminates "generic output" problem.

Sources:
    1. Project memory (from ~/.claude/projects/.../memory/)
    2. Previous task outputs (artifacts from chain or same project)
    3. RAG knowledge base (localhost:8420 search)
    4. Skill-specific hints (from skill_chains.yaml 'receives' field)
    5. Quality feedback (if revision — what to improve)

Usage:
    python context_injector.py --task MNB-002 --json
    python context_injector.py --task MNB-002 --skill dario-naming --project mar-brasa

    # Returns assembled context block ready to inject into Agent prompt

Exit codes:
    0 = context assembled
    1 = error
"""

import argparse
import json
import logging
import subprocess
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
# Dynamic memory dir (fixed: was hardcoded to one user/machine)
_project_base = Path.home() / ".claude" / "projects"
_candidates = list(_project_base.glob("*/memory")) if _project_base.exists() else []
MEMORY_DIR = _candidates[0] if _candidates else _project_base / "default" / "memory"
CHAINS_FILE = ORCH_DIR / "skill_chains.yaml"
RUNS_DIR = ORCH_DIR / "chain_runs"
RAG_URL = "http://localhost:8420"

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("context")


def get_project_memory(project: str) -> str:
    """Load project-specific memory if exists."""
    if not project or not MEMORY_DIR.exists():
        return ""

    # Try common naming patterns
    candidates = [
        f"project_{project}.md",
        f"project_{project.replace('-', '_')}.md",
    ]
    for name in candidates:
        path = MEMORY_DIR / name
        if path.exists():
            content = path.read_text(encoding="utf-8")
            # Extract key info (skip frontmatter)
            lines = content.split("\n")
            body = []
            in_frontmatter = False
            for line in lines:
                if line.strip() == "---":
                    in_frontmatter = not in_frontmatter
                    continue
                if not in_frontmatter:
                    body.append(line)
            return "\n".join(body[:50])  # First 50 lines max

    return ""


def get_previous_outputs(project: str, current_task_id: str) -> list:
    """Get outputs from completed tasks in the same project (DB-first, YAML fallback)."""
    outputs = []

    # Try DB first (has full outputs stored)
    try:
        sys.path.insert(0, str(ORCH_DIR))
        from db import DB
        db = DB()
        with db._conn() as conn:
            rows = conn.execute(
                """SELECT id, skill, quality_score, substr(completion_comment, 1, 500) as preview
                   FROM tasks
                   WHERE project = ? AND id != ? AND status = 'done'
                   AND completion_comment IS NOT NULL AND length(completion_comment) > 50
                   ORDER BY quality_score DESC
                   LIMIT 5""",
                (project, current_task_id),
            ).fetchall()
            for r in rows:
                d = dict(r)
                outputs.append({
                    "task": d["id"],
                    "skill": d["skill"],
                    "output": d["preview"],
                    "score": d.get("quality_score"),
                })
        if outputs:
            return outputs
    except Exception:
        pass

    # YAML fallback
    if not TASKS_DIR.exists():
        return outputs

    for f in TASKS_DIR.glob("*.yaml"):
        try:
            data = load_yaml(str(f))
            if not data:
                continue
            if data.get("project") != project:
                continue
            if data.get("id") == current_task_id:
                continue
            if data.get("status") != "done":
                continue
            comment = data.get("completion_comment", "")
            if comment:
                outputs.append({
                    "task": data.get("id"),
                    "skill": data.get("skill", "?"),
                    "output": comment[:500],
                })
        except Exception:
            pass

    return outputs[:5]


def get_chain_artifacts(project: str, skill: str) -> dict:
    """Get accumulated artifacts from any chain run for this project."""
    if not RUNS_DIR.exists():
        return {}

    for d in sorted(RUNS_DIR.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        state_file = d / "state.yaml"
        if not state_file.exists():
            continue
        state = load_yaml(str(state_file))
        if state and state.get("project") == project:
            artifacts_file = d / "artifacts.yaml"
            if artifacts_file.exists():
                artifacts = load_yaml(str(artifacts_file))
                if artifacts and isinstance(artifacts, dict):
                    return artifacts

    return {}


def search_rag(keywords: list, task_description: str = "") -> list:
    """
    Search RAG knowledge base using multiple strategies:
    1. Semantic search with full task description (vector similarity)
    2. Keyword search as fallback
    3. Filter by relevance score > 0.35
    """
    results = []

    # Strategy 1: Semantic search with task description (HyDE-enhanced if available)
    if task_description:
        try:
            import urllib.request
            import urllib.parse
            # Use the /search endpoint with the full description for better vector match
            query = task_description[:500]  # First 500 chars for semantic search
            payload = json.dumps({"query": query, "top_k": 5}).encode()
            req = urllib.request.Request(
                f"{RAG_URL}/search",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                for r in data.get("results", []):
                    score = r.get("score", 0)
                    if score > 0.35:
                        results.append({
                            "text": r.get("text", "")[:300],
                            "score": round(score, 3),
                            "source": r.get("source", ""),
                            "method": "semantic",
                        })
        except Exception:
            pass

    # Rank results with composite scoring (fixed: was orphan module, now integrated)
    if results:
        try:
            from composite_memory_scoring import score_and_rank
            project = ""  # Will be set by caller
            ranked = score_and_rank(results, scope=project, limit=5)
            results = [{"text": r["content"][:300], "score": r["composite"], "source": r["source"], "method": "ranked"} for r in ranked]
        except ImportError:
            pass  # Fallback to unranked results

    # Strategy 2: Keyword fallback (if semantic returned nothing)
    if not results and keywords:
        try:
            import urllib.request
            import urllib.parse
            query = " ".join(keywords[:4])
            url = f"{RAG_URL}/search?q={urllib.parse.quote(query)}&top_k=3"
            with urllib.request.urlopen(url, timeout=3) as resp:
                data = json.loads(resp.read())
                for r in data.get("results", []):
                    score = r.get("score", 0)
                    if score > 0.35:
                        results.append({
                            "text": r.get("text", "")[:300],
                            "score": round(score, 3),
                            "source": r.get("source", ""),
                            "method": "keyword",
                        })
        except Exception:
            pass

    # Deduplicate by text similarity (crude but effective)
    seen_texts = set()
    unique = []
    for r in results:
        text_key = r["text"][:100]
        if text_key not in seen_texts:
            seen_texts.add(text_key)
            unique.append(r)

    return unique[:5]  # Max 5 chunks


def get_revision_feedback(task_data: dict) -> str:
    """If task is in revision, get quality feedback."""
    notes = task_data.get("notes", [])
    if not isinstance(notes, list):
        return ""

    feedback_lines = []
    for note in notes:
        if isinstance(note, str) and ("REPLAN" in note or "Revision" in note or "feedback" in note.lower()):
            feedback_lines.append(note)

    return "\n".join(feedback_lines[-3:])  # Last 3 feedback notes


def get_skill_hints(skill: str) -> str:
    """Get 'receives' field from skill_chains for context hints."""
    if not CHAINS_FILE.exists():
        return ""

    chains = load_yaml(str(CHAINS_FILE))
    if not chains:
        return ""

    for chain_def in (chains.get("chains") or {}).values():
        for step in (chain_def.get("steps") or []):
            if isinstance(step, dict) and step.get("skill") == skill:
                receives = step.get("receives", "")
                produces = step.get("produces", "")
                if receives or produces:
                    return f"This skill expects: {receives}\nIt should produce: {produces}"

    return ""


def assemble_context(task_id: str, skill: str = "", project: str = "") -> dict:
    """Assemble full context from all sources."""
    result = {
        "task_id": task_id,
        "sections": [],
        "total_tokens_est": 0,
    }

    # Load task data
    task_data = {}
    task_file = TASKS_DIR / f"{task_id}.yaml"
    if task_file.exists():
        task_data = load_yaml(str(task_file)) or {}
        if not skill:
            skill = task_data.get("skill", "")
        if not project:
            project = task_data.get("project", "")

    # 1. Project memory
    memory = get_project_memory(project)
    if memory:
        result["sections"].append({
            "source": "project_memory",
            "content": memory,
            "priority": "high",
        })

    # 2. Previous outputs from same project
    prev_outputs = get_previous_outputs(project, task_id)
    if prev_outputs:
        content = "\n".join([
            f"- [{o['task']}] ({o['skill']}): {o['output'][:150]}"
            for o in prev_outputs
        ])
        result["sections"].append({
            "source": "previous_outputs",
            "content": content,
            "priority": "high",
        })

    # 3. Chain artifacts
    artifacts = get_chain_artifacts(project, skill)
    if artifacts:
        content = json.dumps(artifacts, indent=2, default=str)[:800]
        result["sections"].append({
            "source": "chain_artifacts",
            "content": content,
            "priority": "high",
        })

    # 4. RAG search
    keywords = []
    if skill:
        keywords.append(skill.replace("dario-", "").replace("seo-", "").replace("diva-", ""))
    if project:
        keywords.append(project)
    title = task_data.get("title", "")
    if title:
        keywords.extend(title.split()[:3])

    task_desc = f"{task_data.get('title', '')} {task_data.get('description', '')}"
    rag_results = search_rag(keywords, task_description=task_desc)
    if rag_results:
        content_lines = []
        for r in rag_results:
            source = f" [{r.get('source', '')}]" if r.get("source") else ""
            method = r.get("method", "?")
            content_lines.append(f"- ({r['score']:.2f}, {method}{source}) {r['text']}")
        content = "\n".join(content_lines)
        result["sections"].append({
            "source": "rag_knowledge",
            "content": content,
            "priority": "medium",
            "chunks": len(rag_results),
            "avg_relevance": round(sum(r["score"] for r in rag_results) / len(rag_results), 3),
        })

    # 5. Skill hints
    hints = get_skill_hints(skill)
    if hints:
        result["sections"].append({
            "source": "skill_hints",
            "content": hints,
            "priority": "medium",
        })

    # 6. Revision feedback
    feedback = get_revision_feedback(task_data)
    if feedback:
        result["sections"].append({
            "source": "revision_feedback",
            "content": f"IMPORTANT — Previous attempt failed. Fix these issues:\n{feedback}",
            "priority": "critical",
        })

    # Build final context block
    context_block = f"## Context for {task_id} ({skill})\n\n"
    for section in sorted(result["sections"], key=lambda s: {"critical": 0, "high": 1, "medium": 2}.get(s["priority"], 3)):
        context_block += f"### {section['source'].replace('_', ' ').title()}\n{section['content']}\n\n"

    result["context_block"] = context_block
    result["total_tokens_est"] = len(context_block) // 4  # Rough estimate
    result["sources_used"] = len(result["sections"])

    return result


def main():
    parser = argparse.ArgumentParser(description="DARIO Context Injector")
    parser.add_argument("--task", "-t", required=True, help="Task ID")
    parser.add_argument("--skill", default="", help="Skill (auto-detected from task)")
    parser.add_argument("--project", default="", help="Project (auto-detected from task)")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")

    args = parser.parse_args()
    if args.json:
        logging.getLogger().setLevel(logging.ERROR)

    result = assemble_context(args.task, args.skill, args.project)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"=== CONTEXT for {args.task} ({result['sources_used']} sources, ~{result['total_tokens_est']} tokens) ===\n")
        print(result["context_block"])

    return 0


if __name__ == "__main__":
    sys.exit(main())
