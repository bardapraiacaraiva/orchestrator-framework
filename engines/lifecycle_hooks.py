#!/usr/bin/env python3
"""
DARIO Agent Lifecycle Hooks — Event-driven extensibility (OpenAI SDK-inspired).
=================================================================================
Hooks decouple cross-cutting concerns (logging, budget, quality, evolution)
from execution logic. Register handlers at global or per-agent level.

Events:
    on_task_start(task)              — Before execution begins
    on_skill_start(task, skill)      — Before skill invocation
    on_llm_start(task, model, prompt) — Before LLM call
    on_llm_end(task, model, output, tokens) — After LLM response
    on_tool_end(task, tool, result)   — After tool execution
    on_quality_scored(task, score)    — After quality evaluation
    on_task_complete(task, output)    — After successful completion
    on_task_fail(task, error)         — After failure
    on_tripwire(task, reason)         — When output guardrail fires
    on_interrupt(task, reason)        — When task awaits human

Usage:
    from lifecycle_hooks import HookRegistry, Hook

    registry = HookRegistry()

    @registry.on("task_complete")
    def log_completion(task, output, **kwargs):
        print(f"Task {task['id']} completed")

    @registry.on("quality_scored")
    def feed_evolution(task, score, **kwargs):
        if score >= 90:
            evolution_engine.record_star(task['skill'])

    # Emit events
    registry.emit("task_complete", task=task, output=output)
"""

import logging
from collections import defaultdict
from typing import Any, Callable

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("lifecycle_hooks")


# Type alias for hook handlers
HookHandler = Callable[..., None]


class Hook:
    """A registered hook handler with metadata."""
    def __init__(self, event: str, handler: HookHandler, name: str = "",
                 agent: str = "", priority: int = 50):
        self.event = event
        self.handler = handler
        self.name = name or handler.__name__
        self.agent = agent  # Empty = global, specific = per-agent
        self.priority = priority  # Lower = runs first

    def __repr__(self):
        scope = f"[{self.agent}]" if self.agent else "[global]"
        return f"Hook({self.event}, {self.name}, {scope}, pri={self.priority})"


class HookRegistry:
    """Central registry for all lifecycle hooks."""

    def __init__(self):
        self._hooks: dict[str, list[Hook]] = defaultdict(list)
        self._stats: dict[str, int] = defaultdict(int)

    def register(self, event: str, handler: HookHandler, name: str = "",
                 agent: str = "", priority: int = 50):
        """Register a hook handler for an event."""
        hook = Hook(event, handler, name, agent, priority)
        self._hooks[event].append(hook)
        self._hooks[event].sort(key=lambda h: h.priority)
        log.debug(f"Registered hook: {hook}")

    def on(self, event: str, agent: str = "", priority: int = 50):
        """Decorator to register a hook."""
        def decorator(fn):
            self.register(event, fn, name=fn.__name__, agent=agent, priority=priority)
            return fn
        return decorator

    def emit(self, event: str, agent: str = "", **kwargs):
        """Emit an event, calling all registered hooks in priority order."""
        hooks = self._hooks.get(event, [])
        self._stats[event] += 1

        for hook in hooks:
            # Skip per-agent hooks that don't match
            if hook.agent and hook.agent != agent:
                continue
            try:
                hook.handler(**kwargs)
            except Exception as e:
                log.error(f"Hook '{hook.name}' failed on '{event}': {e}")

    def list_hooks(self) -> list[dict]:
        """List all registered hooks."""
        result = []
        for event, hooks in sorted(self._hooks.items()):
            for h in hooks:
                result.append({
                    "event": event,
                    "name": h.name,
                    "agent": h.agent or "global",
                    "priority": h.priority,
                })
        return result

    def stats(self) -> dict:
        """Get emission statistics."""
        return dict(self._stats)

    def clear(self, event: str = ""):
        """Clear hooks. If event specified, clear only that event."""
        if event:
            self._hooks[event] = []
        else:
            self._hooks.clear()


# =============================================================================
# GLOBAL REGISTRY + DEFAULT HOOKS
# =============================================================================

# Singleton global registry
_global_registry = HookRegistry()


def get_registry() -> HookRegistry:
    """Get the global hook registry."""
    return _global_registry


# --- Default hooks (always active) ---

@_global_registry.on("task_start", priority=10)
def _log_task_start(task, **kwargs):
    log.info(f"[HOOK] task_start: {task.get('id', '?')} ({task.get('skill', '?')})")


@_global_registry.on("task_complete", priority=10)
def _log_task_complete(task, output="", **kwargs):
    log.info(f"[HOOK] task_complete: {task.get('id', '?')} ({len(output)} chars)")


@_global_registry.on("task_fail", priority=10)
def _log_task_fail(task, error="", **kwargs):
    log.warning(f"[HOOK] task_fail: {task.get('id', '?')} — {error[:80]}")


@_global_registry.on("tripwire", priority=10)
def _log_tripwire(task, reason="", **kwargs):
    log.warning(f"[HOOK] tripwire: {task.get('id', '?')} — {reason[:80]}")


@_global_registry.on("quality_scored", priority=20)
def _track_quality(task, score=0, **kwargs):
    """Feed quality data to evolution engine."""
    if score >= 90:
        log.info(f"[HOOK] star_performer: {task.get('skill', '?')} scored {score}")


@_global_registry.on("llm_end", priority=20)
def _track_tokens(task, model="", tokens=0, **kwargs):
    """Track token usage for budget."""
    if tokens > 0:
        log.debug(f"[HOOK] tokens: {model} +{tokens}")


@_global_registry.on("interrupt", priority=10)
def _log_interrupt(task, reason="", **kwargs):
    log.info(f"[HOOK] interrupt: {task.get('id', '?')} awaiting human — {reason[:50]}")


# =============================================================================
# CONVENIENCE: Register custom hooks
# =============================================================================

def on_task_start(fn): return _global_registry.on("task_start")(fn)
def on_task_complete(fn): return _global_registry.on("task_complete")(fn)
def on_task_fail(fn): return _global_registry.on("task_fail")(fn)
def on_skill_start(fn): return _global_registry.on("skill_start")(fn)
def on_llm_start(fn): return _global_registry.on("llm_start")(fn)
def on_llm_end(fn): return _global_registry.on("llm_end")(fn)
def on_quality_scored(fn): return _global_registry.on("quality_scored")(fn)
def on_tripwire(fn): return _global_registry.on("tripwire")(fn)
def on_interrupt(fn): return _global_registry.on("interrupt")(fn)


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import json

    print("=== DARIO Lifecycle Hooks ===\n")

    registry = get_registry()

    # Show registered hooks
    hooks = registry.list_hooks()
    print(f"Registered hooks: {len(hooks)}")
    for h in hooks:
        print(f"  {h['event']:20s} → {h['name']:25s} [{h['agent']}] pri={h['priority']}")

    # Demo emit
    print("\n--- Demo Events ---")
    test_task = {"id": "DEMO-001", "skill": "dario-brand"}
    registry.emit("task_start", task=test_task)
    registry.emit("quality_scored", task=test_task, score=92)
    registry.emit("task_complete", task=test_task, output="Brand output here...")
    registry.emit("tripwire", task=test_task, reason="API key leaked")

    print(f"\n--- Stats ---")
    print(json.dumps(registry.stats(), indent=2))
