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
        self._default = RetryWithModel(upgrade_to="sonnet", max_retries=1)  # Fixed: was SkipStep (silent loss)
        self._register_defaults()

    def _register_defaults(self):
        """Register sensible defaults per skill category."""
        # Creative/strategic → retry with Opus (needs best model)
        for skill in ["dario-brand", "dario-offer", "dario-pitch", "dario-sales-letter",
                       "dario-story-circle", "dario-movement", "dario-c-level",
                       "dario-naming", "dario-content", "dario-social", "dario-pr"]:
            self._handlers[skill] = RetryWithModel(upgrade_to="opus", max_retries=1)

        # Technical/analysis → retry with Sonnet
        for skill in ["seo-schema", "seo-sitemap", "seo-audit", "seo-technical",
                       "seo-content", "seo-local", "seo-plan", "seo-page",
                       "dario-sop", "dario-kw-cluster", "dario-wp-audit",
                       "dario-woo-audit", "dario-cwv-fix", "dario-diagnose",
                       "dario-pentest-checklist", "dario-make-blueprint",
                       "dario-cro", "dario-data"]:
            self._handlers[skill] = RetryWithModel(upgrade_to="sonnet", max_retries=1)

        # Financial/legal → escalate human (too risky)
        for skill in ["dario-proposal", "dario-financial-model", "dario-pricing-calculator",
                       "dario-legal", "dario-negotiation",
                       "diva-contract", "diva-budget", "diva-comparador"]:
            self._handlers[skill] = EscalateHuman("Financial/legal task failed — needs human review")

        # DIVA design → retry with Opus (creative)
        for skill in ["diva-moodboard", "diva-render", "diva-render-brief", "diva-vision",
                       "diva-materials", "diva-landscape", "diva-smart-home", "diva-ffe"]:
            self._handlers[skill] = RetryWithModel(upgrade_to="opus", max_retries=1)

        # DIVA technical → retry with Sonnet
        for skill in ["diva-briefing", "diva-floor-plan", "diva-timeline", "diva-inspection",
                       "diva-licensing", "diva-energy", "diva-bim", "diva-mep", "diva-acoustics",
                       "diva-accessibility", "diva-roadmap", "diva-diagnose", "diva-planradar"]:
            self._handlers[skill] = RetryWithModel(upgrade_to="sonnet", max_retries=1)

        # A360 → retry with Sonnet
        for skill in ["a360-avatar", "a360-nicho", "a360-oferta", "a360-funil",
                       "a360-growth", "a360-lancamento", "a360-metricas", "a360-modelo",
                       "a360-pitch", "a360-scale", "a360-validacao", "a360-case-study"]:
            self._handlers[skill] = RetryWithModel(upgrade_to="sonnet", max_retries=1)

        # Non-critical helpers → skip
        for skill in ["dario-obsidian-save", "dario-rag-ingest", "diva-obsidian-save",
                       "diva-rag-ingest", "dario-projeto", "diva-projeto"]:
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
