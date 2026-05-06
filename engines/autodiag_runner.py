#!/usr/bin/env python3
"""
DARIO AutoDiag Runner — Executes system health checks.
=======================================================
Implements the 7 checks defined in autodiag.yaml as real executable code.
Silent by default — only reports problems.

Usage:
    python autodiag_runner.py              # Run all checks, silent if OK
    python autodiag_runner.py --verbose    # Show all check results
    python autodiag_runner.py --fix        # Apply auto-fixes for fixable issues
    python autodiag_runner.py --json       # Machine-readable output
    python autodiag_runner.py --check X    # Run single check by ID

Exit codes:
    0 = all checks pass
    1 = error (missing files)
    2 = warnings found (non-critical)
    3 = critical issues found
"""

import argparse
import logging
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# License enforcement
try:
    from license_manager import require_license
    require_license()
except (ImportError, SystemExit):
    pass  # License check skipped (dev mode)

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
TASKS_DIR = ORCH_DIR / "tasks" / "active"
COMPANY_FILE = ORCH_DIR / "company.yaml"
QUALITY_FILE = ORCH_DIR / "quality" / "skill-metrics.yaml"
BUDGET_DIR = ORCH_DIR / "budgets"
AUDIT_DIR = ORCH_DIR / "audit"
MEMORY_DIR = Path.home() / ".claude" / "projects" / "C--Users-barda" / "memory"

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("autodiag")


# =============================================================================
# HELPERS
# =============================================================================

def load_all_tasks() -> list:
    tasks = []
    if not TASKS_DIR.exists():
        return tasks
    for f in TASKS_DIR.glob("*.yaml"):
        try:
            data = load_yaml(str(f))
            if data:
                data["_file"] = str(f)
                tasks.append(data)
        except Exception:
            pass
    return tasks


def load_company_workers() -> set:
    if not COMPANY_FILE.exists():
        return set()
    data = load_yaml(str(COMPANY_FILE))
    workers = set()
    for wid in (data.get("workers") or {}).keys():
        workers.add(wid)
    for agent in (data.get("agents") or {}).values():
        if isinstance(agent, dict) and "id" in agent:
            workers.add(agent["id"])
    return workers


# =============================================================================
# CHECKS
# =============================================================================

def check_coherence(tasks: list, workers: set, fix: bool) -> dict:
    """Verify all assignees exist in company.yaml."""
    issues = []
    for t in tasks:
        assignee = t.get("assignee")
        if assignee and assignee != "null" and assignee not in workers:
            issue = {
                "task": t.get("id"),
                "assignee": assignee,
                "problem": "assignee not in company.yaml",
            }
            if fix:
                t["status"] = "blocked"
                t["blocked_reason"] = f"assignee '{assignee}' not found in hierarchy"
                dump_yaml({k: v for k, v in t.items() if k != "_file"}, t["_file"])
                issue["fixed"] = True
            issues.append(issue)

    return {"id": "coherence_check", "severity": "warning", "passed": len(issues) == 0, "issues": issues}


def check_orphans(tasks: list, fix: bool) -> dict:
    """Find tasks with parent IDs that don't exist."""
    task_ids = {t.get("id") for t in tasks}
    issues = []
    for t in tasks:
        parent = t.get("parent")
        if parent and parent not in task_ids:
            issue = {"task": t.get("id"), "parent": parent, "problem": "parent task missing"}
            if fix:
                del_keys = [k for k in t if k == "parent"]
                for k in del_keys:
                    t[k] = None
                t.setdefault("notes", [])
                if isinstance(t.get("notes"), list):
                    t["notes"].append("orphaned — parent removed by autodiag")
                dump_yaml({k: v for k, v in t.items() if k != "_file"}, t["_file"])
                issue["fixed"] = True
            issues.append(issue)

    return {"id": "orphan_detection", "severity": "info", "passed": len(issues) == 0, "issues": issues}


def check_dependencies(tasks: list, fix: bool) -> dict:
    """Verify all depends_on references exist."""
    task_ids = {t.get("id") for t in tasks}
    issues = []
    for t in tasks:
        deps = t.get("depends_on", [])
        if not isinstance(deps, list):
            continue
        broken = [d for d in deps if d not in task_ids]
        if broken:
            issue = {"task": t.get("id"), "broken_deps": broken}
            if fix:
                t["depends_on"] = [d for d in deps if d in task_ids]
                dump_yaml({k: v for k, v in t.items() if k != "_file"}, t["_file"])
                issue["fixed"] = True
            issues.append(issue)

    return {"id": "dependency_integrity", "severity": "warning", "passed": len(issues) == 0, "issues": issues}


