#!/usr/bin/env python3
"""
DARIO Span Tracer — Hierarchical execution tracing (OpenAI SDK-inspired).
==========================================================================
Replaces flat start/end tracing with nested spans. Each operation is a span
with parent-child relationships, enabling precise "where did it fail?" debugging.

Hierarchy:
    TaskSpan (root)
    ├── FilterSpan (pipeline.before)
    │   ├── ModelRouterSpan
    │   └── BudgetCheckSpan
    ├── GuardrailSpan
    ├── ContextSpan (RAG injection)
    ├── LLMSpan (model call)
    │   ├── PromptSpan
    │   └── GenerationSpan
    ├── FilterSpan (pipeline.after)
    │   ├── SchemaValidationSpan
    │   └── OutputGuardrailSpan
    └── ScoringSpan

Usage:
    from span_tracer import SpanTracer, SpanKind

    tracer = SpanTracer()
    with tracer.span("task_execution", kind=SpanKind.TASK, task_id="MNB-001") as root:
        with tracer.span("guardrails", kind=SpanKind.GUARDRAIL, parent=root) as g:
            g.set_attribute("checks", 7)
            g.set_attribute("verdict", "PASS")
        with tracer.span("llm_call", kind=SpanKind.LLM, parent=root) as llm:
            llm.set_attribute("model", "sonnet")
            llm.set_attribute("tokens_in", 1500)
            llm.set_attribute("tokens_out", 800)

    # Export
    tracer.export_json("traces/MNB-001.json")
    tracer.print_tree()

CLI:
    python span_tracer.py --view TASK-001
    python span_tracer.py --list --limit 10
    python span_tracer.py --stats
"""

import argparse
import json
import logging
import sys
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

ORCH_DIR = Path.home() / ".claude" / "orchestrator"
TRACES_DIR = ORCH_DIR / "traces"
TRACES_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("span_tracer")


class SpanKind(str, Enum):
    TASK = "task"
    FILTER = "filter"
    GUARDRAIL = "guardrail"
    CONTEXT = "context"
    LLM = "llm"
    SCORING = "scoring"
    TOOL = "tool"
    CHAIN = "chain"
    STEP = "step"
    CUSTOM = "custom"


class SpanStatus(str, Enum):
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"
    TRIPWIRE = "tripwire"


@dataclass
class Span:
    """A single execution span with timing and attributes."""
    name: str
    kind: SpanKind = SpanKind.CUSTOM
    span_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    parent_id: Optional[str] = None
    trace_id: str = ""
    start_time: float = 0
    end_time: float = 0
    duration_ms: float = 0
    status: SpanStatus = SpanStatus.OK
    attributes: dict = field(default_factory=dict)
    events: list = field(default_factory=list)
    error: str = ""

    def set_attribute(self, key: str, value):
        self.attributes[key] = value

    def add_event(self, name: str, attributes: dict = None):
        self.events.append({
            "name": name,
            "timestamp": time.time(),
            "attributes": attributes or {},
        })

    def set_error(self, error: str):
        self.status = SpanStatus.ERROR
        self.error = error

    def finish(self):
        self.end_time = time.time()
        self.duration_ms = round((self.end_time - self.start_time) * 1000, 2)

    def to_dict(self) -> dict:
        return {
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "trace_id": self.trace_id,
            "name": self.name,
            "kind": self.kind.value,
            "status": self.status.value,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "attributes": self.attributes,
            "events": self.events,
            "error": self.error,
        }


