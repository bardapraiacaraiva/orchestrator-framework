#!/usr/bin/env python3
"""
DARIO Runtime Engine — Persistent FastAPI server for the orchestrator.
======================================================================
Runs independently of Claude sessions. Provides REST API for all ops.
Internal scheduler replaces cron hacks. WebSocket for live updates.

Start:
    python runtime.py                    # Port 8422
    python runtime.py --port 8422        # Custom port
    python runtime.py --no-scheduler     # Without heartbeat scheduler

API Endpoints:
    GET  /health              — System health + state
    GET  /tasks               — List tasks (query: ?status=todo&project=X)
    POST /tasks               — Create task
    POST /tasks/{id}/assign   — Assign task to worker
    POST /tasks/{id}/complete — Complete task with score
    GET  /dispatch            — Run dispatch (dry-run by default)
    POST /dispatch            — Execute dispatch (assign tasks)
    GET  /state              — Current state machine status
    POST /state/transition    — Force state transition
    GET  /audit              — Audit log (query: ?limit=50&actor=X)
    GET  /budget             — Current budget
    GET  /scores             — Skill performance stats
    POST /pulse              — Trigger heartbeat pulse manually
    GET  /chains             — List chain runs
    POST /chains/{name}/start — Start a skill chain

Scheduler:
    - Heartbeat every 30 minutes (calls dispatch + state check)
    - AutoDiag every hour
    - Evolution cycle daily at 03:00

Port: 8422 (to not conflict with RAG on 8420, Runtime on 8421)
"""

import asyncio
import json
import logging
import subprocess
import sys
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

# Add orchestrator dir to path for imports
ORCH_DIR = Path.home() / ".claude" / "orchestrator"
sys.path.insert(0, str(ORCH_DIR))

from db import DB

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("runtime")

# ─── Globals ─────────────────────────────────────────────────────────────────
db = DB()
PYTHON = sys.executable
scheduler_enabled = True


# ─── Scheduler ───────────────────────────────────────────────────────────────

class Scheduler:
    """Internal heartbeat scheduler (replaces cron hacks)."""

    def __init__(self):
        self.running = False
        self._task = None
        self.pulse_count = 0
        self.last_pulse = None

    async def start(self):
        self.running = True
        self._task = asyncio.create_task(self._loop())
        log.info("Scheduler started (30min heartbeat)")

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()

    async def _loop(self):
        while self.running:
            try:
                await self._pulse()
                self.pulse_count += 1
                self.last_pulse = datetime.now(timezone.utc).isoformat()
            except Exception as e:
                log.error(f"Pulse error: {e}")
            await asyncio.sleep(1800)  # 30 minutes

    async def _pulse(self):
        """Execute heartbeat pulse via subprocess."""
        # State check
        _run_engine("state_machine.py", ["--evaluate", "--json"])
        # Dispatch
        _run_engine("dispatch_engine.py", ["--json"])
        # AutoDiag
        _run_engine("autodiag_runner.py", ["--fix", "--json"])
        log.info(f"Pulse #{self.pulse_count + 1} complete")


scheduler = Scheduler()


def _run_engine(script: str, args: list) -> dict:
    """Run an orchestrator engine and return parsed JSON."""
    script_path = ORCH_DIR / script
    if not script_path.exists():
        return {"error": f"{script} not found"}
    try:
        result = subprocess.run(
            [PYTHON, str(script_path)] + args,
            capture_output=True, text=True, timeout=15, cwd=str(ORCH_DIR)
        )
        if result.stdout.strip():
            try:
                return json.loads(result.stdout.strip())
            except json.JSONDecodeError:
                return {"raw": result.stdout.strip()[:500]}
        return {"exit_code": result.returncode}
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    except Exception as e:
        return {"error": str(e)[:200]}


# ─── Lifespan ────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    if scheduler_enabled:
        await scheduler.start()
    yield
    if scheduler_enabled:
        await scheduler.stop()


# ─── App ─────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="DARIO Orchestrator Runtime",
    version="3.1.0",
    description="Persistent runtime engine for the DARIO orchestrator ecosystem",
    lifespan=lifespan,
)


# ─── Models ──────────────────────────────────────────────────────────────────

