#!/usr/bin/env python3
"""
DARIO Termination Conditions — Composable stopping logic (AutoGen-inspired).
==============================================================================
Replaces the hard budget stop with nuanced, composable conditions.
Conditions can be combined with & (AND) and | (OR) operators.

Usage:
    from termination import TokenLimit, Timeout, QualityReached, StallDetection

    # Stop when ANY condition is met
    condition = TokenLimit(50000) | Timeout(300) | QualityReached(90)

    # Stop when ALL conditions are met
    condition = TokenLimit(10000) & QualityReached(70)

    # Check during execution
    ctx = {"tokens_used": 45000, "elapsed_seconds": 120, "last_scores": [85, 88]}
    result = condition.check(ctx)
    if result.should_stop:
        print(f"Stopping: {result.reason}")

Integration:
    Used by executor.py and chain_executor.py to decide when to stop
    multi-step executions, chain runs, and autonomous pulses.
"""

import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

# License enforcement
try:
    from license_manager import require_license
    require_license()
except (ImportError, SystemExit):
    pass  # License check skipped (dev mode)

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("termination")


@dataclass
class TerminationResult:
    """Result of a termination check."""
    should_stop: bool
    reason: str = ""
    condition_name: str = ""
    details: dict = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}


class TerminationCondition(ABC):
    """Base class for termination conditions. Supports & and | composition."""

    name: str = "base"

    @abstractmethod
    def check(self, ctx: dict) -> TerminationResult:
        """Check if this condition is met. ctx contains execution state."""
        ...

    def __or__(self, other: "TerminationCondition") -> "OrCondition":
        """Combine with OR: stop if EITHER condition is met."""
        return OrCondition(self, other)

    def __and__(self, other: "TerminationCondition") -> "AndCondition":
        """Combine with AND: stop only if BOTH conditions are met."""
        return AndCondition(self, other)

    def __repr__(self):
        return f"{self.__class__.__name__}()"


class OrCondition(TerminationCondition):
    """Composite: stop if ANY child condition is met."""
    name = "or"

    def __init__(self, *conditions: TerminationCondition):
        self.conditions = []
        for c in conditions:
            if isinstance(c, OrCondition):
                self.conditions.extend(c.conditions)
            else:
                self.conditions.append(c)

    def check(self, ctx: dict) -> TerminationResult:
        for c in self.conditions:
            r = c.check(ctx)
            if r.should_stop:
                return r
        return TerminationResult(should_stop=False)

    def __repr__(self):
        return " | ".join(repr(c) for c in self.conditions)


class AndCondition(TerminationCondition):
    """Composite: stop only if ALL child conditions are met."""
    name = "and"

    def __init__(self, *conditions: TerminationCondition):
        self.conditions = []
        for c in conditions:
            if isinstance(c, AndCondition):
                self.conditions.extend(c.conditions)
            else:
                self.conditions.append(c)

    def check(self, ctx: dict) -> TerminationResult:
        reasons = []
        for c in self.conditions:
            r = c.check(ctx)
            if not r.should_stop:
                return TerminationResult(should_stop=False)
            reasons.append(r.reason)
        return TerminationResult(
            should_stop=True,
            reason=" AND ".join(reasons),
            condition_name="and",
        )

    def __repr__(self):
        return " & ".join(repr(c) for c in self.conditions)


# =============================================================================
# BUILT-IN CONDITIONS
# =============================================================================

class TokenLimit(TerminationCondition):
    """Stop when total tokens exceed limit."""
    name = "token_limit"

    def __init__(self, max_tokens: int):
        self.max_tokens = max_tokens

    def check(self, ctx: dict) -> TerminationResult:
        used = ctx.get("tokens_used", 0)
        if used >= self.max_tokens:
            return TerminationResult(
                should_stop=True,
                reason=f"Token limit reached: {used:,} >= {self.max_tokens:,}",
                condition_name=self.name,
                details={"tokens_used": used, "limit": self.max_tokens},
            )
        return TerminationResult(should_stop=False)

    def __repr__(self):
        return f"TokenLimit({self.max_tokens:,})"


class Timeout(TerminationCondition):
    """Stop when elapsed time exceeds limit (seconds)."""
    name = "timeout"

    def __init__(self, max_seconds: float):
        self.max_seconds = max_seconds

    def check(self, ctx: dict) -> TerminationResult:
        elapsed = ctx.get("elapsed_seconds", 0)
        # Also check start_time if available
        start = ctx.get("start_time")
        if start:
            elapsed = time.time() - start

        if elapsed >= self.max_seconds:
            return TerminationResult(
                should_stop=True,
                reason=f"Timeout: {elapsed:.0f}s >= {self.max_seconds:.0f}s",
                condition_name=self.name,
                details={"elapsed": elapsed, "limit": self.max_seconds},
            )
        return TerminationResult(should_stop=False)

    def __repr__(self):
        return f"Timeout({self.max_seconds}s)"


class QualityReached(TerminationCondition):
    """Stop when quality score meets threshold."""
    name = "quality_reached"

    def __init__(self, min_score: int):
        self.min_score = min_score

    def check(self, ctx: dict) -> TerminationResult:
        score = ctx.get("quality_score", 0)
        # Also check last_scores list
        scores = ctx.get("last_scores", [])
        if scores:
            score = scores[-1]

        if score >= self.min_score:
            return TerminationResult(
                should_stop=True,
                reason=f"Quality target met: {score} >= {self.min_score}",
                condition_name=self.name,
                details={"score": score, "threshold": self.min_score},
            )
        return TerminationResult(should_stop=False)

    def __repr__(self):
        return f"QualityReached({self.min_score})"


