#!/usr/bin/env python3
"""
DARIO Task Templates — Parametric, reusable task definitions.
==============================================================
Define once, instantiate many times with ${variables}.

Usage:
    # List available templates
    python task_templates.py --list

    # Preview a template with variables
    python task_templates.py --template brand_audit --vars '{"client":"Vivenda","url":"vivendacreative.pt"}'

    # Instantiate (create real tasks in DB)
    python task_templates.py --template brand_audit --vars '{"client":"Vivenda","url":"vivendacreative.pt"}' --create

    # Create a new template
    python task_templates.py --define '{"name":"seo_quick","tasks":[...]}'
"""

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude" / "orchestrator"))
from db import DB

ORCH_DIR = Path.home() / ".claude" / "orchestrator"
TEMPLATES_DIR = ORCH_DIR / "tasks" / "templates"

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("templates")

# =============================================================================
# BUILT-IN TEMPLATES
# =============================================================================

BUILTIN_TEMPLATES = {
    "brand_audit": {
        "name": "Brand Audit & Positioning",
        "description": "Full brand analysis: diagnose → brand positioning → naming review → story",
        "variables": ["client", "url", "industry"],
        "project_prefix": "BA",
        "tasks": [
            {"id": "${prefix}-001", "title": "Diagnóstico holístico — ${client}", "skill": "dario-diagnose",
             "description": "Auditoria completa de ${url}. Indústria: ${industry}.", "priority": "high",
             "depends_on": []},
            {"id": "${prefix}-002", "title": "Brand positioning — ${client}", "skill": "dario-brand",
             "description": "Posicionamento, archetype, messaging para ${client} (${industry}).",
             "priority": "high", "depends_on": ["${prefix}-001"]},
            {"id": "${prefix}-003", "title": "Naming review — ${client}", "skill": "dario-naming",
             "description": "Análise do nome ${client}. KEEP/CHANGE/EVOLVE.", "priority": "medium",
             "depends_on": ["${prefix}-002"]},
            {"id": "${prefix}-004", "title": "Brand story — ${client}", "skill": "dario-story-circle",
             "description": "Narrativa de origem para ${client}. About page + short bio.",
             "priority": "medium", "depends_on": ["${prefix}-002", "${prefix}-003"]},
        ],
    },
    "seo_full": {
        "name": "Full SEO Pipeline",
        "description": "Keywords → clusters → strategy → schema → sitemap",
        "variables": ["client", "url", "industry"],
        "project_prefix": "SEO",
        "tasks": [
            {"id": "${prefix}-001", "title": "Keyword research — ${client}", "skill": "dario-kw-cluster",
             "description": "Cluster keywords para ${url} (${industry}).", "priority": "high",
             "depends_on": []},
            {"id": "${prefix}-002", "title": "SEO strategy — ${client}", "skill": "seo-plan",
             "description": "Estratégia 90 dias para ${url}.", "priority": "high",
             "depends_on": ["${prefix}-001"]},
            {"id": "${prefix}-003", "title": "Schema markup — ${client}", "skill": "seo-schema",
             "description": "JSON-LD structured data para ${url}.", "priority": "medium",
             "depends_on": ["${prefix}-002"]},
            {"id": "${prefix}-004", "title": "Sitemap — ${client}", "skill": "seo-sitemap",
             "description": "XML sitemap optimizado para ${url}.", "priority": "medium",
             "depends_on": ["${prefix}-002"]},
        ],
    },
    "wp_health": {
        "name": "WordPress Health Check",
        "description": "Diagnose → WP audit → SEO audit → CWV fix",
        "variables": ["client", "url"],
        "project_prefix": "WP",
        "tasks": [
            {"id": "${prefix}-001", "title": "Diagnóstico — ${client}", "skill": "dario-diagnose",
             "description": "Diagnóstico holístico de ${url}.", "priority": "high", "depends_on": []},
            {"id": "${prefix}-002", "title": "WP Audit — ${client}", "skill": "dario-wp-audit",
             "description": "Auditoria WordPress completa de ${url}.", "priority": "high",
             "depends_on": ["${prefix}-001"]},
            {"id": "${prefix}-003", "title": "SEO Audit — ${client}", "skill": "seo-audit",
             "description": "Auditoria SEO de ${url}.", "priority": "high",
             "depends_on": ["${prefix}-001"]},
            {"id": "${prefix}-004", "title": "CWV Fix — ${client}", "skill": "dario-cwv-fix",
             "description": "Corrigir Core Web Vitals de ${url}.", "priority": "critical",
             "depends_on": ["${prefix}-002", "${prefix}-003"]},
        ],
    },
    "client_onboard": {
        "name": "New Client Onboarding",
        "description": "Diagnose → audit → brand → proposal",
        "variables": ["client", "url", "industry", "deadline"],
        "project_prefix": "ON",
        "tasks": [
            {"id": "${prefix}-001", "title": "Diagnóstico — ${client}", "skill": "dario-diagnose",
             "description": "Diagnóstico inicial de ${url}. Deadline: ${deadline}.", "priority": "critical",
             "execution_policy": "client_facing", "depends_on": []},
            {"id": "${prefix}-002", "title": "WP Audit — ${client}", "skill": "dario-wp-audit",
             "description": "Auditoria técnica de ${url}.", "priority": "high",
             "depends_on": ["${prefix}-001"]},
            {"id": "${prefix}-003", "title": "Brand analysis — ${client}", "skill": "dario-brand",
             "description": "Posicionamento actual e recomendações para ${client} (${industry}).",
             "priority": "high", "depends_on": ["${prefix}-001"]},
            {"id": "${prefix}-004", "title": "Proposta comercial — ${client}", "skill": "dario-proposal",
             "description": "Proposta 3 opções (Blair Enns) para ${client}. Deadline: ${deadline}.",
             "priority": "critical", "execution_policy": "client_facing",
             "depends_on": ["${prefix}-002", "${prefix}-003"]},
        ],
    },
    "diva_project": {
        "name": "Architecture Project Kickoff",
        "description": "Briefing → diagnose → floor plan + moodboard → budget → timeline",
        "variables": ["client", "location", "project_type", "budget_range"],
        "project_prefix": "ARQ",
        "tasks": [
            {"id": "${prefix}-001", "title": "Briefing — ${client} (${location})", "skill": "diva-briefing",
             "description": "${project_type} em ${location}. Budget: ${budget_range}.", "priority": "critical",
             "depends_on": []},
            {"id": "${prefix}-002", "title": "Diagnóstico — ${client}", "skill": "diva-diagnose",
             "description": "Avaliação estrutural e potencial.", "priority": "high",
             "depends_on": ["${prefix}-001"]},
            {"id": "${prefix}-003", "title": "Floor plan — ${client}", "skill": "diva-floor-plan",
             "description": "Layout optimizado.", "priority": "high",
             "depends_on": ["${prefix}-002"]},
            {"id": "${prefix}-004", "title": "Moodboard — ${client}", "skill": "diva-moodboard",
             "description": "Direcção visual.", "priority": "medium",
             "depends_on": ["${prefix}-001"]},
            {"id": "${prefix}-005", "title": "Orçamento — ${client}", "skill": "diva-budget",
             "description": "Estimativa ProNIC.", "priority": "high",
             "depends_on": ["${prefix}-003", "${prefix}-004"]},
            {"id": "${prefix}-006", "title": "Timeline — ${client}", "skill": "diva-timeline",
             "description": "Cronograma Gantt.", "priority": "medium",
             "depends_on": ["${prefix}-005"]},
        ],
    },
}


