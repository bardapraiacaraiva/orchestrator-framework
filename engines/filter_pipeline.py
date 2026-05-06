#!/usr/bin/env python3
"""
DARIO Filter Pipeline — Composable execution middleware (Semantic Kernel-inspired).
====================================================================================
Wraps every skill execution with before/after hooks. Replaces scattered if-checks
with ordered, composable middleware.

Usage:
    from filter_pipeline import FilterPipeline, LoggingFilter, BudgetFilter, QualityGateFilter

    pipeline = FilterPipeline([
        LoggingFilter(),
        BudgetFilter(warn_pct=80, block_pct=95),
        QualityGateFilter(min_score=60),
    ])

    # Before execution
    ctx = pipeline.before(task, context)
    if ctx.get("blocked"):
        # Don't execute
        ...

    # After execution
    result = pipeline.after(task, output, context)
    if result.get("tripwire"):
        # Output quarantined
        ...

Architecture:
    Filters are ordered and composable. Each filter can:
    - Inspect/modify context before execution
    - Block execution entirely (before)
    - Inspect/modify/quarantine output after execution (after)
    - Trigger side-effects (logging, budget update, notifications)
"""

import json
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ORCH_DIR = Path.home() / ".claude" / "orchestrator"
log = logging.getLogger("filter_pipeline")


class ExecutionFilter(ABC):
    """Base class for execution filters. Implement before() and/or after()."""
    name: str = "base"
    order: int = 50  # Lower = runs earlier

    def before(self, task: dict, context: dict) -> dict:
        """Called before execution. Return context (modified or not).
        Set context['blocked'] = True to prevent execution.
        Set context['block_reason'] = '...' for the reason."""
        return context

    def after(self, task: dict, output: str, context: dict) -> dict:
        """Called after execution. Return result dict.
        Set result['tripwire'] = True to quarantine output.
        Set result['tripwire_reason'] = '...' for the reason."""
        return {"output": output}


class FilterPipeline:
    """Ordered pipeline of execution filters."""

    def __init__(self, filters: list[ExecutionFilter] = None):
        self.filters = sorted(filters or [], key=lambda f: f.order)

    def add(self, f: ExecutionFilter):
        self.filters.append(f)
        self.filters.sort(key=lambda f: f.order)

    def before(self, task: dict, context: dict = None) -> dict:
        """Run all before-filters in order. Stops on first block."""
        ctx = context or {}
        ctx.setdefault("_filter_log", [])
        ctx.setdefault("_start_time", time.time())

        for f in self.filters:
            try:
                ctx = f.before(task, ctx)
                ctx["_filter_log"].append({"filter": f.name, "phase": "before", "blocked": ctx.get("blocked", False)})
                if ctx.get("blocked"):
                    log.warning(f"[BLOCKED] Filter '{f.name}': {ctx.get('block_reason', 'no reason')}")
                    break
            except Exception as e:
                log.error(f"[ERROR] Filter '{f.name}' before() failed: {e}")
                ctx["_filter_log"].append({"filter": f.name, "phase": "before", "error": str(e)})

        return ctx

    def after(self, task: dict, output: str, context: dict = None) -> dict:
        """Run all after-filters in order. Stops on first tripwire."""
        ctx = context or {}
        result = {"output": output, "tripwire": False, "_filter_log": ctx.get("_filter_log", [])}

        for f in self.filters:
            try:
                r = f.after(task, result.get("output", output), ctx)
                result["_filter_log"].append({"filter": f.name, "phase": "after", "tripwire": r.get("tripwire", False)})
                if r.get("tripwire"):
                    result["tripwire"] = True
                    result["tripwire_reason"] = r.get("tripwire_reason", f"Tripwire by {f.name}")
                    result["tripwire_filter"] = f.name
                    log.warning(f"[TRIPWIRE] Filter '{f.name}': {result['tripwire_reason']}")
                    break
                # Allow filters to modify output
                if "output" in r:
                    result["output"] = r["output"]
            except Exception as e:
                log.error(f"[ERROR] Filter '{f.name}' after() failed: {e}")
                result["_filter_log"].append({"filter": f.name, "phase": "after", "error": str(e)})

        # Add timing
        start = ctx.get("_start_time", time.time())
        result["duration_ms"] = int((time.time() - start) * 1000)

        return result


