#!/usr/bin/env python3
"""
DARIO SQLite Persistence Layer — Atomic task/audit/budget storage.
==================================================================
Replaces YAML files for mutable state. YAML stays for config only.
Provides ACID transactions, eliminates race conditions completely.

Tables:
    tasks       — Task lifecycle (status, assignee, scores, timestamps)
    audit       — Append-only event log
    budget      — Monthly token tracking
    scores      — Quality score history per skill
    chain_runs  — Skill chain execution state + checkpoints

Usage as module:
    from db import DB
    db = DB()
    db.create_task(id="MNB-007", title="...", skill="dario-brand", project="mar-brasa")
    db.assign_task("MNB-007", "worker-brand")
    db.complete_task("MNB-007", score=92, tokens=2100, output="...")
    tasks = db.get_tasks(status="todo")
    db.log_event("dispatch", "task_assigned", task_id="MNB-007", details="...")

Usage as CLI:
    python db.py --init                    # Create/migrate database
    python db.py --tasks                   # List all tasks
    python db.py --tasks --status todo     # Filter by status
    python db.py --audit --tail 20         # Last 20 audit entries
    python db.py --budget                  # Current month budget
    python db.py --migrate-yaml            # Import existing YAML tasks into DB
    python db.py --stats                   # Database statistics
"""

import argparse
import json
import logging
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

# License enforcement
try:
    from license_manager import require_license
    require_license()
except (ImportError, SystemExit):
    pass  # License check skipped (dev mode)

ORCH_DIR = Path.home() / ".claude" / "orchestrator"
DB_PATH = ORCH_DIR / "orchestrator.db"
TASKS_DIR = ORCH_DIR / "tasks" / "active"

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("db")


# =============================================================================
# DATABASE CLASS
# =============================================================================