class SpanTracer:
    """Hierarchical span-based tracer for task execution."""

    def __init__(self, trace_id: str = ""):
        self.trace_id = trace_id or uuid.uuid4().hex[:16]
        self.spans: list[Span] = []
        self._active_span: Optional[Span] = None

    @contextmanager
    def span(self, name: str, kind: SpanKind = SpanKind.CUSTOM, parent: Span = None, **attrs):
        """Context manager for creating a span."""
        s = Span(
            name=name,
            kind=kind,
            trace_id=self.trace_id,
            parent_id=parent.span_id if parent else (self._active_span.span_id if self._active_span else None),
            start_time=time.time(),
        )
        for k, v in attrs.items():
            s.set_attribute(k, v)

        prev_active = self._active_span
        self._active_span = s

        try:
            yield s
        except Exception as e:
            s.set_error(str(e))
            raise
        finally:
            s.finish()
            self.spans.append(s)
            self._active_span = prev_active

    def start_span(self, name: str, kind: SpanKind = SpanKind.CUSTOM, parent_id: str = None, **attrs) -> Span:
        """Start a span manually (for non-context-manager usage)."""
        s = Span(
            name=name,
            kind=kind,
            trace_id=self.trace_id,
            parent_id=parent_id or (self._active_span.span_id if self._active_span else None),
            start_time=time.time(),
        )
        for k, v in attrs.items():
            s.set_attribute(k, v)
        return s

    def end_span(self, span: Span):
        """End a manually-started span."""
        span.finish()
        self.spans.append(span)

    def export_json(self, path: str = "") -> str:
        """Export trace as JSON. Returns path."""
        if not path:
            path = str(TRACES_DIR / f"{self.trace_id}.json")

        data = {
            "trace_id": self.trace_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "span_count": len(self.spans),
            "total_duration_ms": sum(s.duration_ms for s in self.spans if not s.parent_id),
            "spans": [s.to_dict() for s in self.spans],
        }

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
        return path

    def get_tree(self) -> list[dict]:
        """Build a tree structure from flat spans."""
        span_map = {s.span_id: s.to_dict() for s in self.spans}
        roots = []

        for s in self.spans:
            node = span_map[s.span_id]
            node["children"] = []

        for s in self.spans:
            node = span_map[s.span_id]
            if s.parent_id and s.parent_id in span_map:
                span_map[s.parent_id]["children"].append(node)
            else:
                roots.append(node)

        return roots

    def print_tree(self, indent: int = 0):
        """Print span tree to console."""
        def _print_node(node, depth):
            status_icon = {"ok": "+", "error": "!", "timeout": "~", "tripwire": "X"}
            icon = status_icon.get(node["status"], "?")
            kind_color = node["kind"][:4].upper()
            duration = f"{node['duration_ms']:.0f}ms"
            attrs = ", ".join(f"{k}={v}" for k, v in list(node["attributes"].items())[:3])
            print(f"{'  ' * depth}[{icon}] {kind_color} {node['name']} ({duration}) {attrs}")
            for child in node.get("children", []):
                _print_node(child, depth + 1)

        for root in self.get_tree():
            _print_node(root, indent)

    def summary(self) -> dict:
        """Get trace summary statistics."""
        total = len(self.spans)
        errors = sum(1 for s in self.spans if s.status == SpanStatus.ERROR)
        by_kind = {}
        for s in self.spans:
            k = s.kind.value
            if k not in by_kind:
                by_kind[k] = {"count": 0, "total_ms": 0}
            by_kind[k]["count"] += 1
            by_kind[k]["total_ms"] += s.duration_ms

        root_spans = [s for s in self.spans if not s.parent_id]
        total_ms = sum(s.duration_ms for s in root_spans)

        return {
            "trace_id": self.trace_id,
            "total_spans": total,
            "errors": errors,
            "total_duration_ms": round(total_ms, 2),
            "by_kind": by_kind,
        }


# =============================================================================
# UTILITIES
# =============================================================================

def load_trace(trace_id: str) -> dict:
    """Load a saved trace from file."""
    path = TRACES_DIR / f"{trace_id}.json"
    if not path.exists():
        # Try to find by prefix
        matches = list(TRACES_DIR.glob(f"{trace_id}*.json"))
        if matches:
            path = matches[0]
        else:
            return {"error": f"Trace {trace_id} not found"}

    return json.loads(path.read_text(encoding="utf-8"))