def resolve_variables(text: str, variables: dict, prefix: str) -> str:
    """Replace ${var} placeholders with values."""
    variables["prefix"] = prefix
    def replacer(match):
        var_name = match.group(1)
        return str(variables.get(var_name, f"${{{var_name}}}"))
    return re.sub(r'\$\{(\w+)\}', replacer, str(text))


def instantiate_template(template_name: str, variables: dict,
                         create: bool = False) -> dict:
    """Instantiate a template with variables."""
    if template_name not in BUILTIN_TEMPLATES:
        # Check custom templates directory
        custom_file = TEMPLATES_DIR / f"{template_name}.json"
        if custom_file.exists():
            template = json.loads(custom_file.read_text(encoding="utf-8"))
        else:
            return {"error": f"Template '{template_name}' not found. Available: {list(BUILTIN_TEMPLATES.keys())}"}
    else:
        template = BUILTIN_TEMPLATES[template_name]

    prefix = template.get("project_prefix", "T")
    # Generate unique prefix with timestamp
    ts = datetime.now(timezone.utc).strftime("%m%d")
    prefix = f"{prefix}{ts}"

    tasks = []
    for task_def in template["tasks"]:
        task = {}
        for key, value in task_def.items():
            if isinstance(value, str):
                task[key] = resolve_variables(value, variables, prefix)
            elif isinstance(value, list):
                task[key] = [resolve_variables(v, variables, prefix) if isinstance(v, str) else v for v in value]
            else:
                task[key] = value
        tasks.append(task)

    result = {
        "template": template_name,
        "description": template.get("description", ""),
        "variables_used": variables,
        "prefix": prefix,
        "tasks_count": len(tasks),
        "tasks": tasks,
        "created": False,
    }

    if create:
        db = DB()
        project = f"{prefix}-{variables.get('client', 'project')}".lower().replace(" ", "-")
        created = 0
        for task in tasks:
            try:
                db.create_task(
                    id=task["id"], title=task["title"],
                    project=project, skill=task.get("skill", ""),
                    priority=task.get("priority", "medium"),
                    description=task.get("description", ""),
                    execution_policy=task.get("execution_policy", "default"),
                    depends_on=task.get("depends_on", []),
                )
                created += 1
            except Exception as e:
                log.warning(f"Failed to create {task['id']}: {e}")
        result["created"] = True
        result["tasks_created"] = created
        result["project"] = project

    return result


