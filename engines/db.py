#!/usr/bin/env python3
"""
DARIO SQLite Persistence Layer v2 — Production-grade data engine.
==================================================================
Reengineered from audit findings: transactional audit, status guards,
schema migrations, SQL injection protection, proper error recovery.

Tables:
    tasks             — Task lifecycle (status, assignee, scores, timestamps)
    audit             — Append-only event log (transactional with state changes)
    budget            — Monthly token tracking with model breakdown
    scores            — Quality score history per skill with model tracking
    chain_runs        — Skill chain execution state
    chain_checkpoints — Per-step checkpoints for chain resume
    schema_versions   — Migration tracking

Valid task statuses:
    todo → in_progress → done
    todo → blocked
    in_progress → blocked
    in_progress → awaiting_human → in_progress → done
    in_progress → suspended → todo (on restart)
    any → pending_approval → todo (approved) or blocked (rejected)

Usage:
    from db import DB
    db = DB()
    db.create_task({"id": "T-001", "title": "...", "skill": "dario-brand"})
    db.assign_task("T-001", "worker-brand")
    db.checkout_task("T-001")
    db.complete_task("T-001", score=92, tokens=2100, output="...")
"""

import argparse
import json
import logging
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ORCH_DIR = Path.home() / ".claude" / "orchestrator"
DB_PATH = ORCH_DIR / "orchestrator.db"
TASKS_DIR = ORCH_DIR / "tasks" / "active"

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("db")

# Schema version — increment on every schema change
CURRENT_SCHEMA_VERSION = 2

# Allowed columns for safe updates (SQL injection prevention)
ALLOWED_TASK_COLUMNS = {
    "title", "description", "project", "skill", "priority", "status",
    "assignee", "execution_policy", "depends_on", "estimated_tokens",
    "actual_tokens", "quality_score", "completion_comment", "parent",
    "dispatch_reason", "blocked_reason", "updated_at", "assigned_at",
    "checked_out_at", "completed_at", "tenant_id", "executor_type",
    "inputs", "outputs", "checklist", "performance", "error_handling",
    "cache_key", "cached_result",
}

# Valid status transitions
VALID_TRANSITIONS = {
    "todo": {"in_progress", "blocked", "pending_approval"},
    "in_progress": {"done", "blocked", "awaiting_human", "suspended", "in_review"},
    "blocked": {"todo"},  # Unblock → back to todo
    "awaiting_human": {"in_progress", "blocked"},
    "suspended": {"todo"},  # Resume → back to todo for re-dispatch
    "pending_approval": {"todo", "blocked"},  # Approved → todo, Rejected → blocked
    "in_review": {"done", "in_progress"},  # Approved → done, Revise → in_progress
    "done": set(),  # Terminal state
}


