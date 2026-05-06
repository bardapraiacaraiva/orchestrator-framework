#!/usr/bin/env python3
"""
DARIO Multi-Mode SSE Streaming — Real-time task events (LangGraph-inspired).
==============================================================================
Server-Sent Events endpoint for real-time task progress. Dashboard and clients
subscribe to events instead of polling.

Stream modes (subscribe to one or more):
    updates    — Per-step state changes (step_start, step_complete, error)
    tokens     — LLM token counts per step
    scores     — Quality scores as they're computed
    state      — Full task state after each step
    system     — System events (budget warnings, SLA breaches)

Usage in FastAPI runtime:
    from sse_streaming import EventBus, stream_task_events

    bus = EventBus()

    @app.get("/tasks/{task_id}/stream")
    async def stream(task_id: str, modes: str = "updates,scores"):
        return StreamingResponse(
            stream_task_events(bus, task_id, modes.split(",")),
            media_type="text/event-stream"
        )

    # Emit events from executor:
    bus.emit(task_id, "step_start", {"step": "guardrails", "skill": "dario-brand"})
    bus.emit(task_id, "step_complete", {"step": "guardrails", "verdict": "PASS", "duration_ms": 45})
"""

import asyncio
import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional

# License enforcement
try:
    from license_manager import require_license
    require_license()
except (ImportError, SystemExit):
    pass  # License check skipped (dev mode)

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("sse_streaming")


@dataclass
class SSEEvent:
    """A single Server-Sent Event."""
    event_type: str  # step_start, step_complete, score, error, state, system
    data: dict
    task_id: str = ""
    timestamp: float = 0
    mode: str = "updates"  # Which stream mode this belongs to

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()

    def to_sse(self) -> str:
        """Format as SSE wire format."""
        payload = {
            "type": self.event_type,
            "task_id": self.task_id,
            "timestamp": self.timestamp,
            "data": self.data,
        }
        return f"event: {self.event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


# Map event types to stream modes
EVENT_MODE_MAP = {
    "step_start": "updates",
    "step_complete": "updates",
    "task_start": "updates",
    "task_complete": "updates",
    "task_fail": "updates",
    "token_update": "tokens",
    "quality_scored": "scores",
    "schema_validated": "scores",
    "tripwire": "scores",
    "state_snapshot": "state",
    "budget_warning": "system",
    "sla_breach": "system",
    "interrupt": "system",
    "error": "updates",
}


class EventBus:
    """
    Central event bus for SSE streaming.
    Supports multiple subscribers per task with mode filtering.
    """

    def __init__(self, max_history: int = 100):
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._global_subscribers: list[asyncio.Queue] = []
        self._history: dict[str, list[SSEEvent]] = defaultdict(list)
        self._max_history = max_history

    def emit(self, task_id: str, event_type: str, data: dict = None):
        """Emit an event to all subscribers of this task + global subscribers."""
        mode = EVENT_MODE_MAP.get(event_type, "updates")
        event = SSEEvent(
            event_type=event_type,
            data=data or {},
            task_id=task_id,
            mode=mode,
        )

        # Store in history
        self._history[task_id].append(event)
        if len(self._history[task_id]) > self._max_history:
            self._history[task_id] = self._history[task_id][-self._max_history:]

        # Notify task-specific subscribers
        for queue in self._subscribers.get(task_id, []):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

        # Notify global subscribers
        for queue in self._global_subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

        log.debug(f"[SSE] {task_id} → {event_type} ({len(self._subscribers.get(task_id, []))} subs)")

    def subscribe(self, task_id: str = "", max_queue: int = 50) -> asyncio.Queue:
        """Subscribe to events. Empty task_id = global subscription."""
        queue = asyncio.Queue(maxsize=max_queue)
        if task_id:
            self._subscribers[task_id].append(queue)
        else:
            self._global_subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue, task_id: str = ""):
        """Remove a subscriber."""
        if task_id and task_id in self._subscribers:
            self._subscribers[task_id] = [q for q in self._subscribers[task_id] if q is not queue]
        else:
            self._global_subscribers = [q for q in self._global_subscribers if q is not queue]

    def get_history(self, task_id: str, limit: int = 50) -> list[dict]:
        """Get recent events for a task."""
        events = self._history.get(task_id, [])[-limit:]
        return [{"type": e.event_type, "data": e.data, "timestamp": e.timestamp, "mode": e.mode} for e in events]

    def stats(self) -> dict:
        """Get bus statistics."""
        return {
            "task_subscriptions": {k: len(v) for k, v in self._subscribers.items() if v},
            "global_subscribers": len(self._global_subscribers),
            "history_tasks": len(self._history),
            "total_events": sum(len(v) for v in self._history.values()),
        }