def main():
    parser = argparse.ArgumentParser(description="DARIO Task Templates")
    parser.add_argument("--list", "-l", action="store_true", help="List templates")
    parser.add_argument("--template", "-t", help="Template name")
    parser.add_argument("--vars", "-v", default="{}", help="Variables as JSON")
    parser.add_argument("--create", action="store_true", help="Create tasks in DB")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")

    args = parser.parse_args()
    if args.json:
        logging.getLogger().setLevel(logging.ERROR)

    if args.list:
        if args.json:
            templates = {k: {"description": v["description"], "variables": v["variables"]}
                         for k, v in BUILTIN_TEMPLATES.items()}
            print(json.dumps(templates, indent=2))
        else:
            print("=== TASK TEMPLATES ===\n")
            for name, tmpl in BUILTIN_TEMPLATES.items():
                vars_str = ", ".join(f"${{{v}}}" for v in tmpl["variables"])
                print(f"  {name:20s} — {tmpl['description']}")
                print(f"  {'':20s}   vars: {vars_str}")
                print(f"  {'':20s}   tasks: {len(tmpl['tasks'])}")
                print()
        return 0

    elif args.template:
        try:
            variables = json.loads(args.vars)
        except json.JSONDecodeError:
            print("Invalid JSON for --vars")
            return 1

        result = instantiate_template(args.template, variables, create=args.create)

        if "error" in result:
            print(result["error"])
            return 1

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"=== TEMPLATE: {args.template} ({'CREATED' if result.get('created') else 'PREVIEW'}) ===\n")
            if result.get("project"):
                print(f"  Project: {result['project']}")
            print(f"  Tasks: {result['tasks_count']}\n")
            for t in result["tasks"]:
                deps = f" (deps: {t['depends_on']})" if t.get("depends_on") else ""
                print(f"  [{t['id']}] {t['title']}")
                print(f"    skill: {t.get('skill','-')} | priority: {t.get('priority','medium')}{deps}")
                print()
        return 0

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