class DB:
    """SQLite persistence layer for the orchestrator — v2 production-grade."""

    def __init__(self, db_path=None):
        self.db_path = db_path or str(DB_PATH)
        self._init_done = False
        self._ensure_schema()

    @contextmanager
    def _conn(self):
        """Context manager for DB connections. WAL set once, not per-connection."""
        conn = sqlite3.connect(self.db_path, timeout=10)
        if not self._init_done:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._init_done = True
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
        """Create tables and run migrations."""
        with self._conn() as conn:
            conn.executescript(BASE_SCHEMA)
            self._run_migrations(conn)

    def _run_migrations(self, conn):
        """Run pending schema migrations."""
        # Get current version
        try:
            row = conn.execute("SELECT MAX(version) FROM schema_versions").fetchone()
            current = row[0] if row and row[0] else 0
        except sqlite3.OperationalError:
            current = 0

        if current < 1:
            # v1: Initial schema (already created by BASE_SCHEMA)
            conn.execute("INSERT OR IGNORE INTO schema_versions (version, description) VALUES (1, 'Initial schema')")

        if current < 2:
            # v2: Add model tracking to scores, tenant_id to audit/budget
            for sql in [
                "ALTER TABLE scores ADD COLUMN model TEXT DEFAULT ''",
                "ALTER TABLE audit ADD COLUMN tenant_id TEXT DEFAULT 'default'",
                "ALTER TABLE budget ADD COLUMN tenant_id TEXT DEFAULT 'default'",
                "CREATE INDEX IF NOT EXISTS idx_scores_task ON scores(task_id)",
                "CREATE INDEX IF NOT EXISTS idx_tasks_skill ON tasks(skill)",
            ]:
                try:
                    conn.execute(sql)
                except sqlite3.OperationalError:
                    pass  # Column already exists
            conn.execute("INSERT OR IGNORE INTO schema_versions (version, description) VALUES (2, 'Add model tracking, tenant_id, indexes')")

    # ─── TASKS ───────────────────────────────────────────────────────────────

    def create_task(self, data: dict = None, **kwargs) -> dict:
        """Create a new task. Accepts dict or kwargs."""
        if data:
            kwargs.update(data)

        task_id = kwargs.get("id", "")
        title = kwargs.get("title", "")
        if not task_id or not title:
            raise ValueError("Task requires 'id' and 'title'")

        now = datetime.now(timezone.utc).isoformat()
        deps = kwargs.get("depends_on", "[]")
        if isinstance(deps, list):
            deps = json.dumps(deps)

        with self._conn() as conn:
            conn.execute("""
                INSERT INTO tasks (id, title, description, project, skill, priority,
                    status, assignee, execution_policy, depends_on, estimated_tokens,
                    parent, tenant_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'todo', ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task_id, title,
                kwargs.get("description", ""),
                kwargs.get("project", ""),
                kwargs.get("skill", ""),
                kwargs.get("priority", "medium"),
                kwargs.get("assignee"),
                kwargs.get("execution_policy", "default"),
                deps,
                kwargs.get("estimated_tokens", 0),
                kwargs.get("parent"),
                kwargs.get("tenant_id", "default"),
                now, now,
            ))
            # Transactional audit — same connection, same transaction
            self._log(conn, "system", "task_created", task_id=task_id,
                     details=f"{title} [{kwargs.get('skill', '')}]")

        return {"id": task_id, "status": "todo"}

    def assign_task(self, task_id: str, worker_id: str, reason: str = "") -> bool:
        """Atomically assign a task (CAS: only if todo and unassigned)."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            cursor = conn.execute("""
                UPDATE tasks SET assignee = ?, assigned_at = ?, dispatch_reason = ?,
                    updated_at = ?
                WHERE id = ? AND status = 'todo' AND (assignee IS NULL OR assignee = '')
            """, (worker_id, now, reason, now, task_id))
            if cursor.rowcount == 0:
                return False
            self._log(conn, "dispatch", "task_assigned", task_id=task_id,
                     details=f"-> {worker_id} | {reason}")
        return True

    def checkout_task(self, task_id: str) -> bool:
        """Atomic assign+checkout: todo → in_progress (requires assignee)."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            cursor = conn.execute("""
                UPDATE tasks SET status = 'in_progress', checked_out_at = ?, updated_at = ?
                WHERE id = ? AND status = 'todo' AND assignee IS NOT NULL AND assignee != ''
            """, (now, now, task_id))
            if cursor.rowcount > 0:
                self._log(conn, "executor", "task_checked_out", task_id=task_id)
            return cursor.rowcount > 0

    def complete_task(self, task_id: str, score: int = 0, tokens: int = 0,
                      output: str = "", status: str = "done") -> bool:
        """Complete a task. Only from in_progress."""
        if status not in ("done", "in_review"):
            status = "done"
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            cursor = conn.execute("""
                UPDATE tasks SET status = ?, quality_score = ?, actual_tokens = ?,
                    completion_comment = ?, completed_at = ?, updated_at = ?
                WHERE id = ? AND status IN ('in_progress', 'in_review')
            """, (status, score, tokens, output[:2000], now, now, task_id))
            if cursor.rowcount > 0:
                if tokens > 0:
                    self._add_budget(conn, tokens, task_id)
                self._log(conn, "executor", "task_completed", task_id=task_id,
                         details=f"score={score} tokens={tokens} status={status}")
            return cursor.rowcount > 0

    def block_task(self, task_id: str, reason: str) -> bool:
        """Block a task. Only from todo or in_progress (fixed: was unguarded)."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            cursor = conn.execute("""
                UPDATE tasks SET status = 'blocked', blocked_reason = ?, updated_at = ?
                WHERE id = ? AND status IN ('todo', 'in_progress')
            """, (reason, now, task_id))
            if cursor.rowcount > 0:
                self._log(conn, "system", "task_blocked", task_id=task_id, details=reason[:200])
            return cursor.rowcount > 0

    def reset_task(self, task_id: str, reason: str = "") -> bool:
        """Reset a task back to todo for re-execution (new: was missing)."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            cursor = conn.execute("""
                UPDATE tasks SET status = 'todo', quality_score = NULL, actual_tokens = NULL,
                    completion_comment = NULL, completed_at = NULL, checked_out_at = NULL,
                    blocked_reason = ?, updated_at = ?
                WHERE id = ? AND status IN ('blocked', 'done', 'in_review', 'suspended')
            """, (reason, now, task_id))
            if cursor.rowcount > 0:
                self._log(conn, "system", "task_reset", task_id=task_id, details=reason[:200])
            return cursor.rowcount > 0

    def delete_task(self, task_id: str) -> bool:
        """Delete a task permanently (new: was missing)."""
        with self._conn() as conn:
            cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            if cursor.rowcount > 0:
                self._log(conn, "system", "task_deleted", task_id=task_id)
            return cursor.rowcount > 0

    def update_task(self, task_id: str, fields: dict) -> bool:
        """Safe update with column whitelist (fixed: was SQL injection vulnerable)."""
        safe = {k: v for k, v in fields.items() if k in ALLOWED_TASK_COLUMNS}
        if not safe:
            return False
        safe["updated_at"] = datetime.now(timezone.utc).isoformat()

        with self._conn() as conn:
            sets = ", ".join(f"{k} = ?" for k in safe)
            vals = list(safe.values()) + [task_id]
            cursor = conn.execute(f"UPDATE tasks SET {sets} WHERE id = ?", vals)
            return cursor.rowcount > 0

    def get_task(self, task_id: str) -> dict:
        """Get a single task."""
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            return dict(row) if row else None

    def get_tasks(self, status: str = None, project: str = None, skill: str = None,
                  assignee: str = None, parent: str = None, unassigned: bool = False,
                  tenant_id: str = None) -> list:
        """Query tasks with filters."""
        query = "SELECT * FROM tasks WHERE 1=1"
        params = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if project:
            query += " AND project = ?"
            params.append(project)
        if skill:
            query += " AND skill = ?"
            params.append(skill)
        if assignee:
            query += " AND assignee = ?"
            params.append(assignee)
        if parent:
            query += " AND parent = ?"
            params.append(parent)
        if tenant_id:
            query += " AND tenant_id = ?"
            params.append(tenant_id)
        if unassigned:
            query += " AND (assignee IS NULL OR assignee = '') AND status = 'todo'"
        query += " ORDER BY CASE priority WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END"

        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def get_task_counts(self) -> dict:
        """Get counts by status."""
        with self._conn() as conn:
            rows = conn.execute("SELECT status, COUNT(*) as cnt FROM tasks GROUP BY status").fetchall()
            return {r["status"]: r["cnt"] for r in rows}

    # ─── AUDIT (transactional) ───────────────────────────────────────────────

    def _log(self, conn, actor: str, action: str, task_id: str = "",
             entity_type: str = "", details: str = ""):
        """Internal: log within existing transaction (fixed: was separate connection)."""
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("""
            INSERT INTO audit (timestamp, actor, action, task_id, entity_type, details)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (now, actor, action, task_id, entity_type, details[:500]))

    def log_event(self, actor: str, action: str, task_id: str = "",
                  entity_type: str = "", details: str = "", conn=None):
        """Log event. If conn provided, uses existing transaction (preferred)."""
        if conn:
            self._log(conn, actor, action, task_id, entity_type, details)
        else:
            with self._conn() as c:
                self._log(c, actor, action, task_id, entity_type, details)

    def get_audit(self, limit: int = 50, actor: str = None, task_id: str = None,
                  action: str = None) -> list:
        """Query audit log."""
        query = "SELECT * FROM audit WHERE 1=1"
        params = []
        if actor:
            query += " AND actor = ?"
            params.append(actor)
        if task_id:
            query += " AND task_id = ?"
            params.append(task_id)
        if action:
            query += " AND action = ?"
            params.append(action)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    # ─── BUDGET ──────────────────────────────────────────────────────────────

    def _add_budget(self, conn, tokens: int, task_id: str = "", model: str = ""):
        """Add tokens to current month budget (within existing transaction)."""
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        conn.execute("""
            INSERT INTO budget (month, tokens_used) VALUES (?, ?)
            ON CONFLICT(month) DO UPDATE SET
                tokens_used = tokens_used + ?,
                updated_at = ?
        """, (month, tokens, tokens, datetime.now(timezone.utc).isoformat()))

    def update_budget(self, tokens: int, model: str = ""):
        """Public budget update (new connection)."""
        with self._conn() as conn:
            self._add_budget(conn, tokens, model=model)

    def get_budget(self, month: str = None) -> dict:
        """Get budget for a month."""
        if not month:
            month = datetime.now(timezone.utc).strftime("%Y-%m")
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM budget WHERE month = ?", (month,)).fetchone()
            if row:
                d = dict(row)
                d["percentage"] = round(d["tokens_used"] / max(d["token_limit"], 1) * 100, 2)
                return d
            return {"month": month, "tokens_used": 0, "token_limit": 50000000, "percentage": 0.0}

    # ─── SCORES ──────────────────────────────────────────────────────────────

    def record_score(self, task_id: str, skill: str, score: int,
                     project: str = "", dimensions: dict = None, model: str = ""):
        """Record a quality score with model tracking."""
        now = datetime.now(timezone.utc).isoformat()
        dims_json = json.dumps(dimensions or {})
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO scores (task_id, skill, score, project, dimensions, model, scored_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (task_id, skill, score, project, dims_json, model, now))

    def get_scores(self, skill: str = None, task_id: str = None,
                   model: str = None, limit: int = 100) -> list:
        """Query scores with filters."""
        query = "SELECT * FROM scores WHERE 1=1"
        params = []
        if skill:
            query += " AND skill = ?"
            params.append(skill)
        if task_id:
            query += " AND task_id = ?"
            params.append(task_id)
        if model:
            query += " AND model = ?"
            params.append(model)
        query += " ORDER BY scored_at DESC LIMIT ?"
        params.append(limit)
        with self._conn() as conn:
            return [dict(r) for r in conn.execute(query, params).fetchall()]

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
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO chain_runs (run_id, chain_name, project, context,
                    status, current_step, total_steps, started_at)
                VALUES (?, ?, ?, ?, 'running', 0, ?, ?)
            """, (run_id, chain_name, project, context, total_steps, now))
        return {"run_id": run_id, "status": "running"}

    def complete_chain_run(self, run_id: str, status: str = "completed") -> bool:
        """Mark chain run as completed/failed (new: was missing)."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            cursor = conn.execute("""
                UPDATE chain_runs SET status = ?, completed_at = ?, updated_at = ?
                WHERE run_id = ? AND status = 'running'
            """, (status, now, now, run_id))
            return cursor.rowcount > 0

    def save_chain_checkpoint(self, run_id: str, step: int, skill: str,
                              artifact_json: str, score: int = 0, status: str = "success"):
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO chain_checkpoints (run_id, step_num, skill, artifact, score, status, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (run_id, step, skill, artifact_json, score, status, now))
            conn.execute("UPDATE chain_runs SET current_step = ?, updated_at = ? WHERE run_id = ?",
                        (step, now, run_id))

    # ─── MIGRATION ───────────────────────────────────────────────────────────

    def migrate_from_yaml(self) -> int:
        """Import existing YAML tasks into SQLite."""
        if not TASKS_DIR.exists():
            return 0
        try:
            import yaml
            def _load(p):
                with open(p, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f)
        except ImportError:
            return 0

        imported = 0
        for f in TASKS_DIR.glob("*.yaml"):
            try:
                data = _load(str(f))
                if not data or not data.get("id"):
                    continue
                if self.get_task(data["id"]):
                    continue
                self.create_task(data)
                imported += 1
            except Exception as e:
                log.warning(f"Failed to import {f.name}: {e}")
        return imported

    # ─── STATS ───────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        with self._conn() as conn:
            task_count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            audit_count = conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0]
            score_count = conn.execute("SELECT COUNT(*) FROM scores").fetchone()[0]
            chain_count = conn.execute("SELECT COUNT(*) FROM chain_runs").fetchone()[0]
        return {
            "tasks": task_count, "audit_entries": audit_count,
            "scores": score_count, "chain_runs": chain_count,
            "db_path": self.db_path,
            "db_size_kb": round(Path(self.db_path).stat().st_size / 1024, 1) if Path(self.db_path).exists() else 0,
        }


# =============================================================================
# SCHEMA
# =============================================================================

BASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_versions (
    version INTEGER PRIMARY KEY,
    description TEXT,
    applied_at TEXT DEFAULT (datetime('now'))
);

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
    completed_at TEXT,
    tenant_id TEXT DEFAULT 'default',
    executor_type TEXT DEFAULT 'agente',
    inputs TEXT DEFAULT '[]',
    outputs TEXT DEFAULT '[]',
    checklist TEXT DEFAULT '{}',
    performance TEXT DEFAULT '{}',
    error_handling TEXT DEFAULT '{}',
    cache_key TEXT,
    cached_result TEXT
);

CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    task_id TEXT DEFAULT '',
    entity_type TEXT DEFAULT '',
    details TEXT DEFAULT '',
    tenant_id TEXT DEFAULT 'default'
);

CREATE TABLE IF NOT EXISTS budget (
    month TEXT PRIMARY KEY,
    tokens_used INTEGER DEFAULT 0,
    token_limit INTEGER DEFAULT 50000000,
    updated_at TEXT,
    tenant_id TEXT DEFAULT 'default'
);

CREATE TABLE IF NOT EXISTS scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT,
    skill TEXT,
    score INTEGER,
    project TEXT DEFAULT '',
    dimensions TEXT DEFAULT '{}',
    model TEXT DEFAULT '',
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
CREATE INDEX IF NOT EXISTS idx_tasks_skill ON tasks(skill);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_task ON audit(task_id);
CREATE INDEX IF NOT EXISTS idx_scores_skill ON scores(skill);
CREATE INDEX IF NOT EXISTS idx_scores_task ON scores(task_id);
"""


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="DARIO SQLite DB v2 — Production-grade persistence")
    parser.add_argument("--init", action="store_true", help="Initialize database")
    parser.add_argument("--tasks", action="store_true", help="List tasks")
    parser.add_argument("--status", help="Filter by status")
    parser.add_argument("--audit", action="store_true", help="Show audit log")
    parser.add_argument("--tail", type=int, default=20, help="Limit entries")
    parser.add_argument("--budget", action="store_true", help="Show budget")
    parser.add_argument("--scores", action="store_true", help="Show scores")
    parser.add_argument("--migrate-yaml", action="store_true", help="Import YAML tasks")
    parser.add_argument("--stats", action="store_true", help="DB statistics")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")
    args = parser.parse_args()

    db = DB()

    if args.init:
        stats = db.stats()
        print(f"DB ready at {DB_PATH} | {stats['tasks']} tasks, {stats['audit_entries']} audit")
    elif args.migrate_yaml:
        n = db.migrate_from_yaml()
        print(json.dumps({"imported": n}) if args.json else f"Imported {n} tasks")
    elif args.tasks:
        tasks = db.get_tasks(status=args.status)
        if args.json:
            print(json.dumps(tasks, indent=2, default=str))
        else:
            for t in tasks:
                m = {"done": "+", "in_progress": "~", "todo": " ", "blocked": "!"}.get(t["status"], "?")
                print(f"  [{m}] {t['id']:12s} {t['status']:15s} {(t.get('assignee') or '-'):20s} {t['title'][:50]}")
    elif args.audit:
        for e in db.get_audit(limit=args.tail):
            ts = e["timestamp"][11:19] if e.get("timestamp") else "?"
            print(f"  [{ts}] {e['actor']}: {e['action']} {e.get('task_id','')} — {e.get('details','')[:60]}")
    elif args.budget:
        b = db.get_budget()
        print(json.dumps(b, indent=2) if args.json else f"  {b['month']}: {b['tokens_used']:,}/{b['token_limit']:,} ({b['percentage']:.2f}%)")
    elif args.scores:
        stats = db.get_skill_stats()
        if args.json:
            print(json.dumps(stats, indent=2))
        else:
            for s in stats:
                print(f"  {s['skill']:30s} avg={s['avg_score']:5.1f} n={s['executions']}")
    elif args.stats:
        s = db.stats()
        print(json.dumps(s, indent=2) if args.json else f"  Tasks={s['tasks']} Audit={s['audit_entries']} Scores={s['scores']} Chains={s['chain_runs']} Size={s['db_size_kb']}KB")
    else:
        parser.print_help()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