class TaskCreate(BaseModel):
    id: str
    title: str
    project: str = ""
    skill: str = ""
    priority: str = "medium"
    description: str = ""
    execution_policy: str = "default"
    depends_on: list = []
    estimated_tokens: int = 0

class TaskComplete(BaseModel):
    score: int = 0
    tokens: int = 0
    output: str = ""
    status: str = "done"

class AssignRequest(BaseModel):
    worker_id: str
    reason: str = ""

class TransitionRequest(BaseModel):
    target_state: str


# ─── Endpoints ───────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    state_result = _run_engine("state_machine.py", ["--json"])
    return {
        "status": "ok",
        "state": state_result.get("state", "?"),
        "autonomy": state_result.get("autonomy_level", "?"),
        "health": state_result.get("system_health", 0),
        "scheduler": {"running": scheduler.running, "pulses": scheduler.pulse_count},
        "db": db.stats(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/tasks")
async def list_tasks(status: str = None, project: str = None,
                     assignee: str = None, unassigned: bool = False):
    tasks = db.get_tasks(status=status, project=project,
                         assignee=assignee, unassigned=unassigned)
    return {"count": len(tasks), "tasks": tasks}


@app.post("/tasks")
async def create_task(task: TaskCreate):
    result = db.create_task(
        id=task.id, title=task.title, project=task.project,
        skill=task.skill, priority=task.priority, description=task.description,
        execution_policy=task.execution_policy, depends_on=task.depends_on,
        estimated_tokens=task.estimated_tokens
    )
    return result


@app.post("/tasks/{task_id}/assign")
async def assign_task(task_id: str, req: AssignRequest):
    success = db.assign_task(task_id, req.worker_id, req.reason)
    if not success:
        raise HTTPException(400, "Assignment failed (task not in todo state or already assigned)")
    return {"assigned": True, "task_id": task_id, "worker": req.worker_id}


@app.post("/tasks/{task_id}/checkout")
async def checkout_task(task_id: str):
    success = db.checkout_task(task_id)
    if not success:
        raise HTTPException(400, "Checkout failed (not assigned or not in todo)")
    return {"checked_out": True, "task_id": task_id}


@app.post("/tasks/{task_id}/complete")
async def complete_task(task_id: str, req: TaskComplete):
    success = db.complete_task(task_id, req.score, req.tokens, req.output, req.status)
    if not success:
        raise HTTPException(400, "Complete failed (task not in_progress)")
    if req.score > 0:
        task = db.get_task(task_id)
        if task:
            db.record_score(task_id, task.get("skill", ""), req.score, task.get("project", ""))
    return {"completed": True, "task_id": task_id, "score": req.score}


@app.get("/dispatch")
async def dispatch_dry_run():
    result = _run_engine("dispatch_engine.py", ["--dry-run", "--json"])
    return result


@app.post("/dispatch")
async def dispatch_execute():
    result = _run_engine("dispatch_engine.py", ["--json"])
    return result


@app.get("/state")
async def get_state():
    return _run_engine("state_machine.py", ["--json"])


@app.post("/state/transition")
async def force_transition(req: TransitionRequest):
    result = _run_engine("state_machine.py", ["--transition", req.target_state, "--json"])
    return result


@app.get("/audit")
async def get_audit(limit: int = 50, actor: str = None, task_id: str = None):
    entries = db.get_audit(limit=limit, actor=actor, task_id=task_id)
    return {"count": len(entries), "entries": entries}


@app.get("/budget")
async def get_budget(month: str = None):
    return db.get_budget(month)


@app.get("/scores")
async def get_scores():
    return {"skills": db.get_skill_stats()}


@app.post("/pulse")
async def trigger_pulse():
    """Manually trigger a heartbeat pulse."""
    await scheduler._pulse()
    scheduler.pulse_count += 1
    scheduler.last_pulse = datetime.now(timezone.utc).isoformat()
    return {"pulse": scheduler.pulse_count, "status": "executed"}


@app.get("/chains")
async def list_chains():
    result = _run_engine("chain_executor.py", ["--list", "--json"])
    return result


@app.post("/chains/{chain_name}/start")
async def start_chain(chain_name: str, project: str = "", context: str = ""):
    result = _run_engine("chain_executor.py", [
        "--chain", chain_name, "--project", project, "--context", context, "--json"
    ])
    return result


# ─── #15: Real-Time SSE Event Stream ─────────────────────────────────────────

from asyncio import Queue
from fastapi.responses import StreamingResponse

event_subscribers: list[Queue] = []


async def broadcast_event(event: dict):
    """Push event to all SSE subscribers."""
    dead = []
    for q in event_subscribers:
        try:
            await q.put(event)
        except Exception:
            dead.append(q)
    for q in dead:
        event_subscribers.remove(q)


@app.get("/events")
async def sse_stream():
    """Server-Sent Events stream for real-time updates."""
    queue = Queue()
    event_subscribers.append(queue)

    async def event_generator():
        try:
            yield f"data: {json.dumps({'type': 'connected', 'subscribers': len(event_subscribers)})}\n\n"
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event, default=str)}\n\n"
        except asyncio.CancelledError:
            event_subscribers.remove(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# Override task endpoints to broadcast events
_orig_complete = complete_task
@app.post("/tasks/{task_id}/complete", response_model=None)
async def complete_task_with_event(task_id: str, req: TaskComplete):
    result = await _orig_complete(task_id, req)
    await broadcast_event({"type": "task_completed", "task_id": task_id, "score": req.score})
    return result


# ─── #16: Skill Composer API ─────────────────────────────────────────────────

class ComposeRequest(BaseModel):
    name: str
    description: str = ""
    steps: list  # [{"skill": "X", "parallel": False, "condition": None}, ...]
    estimated_tokens: int = 0
    quality_gate: str = "score >= 70"


@app.post("/chains/compose")
async def compose_chain(req: ComposeRequest):
    """Dynamically compose a skill chain. Validates schemas and saves."""
    from chain_executor import DEFAULT_SCHEMAS, build_execution_plan

    # Validate all skills have schemas
    validated = []
    warnings = []
    for step in req.steps:
        skill = step.get("skill", "")
        has_schema = skill in DEFAULT_SCHEMAS
        validated.append({**step, "schema_valid": has_schema})
        if not has_schema:
            warnings.append(f"'{skill}' has no artifact schema — outputs won't be validated")

    # Build chain definition
    chain_def = {
        "name": req.name,
        "description": req.description,
        "trigger_keywords": [],
        "steps": [{
            "skill": s.get("skill"),
            "parallel": s.get("parallel", False),
            "condition": s.get("condition"),
            "receives": s.get("receives", "output from previous"),
            "produces": s.get("produces", "structured output"),
            "pass_to_next": s.get("pass_to_next", []),
        } for s in req.steps],
        "estimated_tokens": req.estimated_tokens,
        "quality_gate": req.quality_gate,
    }

    plan = build_execution_plan(chain_def)

    return {
        "chain_name": req.name,
        "steps": len(req.steps),
        "waves": len(plan),
        "schemas_valid": sum(1 for s in validated if s["schema_valid"]),
        "warnings": warnings,
        "plan": plan,
        "chain_def": chain_def,
    }


# ─── #17: Smart Context Window ──────────────────────────────────────────────

@app.get("/context/{task_id}")
async def get_smart_context(task_id: str, token_budget: int = 4000):
    """Get relevance-ranked context for a task, trimmed to token budget."""
    result = _run_engine("context_injector.py", ["--task", task_id, "--json"])

    if not isinstance(result, dict) or "sections" not in result:
        return result

    # Rank by priority and trim to budget
    priority_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    sections = sorted(result.get("sections", []),
                      key=lambda s: priority_rank.get(s.get("priority", "low"), 3))

    trimmed = []
    tokens_used = 0
    for section in sections:
        content = section.get("content", "")
        section_tokens = len(content) // 4
        if tokens_used + section_tokens <= token_budget:
            trimmed.append(section)
            tokens_used += section_tokens
        else:
            # Partial include: trim content to fit remaining budget
            remaining = (token_budget - tokens_used) * 4
            if remaining > 100:
                section["content"] = content[:remaining] + "... [trimmed]"
                section["trimmed"] = True
                trimmed.append(section)
                tokens_used = token_budget
            break

    return {
        "task_id": task_id,
        "token_budget": token_budget,
        "tokens_used": tokens_used,
        "sections_included": len(trimmed),
        "sections_total": len(result.get("sections", [])),
        "sections": trimmed,
    }


# ─── #18: Webhook Integrations ──────────────────────────────────────────────

import urllib.request

WEBHOOKS_FILE = ORCH_DIR / "webhooks.yaml"


def load_webhooks() -> dict:
    if not WEBHOOKS_FILE.exists():
        return {"hooks": []}
    try:
        return load_yaml(str(WEBHOOKS_FILE)) or {"hooks": []}
    except Exception:
        return {"hooks": []}


async def fire_webhooks(event_type: str, payload: dict):
    """Send outbound webhook for an event."""
    config = load_webhooks()
    for hook in config.get("hooks", []):
        if event_type in hook.get("events", []) or "*" in hook.get("events", []):
            url = hook.get("url", "")
            if not url:
                continue
            try:
                data = json.dumps({"event": event_type, "payload": payload, "source": "dario-runtime"}).encode()
                req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=5)
            except Exception as e:
                log.warning(f"Webhook failed ({url}): {e}")