def check_budget_drift(tasks: list, fix: bool) -> dict:
    """Compare sum of task tokens vs budget total."""
    now = datetime.now(timezone.utc)
    budget_file = BUDGET_DIR / f"{now.strftime('%Y-%m')}.yaml"
    if not budget_file.exists():
        return {"id": "budget_drift", "severity": "warning", "passed": True, "issues": [], "note": "no budget file"}

    budget = load_yaml(str(budget_file))
    recorded_total = int(budget.get("total_tokens_used") or 0)

    # Sum actual tokens from tasks
    task_sum = 0
    for t in tasks:
        tokens = t.get("actual_tokens")
        if tokens and str(tokens).isdigit():
            task_sum += int(tokens)

    drift = abs(recorded_total - task_sum)
    issues = []
    if drift > 1000:  # >1K token drift
        issue = {"recorded": recorded_total, "calculated": task_sum, "drift": drift}
        if fix and task_sum > 0:
            budget["total_tokens_used"] = task_sum
            budget["percentage"] = round(task_sum / int(budget.get("limit", 50000000)) * 100, 2)
            budget["last_updated"] = now.isoformat()
            dump_yaml(budget, str(budget_file))
            issue["fixed"] = True
        issues.append(issue)

    return {"id": "budget_drift", "severity": "warning", "passed": len(issues) == 0, "issues": issues}


def check_stale_review(tasks: list, fix: bool) -> dict:
    """Find tasks in_review too long."""
    issues = []
    now = datetime.now(timezone.utc)
    for t in tasks:
        if t.get("status") != "in_review":
            continue
        scored_at = t.get("scored_at") or t.get("updated_at") or t.get("assigned_at")
        if not scored_at:
            continue
        try:
            ts = datetime.fromisoformat(str(scored_at).replace("Z", "+00:00"))
            age_hours = (now - ts).total_seconds() / 3600
            sla = {"critical": 1, "client_facing": 4, "financial": 2}.get(
                t.get("execution_policy", "default"), 8
            )
            if age_hours > sla * 2:
                issue = {"task": t.get("id"), "age_hours": round(age_hours, 1), "sla": sla}
                # Auto-approve if score meets threshold
                if fix:
                    score = t.get("quality_score", 0)
                    if score and int(score) >= 75:
                        t["status"] = "done"
                        dump_yaml({k: v for k, v in t.items() if k != "_file"}, t["_file"])
                        issue["fixed"] = True
                        issue["action"] = "auto-approved (score >= 75)"
                issues.append(issue)
        except (ValueError, TypeError):
            pass

    return {"id": "stale_review", "severity": "critical", "passed": len(issues) == 0, "issues": issues}


def check_quality_regression(tasks: list, fix: bool) -> dict:
    """Check if recent scores show regression."""
    if not QUALITY_FILE.exists():
        return {"id": "quality_regression", "severity": "critical", "passed": True, "issues": [], "note": "no metrics"}

    metrics = load_yaml(str(QUALITY_FILE))
    all_scores = []
    for sd in (metrics.get("skills") or {}).values():
        if isinstance(sd, dict):
            scores = sd.get("live_scores") or sd.get("scores") or []
            if isinstance(scores, list):
                all_scores.extend(scores)

    issues = []
    if len(all_scores) >= 5:
        last_5_avg = sum(all_scores[-5:]) / 5
        baseline = metrics.get("global_avg_quality", 85)
        drop = baseline - last_5_avg
        if drop > 15:
            issues.append({
                "last_5_avg": round(last_5_avg, 1),
                "baseline": baseline,
                "drop": round(drop, 1),
                "action": "quality regression detected — review needed",
            })

    return {"id": "quality_regression", "severity": "critical", "passed": len(issues) == 0, "issues": issues}


