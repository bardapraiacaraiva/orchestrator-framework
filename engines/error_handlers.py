#!/usr/bin/env python3
"""
DARIO Per-Node Error Handlers — Graceful degradation (LangGraph-inspired).
============================================================================
Each chain step can define a fallback handler that returns a default value
instead of aborting the entire chain. Enables partial results over total failure.

Handler types:
    FallbackValue   — Return a static default value
    FallbackSkill   — Try an alternative skill
    RetryWithModel  — Retry with a different model (e.g., upgrade to Opus)
    SkipStep        — Skip this step and continue chain
    EscalateHuman   — Interrupt for human input

Usage:
    from error_handlers import ErrorHandlerRegistry, FallbackValue, RetryWithModel

    registry = ErrorHandlerRegistry()
    registry.register("dario-naming", FallbackValue({"candidates": ["Projeto X"], "note": "Fallback names"}))
    registry.register("seo-audit", RetryWithModel(upgrade_to="opus", max_retries=1))
    registry.register("dario-content", SkipStep(reason="Non-critical"))

    # On error during chain execution:
    handler = registry.get("dario-naming")
    result = handler.handle(error, task, context)
    if result.recovered:
        # Use result.output as the step output, continue chain
"""

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

# License enforcement
try:
    from license_manager import require_license
    require_license()
except (ImportError, SystemExit):
    pass  # License check skipped (dev mode)

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("error_handlers")


@dataclass
class RecoveryResult:
    """Result of an error handler attempt."""
    recovered: bool = False
    output: Any = None
    action: str = ""  # fallback_value, retry, skip, escalate
    reason: str = ""
    original_error: str = ""
    retries_used: int = 0


class ErrorHandler(ABC):
    """Base class for per-node error handlers."""
    name: str = "base"

    @abstractmethod
    def handle(self, error: Exception, task: dict, context: dict) -> RecoveryResult:
        ...


class FallbackValue(ErrorHandler):
    """Return a static default value on error."""
    name = "fallback_value"

    def __init__(self, default_output: Any):
        self.default_output = default_output

    def handle(self, error: Exception, task: dict, context: dict) -> RecoveryResult:
        log.info(f"[FALLBACK] {task.get('skill', '?')}: using default value")
        output = self.default_output
        if callable(output):
            output = output(task, context)
        if isinstance(output, dict):
            output = json.dumps(output, ensure_ascii=False, indent=2)
        return RecoveryResult(
            recovered=True,
            output=str(output),
            action="fallback_value",
            reason=f"Using fallback value for {task.get('skill', '?')}",
            original_error=str(error)[:200],
        )


class FallbackSkill(ErrorHandler):
    """Try an alternative skill on error."""
    name = "fallback_skill"

    def __init__(self, alternative_skill: str):
        self.alternative_skill = alternative_skill

    def handle(self, error: Exception, task: dict, context: dict) -> RecoveryResult:
        log.info(f"[FALLBACK] {task.get('skill', '?')} failed → trying {self.alternative_skill}")
        return RecoveryResult(
            recovered=True,
            output=None,  # Caller should re-execute with alternative skill
            action="fallback_skill",
            reason=f"Falling back to {self.alternative_skill}",
            original_error=str(error)[:200],
        )


class RetryWithModel(ErrorHandler):
    """Retry with a more capable model on error."""
    name = "retry_with_model"

    def __init__(self, upgrade_to: str = "opus", max_retries: int = 1):
        self.upgrade_to = upgrade_to
        self.max_retries = max_retries

    def handle(self, error: Exception, task: dict, context: dict) -> RecoveryResult:
        retries = context.get("_retry_count", 0)
        if retries >= self.max_retries:
            return RecoveryResult(
                recovered=False,
                action="retry_exhausted",
                reason=f"Max retries ({self.max_retries}) exhausted on model upgrade",
                original_error=str(error)[:200],
                retries_used=retries,
            )
        log.info(f"[RETRY] {task.get('skill', '?')}: upgrading to {self.upgrade_to} (attempt {retries+1})")
        return RecoveryResult(
            recovered=True,
            output=None,  # Caller should re-execute with upgraded model
            action="retry_with_model",
            reason=f"Upgrading to {self.upgrade_to} after error",
            original_error=str(error)[:200],
            retries_used=retries + 1,
        )