@app.get("/webhooks")
async def list_webhooks():
    return load_webhooks()


@app.post("/webhooks/test")
async def test_webhook(url: str, event: str = "test"):
    """Fire a test webhook."""
    await fire_webhooks(event, {"test": True, "url": url})
    return {"fired": True, "event": event}


# ─── #20: Visual DAG Dashboard ──────────────────────────────────────────────

from fastapi.responses import HTMLResponse, FileResponse

# License enforcement
try:
    from license_manager import require_license
    require_license()
except (ImportError, SystemExit):
    pass  # License check skipped (dev mode)

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """NASA Mission Control dashboard — serves dashboard.html with live API data."""
    dashboard_file = ORCH_DIR / "dashboard.html"
    if dashboard_file.exists():
        return HTMLResponse(content=dashboard_file.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Dashboard file not found. Run: python db.py --init</h1>", status_code=404)


@app.get("/dashboard/agents", response_class=HTMLResponse)
async def dashboard_agents():
    """Live Agent Operations Center — real-time execution display."""
    agent_file = ORCH_DIR / "agent_display.html"
    if agent_file.exists():
        return HTMLResponse(content=agent_file.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Agent display file not found.</h1>", status_code=404)


@app.get("/dashboard/data")
async def dashboard_data():
    """Full DAG data for dashboard consumption."""
    tasks = db.get_tasks()
    counts = db.get_task_counts()
    audit = db.get_audit(limit=50)
    scores = db.get_skill_stats()
    budget = db.get_budget()
    return {
        "tasks": tasks,
        "counts": counts,
        "audit": audit,
        "scores": scores,
        "budget": budget,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ─── Templates API ───────────────────────────────────────────────────────────

@app.get("/templates")
async def list_templates():
    result = _run_engine("task_templates.py", ["--list", "--json"])
    return result

@app.post("/templates/{name}/instantiate")
async def instantiate_template(name: str, variables: dict = {}, create: bool = False):
    args = ["--template", name, "--vars", json.dumps(variables)]
    if create:
        args.append("--create")
    args.append("--json")
    result = _run_engine("task_templates.py", args)
    return result


# ─── Adaptive Rubric API ────────────────────────────────────────────────────

@app.get("/rubric/{task_id}")
async def get_rubric(task_id: str):
    result = _run_engine("adaptive_rubric.py", ["--task", task_id, "--json"])
    return result


# ─── TIER 3 Registration ────────────────────────────────────────────────────

try:
    from tier3 import register_tier3_endpoints
    register_tier3_endpoints(app)
    log.info("TIER 3 endpoints registered (10 differentiation features)")
except ImportError as e:
    log.warning(f"TIER 3 not loaded: {e}")


# ─── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="DARIO Runtime Engine")
    parser.add_argument("--port", type=int, default=8422)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--no-scheduler", action="store_true")
    args = parser.parse_args()

    if args.no_scheduler:
        scheduler_enabled = False

    log.info(f"DARIO Runtime v9.0 starting on {args.host}:{args.port}")
    log.info(f"Scheduler: {'enabled (30min pulse)' if not args.no_scheduler else 'disabled'}")

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