def check_memory_staleness(fix: bool) -> dict:
    """Check if project memories are stale (>30 days)."""
    issues = []
    if not MEMORY_DIR.exists():
        return {"id": "memory_staleness", "severity": "info", "passed": True, "issues": []}

    now = datetime.now(timezone.utc)
    threshold = timedelta(days=30)

    for f in MEMORY_DIR.glob("*.md"):
        if f.name == "MEMORY.md":
            continue
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            age = now - mtime
            if age > threshold:
                issues.append({
                    "file": f.name,
                    "age_days": age.days,
                    "last_modified": mtime.strftime("%Y-%m-%d"),
                })
        except Exception:
            pass

    return {"id": "memory_staleness", "severity": "info", "passed": len(issues) == 0, "issues": issues}


# =============================================================================
# MAIN
# =============================================================================

def run_all_checks(fix: bool = False, single: str = None) -> list:
    tasks = load_all_tasks()
    workers = load_company_workers()

    all_checks = {
        "coherence_check": lambda: check_coherence(tasks, workers, fix),
        "orphan_detection": lambda: check_orphans(tasks, fix),
        "dependency_integrity": lambda: check_dependencies(tasks, fix),
        "budget_drift": lambda: check_budget_drift(tasks, fix),
        "stale_review": lambda: check_stale_review(tasks, fix),
        "quality_regression": lambda: check_quality_regression(tasks, fix),
        "memory_staleness": lambda: check_memory_staleness(fix),
    }

    if single:
        if single not in all_checks:
            return [{"id": single, "error": f"Unknown check. Available: {list(all_checks.keys())}"}]
        return [all_checks[single]()]

    return [fn() for fn in all_checks.values()]


def log_results(results: list):
    """Append to audit log."""
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    log_file = AUDIT_DIR / "autodiag.log"
    ts = datetime.now(timezone.utc).isoformat()

    warnings = sum(1 for r in results if not r.get("passed") and r.get("severity") == "warning")
    criticals = sum(1 for r in results if not r.get("passed") and r.get("severity") == "critical")

    if warnings == 0 and criticals == 0:
        code = f"DARIO_AUTODIAG_OK_{ts}"
    elif criticals > 0:
        code = f"DARIO_AUTODIAG_FAIL_{criticals}critical_{warnings}warn_{ts}"
    else:
        code = f"DARIO_AUTODIAG_WARN_{warnings}issues_{ts}"

    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(f"[{ts}] {code}\n")
        for r in results:
            if not r.get("passed"):
                f.write(f"  {r['id']}: {len(r.get('issues', []))} issues ({r.get('severity')})\n")


def main():
    parser = argparse.ArgumentParser(description="DARIO AutoDiag — System health checks")
    parser.add_argument("--fix", "-f", action="store_true", help="Apply auto-fixes")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show all results")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")
    parser.add_argument("--check", "-c", help="Run single check by ID")

    args = parser.parse_args()
    if args.json:
        logging.getLogger().setLevel(logging.ERROR)

    results = run_all_checks(fix=args.fix, single=args.check)
    log_results(results)

    passed = sum(1 for r in results if r.get("passed"))
    warnings = [r for r in results if not r.get("passed") and r.get("severity") == "warning"]
    criticals = [r for r in results if not r.get("passed") and r.get("severity") == "critical"]
    infos = [r for r in results if not r.get("passed") and r.get("severity") == "info"]

    if args.json:
        import json
        print(json.dumps({
            "passed": passed,
            "total": len(results),
            "warnings": len(warnings),
            "criticals": len(criticals),
            "infos": len(infos),
            "results": results,
        }, indent=2))
    else:
        if not args.verbose and not warnings and not criticals and not infos:
            print(f"DARIO_AUTODIAG_OK — {passed}/{len(results)} checks passed")
        else:
            print(f"=== AUTODIAG: {passed}/{len(results)} passed ===\n")
            for r in results:
                status = "PASS" if r.get("passed") else r.get("severity", "?").upper()
                mark = "+" if r.get("passed") else "!"
                print(f"  [{mark}] {r['id']}: {status}")
                if not r.get("passed") or args.verbose:
                    for issue in r.get("issues", []):
                        fixed = " [FIXED]" if issue.get("fixed") else ""
                        print(f"      - {issue}{fixed}")
            if warnings or criticals:
                print(f"\n  Summary: {len(criticals)} critical, {len(warnings)} warning, {len(infos)} info")

    if criticals:
        return 3
    elif warnings:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