class DB:
    """SQLite persistence layer for the orchestrator."""

    def __init__(self, db_path=None):
        self.db_path = db_path or str(DB_PATH)
        self._ensure_schema()

    @contextmanager
    def _conn(self):
        """Context manager for DB connections with WAL mode."""
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _ensure_schema(self):
        """Create tables if they don't exist."""
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    # ─── TASKS ───────────────────────────────────────────────────────────────

    def create_task(self, id: str, title: str, project: str = "", skill: str = "",
                    priority: str = "medium", description: str = "",
                    execution_policy: str = "default", depends_on: list = None,
                    estimated_tokens: int = 0, parent: str = None) -> dict:
        """Create a new task."""
        now = datetime.now(timezone.utc).isoformat()
        deps_json = json.dumps(depends_on or [])

        with self._conn() as conn:
            conn.execute("""
                INSERT INTO tasks (id, title, description, project, skill, priority,
                    status, execution_policy, depends_on, estimated_tokens, parent,
                    created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'todo', ?, ?, ?, ?, ?, ?)
            """, (id, title, description, project, skill, priority,
                  execution_policy, deps_json, estimated_tokens, parent, now, now))

        self.log_event("system", "task_created", task_id=id, details=f"{title} [{skill}]")
        return {"id": id, "status": "todo"}

    def assign_task(self, task_id: str, worker_id: str, reason: str = "") -> bool:
        """Atomically assign a task (CAS: only if status=todo and no assignee)."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            cursor = conn.execute("""
                UPDATE tasks SET assignee = ?, assigned_at = ?, dispatch_reason = ?,
                    updated_at = ?
                WHERE id = ? AND status = 'todo' AND (assignee IS NULL OR assignee = '')
            """, (worker_id, now, reason, now, task_id))
            if cursor.rowcount == 0:
                return False  # Race condition avoided — someone else assigned it
        self.log_event("dispatch", "task_assigned", task_id=task_id,
                       details=f"→ {worker_id} | {reason}")
        return True

    def checkout_task(self, task_id: str) -> bool:
        """Set task to in_progress (atomic checkout)."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            cursor = conn.execute("""
                UPDATE tasks SET status = 'in_progress', checked_out_at = ?, updated_at = ?
                WHERE id = ? AND status = 'todo' AND assignee IS NOT NULL
            """, (now, now, task_id))
            return cursor.rowcount > 0

    def complete_task(self, task_id: str, score: int = 0, tokens: int = 0,
                      output: str = "", status: str = "done") -> bool:
        """Complete a task with score and output."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            cursor = conn.execute("""
                UPDATE tasks SET status = ?, quality_score = ?, actual_tokens = ?,
                    completion_comment = ?, completed_at = ?, updated_at = ?
                WHERE id = ? AND status = 'in_progress'
            """, (status, score, tokens, output, now, now, task_id))
            if cursor.rowcount > 0 and tokens > 0:
                self._add_budget(conn, tokens, task_id)
            return cursor.rowcount > 0

    def block_task(self, task_id: str, reason: str) -> bool:
        """Block a task."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            cursor = conn.execute("""
                UPDATE tasks SET status = 'blocked', blocked_reason = ?, updated_at = ?
                WHERE id = ?
            """, (reason, now, task_id))
            return cursor.rowcount > 0

    def get_task(self, task_id: str) -> dict:
        """Get a single task."""
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            return dict(row) if row else None

    def get_tasks(self, status: str = None, project: str = None,
                  assignee: str = None, unassigned: bool = False) -> list:
        """Query tasks with filters."""
        query = "SELECT * FROM tasks WHERE 1=1"
        params = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if project:
            query += " AND project = ?"
            params.append(project)
        if assignee:
            query += " AND assignee = ?"
            params.append(assignee)
        if unassigned:
            query += " AND (assignee IS NULL OR assignee = '') AND status = 'todo'"
        query += " ORDER BY CASE priority WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END"

        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def get_task_counts(self) -> dict:
        """Get counts by status."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM tasks GROUP BY status"
            ).fetchall()
            return {r["status"]: r["cnt"] for r in rows}

    # ─── AUDIT ───────────────────────────────────────────────────────────────

    def log_event(self, actor: str, action: str, task_id: str = "",
                  entity_type: str = "", details: str = ""):
        """Append an event to the audit log (append-only, never delete)."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO audit (timestamp, actor, action, task_id, entity_type, details)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (now, actor, action, task_id, entity_type, details))

    def get_audit(self, limit: int = 50, actor: str = None, task_id: str = None) -> list:
        """Query audit log."""
        query = "SELECT * FROM audit WHERE 1=1"
        params = []
        if actor:
            query += " AND actor = ?"
            params.append(actor)
        if task_id:
            query += " AND task_id = ?"
            params.append(task_id)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    # ─── BUDGET ──────────────────────────────────────────────────────────────

    def _add_budget(self, conn, tokens: int, task_id: str):
        """Add tokens to current month budget (called within transaction)."""
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        conn.execute("""
            INSERT INTO budget (month, tokens_used) VALUES (?, ?)
            ON CONFLICT(month) DO UPDATE SET
                tokens_used = tokens_used + ?,
                updated_at = ?
        """, (month, tokens, tokens, datetime.now(timezone.utc).isoformat()))

    def get_budget(self, month: str = None) -> dict:
        """Get budget for a month."""
        if not month:
            month = datetime.now(timezone.utc).strftime("%Y-%m")
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM budget WHERE month = ?", (month,)).fetchone()
            if row:
                d = dict(row)
                d["percentage"] = round(d["tokens_used"] / d["token_limit"] * 100, 2)
                return d
            return {"month": month, "tokens_used": 0, "token_limit": 50000000, "percentage": 0.0}

    # ─── SCORES ──────────────────────────────────────────────────────────────

    def record_score(self, task_id: str, skill: str, score: int,
                     project: str = "", dimensions: dict = None):
        """Record a quality score."""
        now = datetime.now(timezone.utc).isoformat()
        dims_json = json.dumps(dimensions or {})
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO scores (task_id, skill, score, project, dimensions, scored_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (task_id, skill, score, project, dims_json, now))

    def get_skill_stats(self) -> list:
        """Get aggregate stats per skill."""
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT skill, COUNT(*) as executions,
                    ROUND(AVG(score), 1) as avg_score,
                    MIN(score) as min_score, MAX(score) as max_score
                FROM scores GROUP BY skill ORDER BY avg_score DESC
            """).fetchall()
            return [dict(r) for r in rows]

    # ─── CHAIN RUNS ─────────────────────────────────────────────────────────

    def create_chain_run(self, run_id: str, chain_name: str, project: str,
                         context: str, total_steps: int) -> dict:
        """Create a chain run record."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO chain_runs (run_id, chain_name, project, context,
                    status, current_step, total_steps, started_at)
                VALUES (?, ?, ?, ?, 'running', 0, ?, ?)
            """, (run_id, chain_name, project, context, total_steps, now))
        return {"run_id": run_id, "status": "running"}

    def save_chain_checkpoint(self, run_id: str, step: int, skill: str,
                              artifact_json: str, score: int = 0, status: str = "success"):
        """Save a chain step checkpoint."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO chain_checkpoints (run_id, step_num, skill, artifact, score, status, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (run_id, step, skill, artifact_json, score, status, now))
            conn.execute("""
                UPDATE chain_runs SET current_step = ?, updated_at = ? WHERE run_id = ?
            """, (step, now, run_id))

    # ─── MIGRATION ───────────────────────────────────────────────────────────

    def migrate_from_yaml(self) -> int:
        """Import existing YAML tasks into SQLite."""
        if not TASKS_DIR.exists():
            return 0

        try:
            from ruamel.yaml import YAML
            yaml_engine = YAML()
            def _load(p):
                with open(p, 'r', encoding='utf-8') as f:
                    return yaml_engine.load(f)
        except ImportError:
            import yaml
            def _load(p):
                with open(p, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f)

        imported = 0
        for f in TASKS_DIR.glob("*.yaml"):
            try:
                data = _load(str(f))
                if not data or not data.get("id"):
                    continue

                # Check if already exists
                existing = self.get_task(data["id"])
                if existing:
                    continue

                now = datetime.now(timezone.utc).isoformat()
                deps = json.dumps(data.get("depends_on", []) or [])

                with self._conn() as conn:
                    conn.execute("""
                        INSERT OR IGNORE INTO tasks
                        (id, title, description, project, skill, priority, status,
                         assignee, execution_policy, depends_on, estimated_tokens,
                         actual_tokens, quality_score, completion_comment, parent,
                         created_at, updated_at, assigned_at, checked_out_at, completed_at,
                         dispatch_reason, blocked_reason)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        data.get("id"), data.get("title", ""), data.get("description", ""),
                        data.get("project", ""), data.get("skill", ""),
                        data.get("priority", "medium"), data.get("status", "todo"),
                        data.get("assignee"), data.get("execution_policy", "default"),
                        deps, data.get("estimated_tokens", 0),
                        data.get("actual_tokens"), data.get("quality_score"),
                        data.get("completion_comment"), data.get("parent"),
                        data.get("created_at", now), data.get("updated_at", now),
                        data.get("assigned_at"), data.get("checked_out_at"),
                        data.get("completed_at"), data.get("dispatch_reason"),
                        data.get("blocked_reason"),
                    ))
                imported += 1
            except Exception as e:
                log.warning(f"Failed to import {f.name}: {e}")

        return imported

    # ─── STATS ───────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Database statistics."""
        with self._conn() as conn:
            task_count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            audit_count = conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0]
            score_count = conn.execute("SELECT COUNT(*) FROM scores").fetchone()[0]
            chain_count = conn.execute("SELECT COUNT(*) FROM chain_runs").fetchone()[0]
        return {
            "tasks": task_count,
            "audit_entries": audit_count,
            "scores": score_count,
            "chain_runs": chain_count,
            "db_path": self.db_path,
            "db_size_kb": round(Path(self.db_path).stat().st_size / 1024, 1) if Path(self.db_path).exists() else 0,
        }