# =============================================================================
# BUILT-IN FILTERS
# =============================================================================

class LoggingFilter(ExecutionFilter):
    """Logs task execution start/end with timing."""
    name = "logging"
    order = 10

    def before(self, task: dict, context: dict) -> dict:
        task_id = task.get("id", "?")
        skill = task.get("skill", "?")
        log.info(f"[EXEC] {task_id} | skill={skill} | start")
        return context

    def after(self, task: dict, output: str, context: dict) -> dict:
        task_id = task.get("id", "?")
        duration = int((time.time() - context.get("_start_time", time.time())) * 1000)
        output_len = len(output) if output else 0
        log.info(f"[EXEC] {task_id} | {duration}ms | output={output_len} chars")
        return {"output": output}


class BudgetFilter(ExecutionFilter):
    """Checks budget before execution. Warns at warn_pct, blocks at block_pct."""
    name = "budget"
    order = 20

    def __init__(self, warn_pct: float = 80, block_pct: float = 95):
        self.warn_pct = warn_pct
        self.block_pct = block_pct

    def _get_budget_pct(self) -> float:
        try:
            import sys
            sys.path.insert(0, str(ORCH_DIR))
            from db import DB
            budget = DB().get_budget()
            if budget:
                used = budget.get("tokens_used", 0)
                limit = budget.get("token_limit", 50_000_000)
                return (used / limit) * 100 if limit > 0 else 0
        except Exception:
            pass
        return 0

    def before(self, task: dict, context: dict) -> dict:
        pct = self._get_budget_pct()
        context["budget_pct"] = pct

        if pct >= self.block_pct:
            context["blocked"] = True
            context["block_reason"] = f"Budget at {pct:.1f}% (limit: {self.block_pct}%)"
        elif pct >= self.warn_pct:
            log.warning(f"[BUDGET] {pct:.1f}% used — approaching limit")
        return context


class QualityGateFilter(ExecutionFilter):
    """Post-execution quality gate. Tripwire if score below threshold."""
    name = "quality_gate"
    order = 80

    def __init__(self, min_score: int = 60):
        self.min_score = min_score

    def after(self, task: dict, output: str, context: dict) -> dict:
        # Score is set by the scoring step, not this filter
        # This filter checks if a score was already computed and gates on it
        score = context.get("quality_score", None)
        if score is not None and score < self.min_score:
            return {
                "output": output,
                "tripwire": True,
                "tripwire_reason": f"Quality score {score} below threshold {self.min_score}",
            }
        return {"output": output}


class TokenBudgetFilter(ExecutionFilter):
    """Tracks token usage per execution and updates budget."""
    name = "token_budget"
    order = 90

    def after(self, task: dict, output: str, context: dict) -> dict:
        tokens = context.get("actual_tokens", 0)
        if tokens > 0:
            try:
                import sys
                sys.path.insert(0, str(ORCH_DIR))
                from db import DB
                DB().update_budget(tokens)
                log.info(f"[BUDGET] +{tokens} tokens recorded")
            except Exception as e:
                log.error(f"[BUDGET] Failed to update: {e}")
        return {"output": output}


# =============================================================================
# FACTORY: Default pipeline
# =============================================================================

def default_pipeline() -> FilterPipeline:
    """Create the default DARIO filter pipeline."""
    return FilterPipeline([
        LoggingFilter(),
        BudgetFilter(warn_pct=80, block_pct=95),
        QualityGateFilter(min_score=60),
        TokenBudgetFilter(),
    ])


if __name__ == "__main__":
    # Quick test
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    pipe = default_pipeline()
    test_task = {"id": "TEST-001", "skill": "dario-brand", "project": "test"}

    print("=== BEFORE ===")
    ctx = pipe.before(test_task)
    print(json.dumps({k: v for k, v in ctx.items() if not k.startswith("_")}, indent=2))

    print("\n=== AFTER ===")
    result = pipe.after(test_task, "Test output content here", ctx)
    print(json.dumps({k: v for k, v in result.items() if not k.startswith("_")}, indent=2))