class SkipStep(ErrorHandler):
    """Skip this step and continue the chain."""
    name = "skip"

    def __init__(self, reason: str = "Non-critical step"):
        self.reason = reason

    def handle(self, error: Exception, task: dict, context: dict) -> RecoveryResult:
        log.info(f"[SKIP] {task.get('skill', '?')}: {self.reason}")
        return RecoveryResult(
            recovered=True,
            output=f"[SKIPPED: {self.reason}]",
            action="skip",
            reason=self.reason,
            original_error=str(error)[:200],
        )


class EscalateHuman(ErrorHandler):
    """Escalate to human on error."""
    name = "escalate_human"

    def __init__(self, message: str = ""):
        self.message = message

    def handle(self, error: Exception, task: dict, context: dict) -> RecoveryResult:
        msg = self.message or f"Error in {task.get('skill', '?')}: {str(error)[:100]}"
        log.info(f"[ESCALATE] {task.get('skill', '?')}: awaiting human")
        return RecoveryResult(
            recovered=False,
            action="escalate_human",
            reason=msg,
            original_error=str(error)[:200],
        )


class ErrorHandlerRegistry:
    """Registry of per-skill error handlers."""

    def __init__(self):
        self._handlers: dict[str, ErrorHandler] = {}
        self._default = SkipStep("No handler defined — step skipped")
        self._register_defaults()

    def _register_defaults(self):
        """Register sensible defaults per skill category."""
        # Creative skills → retry with better model
        for skill in ["dario-brand", "dario-offer", "dario-pitch", "dario-sales-letter",
                       "dario-story-circle", "dario-movement"]:
            self._handlers[skill] = RetryWithModel(upgrade_to="opus", max_retries=1)

        # Technical skills → retry then skip
        for skill in ["seo-schema", "seo-sitemap", "dario-sop", "dario-kw-cluster"]:
            self._handlers[skill] = RetryWithModel(upgrade_to="sonnet", max_retries=1)

        # Financial/legal → escalate human (too risky to auto-recover)
        for skill in ["dario-proposal", "dario-financial-model", "diva-contract", "diva-budget"]:
            self._handlers[skill] = EscalateHuman("Financial/legal task failed — needs human review")

        # Non-critical → skip
        for skill in ["dario-obsidian-save", "dario-rag-ingest"]:
            self._handlers[skill] = SkipStep("Non-critical helper task")

    def register(self, skill: str, handler: ErrorHandler):
        self._handlers[skill] = handler

    def get(self, skill: str) -> ErrorHandler:
        return self._handlers.get(skill, self._default)

    def list_handlers(self) -> list[dict]:
        return [
            {"skill": skill, "handler": h.name, "type": type(h).__name__}
            for skill, h in sorted(self._handlers.items())
        ]


# Singleton
_registry = ErrorHandlerRegistry()

def get_error_registry() -> ErrorHandlerRegistry:
    return _registry


if __name__ == "__main__":
    print("=== DARIO Error Handlers ===\n")
    registry = get_error_registry()
    handlers = registry.list_handlers()
    print(f"{len(handlers)} handlers registered:\n")

    by_type = {}
    for h in handlers:
        t = h["type"]
        if t not in by_type:
            by_type[t] = []
        by_type[t].append(h["skill"])

    for handler_type, skills in sorted(by_type.items()):
        print(f"  {handler_type}:")
        for s in skills:
            print(f"    → {s}")
        print()

    # Test
    task = {"id": "T1", "skill": "dario-brand"}
    handler = registry.get("dario-brand")
    result = handler.handle(Exception("Test error"), task, {})
    print(f"Test: dario-brand error → {result.action} (recovered={result.recovered})")