# =============================================================================
# SCHEMA
# =============================================================================

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    project TEXT DEFAULT '',
    skill TEXT DEFAULT '',
    priority TEXT DEFAULT 'medium',
    status TEXT DEFAULT 'todo',
    assignee TEXT,
    execution_policy TEXT DEFAULT 'default',
    depends_on TEXT DEFAULT '[]',
    estimated_tokens INTEGER DEFAULT 0,
    actual_tokens INTEGER,
    quality_score INTEGER,
    completion_comment TEXT,
    parent TEXT,
    dispatch_reason TEXT,
    blocked_reason TEXT,
    created_at TEXT,
    updated_at TEXT,
    assigned_at TEXT,
    checked_out_at TEXT,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    task_id TEXT DEFAULT '',
    entity_type TEXT DEFAULT '',
    details TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS budget (
    month TEXT PRIMARY KEY,
    tokens_used INTEGER DEFAULT 0,
    token_limit INTEGER DEFAULT 50000000,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT,
    skill TEXT,
    score INTEGER,
    project TEXT DEFAULT '',
    dimensions TEXT DEFAULT '{}',
    scored_at TEXT
);

CREATE TABLE IF NOT EXISTS chain_runs (
    run_id TEXT PRIMARY KEY,
    chain_name TEXT,
    project TEXT,
    context TEXT,
    status TEXT DEFAULT 'running',
    current_step INTEGER DEFAULT 0,
    total_steps INTEGER DEFAULT 0,
    started_at TEXT,
    completed_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS chain_checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    step_num INTEGER,
    skill TEXT,
    artifact TEXT,
    score INTEGER DEFAULT 0,
    status TEXT DEFAULT 'success',
    timestamp TEXT,
    FOREIGN KEY (run_id) REFERENCES chain_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project);
CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks(assignee);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_task ON audit(task_id);
CREATE INDEX IF NOT EXISTS idx_scores_skill ON scores(skill);
"""


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="DARIO SQLite DB — Orchestrator persistence")
    parser.add_argument("--init", action="store_true", help="Initialize database")
    parser.add_argument("--tasks", action="store_true", help="List tasks")
    parser.add_argument("--status", help="Filter tasks by status")
    parser.add_argument("--audit", action="store_true", help="Show audit log")
    parser.add_argument("--tail", type=int, default=20, help="Limit entries")
    parser.add_argument("--budget", action="store_true", help="Show budget")
    parser.add_argument("--scores", action="store_true", help="Show skill scores")
    parser.add_argument("--migrate-yaml", action="store_true", help="Import YAML tasks")
    parser.add_argument("--stats", action="store_true", help="DB statistics")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")

    args = parser.parse_args()

    db = DB()

    if args.init:
        print(f"Database initialized at {DB_PATH}")
        stats = db.stats()
        print(f"Tables ready. Current: {stats['tasks']} tasks, {stats['audit_entries']} audit entries")
        return 0

    elif args.migrate_yaml:
        imported = db.migrate_from_yaml()
        if args.json:
            print(json.dumps({"imported": imported}))
        else:
            print(f"Imported {imported} tasks from YAML into SQLite")
        return 0

    elif args.tasks:
        tasks = db.get_tasks(status=args.status)
        if args.json:
            print(json.dumps(tasks, indent=2, default=str))
        else:
            print(f"=== TASKS ({len(tasks)}) ===\n")
            for t in tasks:
                mark = {"done": "+", "in_progress": "~", "todo": " ", "blocked": "!"}.get(t["status"], "?")
                print(f"  [{mark}] {t['id']:12s} {t['status']:12s} {t.get('assignee') or '-':20s} {t['title'][:50]}")
        return 0

    elif args.audit:
        entries = db.get_audit(limit=args.tail)
        if args.json:
            print(json.dumps(entries, indent=2))
        else:
            print(f"=== AUDIT (last {args.tail}) ===\n")
            for e in entries:
                ts = e["timestamp"][11:19] if e.get("timestamp") else "?"
                print(f"  [{ts}] {e['actor']}: {e['action']} {e.get('task_id','')} — {e.get('details','')[:60]}")
        return 0

    elif args.budget:
        b = db.get_budget()
        if args.json:
            print(json.dumps(b, indent=2))
        else:
            print(f"  Month: {b['month']}")
            print(f"  Used:  {b['tokens_used']:,} / {b['token_limit']:,} ({b['percentage']:.2f}%)")
        return 0

    elif args.scores:
        stats = db.get_skill_stats()
        if args.json:
            print(json.dumps(stats, indent=2))
        else:
            print("=== SKILL SCORES ===\n")
            for s in stats:
                print(f"  {s['skill']:30s} avg={s['avg_score']:5.1f} n={s['executions']} range=[{s['min_score']}-{s['max_score']}]")
        return 0

    elif args.stats:
        s = db.stats()
        if args.json:
            print(json.dumps(s, indent=2))
        else:
            print(f"  Tasks:       {s['tasks']}")
            print(f"  Audit:       {s['audit_entries']}")
            print(f"  Scores:      {s['scores']}")
            print(f"  Chain runs:  {s['chain_runs']}")
            print(f"  DB size:     {s['db_size_kb']} KB")
            print(f"  Path:        {s['db_path']}")
        return 0

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