def list_traces(limit: int = 20) -> list[dict]:
    """List recent traces."""
    traces = sorted(TRACES_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    result = []
    for t in traces:
        try:
            data = json.loads(t.read_text(encoding="utf-8"))
            result.append({
                "trace_id": data.get("trace_id", t.stem),
                "created_at": data.get("created_at", ""),
                "span_count": data.get("span_count", 0),
                "total_duration_ms": data.get("total_duration_ms", 0),
            })
        except Exception:
            pass
    return result


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="DARIO Span Tracer — Hierarchical execution tracing")
    parser.add_argument("--view", help="View a trace by ID")
    parser.add_argument("--list", action="store_true", help="List recent traces")
    parser.add_argument("--limit", type=int, default=20, help="Limit for --list")
    parser.add_argument("--stats", action="store_true", help="Show trace statistics")
    parser.add_argument("--demo", action="store_true", help="Run demo trace")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.demo:
        tracer = SpanTracer()
        with tracer.span("execute_task", kind=SpanKind.TASK, task_id="DEMO-001") as root:
            with tracer.span("filter_before", kind=SpanKind.FILTER, parent=root):
                time.sleep(0.01)
            with tracer.span("guardrails", kind=SpanKind.GUARDRAIL, parent=root, checks=7, verdict="PASS"):
                time.sleep(0.005)
            with tracer.span("context_injection", kind=SpanKind.CONTEXT, parent=root, sources=3, tokens=1200):
                time.sleep(0.008)
            with tracer.span("llm_call", kind=SpanKind.LLM, parent=root, model="sonnet", tokens_in=2000) as llm:
                time.sleep(0.05)
                llm.set_attribute("tokens_out", 1500)
            with tracer.span("filter_after", kind=SpanKind.FILTER, parent=root) as af:
                with tracer.span("schema_validation", kind=SpanKind.GUARDRAIL, parent=af, valid=True):
                    time.sleep(0.003)
                with tracer.span("output_guardrails", kind=SpanKind.GUARDRAIL, parent=af, tripwire=False):
                    time.sleep(0.002)
            with tracer.span("scoring", kind=SpanKind.SCORING, parent=root, score=87):
                time.sleep(0.005)

        print("=== TRACE TREE ===")
        tracer.print_tree()
        print(f"\n=== SUMMARY ===")
        print(json.dumps(tracer.summary(), indent=2))

        path = tracer.export_json()
        print(f"\nExported to: {path}")
        return 0

    if args.view:
        data = load_trace(args.view)
        if "error" in data:
            print(data["error"])
            return 1
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            print(f"Trace: {data['trace_id']} | {data['span_count']} spans | {data['total_duration_ms']:.0f}ms")
            # Rebuild tree for display
            tracer = SpanTracer(data["trace_id"])
            for sd in data["spans"]:
                s = Span(name=sd["name"], kind=SpanKind(sd["kind"]))
                s.span_id = sd["span_id"]
                s.parent_id = sd["parent_id"]
                s.duration_ms = sd["duration_ms"]
                s.status = SpanStatus(sd["status"])
                s.attributes = sd["attributes"]
                s.error = sd.get("error", "")
                tracer.spans.append(s)
            tracer.print_tree()
        return 0

    if args.list:
        traces = list_traces(args.limit)
        if args.json:
            print(json.dumps(traces, indent=2))
        else:
            for t in traces:
                print(f"  {t['trace_id']} | {t['span_count']:3d} spans | {t['total_duration_ms']:6.0f}ms | {t['created_at'][:19]}")
        return 0

    if args.stats:
        traces = list_traces(100)
        total = len(traces)
        total_spans = sum(t["span_count"] for t in traces)
        avg_duration = sum(t["total_duration_ms"] for t in traces) / max(total, 1)
        print(f"Traces: {total}")
        print(f"Total spans: {total_spans}")
        print(f"Avg duration: {avg_duration:.0f}ms")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