class StallDetection(TerminationCondition):
    """Stop when last N outputs/scores are identical (agent is stuck)."""
    name = "stall_detection"

    def __init__(self, window: int = 3):
        self.window = window

    def check(self, ctx: dict) -> TerminationResult:
        scores = ctx.get("last_scores", [])
        outputs = ctx.get("last_outputs", [])

        # Check score stall
        if len(scores) >= self.window:
            recent = scores[-self.window:]
            if len(set(recent)) == 1:
                return TerminationResult(
                    should_stop=True,
                    reason=f"Stall detected: last {self.window} scores identical ({recent[0]})",
                    condition_name=self.name,
                    details={"stalled_scores": recent},
                )

        # Check output stall (same output hash)
        if len(outputs) >= self.window:
            recent_hashes = [hash(o[:200]) for o in outputs[-self.window:]]
            if len(set(recent_hashes)) == 1:
                return TerminationResult(
                    should_stop=True,
                    reason=f"Stall detected: last {self.window} outputs identical",
                    condition_name=self.name,
                )

        return TerminationResult(should_stop=False)

    def __repr__(self):
        return f"StallDetection(window={self.window})"


class MaxSteps(TerminationCondition):
    """Stop after N execution steps."""
    name = "max_steps"

    def __init__(self, max_steps: int):
        self.max_steps = max_steps

    def check(self, ctx: dict) -> TerminationResult:
        steps = ctx.get("step_count", 0)
        if steps >= self.max_steps:
            return TerminationResult(
                should_stop=True,
                reason=f"Max steps reached: {steps} >= {self.max_steps}",
                condition_name=self.name,
                details={"steps": steps, "limit": self.max_steps},
            )
        return TerminationResult(should_stop=False)

    def __repr__(self):
        return f"MaxSteps({self.max_steps})"


class BudgetPercent(TerminationCondition):
    """Stop when monthly budget exceeds percentage."""
    name = "budget_percent"

    def __init__(self, max_percent: float = 95.0):
        self.max_percent = max_percent

    def check(self, ctx: dict) -> TerminationResult:
        pct = ctx.get("budget_pct", 0)
        if pct >= self.max_percent:
            return TerminationResult(
                should_stop=True,
                reason=f"Budget limit: {pct:.1f}% >= {self.max_percent}%",
                condition_name=self.name,
                details={"budget_pct": pct, "limit": self.max_percent},
            )
        return TerminationResult(should_stop=False)

    def __repr__(self):
        return f"BudgetPercent({self.max_percent}%)"


class TripwireTriggered(TerminationCondition):
    """Stop when a tripwire was triggered by output guardrails."""
    name = "tripwire"

    def check(self, ctx: dict) -> TerminationResult:
        if ctx.get("tripwire"):
            return TerminationResult(
                should_stop=True,
                reason=f"Tripwire: {ctx.get('tripwire_reason', 'output guardrail')}",
                condition_name=self.name,
            )
        return TerminationResult(should_stop=False)


# =============================================================================
# PRESETS: Common condition combinations
# =============================================================================

def default_task_conditions() -> TerminationCondition:
    """Default conditions for single task execution."""
    return TokenLimit(100_000) | Timeout(600) | TripwireTriggered()


def chain_conditions() -> TerminationCondition:
    """Default conditions for chain execution."""
    return TokenLimit(500_000) | Timeout(1800) | MaxSteps(20) | StallDetection(3)


def pulse_conditions() -> TerminationCondition:
    """Default conditions for heartbeat pulse."""
    return TokenLimit(200_000) | Timeout(900) | BudgetPercent(95)


def conservative_conditions() -> TerminationCondition:
    """Conservative: save budget but allow full task completion."""
    return TokenLimit(80_000) | Timeout(300) | BudgetPercent(80) | StallDetection(2)


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import json

    print("=== Composable Termination Conditions ===\n")

    # Demo composition
    c1 = TokenLimit(50_000) | Timeout(300) | QualityReached(90)
    print(f"Condition: {c1}")

    # Test scenarios
    tests = [
        {"name": "Under limits", "ctx": {"tokens_used": 10000, "elapsed_seconds": 60, "quality_score": 70}},
        {"name": "Token exceeded", "ctx": {"tokens_used": 60000, "elapsed_seconds": 60}},
        {"name": "Timeout", "ctx": {"tokens_used": 10000, "elapsed_seconds": 400}},
        {"name": "Quality met", "ctx": {"tokens_used": 10000, "elapsed_seconds": 60, "quality_score": 95}},
        {"name": "Stall", "ctx": {"last_scores": [72, 72, 72]}},
    ]

    c2 = c1 | StallDetection(3)
    print(f"With stall: {c2}\n")

    for t in tests:
        r = c2.check(t["ctx"])
        mark = "STOP" if r.should_stop else "CONTINUE"
        print(f"  [{mark:8s}] {t['name']:20s} → {r.reason or 'OK'}")

    print(f"\n--- Presets ---")
    print(f"  default_task:   {default_task_conditions()}")
    print(f"  chain:          {chain_conditions()}")
    print(f"  pulse:          {pulse_conditions()}")
    print(f"  conservative:   {conservative_conditions()}")