async def stream_task_events(
    bus: EventBus,
    task_id: str,
    modes: list[str] = None,
    timeout: float = 300,
) -> AsyncGenerator[str, None]:
    """
    Async generator for SSE streaming. Use with FastAPI StreamingResponse.

    Args:
        bus: EventBus instance
        task_id: Task to subscribe to (empty = all tasks)
        modes: Filter by modes (updates, tokens, scores, state, system)
        timeout: Max stream duration in seconds
    """
    if modes is None:
        modes = ["updates", "scores"]

    queue = bus.subscribe(task_id)
    start = time.time()

    try:
        # Send initial connection event
        yield f"event: connected\ndata: {json.dumps({'task_id': task_id, 'modes': modes})}\n\n"

        # Send history replay
        history = bus.get_history(task_id, limit=20)
        for h in history:
            if h["mode"] in modes:
                yield SSEEvent(h["type"], h["data"], task_id, h["timestamp"], h["mode"]).to_sse()

        # Stream live events
        while time.time() - start < timeout:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30)
                if event.mode in modes:
                    yield event.to_sse()
            except asyncio.TimeoutError:
                # Send keepalive
                yield f": keepalive {datetime.now(timezone.utc).isoformat()}\n\n"

    finally:
        bus.unsubscribe(queue, task_id)


# =============================================================================
# CONVENIENCE EMITTERS (for use in executor.py)
# =============================================================================

# Singleton bus
_bus = EventBus()

def get_bus() -> EventBus:
    return _bus

def emit_step_start(task_id: str, step: str, **data):
    _bus.emit(task_id, "step_start", {"step": step, **data})

def emit_step_complete(task_id: str, step: str, **data):
    _bus.emit(task_id, "step_complete", {"step": step, **data})

def emit_score(task_id: str, score: int, skill: str = "", **data):
    _bus.emit(task_id, "quality_scored", {"score": score, "skill": skill, **data})

def emit_error(task_id: str, error: str, step: str = ""):
    _bus.emit(task_id, "error", {"error": error, "step": step})

def emit_tripwire(task_id: str, reason: str):
    _bus.emit(task_id, "tripwire", {"reason": reason})

def emit_system(event_type: str, **data):
    _bus.emit("", event_type, data)


if __name__ == "__main__":
    print("=== DARIO SSE Streaming ===\n")

    bus = get_bus()

    # Simulate events
    task_id = "DEMO-001"
    bus.emit(task_id, "task_start", {"skill": "dario-brand"})
    bus.emit(task_id, "step_start", {"step": "guardrails"})
    bus.emit(task_id, "step_complete", {"step": "guardrails", "verdict": "PASS", "duration_ms": 12})
    bus.emit(task_id, "step_start", {"step": "llm_call", "model": "sonnet"})
    bus.emit(task_id, "token_update", {"input": 2000, "output": 1500})
    bus.emit(task_id, "step_complete", {"step": "llm_call", "duration_ms": 3500})
    bus.emit(task_id, "quality_scored", {"score": 87, "skill": "dario-brand"})
    bus.emit(task_id, "task_complete", {"score": 87, "tokens": 3500})

    print(f"Stats: {json.dumps(bus.stats(), indent=2)}")
    print(f"\nHistory ({task_id}):")
    for e in bus.get_history(task_id):
        print(f"  [{e['type']:20s}] {json.dumps(e['data'])}")
